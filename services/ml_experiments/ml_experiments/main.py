from pathlib import Path
import logging
import json
import re
import time
import uuid

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, ConfigDict
from opentelemetry.propagate import inject
from prometheus_client import Counter, Histogram, REGISTRY, make_asgi_app
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from .data_client import DataServiceError, source_signal
from .db import get_session, session_factory
from .schemas import HealthResponse, LdaModel, ExperimentMetrics, SignalSummary
from .models import SignalSummaryJob, SourceLdaRun
from .registry import router as registry_router

logging.basicConfig(level=logging.INFO, format="%(message)s")
app = FastAPI(title="ML Experiments API", version="0.1.0")
app.include_router(registry_router)
app.mount("/metrics", make_asgi_app())
REQUESTS = Counter("ml_experiments_requests_total", "HTTP requests", ["method", "route", "status"])
LATENCY = Histogram("ml_experiments_request_seconds", "HTTP request duration", ["method", "route"])
logger = logging.getLogger("ml_experiments")
logger.setLevel(logging.INFO)


class ExperimentCollector:
    def describe(self):
        yield GaugeMetricFamily(
            "ml_experiments_runs", "Persisted LDA runs by status", labels=["status"]
        )

    def collect(self):
        metric = GaugeMetricFamily(
            "ml_experiments_runs", "Persisted LDA runs by status", labels=["status"]
        )
        try:
            with session_factory()() as session:
                for status, count in session.execute(
                    text(
                        "SELECT status, count(*) FROM ml_experiments.source_lda_runs GROUP BY status"
                    )
                ):
                    metric.add_metric([status], count)
        except SQLAlchemyError:
            logger.warning("experiment_metrics_database_unavailable")
        yield metric


REGISTRY.register(ExperimentCollector())


class JobCreate(BaseModel):
    split_id: uuid.UUID


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    split_id: uuid.UUID
    status: str
    split_checksum: str | None
    result: SignalSummary | None
    error: str | None


class ExperimentCreate(BaseModel):
    manifest_id: uuid.UUID
    target_participant_id: uuid.UUID


class ExperimentResponse(ExperimentCreate):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: str
    manifest_checksum: str | None
    model: LdaModel | None
    model_checksum: str | None
    metrics: ExperimentMetrics | None
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
                "service": "ml_experiments",
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
    session.execute(text("SELECT 1 FROM ml_experiments.signal_summary_jobs LIMIT 1"))
    return {"status": "ready"}


@app.post("/v1/synthetic-signal-summary-jobs", response_model=JobResponse, status_code=201)
def create_job(body: JobCreate, request: Request, session: Session = Depends(get_session)):
    job = SignalSummaryJob(split_id=body.split_id, status="running")
    session.add(job)
    session.commit()
    try:
        split, signal = source_signal(body.split_id, request.state.correlation_id)
        samples = signal["samples"]
        means = [sum(float(row[i]) for row in samples) / len(samples) for i in range(4)]
        job.split_checksum = split["checksum"]
        job.result = {
            "kind": "synthetic_signal_summary",
            "sample_count": len(samples),
            "channel_means": means,
        }
        job.status = "succeeded"
    except DataServiceError as error:
        job.status = "failed"
        job.error = str(error)
    session.commit()
    return job


@app.get("/v1/synthetic-signal-summary-jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: uuid.UUID, session: Session = Depends(get_session)):
    job = session.get(SignalSummaryJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post(
    "/v1/source-lda-experiments",
    response_model=ExperimentResponse,
    status_code=202,
    tags=["experiments"],
)
def create_source_lda_experiment(
    body: ExperimentCreate,
    request: Request,
    response: Response,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    session: Session = Depends(get_session),
):
    if idempotency_key is not None and not re.fullmatch(r"[A-Za-z0-9._:-]{1,100}", idempotency_key):
        raise HTTPException(status_code=422, detail="Invalid idempotency key")
    carrier = {}
    inject(carrier)
    trace_context = {
        key: value for key, value in carrier.items() if key in {"traceparent", "tracestate"}
    }
    run = SourceLdaRun(
        manifest_id=body.manifest_id,
        target_participant_id=body.target_participant_id,
        status="queued",
        idempotency_key=idempotency_key,
        correlation_id=request.state.correlation_id,
        trace_context=trace_context,
    )
    try:
        session.add(run)
        session.commit()
    except IntegrityError as error:
        session.rollback()
        if idempotency_key is None or getattr(error.orig, "sqlstate", None) != "23505":
            raise
        run = session.query(SourceLdaRun).filter_by(idempotency_key=idempotency_key).one()
        if (
            run.manifest_id != body.manifest_id
            or run.target_participant_id != body.target_participant_id
        ):
            raise HTTPException(
                status_code=409, detail="Idempotency key belongs to a different request"
            ) from error
    response.headers["Location"] = f"/v1/source-lda-experiments/{run.id}"
    return run


@app.get(
    "/v1/source-lda-experiments/{run_id}", response_model=ExperimentResponse, tags=["experiments"]
)
def get_source_lda_experiment(run_id: uuid.UUID, session: Session = Depends(get_session)):
    run = session.get(SourceLdaRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return run


@app.get("/v1/source-lda-experiments/{run_id}/model", response_model=LdaModel, tags=["experiments"])
def get_source_lda_model(run_id: uuid.UUID, session: Session = Depends(get_session)):
    row = session.execute(
        text("""SELECT model::text, model_checksum FROM ml_experiments.source_lda_runs
        WHERE id = :id AND status = 'succeeded' AND model_checksum IS NOT NULL"""),
        {"id": run_id},
    ).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Published model not found")
    return Response(
        content=row[0], media_type="application/json", headers={"X-Artifact-SHA256": row[1]}
    )


def published_openapi():
    if app.openapi_schema is None:
        app.openapi_schema = json.loads(
            Path(__file__).with_name("openapi.json").read_text(encoding="utf-8")
        )
    return app.openapi_schema


app.openapi = published_openapi
