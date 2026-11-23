# Recognition Service

## Database extension available

The additive SQL migrations and [database acceptance tests](../../database/README_TEACHER.md) now provide identity persistence (separate schema), source/publication metadata, generic ML registry/leases/packages/evaluations and terminal desktop reports in their owning schemas. Existing endpoints still use their original tables; this does not automatically implement new cloud or Electron contracts.

## Accepted local runtime boundary

The [accepted architecture](../../docs/ARCHITECTURE_DECISIONS.md) places live recognition and replay in the Electron client's bundled Python runtime alongside direct PLUX SDK acquisition and local calibration/adaptation. The per-window path needs no cloud response. Local pending session summaries/artifacts synchronize via authorized cloud APIs.

The PostgreSQL-backed HTTP service below is the current development replay implementation, not the packaged desktop runtime. Direct acquisition, interactive adaptation, Electron lifecycle, offline persistence and synchronization remain to be implemented. Cloud connectivity failure and device/input failure must be distinct states.

The first increment verifies a published LDA model and a recording, then runs offline replay using an independent implementation of the feature contract. It returns predicted gesture labels and processing timings; it does not yet control a simulated hand or connect to BITalino. The metric excludes buffering and rendering and does not establish the end-to-end latency requirement.

Set `RECOGNITION_DATABASE_URL`, `DATA_SERVICE_URL` and `ML_SERVICE_URL`, apply `migrations/0001_replay.sql` to a disposable PostgreSQL database and install `requirements.txt`. From this directory run:

```powershell
python -m uvicorn recognition.main:app --host 127.0.0.1 --port 8003
```

The API documentation is at `http://127.0.0.1:8003/docs`. The event consumer records `ModelPublished` idempotently; invalid messages and events that exhaust retries go to a dead-letter queue. Redis can cache checksum-verified immutable model bytes for five minutes; if Redis is unavailable, the service fetches the model from ML. The cache is a trusted internal component, not an authenticity signature. The prototype has no authentication, streaming, pause/stop or worker recovery. Use localhost and synthetic data only.
