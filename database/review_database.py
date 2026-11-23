"""Create/check the service schema only in an explicitly named review database.

Set TEST_DATABASE_URL to a PostgreSQL database named myocontrol_review_*.
This runner never drops a database, provisions real passwords or edits research data.
"""
import importlib.util
import hashlib
import os
from pathlib import Path
import sys
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / ".deps").exists():
    sys.path.insert(0, str(ROOT / ".deps"))

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo


def check_upgrade(dsn, migrator):
    """Keep a separately named upgrade fixture; never reset an existing database."""
    name = 'myocontrol_review_upgrade_' + uuid.uuid4().hex[:12]
    with psycopg.connect(dsn, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    upgraded_dsn = make_conninfo(dsn, dbname=name)
    with psycopg.connect(upgraded_dsn, autocommit=True) as c:
        c.execute('''CREATE TABLE public.service_schema_migrations (
            service text NOT NULL, name text NOT NULL, checksum char(64) NOT NULL,
            applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (service,name))''')
        old_counts = {'data_protocol': 5, 'ml_experiments': 6, 'recognition': 2}
        with c.transaction():
            for service, count in old_counts.items():
                for path in sorted((ROOT/'services'/service/'migrations').glob('*.sql'))[:count]:
                    source = path.read_text(encoding='utf-8').replace('\r\n','\n')
                    c.execute(source, prepare=False)
                    c.execute('INSERT INTO public.service_schema_migrations(service,name,checksum) VALUES (%s,%s,%s)',
                              (service,path.name,hashlib.sha256(source.encode()).hexdigest()))
            participant, run = uuid.uuid4(), uuid.uuid4()
            c.execute("INSERT INTO data_protocol.participants(id,pseudonym) VALUES (%s,'upgrade_fixture')",(participant,))
            c.execute("INSERT INTO ml_experiments.source_lda_runs(id,manifest_id,target_participant_id,status) VALUES (%s,%s,%s,'queued')",
                      (run,uuid.uuid4(),participant))
        migrator.apply_migrations(c,{s:ROOT/'services'/s/'migrations' for s in migrator.SERVICES},ROOT/'database/service_roles.sql')
        assert c.execute('SELECT pseudonym FROM data_protocol.participants WHERE id=%s',(participant,)).fetchone()==('upgrade_fixture',)
        assert c.execute('SELECT status FROM ml_experiments.source_lda_runs WHERE id=%s',(run,)).fetchone()==('queued',)
        print(f'Upgrade preserved existing participant and queued LDA run: {name}',flush=True)


def main():
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        raise SystemExit("Set TEST_DATABASE_URL to a disposable myocontrol_review_* database")
    with psycopg.connect(dsn, autocommit=True) as connection:
        database = connection.execute("SELECT current_database()").fetchone()[0]
        if not database.startswith("myocontrol_review_"):
            raise SystemExit("Refusing to mutate a database not named myocontrol_review_*")
        spec = importlib.util.spec_from_file_location("review_migrator", ROOT / "services/migrator/migrate.py")
        migrator = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(migrator)
        paths = {name: ROOT / "services" / name / "migrations" for name in migrator.SERVICES}
        migrator.apply_migrations(connection, paths, ROOT / "database/service_roles.sql")
        before = connection.execute("SELECT count(*) FROM public.service_schema_migrations").fetchone()[0]
        migrator.apply_migrations(connection, paths, ROOT / "database/service_roles.sql")
        after = connection.execute("SELECT count(*) FROM public.service_schema_migrations").fetchone()[0]
        if before != after:
            raise RuntimeError("Re-running migrations changed history")
        print(f"Migration repeat check passed: {after} immutable migration records", flush=True)
    check_upgrade(dsn, migrator)
    suite = unittest.defaultTestLoader.discover(str(ROOT / "database/tests"), pattern="test_cloud_database.py")
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
