from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["live", "ready"]


class ProtocolResponse(BaseModel):
    id: UUID
    name: str
    version: int
    gesture_codes: list[str]


class SegmentResponse(BaseModel):
    id: UUID
    recording_id: UUID
    gesture_code: str
    repetition_key: str
    start_sample: int
    end_sample: int


class ManifestResponse(BaseModel):
    id: UUID
    name: str
    version: int
    protocol_id: UUID
    state: Literal["draft", "frozen"]
    checksum: str | None


class ParticipantAssignmentResponse(BaseModel):
    manifest_id: UUID
    participant_id: UUID
    category: Literal["source", "development", "target"]


class UnitResponse(ParticipantAssignmentResponse):
    id: UUID
    segment_id: UUID
    role: Literal["source_train", "development_validation", "target_calibration", "target_test"]


class SnapshotUnit(BaseModel):
    id: UUID
    participant_id: UUID
    category: Literal["source", "development", "target"]
    role: Literal["source_train", "development_validation", "target_calibration", "target_test"]
    segment_id: UUID
    recording_id: UUID
    gesture_code: str
    repetition_key: str
    start_sample: int
    end_sample: int
    sample_rate_hz: float
    sample_count: int
    artifact_sha256: str


class SnapshotResponse(ManifestResponse):
    protocol_name: str
    protocol_version: int
    gesture_codes: list[str]
    units: list[SnapshotUnit]


class CalibrationResponse(BaseModel):
    id: UUID
    manifest_id: UUID
    participant_id: UUID
    selection_version: str
    budget_per_gesture: int
    state: Literal["draft", "frozen"]


class CalibrationItemResponse(BaseModel):
    subset_id: UUID
    unit_id: UUID


class CalibrationDuration(BaseModel):
    gesture_code: str
    unique_seconds: float


class CalibrationDetailResponse(CalibrationResponse):
    unit_ids: list[UUID]
    durations: list[CalibrationDuration]
