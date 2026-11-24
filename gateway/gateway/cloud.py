"""Authenticated cloud read API; identity context is supplied only by this gateway."""
import os
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from .identity import principal

router = APIRouter(prefix="/cloud/v1", tags=["cloud registry"])


@router.get("/{collection}")
@router.get("/{collection}/{item_id}")
async def registry(collection: str, request: Request, item_id: UUID | None = None, actor=Depends(principal)):
    if collection not in {"runs", "models", "results"}:
        raise HTTPException(404, "Collection not found")
    secret = os.environ.get("CLOUD_INTERNAL_KEY", "")
    address = os.environ.get("ML_SERVICE_URL", "")
    if len(secret) < 32 or not address:
        raise HTTPException(503, "Cloud registry is not configured")
    path = f"/v1/registry/{collection}" + (f"/{item_id}" if item_id else "")
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(15, connect=2), follow_redirects=False) as client:
            result = await client.get(address.rstrip("/") + path, params=request.query_params, headers={
                "X-Cloud-Key": secret, "X-Operator-ID": str(actor["operator_id"]),
                "X-Correlation-ID": request.state.correlation_id})
    except httpx.TimeoutException:
        raise HTTPException(504, "Registry request timed out") from None
    except httpx.HTTPError:
        raise HTTPException(502, "Registry unavailable") from None
    return Response(result.content, status_code=result.status_code, media_type="application/json",
                    headers={"Cache-Control": "no-store"})
