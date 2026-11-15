# ML Experiments Service

The service retrieves frozen manifests and signals from the Data and Protocol API. It implements a synthetic signal-summary job and an initial source-only shrinkage LDA experiment. The experiment extracts versioned four-channel time-domain features, fits only source data and evaluates on the selected target test. Models and metrics are stored in its own PostgreSQL schema. Results on synthetic signals are infrastructure checks, not evidence of performance on measured EMG.

Set `ML_DATABASE_URL` to a SQLAlchemy PostgreSQL URL, set `DATA_SERVICE_URL` to the Data and Protocol service address and apply `migrations/0001_summary_jobs.sql` to a disposable database. Install `requirements.txt`, then run from this directory:

```powershell
python -m uvicorn ml_experiments.main:app --host 127.0.0.1 --port 8002
```

The API documentation is at `http://127.0.0.1:8002/docs`. Source-only LDA experiments are queued and processed by the separate `ml_experiments.experiment_worker` process. A worker records a heartbeat; jobs whose heartbeat expires are marked `interrupted`. The API supports an optional `Idempotency-Key` header. This is a development implementation without service-level authentication; use localhost and synthetic data. Personalisation, target-only training, SVM and MLP, exhaustive provenance and further recovery testing are TBD.

Create a synthetic split in the Data and Protocol API first, then submit its ID to `POST /v1/synthetic-signal-summary-jobs`. A successful response includes the split checksum, sample count and four computed channel means; retrieve the same job by its ID. Dependency errors produce a persisted `failed` job. Calls use a two-second connection timeout and five-second read/write/pool timeouts, with no automatic retries or overall request deadline.

`POST /v1/source-lda-experiments` accepts a frozen research manifest and target participant and returns `202 Accepted` with a job ID. Poll `GET /v1/source-lda-experiments/{id}` for its status. A successful run stores the frozen manifest snapshot, feature configuration, model coefficients, checksum, accuracy, macro-F1, confusion matrix and rest false-activation rate. It emits `ModelPublished` through a transactional outbox. The separate outbox process uses RabbitMQ publisher confirms; consumers must be idempotent because a crash can cause redelivery.
