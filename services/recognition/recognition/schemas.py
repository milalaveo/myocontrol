from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["live", "ready"]


class Prediction(BaseModel):
    start_sample: int
    gesture: str
    command: str


class ReplayResult(BaseModel):
    feature_version: str
    predictions: list[Prediction]
    prediction_count: int
    processing_p95_ms: float
    timing_scope: str


class ReplayFailure(BaseModel):
    command: Literal["neutral"]
    reason: str


class AvailableModel(BaseModel):
    model_run_id: UUID
    manifest_id: UUID
    received_at: datetime
