# MyoControl Database — Teacher Review Guide

This is the entry point for checking the **current service database**, including the cloud-storage/local-Electron architecture. The task being demonstrated is database design, migration, integrity, access isolation and persistence. HTTP operator authentication now has separate [gateway tests](../gateway/tests/test_cloud_access.py). Electron and real-data model training remain separate application deliverables and are not claimed complete by these database checks.

## 1. What is implemented

| Schema | Persistent responsibility |
| --- | --- |
| `identity` | Cloud operator accounts, registered desktop/worker clients, scoped expiring/revocable access-session digests. |
| `data_protocol` | Participants, recordings, segments, protocol/split versions, calibration selections, original-source provenance and idempotent client recording receipts. |
| `ml_experiments` | Existing source-LDA flow plus generic LDA/SVM/MLP experiment runs, worker leases, artifact/model/adaptation-package registry, class mappings, evaluations and confusion counts. |
| `recognition` | Existing development replay/events plus immutable synchronized terminal desktop-session reports. |

Operator accounts are distinct from research participants and PostgreSQL service logins. `myoprosthesis` is a historical schema with its own Alembic migrations, not a second copy that must be deployed for the service checks below.

## 2. Files to review

1. [Logical diagrams](SERVICE_MODEL.md) and the PNG diagrams in this directory.
2. [Generated physical dictionary](SERVICE_DATA_DICTIONARY.md): every current service table/column, type, nullability, default, key, CHECK and index.
3. [Service DDL snapshot](service_schema.sql): generated from the tested review database; contains no operator or research row data, only schema and migration bookkeeping.
4. Source migrations: [Identity](../services/identity/migrations/), [Data](../services/data_protocol/migrations/), [ML](../services/ml_experiments/migrations/), [Recognition](../services/recognition/migrations/).
5. [Service roles](service_roles.sql), [migration runner](../services/migrator/migrate.py), [acceptance tests](tests/test_cloud_database.py).
6. [Architectural decision](../docs/ARCHITECTURE_DECISIONS.md) and [implementation status](IMPLEMENTATION.md).

The original `schema.sql`, Alembic migrations and original-schema column inventory are deliberately retained and labelled historical. Use `service_schema.sql` for the current application.

## 3. Recommended isolated review setup

Requirements: Docker with Linux containers, Python 3.12 with the pinned [database dependencies](requirements.txt), and a free local port 55440. Run commands from the repository root. This starts a **separate disposable PostgreSQL 18**, not the application's data volume.

```powershell
docker run --name myocontrol-db-review -d -p 127.0.0.1:55440:5432 -e POSTGRES_DB=myocontrol_review_teacher -e POSTGRES_USER=review_admin -e POSTGRES_PASSWORD=review-only-password postgres:18
docker exec myocontrol-db-review pg_isready -U review_admin -d myocontrol_review_teacher
python -m pip install -r database/requirements.txt
$env:TEST_DATABASE_URL='postgresql://review_admin:review-only-password@127.0.0.1:55440/myocontrol_review_teacher'
python database/review_database.py
```

Wait for `pg_isready` to report accepting connections before running the Python checker. The example password is only for this isolated loopback-bound test container; use separately generated secrets in application deployment. Python and Docker here are reviewer/developer tools, not end-user Electron installation requirements.

On Linux/macOS, the equivalent environment assignment is:

```bash
export TEST_DATABASE_URL='postgresql://review_admin:review-only-password@127.0.0.1:55440/myocontrol_review_teacher'
python database/review_database.py
```

An existing disposable PostgreSQL 16+ instance can also be used. Create a database named `myocontrol_review_*` and set the connection string; the runner refuses mutation of databases with other names. The review account needs permission to create test databases and NOLOGIN roles. Local checks were run on PostgreSQL 16; CI is configured to repeat the checks on PostgreSQL 18.

## 4. Expected verification

The runner:

- applies all 17 immutable service migrations and provisions isolated NOLOGIN roles;
- repeats migration application and checks that history does not change;
- creates an additional uniquely named review database, installs the previous 13-migration service schema, inserts synthetic existing data, then upgrades and verifies preservation;
- executes relational acceptance tests with positive and negative cases;
- exercises two concurrent workers and confirms that they claim different jobs;
- detects deliberately changed migration checksums.

