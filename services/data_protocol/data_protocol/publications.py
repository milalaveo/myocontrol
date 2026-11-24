import hashlib
import hmac
import json
import os
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, model_validator
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import get_session
from .storage import read_signal, save_signal

router = APIRouter(prefix="/v1/client-recordings", tags=["desktop publications"])
key = APIKeyHeader(name="X-Cloud-Key", scheme_name="GatewayKey", auto_error=False)


def actor(
    x_cloud_key: str | None = Depends(key),
    x_operator_id: UUID | None = Header(default=None),
    x_client_id: UUID | None = Header(default=None),
):
    secret = os.environ.get("CLOUD_INTERNAL_KEY", "")
    if len(secret) < 32:
        raise HTTPException(503, "Desktop publication is not configured")
    if (
        not hmac.compare_digest(secret.encode(), (x_cloud_key or "").encode())
        or x_operator_id is None
    ):
        raise HTTPException(401, "Trusted desktop gateway context required")
    return {"operator": x_operator_id, "client": x_client_id}


class ClientRecordingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    local_recording_id: UUID
    participant_key: str = Field(min_length=1, max_length=100)
    sample_rate_hz: FiniteFloat = Field(ge=1, le=100000)
    channel_map: list[int] = Field(min_length=1, max_length=6)
    samples: list[list[FiniteFloat]] = Field(min_length=1, max_length=10000)
    source_kind: Literal["synthetic", "dataset", "device"]
    source_name: str = Field(min_length=1, max_length=120)
    source_version: str = Field(min_length=1, max_length=120)
    units: str = Field(min_length=1, max_length=120)
    original_signal_key: str = Field(min_length=1, max_length=120)
    original_sha256: str = Field(pattern="^[0-9a-f]{64}$")
    original_start_sample: int = Field(ge=0)
    purpose: Literal["research", "calibration"] = "research"
    gesture_code: str | None = Field(default=None, pattern="^[A-Za-z0-9_-]{1,100}$")

    @model_validator(mode="after")
    def validate_recording(self):
        if len(set(self.channel_map)) != len(self.channel_map) or any(
            c < 0 or c > 11 for c in self.channel_map
        ):
            raise ValueError(
                "Channel mapping must contain unique source channel indices"
            )
        if any(len(row) != len(self.channel_map) for row in self.samples):
            raise ValueError("Sample width must match channel mapping")
        if self.purpose == "calibration" and self.gesture_code is None:
            raise ValueError("Calibration recordings require a gesture label")
        if any(
            not value.strip()
            for value in (
                self.participant_key,
                self.source_name,
                self.source_version,
                self.units,
                self.original_signal_key,
            )
        ):
            raise ValueError("Source identity fields must not be blank")
        return self


class PublicationReceipt(BaseModel):
    id: UUID
    recording_id: UUID
    local_recording_id: UUID
    payload_sha256: str
    received_at: datetime


class OwnedRecording(BaseModel):
    id: UUID
    local_recording_id: UUID
    sample_rate_hz: float
    sample_count: int
    channel_count: int
    artifact_sha256: str
    source_kind: str
    source_name: str
    source_version: str
    source_participant_key: str
    original_signal_key: str
    original_sha256: str
    original_start_sample: int
    original_end_sample: int
    channel_map: list[int]
    units: str
    received_at: datetime


class OwnedRecordingPage(BaseModel):
    items: list[OwnedRecording]
    next_offset: int | None


class OwnedSignal(BaseModel):
    sample_rate_hz: float
    channel_map: list[int]
    units: str
    source_kind: str
    source_name: str
    source_version: str
    samples: list[list[float]]


RECEIPT = "SELECT id,recording_id,local_recording_id,payload_sha256,received_at FROM data_protocol.client_publications WHERE operator_id=:operator AND local_recording_id=:local"
OWNED = """SELECT r.id,c.local_recording_id,r.sample_rate_hz,r.sample_count,r.channel_count,r.artifact_sha256,
    p.source_kind,p.source_name,p.source_version,p.source_participant_key,p.original_signal_key,p.original_sha256,
    p.original_start_sample,p.original_end_sample,p.channel_map,p.units,c.received_at
    FROM data_protocol.client_publications c JOIN data_protocol.recordings r ON r.id=c.recording_id
    JOIN data_protocol.recording_provenance p ON p.recording_id=r.id WHERE c.operator_id=:operator"""


