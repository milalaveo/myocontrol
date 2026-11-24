from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["live", "ready"]


class OperatorSummary(BaseModel):
    id: UUID
    display_name: str
    role: Literal["operator", "reviewer", "administrator"]


class SessionResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
    expires_at: datetime
    operator: OperatorSummary


class CurrentOperatorResponse(BaseModel):
    operator_id: UUID
    display_name: str
    role: Literal["operator", "reviewer", "administrator"]
    scope: Literal["web", "desktop", "training_worker"]
    client_id: UUID | None
    expires_at: datetime


class ClientTokenResponse(BaseModel):
    client_id: UUID
    access_token: str
    token_type: Literal["bearer"]
    expires_at: datetime
    scope: Literal["desktop", "training_worker"]


class ClientResponse(BaseModel):
    id: UUID
    kind: Literal["desktop", "training_worker"]
    name: str
    platform: str
    state: Literal["active", "revoked"]
    created_at: datetime
