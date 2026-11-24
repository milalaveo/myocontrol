from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["live", "ready"]


class FeatureConfig(BaseModel):
    version: str
    channels: int
    order: str
    features: list[str]
    window_ms: int
    step_ms: int
    zc_threshold: float
    ssc_threshold: float
    filter: str
    sample_rate_hz: float
    fit_roles: list[str]


class LdaModel(BaseModel):
    family: Literal["lda"]
    solver: str
    shrinkage: str
    classes: list[str]
    coefficients: list[list[float]]
    intercepts: list[float]
    feature_config: FeatureConfig
    sklearn_version: str


class ExperimentMetrics(BaseModel):
    accuracy: float
    macro_f1: float
    rest_false_activation_rate: float | None
    rest_false_activation_missing_reason: str | None
    class_order: list[str]
    confusion_matrix: list[list[int]]
    training_windows: int
    test_windows: int


class SignalSummary(BaseModel):
    kind: Literal["synthetic_signal_summary"]
    sample_count: int
    channel_means: list[float]


class RegistryRun(BaseModel):
    id: UUID
    kind: Literal["source_train", "personalise", "target_train", "evaluate"]
    family: Literal["lda", "svm", "mlp"]
    condition: Literal["source_only", "personalised", "target_only"]
    execution_location: Literal["local_workstation", "desktop"]
    manifest_id: UUID
    manifest_sha256: str
    target_participant_id: UUID | None
    calibration_subset_id: UUID | None
    parent_model_id: UUID | None
    evaluated_model_id: UUID | None
    feature_contract: dict[str, Any]
    parameters: dict[str, Any]
    seed: int
    software_version: str
    status: Literal["queued", "running", "succeeded", "failed", "interrupted"]
    created_at: datetime
    started_at: datetime | None
    heartbeat_at: datetime | None
    lease_expires_at: datetime | None
    completed_at: datetime | None
    error: str | None


class PublishedModel(BaseModel):
    id: UUID
    name: str
    run_id: UUID
    operator_id: UUID
    family: Literal["lda", "svm", "mlp"]
    condition: Literal["source_only", "personalised", "target_only"]
    parent_model_id: UUID | None
    calibration_subset_id: UUID | None
    manifest_id: UUID
    manifest_sha256: str
    feature_contract: dict[str, Any]
    adaptation_method: Literal["none", "lda_statistics", "svm_weighted", "mlp_replay"]
    sha256: str
    size_bytes: int
    published_at: datetime


class EvaluationResult(BaseModel):
    id: UUID
    model_id: UUID
    run_id: UUID
    family: Literal["lda", "svm", "mlp"]
    condition: Literal["source_only", "personalised", "target_only"]
    manifest_id: UUID
    manifest_sha256: str
    target_participant_id: UUID
    calibration_subset_id: UUID | None
    feature_contract: dict[str, Any]
    seed: int
    software_version: str
    accuracy: float
    macro_f1: float
    rest_false_activation_rate: float | None
    rest_missing_reason: str | None


class ConfusionCount(BaseModel):
    actual_class: str
    predicted_class: str
    count: int


class EvaluationDetail(EvaluationResult):
    confusion_counts: list[ConfusionCount]


class RunPage(BaseModel):
    items: list[RegistryRun]
    next_offset: int | None


class ModelPage(BaseModel):
    items: list[PublishedModel]
    next_offset: int | None


class ResultPage(BaseModel):
    items: list[EvaluationResult]
    next_offset: int | None
