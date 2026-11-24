"""Owner-scoped cloud reads. This module never executes training or inference."""
import hmac
import os
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.orm import Session

from .db import get_session

router = APIRouter(prefix="/v1/registry", tags=["cloud registry"])


def operator(x_cloud_key: str = Header(default=""), x_operator_id: UUID | None = Header(default=None)):
    secret = os.environ.get("CLOUD_INTERNAL_KEY", "")
    if len(secret) < 32:
        raise HTTPException(503, "Cloud registry is not configured")
    if not hmac.compare_digest(secret.encode(), x_cloud_key.encode()) or x_operator_id is None:
        raise HTTPException(401, "Trusted gateway context required")
    return x_operator_id


# Explicit projections exclude lease hashes, raw storage paths and credentials.
RUNS = """SELECT id,kind,family,condition,execution_location,manifest_id,manifest_sha256,
    target_participant_id,calibration_subset_id,parent_model_id,evaluated_model_id,feature_contract,
    parameters,seed,software_version,status,created_at,started_at,heartbeat_at,lease_expires_at,completed_at,error
    FROM ml_experiments.experiment_runs WHERE operator_id=:operator"""
MODELS = "SELECT * FROM ml_experiments.published_models WHERE operator_id=:operator"
RESULTS = """SELECT e.* FROM ml_experiments.reviewer_results e JOIN ml_experiments.experiment_runs r ON r.id=e.run_id
    WHERE r.operator_id=:operator"""
QUERIES = {"runs": (RUNS, "created_at DESC,id DESC", "id"),
           "models": (MODELS, "published_at DESC,id DESC", "id"),
           "results": (RESULTS, "e.id DESC", "e.id")}


@router.get("/{collection}")
def listing(collection: str, limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0),
            actor: UUID = Depends(operator), session: Session = Depends(get_session)):
    if collection not in QUERIES:
        raise HTTPException(404, "Collection not found")
    sql, order, _ = QUERIES[collection]
    rows = list(session.execute(text(f"{sql} ORDER BY {order} LIMIT :limit OFFSET :offset"),
                {"operator": actor, "limit": limit + 1, "offset": offset}).mappings())
    return {"items": [dict(row) for row in rows[:limit]],
            "next_offset": offset + limit if len(rows) > limit else None}


@router.get("/{collection}/{item_id}")
def detail(collection: str, item_id: UUID, actor: UUID = Depends(operator), session: Session = Depends(get_session)):
    if collection not in QUERIES:
        raise HTTPException(404, "Collection not found")
    sql, _, key = QUERIES[collection]
    row = session.execute(text(f"{sql} AND {key}=:id"), {"operator": actor, "id": item_id}).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "Registry item not found")
    result = dict(row)
    if collection == "results":
        result["confusion_counts"] = [dict(item) for item in session.execute(text("""SELECT actual_class,predicted_class,count
            FROM ml_experiments.confusion_counts WHERE evaluation_id=:id ORDER BY actual_class,predicted_class"""),
            {"id": item_id}).mappings()]
    return result
