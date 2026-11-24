import os
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response

from .identity import principal

router = APIRouter(prefix="/cloud/v1/recordings", tags=["desktop recordings"])


async def forward(request, actor, suffix="", params=None):
    secret = os.environ.get("CLOUD_INTERNAL_KEY", "")
    address = os.environ.get("DATA_SERVICE_URL", "")
    if len(secret) < 32 or not address:
        raise HTTPException(503, "Desktop publication is not configured")
    if request.method == "POST" and (
        actor["scope"] != "desktop"
        or not actor["client_id"]
        or actor["role"] == "reviewer"
    ):
        raise HTTPException(
            403, "Desktop client session required for recording publication"
        )
    payload = bytearray()
    async for chunk in request.stream():
        payload.extend(chunk)
        if len(payload) > 2_000_000:
            raise HTTPException(413, "Request body is too large")
    headers = {
        "X-Cloud-Key": secret,
        "X-Operator-ID": str(actor["operator_id"]),
        "X-Correlation-ID": request.state.correlation_id,
        "Content-Type": "application/json",
    }
    if actor["client_id"]:
        headers["X-Client-ID"] = str(actor["client_id"])
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(20, connect=2), follow_redirects=False
        ) as client:
            result = await client.request(
                request.method,
                address.rstrip("/") + "/v1/client-recordings" + suffix,
                params=params,
                content=bytes(payload),
                headers=headers,
            )
    except httpx.TimeoutException:
        raise HTTPException(504, "Recording service timed out") from None
    except httpx.HTTPError:
        raise HTTPException(502, "Recording service unavailable") from None
    return Response(
        result.content,
        status_code=result.status_code,
        media_type="application/json",
        headers={"Cache-Control": "no-store"},
    )


@router.post("", status_code=201)
async def publish(request: Request, actor=Depends(principal)):
    return await forward(request, actor)


@router.get("")
async def listing(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    actor=Depends(principal),
):
    return await forward(request, actor, params={"limit": limit, "offset": offset})


@router.get("/{recording_id}/signal")
async def signal(recording_id: UUID, request: Request, actor=Depends(principal)):
    return await forward(request, actor, "/" + str(recording_id) + "/signal")
