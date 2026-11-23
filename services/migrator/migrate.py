"""Apply immutable service migrations and provision isolated database roles."""

import hashlib
import os
from pathlib import Path

import psycopg
from psycopg import sql


def required(name):
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


SERVICES = ("identity", "data_protocol", "ml_experiments", "recognition")


def apply_migrations(connection, directories, roles_path):
    """One locked transaction; existing files are checksum-checked, never replayed."""
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(546942018234)")
            cursor.execute("""CREATE TABLE IF NOT EXISTS public.service_schema_migrations (
                service text NOT NULL, name text NOT NULL, checksum char(64) NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (service, name))""")
            for service in SERVICES:
                paths = sorted(Path(directories[service]).glob("*.sql"))
                if not paths:
                    raise RuntimeError(f"No migration files for {service}")
                for path in paths:
                    source = path.read_text(encoding="utf-8").replace("\r\n", "\n")
                    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
                    cursor.execute("SELECT checksum FROM public.service_schema_migrations WHERE service = %s AND name = %s", (service, path.name))
                    existing = cursor.fetchone()
                    if existing:
                        if existing[0] != digest:
                            raise RuntimeError(f"Applied migration changed: {service}/{path.name}")
                        continue
                    cursor.execute(source, prepare=False)
                    cursor.execute("INSERT INTO public.service_schema_migrations(service, name, checksum) VALUES (%s, %s, %s)", (service, path.name, digest))
                    print(f"Applied {service}/{path.name}", flush=True)
            cursor.execute(Path(roles_path).read_text(encoding="utf-8"), prepare=False)


def main():
    migrations = Path("/migrations")
    with psycopg.connect(host=required("DB_HOST"), port=int(os.environ.get("DB_PORT", "5432")),
                         dbname=required("DB_NAME"), user=required("DB_ADMIN_USER"),
                         password=required("DB_ADMIN_PASSWORD")) as connection:
        apply_migrations(connection, {service: migrations / service for service in SERVICES}, migrations / "service_roles.sql")
        with connection.transaction():
            with connection.cursor() as cursor:
                for login, group, variable in (
                    ("identity_service_login", "myocontrol_identity", "IDENTITY_DB_PASSWORD"),
                    ("data_service_login", "myocontrol_data", "DATA_DB_PASSWORD"),
                    ("ml_service_login", "myocontrol_ml", "ML_DB_PASSWORD"),
                    ("recognition_service_login", "myocontrol_recognition", "RECOGNITION_DB_PASSWORD"),
                ):
                    # No identity HTTP service consumes this optional login yet.
                    if variable == "IDENTITY_DB_PASSWORD" and not os.environ.get(variable):
                        continue
                    password = required(variable)
                    cursor.execute("SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication FROM pg_roles WHERE rolname = %s", (login,))
                    existing = cursor.fetchone()
                    if existing and existing[0]:
                        raise RuntimeError(f"Existing login {login} has unexpected privileges")
                    if not existing:
                        cursor.execute(sql.SQL("CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION").format(sql.Identifier(login)))
                    cursor.execute(sql.SQL("ALTER ROLE {} LOGIN INHERIT PASSWORD {}").format(sql.Identifier(login), sql.Literal(password)))
                    cursor.execute(sql.SQL("GRANT {} TO {}").format(sql.Identifier(group), sql.Identifier(login)))
    artifact_root = Path("/signal-data")
    artifact_root.mkdir(parents=True, exist_ok=True)
    os.chown(artifact_root, 65532, 65532)


if __name__ == "__main__":
    main()