Tests cover account/hash/scope/expiry rules, disabled access, immutable run inputs, submission uniqueness, lease fencing/expiry, incomplete model publication, required LDA/SVM/MLP adaptation material, parent/subset rules, metric arithmetic, complete confusion matrices, missing-rest semantics, client retries/conflicts, source provenance, terminal session reports and reviewer/service privilege isolation.

Most fixtures roll back. The concurrent test intentionally retains two terminal failed **synthetic** runs, and the upgrade rehearsal leaves a separately named `myocontrol_review_upgrade_*` database for inspection. The runner never resets/drops an existing database or changes production volumes.

## 5. Inspect the database

```powershell
docker exec -it myocontrol-db-review psql -U review_admin -d myocontrol_review_teacher
```

Useful SQL/psql commands:

```sql
\dn
\dt identity.*
\dt data_protocol.*
\dt ml_experiments.*
\dt recognition.*
SELECT service, name, applied_at
FROM public.service_schema_migrations ORDER BY service, name;

BEGIN;
SET LOCAL ROLE myocontrol_reviewer;
SELECT * FROM ml_experiments.published_models;
SELECT * FROM ml_experiments.reviewer_results;
ROLLBACK;
```

These views can be empty after rollback-based tests. They are live SQL projections, not prefilled performance claims. Negative privilege checks are automated in the test suite; no password/token or lease hashes are exposed through reviewer views. A reviewer SQL role is not permission to publicly release all pseudonymous research results.

## 6. Transactional design worth checking

- A generic run starts queued, is claimed with a worker/lease identity, and becomes immutable after success/failure/interruption. Expired/wrong leases cannot complete a job. Retries are new run identities.
- Model publication requires verified same-owner artifacts, at least two classes including rest, matching source-parent conditions and required adaptation material. Published package/class membership cannot change.
- Success of a fitting run and publication of its model must commit together. A deferred constraint rejects success without complete output.
- Evaluation success requires the full class-pair confusion matrix, matching model/frozen conditions and correct accuracy/macro-F1/rest false-activation arithmetic (tolerance `1e-9`). No rest windows means NULL with a reason, not a fabricated zero.
- Recording publication uses an operator/client/local UUID key. An identical retry returns the old receipt; a changed digest or target recording is a conflict.
- Terminal desktop reports retain timestamps, measurement boundaries and actual neutral confirmation. Cloud persistence does not prove a physical or rendered neutral action occurred.

## 7. Ownership and enforcement boundaries

Within each service schema, PostgreSQL enforces declared FKs and constraints. UUID references to another service (operator, client, manifest, participant, subset, model or recording) are external references and must be validated/authorized through the owning API. Desktop users and remote workers do not receive PostgreSQL credentials.

The gateway implements Argon2id password verification, opaque token generation, hashed session storage, expiry/revocation checks and owner-scoped registry reads. Other domain routes retain development Basic authentication; worker publication, desktop synchronization and offline grants still require application code. The database stores artifact-verification attestations, not file bytes. It cannot prove what arrays were passed to model fit or that real gestures/labels are correct. The current synthetic ingestion/split path is not a complete real-data identity solution; legacy checksums are not silently rewritten to assert new provenance.

## 8. DDL snapshot and regression checks

Migrations are the authoritative upgrade path. The generated `service_schema.sql` is an alternative clean-database snapshot, not a script to execute over existing tables. Apply [service roles](service_roles.sql) afterwards with an owner/review administrator. Migration ledger rows in the snapshot let the normal migrator verify and skip already represented revisions.

Existing Data/ML/Recognition API tests remain separate regressions, as do the original Alembic/SQL tests. CI runs both the previous paths and the new review runner. Successful database tests do not establish completed cloud deployment, Electron distribution, personalisation implementation or recognition quality on measured data.

For the normal application deployment, use [database README](README.md). For backup/restore scope and limitations, see [restore guide](../deploy/RESTORE.md). Stop only the isolated review container when finished; no production database reset is required.
