"""HTTP interface for the data and protocol service."""

import logging
import json
import re
import time
import uuid
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, field_validator
from prometheus_client import Counter, Histogram, make_asgi_app
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .db import get_session
from .repository import ParticipantRepository, RecordingRepository, ResearchRepository
from .models import SyntheticSplit
from .storage import read_signal, save_signal

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("data_protocol")
logger.setLevel(logging.INFO)
app = FastAPI(title="Data and Protocol API", version="0.1.0")
app.mount("/metrics", make_asgi_app())
REQUESTS = Counter("data_protocol_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("data_protocol_request_seconds", "HTTP request duration", ["method", "route"])


class ParticipantCreate(BaseModel):
    pseudonym: str = Field(min_length=1, max_length=100)

    @field_validator("pseudonym")
    @classmethod
    def validate_pseudonym(cls, value):
        value = value.strip()
        if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
            raise ValueError("Use only letters, digits, hyphens and underscores")
        return value


class ParticipantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    pseudonym: str


class RecordingCreate(BaseModel):
    participant_id: uuid.UUID
    sample_rate_hz: FiniteFloat = Field(gt=0, le=100000)
    samples: list[tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]] = Field(min_length=1, max_length=10000)


class RecordingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    participant_id: uuid.UUID
    sample_rate_hz: float
    sample_count: int
    artifact_sha256: str


class SyntheticSplitCreate(BaseModel):
    source_recording_id: uuid.UUID
    test_recording_id: uuid.UUID


