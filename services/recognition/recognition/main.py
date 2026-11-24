from pathlib import Path
import logging
import json
import re
import time
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from prometheus_client import Counter, Histogram, make_asgi_app
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .clients import DependencyError, load_inputs
from .db import get_session
from .inference import replay
from .models import ReplaySession
from .schemas import HealthResponse, ReplayResult, ReplayFailure, AvailableModel

logging.basicConfig(level=logging.INFO, format="%(message)s")
app = FastAPI(title="Recognition API", version="0.1.0")
app.mount("/metrics", make_asgi_app())
REQUESTS = Counter("recognition_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("recognition_request_seconds", "HTTP request duration", ["method", "route"])
REPLAYS = Counter("recognition_replays_total", "Completed replay sessions", ["status"])
REPLAY_P95 = Histogram(
    "recognition_replay_processing_p95_seconds",
    "Replay session p95 feature and prediction processing time",
)
logger = logging.getLogger("recognition")
logger.setLevel(logging.INFO)


class ReplayCreate(BaseModel):
    model_run_id: uuid.UUID
    recording_id: uuid.UUID


class ReplayResponse(ReplayCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: str
    model_checksum: str | None
    result: ReplayResult | ReplayFailure | None
    error: str | None


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
        response = JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "correlation_id": correlation},
        )
    response.headers["X-Correlation-ID"] = correlation
    route = getattr(request.scope.get("route"), "path", "unmatched")
    elapsed = time.perf_counter() - started
    REQUESTS.labels(request.method, route, str(response.status_code)).inc()
    LATENCY.labels(request.method, route).observe(elapsed)
    logger.info(
        json.dumps(
            {
                "event": "http_request",
                "service": "recognition",
                "correlation_id": correlation,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round(elapsed * 1000, 3),
            }
        )
    )
    return response


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, exc: SQLAlchemyError):
    logger.error(
        "database_error correlation_id=%s type=%s", request.state.correlation_id, type(exc).__name__
    )
    return JSONResponse(
        status_code=503,
        content={
            "detail": "Database operation failed",
            "correlation_id": request.state.correlation_id,
        },
    )


@app.get("/health/live", response_model=HealthResponse)
def live():
    return {"status": "live"}


@app.get("/health/ready", response_model=HealthResponse)
def ready(session: Session = Depends(get_session)):
    session.execute(text("SELECT 1 FROM recognition.replay_sessions LIMIT 1"))
    return {"status": "ready"}


@app.post("/v1/replay-sessions", response_model=ReplayResponse, status_code=201)
def create_replay(body: ReplayCreate, request: Request, session: Session = Depends(get_session)):
    replay_session = ReplaySession(
        model_run_id=body.model_run_id, recording_id=body.recording_id, status="running"
    )
    session.add(replay_session)
    session.commit()
    try:
        model, checksum, signal = load_inputs(
            body.model_run_id, body.recording_id, request.state.correlation_id
        )
        replay_session.result = replay(model, signal)
        replay_session.model_checksum = checksum
        replay_session.status = "succeeded"
    except (DependencyError, ValueError, KeyError, TypeError) as error:
        replay_session.status = "failed"
        replay_session.error = str(error)[:200]
        replay_session.result = {"command": "neutral", "reason": "replay failed"}
    session.commit()
    REPLAYS.labels(replay_session.status).inc()
    if replay_session.status == "succeeded":
        REPLAY_P95.observe(replay_session.result["processing_p95_ms"] / 1000)
    return replay_session


@app.get("/v1/replay-sessions/{session_id}", response_model=ReplayResponse)
def get_replay(session_id: uuid.UUID, session: Session = Depends(get_session)):
    replay_session = session.get(ReplaySession, session_id)
    if replay_session is None:
        raise HTTPException(status_code=404, detail="Replay session not found")
    return replay_session


@app.get("/v1/available-models/{model_run_id}", response_model=AvailableModel)
def available_model(model_run_id: uuid.UUID, session: Session = Depends(get_session)):
    row = (
        session.execute(
            text("""SELECT model_run_id, manifest_id, received_at FROM recognition.model_events
        WHERE model_run_id = :id ORDER BY received_at DESC LIMIT 1"""),
            {"id": model_run_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Model event not received")
    return dict(row)


def published_openapi():
    if app.openapi_schema is None:
        app.openapi_schema = json.loads(
            Path(__file__).with_name("openapi.json").read_text(encoding="utf-8")
        )
    return app.openapi_schema


app.openapi = published_openapi
