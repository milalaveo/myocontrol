"""Claim LDA jobs, keep a lease alive and publish results atomically."""

import json
import logging
import threading
import time
import uuid
from datetime import datetime, timezone

from opentelemetry import context, trace
from opentelemetry.propagate import extract, inject
from sqlalchemy import select, text

from .data_client import DataServiceError, research_inputs
from .db import session_factory
from .models import OutboxEvent, SourceLdaRun
from .training import train_source_lda

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("experiment_worker")
HEARTBEAT_SECONDS = 10
STALE_SECONDS = 120
RECOVERY_INTERVAL_SECONDS = 30
IDLE_SECONDS = 1


def claim_one():
    with session_factory()() as session:
        with session.begin():
            run = session.scalars(select(SourceLdaRun).where(SourceLdaRun.status == "queued")
                                  .order_by(SourceLdaRun.created_at, SourceLdaRun.id)
                                  .with_for_update(skip_locked=True).limit(1)).first()
            if run is None:
                return None
            now = datetime.now(timezone.utc)
            run.status, run.started_at, run.heartbeat_at = "running", now, now
            return run.id


def heartbeat(run_id, stop):
    while not stop.wait(HEARTBEAT_SECONDS):
        try:
            with session_factory()() as session:
                with session.begin():
                    session.execute(text("""UPDATE ml_experiments.source_lda_runs SET heartbeat_at = clock_timestamp()
                        WHERE id = :id AND status = 'running'"""), {"id": run_id})
        except Exception:
            logger.exception("experiment_heartbeat_failed run_id=%s", run_id)


def recover_stale():
    with session_factory()() as session:
        with session.begin():
            result = session.execute(text("""UPDATE ml_experiments.source_lda_runs SET status = 'interrupted',
                completed_at = clock_timestamp(), error = 'Worker heartbeat expired'
                WHERE status = 'running' AND heartbeat_at < clock_timestamp() - make_interval(secs => :seconds)"""),
                {"seconds": STALE_SECONDS})
            return result.rowcount


def process(run_id):
    with session_factory()() as session:
        run = session.get(SourceLdaRun, run_id)
        if run is None or run.status != "running":
            return False
        manifest_id, target_id, correlation, trace_context = run.manifest_id, run.target_participant_id, run.correlation_id, run.trace_context
    token = context.attach(extract(trace_context))
    try:
        with trace.get_tracer(__name__).start_as_current_span("experiment.execute"):
            return execute(run_id, manifest_id, target_id, correlation)
    finally:
        context.detach(token)


def execute(run_id, manifest_id, target_id, correlation):
    stop = threading.Event()
    heartbeat_thread = threading.Thread(target=heartbeat, args=(run_id, stop), daemon=True)
    heartbeat_thread.start()
    try:
        snapshot, signals = research_inputs(manifest_id, target_id, correlation)
        output = train_source_lda(snapshot, signals, target_id)
        error_message = None
    except (DataServiceError, ValueError) as error:
        snapshot, output, error_message = None, None, str(error)
    except Exception:
        logger.exception("training_failed correlation_id=%s run_id=%s", correlation, run_id)
        snapshot, output, error_message = None, None, "Experiment failed unexpectedly"
    finally:
        stop.set()
        heartbeat_thread.join(timeout=2)
    with session_factory()() as session:
        with session.begin():
            run = session.scalars(select(SourceLdaRun).where(SourceLdaRun.id == run_id).with_for_update()).one()
            if run.status != "running":
                logger.warning("experiment_result_discarded run_id=%s status=%s", run_id, run.status)
                return False
            run.completed_at = datetime.now(timezone.utc)
            if error_message is None:
                run.manifest_checksum, run.snapshot = snapshot["checksum"], snapshot
                run.model, run.metrics, run.status = output["model"], output["metrics"], "succeeded"
                event_id = uuid.uuid4()
                event_context = {}
                inject(event_context)
                event_context = {key: value for key, value in event_context.items() if key in {"traceparent", "tracestate"}}
                session.add(OutboxEvent(id=event_id, run_id=run.id, event_type="ModelPublished", payload={
                    "event_id": str(event_id), "event_type": "ModelPublished", "schema_version": 1,
                    "model_run_id": str(run.id), "manifest_id": str(run.manifest_id), "correlation_id": correlation,
                    "trace_context": event_context,
                }))
            else:
                run.status, run.error = "failed", error_message
            logger.info(json.dumps({"event": "experiment_completed", "run_id": str(run_id),
                                    "correlation_id": correlation, "status": run.status}))
    return True


def main():
    next_recovery = 0.0
    while True:
        try:
            if time.monotonic() >= next_recovery:
                interrupted = recover_stale()
                if interrupted:
                    logger.warning("interrupted_stale_experiments count=%s", interrupted)
                next_recovery = time.monotonic() + RECOVERY_INTERVAL_SECONDS
            run_id = claim_one()
            if run_id is None:
                time.sleep(IDLE_SECONDS)
            else:
                process(run_id)
        except Exception:
            logger.exception("experiment_worker_error")
            time.sleep(3)


if __name__ == "__main__":
    main()
