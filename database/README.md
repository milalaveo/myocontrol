# Database

The project uses PostgreSQL 18, SQLAlchemy 2.0 and psycopg 3. The current Compose application uses `data_protocol`, `ml_experiments` and `recognition`. The earlier backend uses a separate `myoprosthesis` schema managed with Alembic. Compose does not migrate historical data between these implementations.

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

The service migrator was also run on an isolated empty PostgreSQL 18 instance: 5 Data & Protocol, 6 ML Experiments and 2 Recognition migrations completed successfully. This verifies schema creation; synthetic tests do not establish recognition performance on measured signals.

**TBD:** validated real-data identity rules, final research comparison rules, participant-data governance and a complete backup/retention policy. Local backup and partial restore instructions are in [deploy](../deploy/RESTORE.md).