@router.post("", status_code=201, response_model=PublicationReceipt)
def publish(
    body: ClientRecordingCreate,
    owner=Depends(actor),
    session: Session = Depends(get_session),
):
    if owner["client"] is None:
        raise HTTPException(403, "Desktop client context required for publication")
    payload = json.dumps(
        body.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    digest = hashlib.sha256(payload.encode()).hexdigest()
    values = {**owner, "local": body.local_recording_id}
    session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
        {"key": str(owner["operator"]) + ":" + str(body.local_recording_id)},
    )
    existing = session.execute(text(RECEIPT), values).mappings().one_or_none()
    if existing:
        if existing["payload_sha256"] != digest:
            raise HTTPException(
                409, "Local recording identity conflicts with a previous publication"
            )
        return dict(existing)
    participant_name = (
        "desktop_"
        + hashlib.sha256(
            (str(owner["operator"]) + ":" + body.participant_key).encode()
        ).hexdigest()
    )
    participant = session.execute(
        text(
            "INSERT INTO data_protocol.participants(id,pseudonym) VALUES (:id,:name) ON CONFLICT(pseudonym) DO NOTHING RETURNING id"
        ),
        {"id": uuid4(), "name": participant_name},
    ).scalar_one_or_none()
    if participant is None:
        participant = session.execute(
            text("SELECT id FROM data_protocol.participants WHERE pseudonym=:name"),
            {"name": participant_name},
        ).scalar_one()
    artifact = json.dumps(
        {
            "format": "desktop-signal-v1",
            "sample_rate_hz": body.sample_rate_hz,
            "samples": body.samples,
        },
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    checksum = save_signal(artifact)
    recording = uuid4()
    session.execute(
        text(
            """INSERT INTO data_protocol.recordings(id,participant_id,sample_rate_hz,sample_count,artifact_sha256,channel_count)
        VALUES (:id,:participant,:rate,:count,:sha,:channels)"""
        ),
        {
            "id": recording,
            "participant": participant,
            "rate": body.sample_rate_hz,
            "count": len(body.samples),
            "sha": checksum,
            "channels": len(body.channel_map),
        },
    )
    session.execute(
        text(
            """INSERT INTO data_protocol.recording_provenance(recording_id,operator_id,source_kind,source_name,source_version,
        source_participant_key,original_signal_key,original_sha256,original_start_sample,original_end_sample,channel_map,units,identity_method_version)
        VALUES (:recording,:operator,:kind,:name,:version,:participant,:signal,:sha,:start,:end,CAST(:map AS jsonb),:units,'local-samples-v1')"""
        ),
        {
            "recording": recording,
            "operator": owner["operator"],
            "kind": body.source_kind,
            "name": body.source_name,
            "version": body.source_version,
            "participant": body.participant_key,
            "signal": body.original_signal_key,
            "sha": body.original_sha256,
            "start": body.original_start_sample,
            "end": body.original_start_sample + len(body.samples),
            "map": json.dumps(body.channel_map),
            "units": body.units,
        },
    )
    if body.gesture_code:
        session.execute(
            text(
                """INSERT INTO data_protocol.labelled_segments(id,recording_id,gesture_code,repetition_key,start_sample,end_sample)
            VALUES (:id,:recording,:gesture,:repetition,0,:end)"""
            ),
            {
                "id": uuid4(),
                "recording": recording,
                "gesture": body.gesture_code,
                "repetition": body.original_signal_key,
                "end": len(body.samples),
            },
        )
    session.execute(
        text(
            """INSERT INTO data_protocol.client_publications(operator_id,client_id,local_recording_id,recording_id,payload_sha256)
        VALUES (:operator,:client,:local,:recording,:sha)"""
        ),
        {**values, "recording": recording, "sha": digest},
    )
    receipt = dict(session.execute(text(RECEIPT), values).mappings().one())
    session.commit()
    return receipt


@router.get("", response_model=OwnedRecordingPage)
def listing(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    owner=Depends(actor),
    session: Session = Depends(get_session),
):
    rows = list(
        session.execute(
            text(
                OWNED
                + " ORDER BY c.received_at DESC,r.id DESC LIMIT :limit OFFSET :offset"
            ),
            {**owner, "limit": limit + 1, "offset": offset},
        ).mappings()
    )
    return {
        "items": [dict(row) for row in rows[:limit]],
        "next_offset": offset + limit if len(rows) > limit else None,
    }


@router.get("/{recording_id}/signal", response_model=OwnedSignal)
def signal(
    recording_id: UUID, owner=Depends(actor), session: Session = Depends(get_session)
):
    row = (
        session.execute(text(OWNED + " AND r.id=:id"), {**owner, "id": recording_id})
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise HTTPException(404, "Recording not found")
    try:
        payload = json.loads(read_signal(row["artifact_sha256"]))
    except (OSError, ValueError):
        raise HTTPException(503, "Signal artifact missing or invalid") from None
    return {
        "sample_rate_hz": row["sample_rate_hz"],
        "samples": payload["samples"],
        **{
            key: row[key]
            for key in (
                "channel_map",
                "units",
                "source_kind",
                "source_name",
                "source_version",
            )
        },
    }
