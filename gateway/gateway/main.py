"""Local gateway with standard HTTP Basic authentication and rate limiting."""

import hmac
import ipaddress
import json
import logging
import os
import re
import threading
import time
import uuid

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from prometheus_client import Counter, Histogram, make_asgi_app
from sqlalchemy.exc import SQLAlchemyError

from .identity import router as identity_router
from .cloud import router as cloud_router

logging.basicConfig(level=logging.INFO, format="%(message)s")
app = FastAPI(title="Myocontrol Gateway", version="0.1.0")
app.include_router(identity_router)
app.include_router(cloud_router)
app.mount("/metrics", make_asgi_app())
REQUESTS = Counter("gateway_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("gateway_request_seconds", "HTTP request duration", ["method", "route"])
security = HTTPBasic()
logger = logging.getLogger("gateway")
logger.setLevel(logging.INFO)
lock = threading.Lock()
requests_by_client = {}
SERVICES = {"data": "DATA_SERVICE_URL", "experiments": "ML_SERVICE_URL", "recognition": "RECOGNITION_SERVICE_URL"}


@app.exception_handler(SQLAlchemyError)
async def database_error(request: Request, error: SQLAlchemyError):
    logger.error("identity_database_unavailable type=%s", type(error).__name__)
    return JSONResponse(status_code=503, content={"detail": "Operator access unavailable"})


@app.middleware("http")
async def correlation_id(request: Request, call_next):
    candidate = request.headers.get("x-correlation-id", "")
    correlation = candidate if re.fullmatch(r"[A-Za-z0-9_-]{1,64}", candidate) else uuid.uuid4().hex
    request.state.correlation_id = correlation
    started = time.perf_counter()
    try:
        if request.url.path not in {"/health/live", "/metrics", "/metrics/"}:
            enforce_rate_limit(client_address(request))
        response = await call_next(request)
    except HTTPException as error:
        response = JSONResponse(status_code=error.status_code, content={"detail": error.detail}, headers=error.headers)
    except Exception:
        logger.exception("unhandled_error correlation_id=%s", correlation)
        response = JSONResponse(status_code=500, content={"detail": "Internal server error", "correlation_id": correlation})
    response.headers["X-Correlation-ID"] = correlation
    if request.url.path.startswith(("/auth/", "/cloud/")):
        response.headers["Cache-Control"] = "no-store"
    route = getattr(request.scope.get("route"), "path", "unmatched")
    elapsed = time.perf_counter() - started
    REQUESTS.labels(request.method, route, str(response.status_code)).inc()
    LATENCY.labels(request.method, route).observe(elapsed)
    logger.info(json.dumps({"event": "http_request", "service": "gateway", "correlation_id": correlation,
                            "method": request.method, "path": request.url.path, "status": response.status_code,
                            "duration_ms": round(elapsed * 1000, 3)}))
    return response


def authenticate(credentials: HTTPBasicCredentials = Depends(security)):
    username, password = os.environ.get("GATEWAY_USERNAME"), os.environ.get("GATEWAY_PASSWORD")
    if not username or not password:
        raise HTTPException(status_code=503, detail="Gateway credentials are not configured")
    if not (hmac.compare_digest(credentials.username.encode("utf-8"), username.encode("utf-8")) and
            hmac.compare_digest(credentials.password.encode("utf-8"), password.encode("utf-8"))):
        raise HTTPException(status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Basic"})
    return username


def enforce_rate_limit(client):
    now = time.monotonic()
    try:
        limit = int(os.environ.get("GATEWAY_REQUESTS_PER_MINUTE", "60"))
    except ValueError as error:
        raise HTTPException(status_code=503, detail="Gateway rate limit is invalid") from error
    if limit < 1:
        raise HTTPException(status_code=503, detail="Gateway rate limit is invalid")
    with lock:
        for key, (start, _) in list(requests_by_client.items()):
            if now - start >= 60:
                del requests_by_client[key]
        start, count = requests_by_client.get(client, (now, 0))
        if count >= limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded", headers={"Retry-After": str(max(1, int(60 - (now - start))))})
        requests_by_client[client] = (start, count + 1)


def client_address(request: Request):
    address = request.client.host if request.client else "unknown"
    trusted_proxy = os.environ.get("GATEWAY_TRUSTED_PROXY_IP")
    if trusted_proxy and address == trusted_proxy:
        forwarded = request.headers.get("x-real-ip", "")
        try:
            return str(ipaddress.ip_address(forwarded))
        except ValueError:
            return address
    return address


@app.get("/health/live")
def live():
    return {"status": "live"}


@app.get("/{service}/docs", include_in_schema=False)
def service_docs(service: str, username: str = Depends(authenticate)):
    if service not in SERVICES:
        raise HTTPException(status_code=404, detail="Route not found")
    return get_swagger_ui_html(openapi_url=f"/{service}/openapi.json", title=f"{service} API")


@app.api_route("/{service}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(service: str, path: str, request: Request, username: str = Depends(authenticate)):
    if path == "v1/registry" or path.startswith("v1/registry/"):
        raise HTTPException(status_code=403, detail="Use operator-authenticated cloud routes")
    if service not in SERVICES or not (path.startswith("v1/") or path in {"health/live", "health/ready", "openapi.json"}) or ".." in path.split("/"):
        raise HTTPException(status_code=404, detail="Route not found")
    address = os.environ.get(SERVICES[service])
    if not address:
        raise HTTPException(status_code=503, detail="Service address is not configured")
    payload = await request.body()
    if len(payload) > 2_000_000:
        raise HTTPException(status_code=413, detail="Request body is too large")
    correlation = request.state.correlation_id
    headers = {"X-Correlation-ID": correlation}
    if "content-type" in request.headers:
        headers["Content-Type"] = request.headers["content-type"]
    if "idempotency-key" in request.headers:
        headers["Idempotency-Key"] = request.headers["idempotency-key"]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=2.0), follow_redirects=False) as client:
            response = await client.request(request.method, f"{address.rstrip('/')}/{path}", params=request.query_params,
                                            content=payload, headers=headers)
    except httpx.TimeoutException as error:
        raise HTTPException(status_code=504, detail="Service request timed out", headers={"X-Correlation-ID": correlation}) from error
    except httpx.HTTPError as error:
        raise HTTPException(status_code=502, detail="Service unavailable", headers={"X-Correlation-ID": correlation}) from error
    response_headers = {"X-Correlation-ID": correlation}
    for name in ("content-type", "retry-after", "www-authenticate"):
        if name in response.headers:
            response_headers[name] = response.headers[name]
    location = response.headers.get("location", "")
    if location.startswith("/") and not location.startswith("//"):
        response_headers["Location"] = f"/{service}{location}"
    content = response.content
    if path == "openapi.json" and response.is_success:
        try:
            document = response.json()
            document["servers"] = [{"url": f"/{service}"}]
            content = json.dumps(document, separators=(",", ":")).encode("utf-8")
        except (ValueError, TypeError, AttributeError) as error:
            raise HTTPException(status_code=502, detail="Invalid service API document") from error
    return Response(content=content, status_code=response.status_code, headers=response_headers)
