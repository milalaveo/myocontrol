# ML Experiments Service

API reference: [versioned OpenAPI JSON](ml_experiments/openapi.json), [Getting Started and integration tutorials](../../api/README.md). The gateway serves the complete client contract at `/docs`, `/redoc` and `/openapi.json`. CI validates stored specifications and all body examples.


## Database extension available

The additive SQL migrations and [database acceptance tests](../../database/README_TEACHER.md) now provide identity persistence (separate schema), source/publication metadata, generic ML registry/leases/packages/evaluations and terminal desktop reports in their owning schemas. Existing endpoints still use their original tables; this does not automatically implement new cloud or Electron contracts.

## Accepted execution boundary

Per [ADR-001](../../docs/ARCHITECTURE_DECISIONS.md), cloud ML APIs own job/model/result metadata and publication, while **general training and batch evaluation execute on a powerful local workstation**. Interactive calibration/adaptation executes in Electron. External workers retrieve inputs/jobs and publish outputs through authenticated APIs, not direct cloud database access.

The existing worker below polls its own PostgreSQL schema in a single-host development Compose. Remote job leasing/heartbeat/publication APIs, reproducible workstation packaging and method-specific adaptation packages are not yet implemented. General training must not be moved to cloud compute merely because job submission uses a web page.

The first cloud API slice is read-only: `GET /v1/registry/{runs|models|results}` and `/{id}`. Requests require a private `CLOUD_INTERNAL_KEY` and a gateway-verified `X-Operator-ID`; the service filters every query by owner. Lists use `limit` (1–100) and `offset`, returning `items` and nullable `next_offset`. Results include confusion counts in their detail endpoint. Raw lease digests and artifact storage paths are excluded. Public clients use `/cloud/v1/...` with an operator bearer session, never these internal headers. No new model is trained or published by browsing these endpoints. Legacy `source_lda_runs` are not relabelled as generic registry runs.

The service retrieves frozen manifests and signals from the Data and Protocol API. It implements a synthetic signal-summary job and an initial source-only shrinkage LDA experiment. The experiment extracts versioned four-channel time-domain features, fits only source data and evaluates on the selected target test. Models and metrics are stored in its own PostgreSQL schema. Results on synthetic signals are infrastructure checks, not evidence of performance on measured EMG.

Set `ML_DATABASE_URL` to a SQLAlchemy PostgreSQL URL, set `DATA_SERVICE_URL` to the Data and Protocol service address and apply `migrations/0001_summary_jobs.sql` to a disposable database. Install `requirements.txt`, then run from this directory:

```powershell
python -m uvicorn ml_experiments.main:app --host 127.0.0.1 --port 8002
```

The API documentation is at `http://127.0.0.1:8002/docs`. Source-only LDA experiments are queued and processed by the separate `ml_experiments.experiment_worker` process. A worker records a heartbeat; jobs whose heartbeat expires are marked `interrupted`. The API supports an optional `Idempotency-Key` header. This is a development implementation without service-level authentication; use localhost and synthetic data. Personalisation, target-only training, SVM and MLP, exhaustive provenance and further recovery testing are TBD.

Create a synthetic split in the Data and Protocol API first, then submit its ID to `POST /v1/synthetic-signal-summary-jobs`. A successful response includes the split checksum, sample count and four computed channel means; retrieve the same job by its ID. Dependency errors produce a persisted `failed` job. Calls use a two-second connection timeout and five-second read/write/pool timeouts, with no automatic retries or overall request deadline.

`POST /v1/source-lda-experiments` accepts a frozen research manifest and target participant and returns `202 Accepted` with a job ID. Poll `GET /v1/source-lda-experiments/{id}` for its status. A successful run stores the frozen manifest snapshot, feature configuration, model coefficients, checksum, accuracy, macro-F1, confusion matrix and rest false-activation rate. It emits `ModelPublished` through a transactional outbox. The separate outbox process uses RabbitMQ publisher confirms; consumers must be idempotent because a crash can cause redelivery.
