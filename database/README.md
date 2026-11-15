# Database

The project uses PostgreSQL 18, SQLAlchemy 2.0, psycopg 3 and Alembic. Direct Python dependencies are listed in `requirements.txt`.

Database documentation includes the [logical model](LOGICAL_MODEL.md), [logical data dictionary](DATA_DICTIONARY.md), [column inventory](COLUMN_INVENTORY.md), generated [SQL DDL](schema.sql) and [implementation status](IMPLEMENTATION.md).

## Local setup

From the project root, set `POSTGRES_PASSWORD` in the environment and start PostgreSQL:

```powershell
docker compose up -d database
```

Compose binds PostgreSQL to `127.0.0.1:5434` by default and stores its data in a named volume. An existing PostgreSQL container can be used instead. Changing the environment password does not change credentials already initialised in a volume. Use `docker compose stop` to stop the container while retaining its data.

Install `database/requirements.txt` in a Python virtual environment and set `DATABASE_URL` to a PostgreSQL connection URL using the `postgresql+psycopg` dialect. Apply migrations from the project root:

```powershell
python -m alembic -c database/alembic.ini upgrade head
```

Generate SQL without applying it with `python -m alembic -c database/alembic.ini upgrade head --sql`. Migrations use the SQL files in `migrations/`; automatic downgrade is unsupported. Back up persistent databases before upgrading.

## Tests and data

The numbered SQL tests in `tests/` are designed for a disposable database at the corresponding migration revision. Python concurrency tests use `TEST_DATABASE_URL` and leave synthetic records in that database. `seeds/` contains repeatable reference data, and `roles.sql` defines the initial database roles.

The schema covers recordings, split manifests, calibration, runs, models and evaluations. New split checksums include the protocol and signal provenance. See [implementation status](IMPLEMENTATION.md) for the checksum format, verification boundaries and known limitations.

**TBD:** DB2 import identity and validation; complete experimental compatibility checks; automatic artifact reconciliation and job recovery; role hardening; a complete column-level dictionary; and backup and retention policies. Transitive dependency versions and the PostgreSQL image digest also remain to be pinned.
