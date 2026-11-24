# Database

## Accepted persistence target

[ADR-001](../docs/ARCHITECTURE_DECISIONS.md) places operator accounts, published models, research metadata and experiment results in the cloud. Electron retains prepared packages and unpublished local work and synchronizes through APIs; external training workers also use APIs rather than database credentials. Large artifacts remain in controlled file/object storage.

New migrations implement operator/client/session persistence, recording publication receipts/provenance, generic model/run/package/evaluation records and terminal desktop reports. The gateway now implements operator login, scoped/revocable client tokens and owner-filtered registry reads. Authorization of legacy domain routes and transfer/runtime integration remain outstanding. Start review with [README_TEACHER.md](README_TEACHER.md), [current diagrams](SERVICE_MODEL.md), [generated dictionary](SERVICE_DATA_DICTIONARY.md) and [service DDL](service_schema.sql).

The project uses PostgreSQL 18, SQLAlchemy 2.0 and psycopg 3. The current Compose application uses `data_protocol`, `ml_experiments` and `recognition`. The earlier backend uses a separate `myoprosthesis` schema managed with Alembic. Compose does not migrate historical data between these implementations.

## New identity and registry layer

`identity` has its own isolated NOLOGIN group and login provisioning via `IDENTITY_DB_PASSWORD`. Configure a distinct password plus `CLOUD_INTERNAL_KEY` for the new gateway identity adapter; see [cloud setup](../gateway/README.md). Legacy Basic routes still work without those variables, while the cloud portal returns an explicit configuration error.

The new generic ML registry coexists with `source_lda_runs`; no implicit backfill or model conversion is performed. Account IDs in another service schema are API-validated external UUIDs. The cloud/desktop/worker clients do not receive database credentials.

## Materials for review

- [Data dictionary](DATA_DICTIONARY.md): tables, fields, types and keys for both implementations.
- [Logical model](LOGICAL_MODEL.md): implemented relationships and ER diagrams.
- Current service migrations: [Data & Protocol](../services/data_protocol/migrations/), [ML Experiments](../services/ml_experiments/migrations/), [Recognition](../services/recognition/migrations/).
- [Service migrator](../services/migrator/migrate.py) and [schema roles](service_roles.sql).
- Original backend: [Alembic configuration](alembic.ini), [SQL migrations](migrations/), generated [DDL](schema.sql), [column inventory](COLUMN_INVENTORY.md) and [implementation status](IMPLEMENTATION.md).

## Recommended setup: current service schemas

Install Docker Desktop with Linux containers and Docker Compose v2. Clone the repository and open PowerShell in its root. Create a local `.env` following the [root README](../README.md#local-services), replacing all password placeholders. Supply all listed Compose variables even when starting only PostgreSQL: Compose validates the entire configuration.

To create the service database structure without starting the APIs:

```powershell
docker compose up -d --build database migrate
docker compose logs migrate
docker compose ps -a migrate
```

The migration container must finish with exit code 0. It applies SQL files in filename order and records their names and checksums in `public.service_schema_migrations`. Re-running skips unchanged applied migrations and rejects modified applied SQL. The migrator also provisions separate application logins and schema grants. No tables need to be created manually.

Inspect the schema and history using the default PostgreSQL username and database name:

```powershell
docker compose exec database psql -U thesis_admin -d thesis -c '\dn'
docker compose exec database psql -U thesis_admin -d thesis -c 'SELECT service, name, applied_at FROM public.service_schema_migrations ORDER BY service, name;'
```

Adapt the username/database if `POSTGRES_USER` or `POSTGRES_DB` is overridden. PostgreSQL binds to `127.0.0.1:5434` by default. Named volumes persist data; changing `.env` alone does not reset the password of an existing database.

To start the APIs:

```powershell
docker compose up -d --build
```

Interactive API documentation is at `http://127.0.0.1:8000/data/docs`, `/experiments/docs` and `/recognition/docs`. Sign in with `GATEWAY_USERNAME` and `GATEWAY_PASSWORD`. Stop services while keeping data with `docker compose stop`.

## Original backend: separate Alembic setup

Use a separate empty PostgreSQL database for this schema. Install Python 3.12 and use a virtual environment. Set `DATABASE_URL` to that database with the `postgresql+psycopg` dialect; credentials belong in the environment and must be URL-encoded where needed. Run from the repository root:

```powershell
python -m pip install -r database/requirements.txt
python -m alembic -c database/alembic.ini upgrade head
python -m alembic -c database/alembic.ini current
```

Generate original-schema SQL without applying it using `python -m alembic -c database/alembic.ini upgrade head --sql`. `schema.sql` covers only the original schema. Automatic downgrade is unsupported. `roles.sql` and `seeds/001_reference_gestures.sql` are separate original-backend scripts.

## Verification and remaining work

The [Database checks workflow](../.github/workflows/database.yml) tests original migrations, constraints, concurrency, service APIs and schema isolation, and applies generated SQL on a clean database. Numbered SQL tests target particular migration revisions; run them on disposable databases in workflow order.

The baseline 13 migrations were previously exercised on PostgreSQL 18. The new 17-migration state was verified locally on PostgreSQL 16.3 with repeat/upgrade checks, 18 acceptance tests, DDL restore and existing service tests. CI is configured to repeat on PostgreSQL 18. See the teacher guide for reproducible commands; no synthetic check establishes recognition performance on measured EMG.

**TBD:** validated real-data identity rules, final research comparison rules, participant-data governance and a complete backup/retention policy. Local backup and partial restore instructions are in [deploy](../deploy/RESTORE.md).