class SyntheticSplitResponse(SyntheticSplitCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    checksum: str


class ProtocolCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    version: int = Field(gt=0)
    gesture_codes: list[str] = Field(min_length=1, max_length=50)

    @field_validator("gesture_codes")
    @classmethod
    def valid_gestures(cls, value):
        if "rest" not in value or len(set(value)) != len(value) or any(not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", code) for code in value):
            raise ValueError("Gesture codes must be unique identifiers and include rest")
        return value


class SegmentCreate(BaseModel):
    recording_id: uuid.UUID
    gesture_code: str = Field(pattern=r"^[A-Za-z0-9_-]{1,100}$")
    repetition_key: str = Field(min_length=1, max_length=100)
    start_sample: int = Field(ge=0)
    end_sample: int = Field(gt=0)


class ManifestCreate(BaseModel):
    protocol_id: uuid.UUID
    name: str = Field(min_length=1, max_length=120)
    version: int = Field(gt=0)


class ParticipantAssignment(BaseModel):
    participant_id: uuid.UUID
    category: Literal["source", "development", "target"]


class UnitCreate(ParticipantAssignment):
    segment_id: uuid.UUID
    role: Literal["source_train", "development_validation", "target_calibration", "target_test"]


class CalibrationCreate(BaseModel):
    manifest_id: uuid.UUID
    participant_id: uuid.UUID
    selection_version: str = Field(min_length=1, max_length=100)
    budget_per_gesture: int = Field(gt=0, le=1000)


class CalibrationItemCreate(BaseModel):
    unit_id: uuid.UUID


def commit_research_operation(session, operation):
    try:
        result = dict(operation())
        session.commit()
        return result
    except DBAPIError as error:
        session.rollback()
        code = getattr(error.orig, "sqlstate", None)
        if code == "23503":
            raise HTTPException(status_code=404, detail="Referenced record not found") from error
        if code in {"23505", "23514", "P0001"}:
            raise HTTPException(status_code=409, detail="Operation conflicts with split constraints") from error
        raise


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    candidate = request.headers.get("x-correlation-id", "")
    correlation = candidate if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", candidate) else uuid.uuid4().hex
    request.state.correlation_id = correlation
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("unhandled_error correlation_id=%s", correlation)
        response = JSONResponse(status_code=500, content={"detail": "Internal server error", "correlation_id": correlation})
    response.headers["X-Correlation-ID"] = correlation
    route = getattr(request.scope.get("route"), "path", "unmatched")
    elapsed = time.perf_counter() - started
    REQUESTS.labels(request.method, route, str(response.status_code)).inc()
    LATENCY.labels(request.method, route).observe(elapsed)
    logger.info(json.dumps({"event": "http_request", "service": "data_protocol", "correlation_id": correlation,
                            "method": request.method, "path": request.url.path, "status": response.status_code,
                            "duration_ms": round(elapsed * 1000, 3)}))
    return response


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    logger.error("database_error correlation_id=%s type=%s", request.state.correlation_id, type(exc).__name__)
    return JSONResponse(status_code=503, content={"detail": "Database operation failed", "correlation_id": request.state.correlation_id})


@app.get("/health/live", tags=["health"])
def live():
    return {"status": "live"}


@app.get("/health/ready", tags=["health"])
def ready(session: Session = Depends(get_session)):
    session.execute(text("SELECT 1 FROM data_protocol.participants LIMIT 1"))
    return {"status": "ready"}


@app.post("/v1/participants", response_model=ParticipantResponse, status_code=201, tags=["participants"])
def create_participant(body: ParticipantCreate, session: Session = Depends(get_session)):
    try:
        participant = ParticipantRepository(session).create(body.pseudonym)
        session.commit()
        return participant
    except IntegrityError as error:
        session.rollback()
        if getattr(error.orig, "sqlstate", None) == "23505":
            raise HTTPException(status_code=409, detail="Pseudonym already exists") from error
        raise


@app.get("/v1/participants", response_model=list[ParticipantResponse], tags=["participants"])
def list_participants(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: Session = Depends(get_session),
):
    return ParticipantRepository(session).list(limit, offset)


@app.get("/v1/participants/{participant_id}", response_model=ParticipantResponse, tags=["participants"])
def get_participant(participant_id: uuid.UUID, session: Session = Depends(get_session)):
    participant = ParticipantRepository(session).get(participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Participant not found")
    return participant


@app.post("/v1/recordings", response_model=RecordingResponse, status_code=201, tags=["recordings"])
def create_recording(body: RecordingCreate, session: Session = Depends(get_session)):
    if ParticipantRepository(session).get(body.participant_id) is None:
        raise HTTPException(status_code=404, detail="Participant not found")
    payload = json.dumps({"format": "four-channel-v1", "sample_rate_hz": body.sample_rate_hz, "samples": body.samples},
                         sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    checksum = save_signal(payload)
    recording = RecordingRepository(session).create(body.participant_id, body.sample_rate_hz, len(body.samples), checksum)
    session.commit()
    return recording


@app.get("/v1/recordings", response_model=list[RecordingResponse], tags=["recordings"])
def list_recordings(
    participant_id: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    session: Session = Depends(get_session),
):
    return RecordingRepository(session).list(participant_id, limit, offset)


@app.get("/v1/recordings/{recording_id}", response_model=RecordingResponse, tags=["recordings"])
def get_recording(recording_id: uuid.UUID, session: Session = Depends(get_session)):
    recording = RecordingRepository(session).get(recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    return recording


@app.get("/v1/recordings/{recording_id}/signal", response_model=RecordingCreate, tags=["recordings"])
def get_recording_signal(recording_id: uuid.UUID, session: Session = Depends(get_session)):
    recording = RecordingRepository(session).get(recording_id)
    if recording is None:
        raise HTTPException(status_code=404, detail="Recording not found")
    try:
        payload = json.loads(read_signal(recording.artifact_sha256))
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=503, detail="Signal artifact missing or invalid") from error
    return {"participant_id": recording.participant_id, "sample_rate_hz": payload["sample_rate_hz"], "samples": payload["samples"]}


@app.post("/v1/synthetic-splits", response_model=SyntheticSplitResponse, status_code=201, tags=["synthetic splits"])
def create_synthetic_split(body: SyntheticSplitCreate, session: Session = Depends(get_session)):
    split = SyntheticSplit(source_recording_id=body.source_recording_id, test_recording_id=body.test_recording_id)
    try:
        session.add(split)
        session.flush()
        session.refresh(split)
        session.commit()
        return split
    except IntegrityError as error:
        session.rollback()
        if getattr(error.orig, "sqlstate", None) == "23503":
            raise HTTPException(status_code=404, detail="Recording not found") from error
        if getattr(error.orig, "sqlstate", None) == "23514":
            raise HTTPException(status_code=409, detail="Source and test recordings overlap") from error
        raise


@app.get("/v1/synthetic-splits/{split_id}", response_model=SyntheticSplitResponse, tags=["synthetic splits"])
def get_synthetic_split(split_id: uuid.UUID, session: Session = Depends(get_session)):
    split = session.get(SyntheticSplit, split_id)
    if split is None:
        raise HTTPException(status_code=404, detail="Split not found")
    return split


@app.post("/v1/protocols", status_code=201, tags=["research protocol"])
def create_protocol(body: ProtocolCreate, session: Session = Depends(get_session)):
    return commit_research_operation(session, lambda: ResearchRepository(session).create_protocol(body.name, body.version, body.gesture_codes))


@app.post("/v1/segments", status_code=201, tags=["research protocol"])
def create_segment(body: SegmentCreate, session: Session = Depends(get_session)):
    return commit_research_operation(session, lambda: ResearchRepository(session).create_segment(**body.model_dump()))


@app.post("/v1/research-manifests", status_code=201, tags=["research protocol"])
def create_research_manifest(body: ManifestCreate, session: Session = Depends(get_session)):
    return commit_research_operation(session, lambda: ResearchRepository(session).create_manifest(**body.model_dump()))


@app.post("/v1/research-manifests/{manifest_id}/participants", status_code=201, tags=["research protocol"])
def add_research_participant(manifest_id: uuid.UUID, body: ParticipantAssignment, session: Session = Depends(get_session)):
    return commit_research_operation(session, lambda: ResearchRepository(session).assign_participant(manifest_id, **body.model_dump()))


@app.post("/v1/research-manifests/{manifest_id}/units", status_code=201, tags=["research protocol"])
def add_research_unit(manifest_id: uuid.UUID, body: UnitCreate, session: Session = Depends(get_session)):
    return commit_research_operation(session, lambda: ResearchRepository(session).add_unit(manifest_id, **body.model_dump()))


@app.post("/v1/research-manifests/{manifest_id}/freeze", tags=["research protocol"])
def freeze_research_manifest(manifest_id: uuid.UUID, session: Session = Depends(get_session)):
    def freeze():
        result = ResearchRepository(session).freeze_manifest(manifest_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Draft manifest not found")
        return result
    return commit_research_operation(session, freeze)


@app.get("/v1/research-manifests/{manifest_id}", tags=["research protocol"])
def get_research_manifest(manifest_id: uuid.UUID, session: Session = Depends(get_session)):
    manifest = ResearchRepository(session).get_manifest(manifest_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="Manifest not found")
    return dict(manifest)


@app.get("/v1/research-manifests/{manifest_id}/snapshot", tags=["research protocol"])
def get_frozen_research_snapshot(manifest_id: uuid.UUID, session: Session = Depends(get_session)):
    snapshot = ResearchRepository(session).frozen_snapshot(manifest_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Frozen manifest not found")
    return snapshot


@app.post("/v1/calibration-subsets", status_code=201, tags=["calibration"])
def create_calibration_subset(body: CalibrationCreate, session: Session = Depends(get_session)):
    return commit_research_operation(session, lambda: ResearchRepository(session).create_calibration(**body.model_dump()))


@app.post("/v1/calibration-subsets/{subset_id}/items", status_code=201, tags=["calibration"])
def add_calibration_item(subset_id: uuid.UUID, body: CalibrationItemCreate, session: Session = Depends(get_session)):
    return commit_research_operation(session, lambda: ResearchRepository(session).add_calibration_item(subset_id, body.unit_id))


@app.post("/v1/calibration-subsets/{subset_id}/freeze", tags=["calibration"])
def freeze_calibration_subset(subset_id: uuid.UUID, session: Session = Depends(get_session)):
    def freeze():
        result = ResearchRepository(session).freeze_calibration(subset_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Draft calibration subset not found")
        return result
    return commit_research_operation(session, freeze)


@app.get("/v1/calibration-subsets/{subset_id}", tags=["calibration"])
def get_calibration_subset(subset_id: uuid.UUID, session: Session = Depends(get_session)):
    subset = ResearchRepository(session).get_calibration(subset_id)
    if subset is None:
        raise HTTPException(status_code=404, detail="Calibration subset not found")
    return subset
