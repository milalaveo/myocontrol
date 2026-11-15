"""Run only against a disposable migrated PostgreSQL database."""

import os
from pathlib import Path
import tempfile
import unittest
import uuid

import psycopg

from myoprosthesis.experiments.synthetic_workflow import run_synthetic_rehearsal
from myoprosthesis.persistence.artifacts import LocalArtifactStore, StoredArtifact
from myoprosthesis.persistence.publication import publish_source_model, referenced_local_keys


@unittest.skipUnless(os.getenv("TEST_DATABASE_URL"), "Set TEST_DATABASE_URL to a disposable database")
class SyntheticIntegrationTests(unittest.TestCase):
    def test_rehearsal_and_failure_reconciliation(self):
        with tempfile.TemporaryDirectory() as directory, psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as connection:
            store = LocalArtifactStore(Path(directory))
            result = run_synthetic_rehearsal(connection, store)
            self.assertTrue(result["synthetic"])
            key = connection.execute("SELECT a.storage_key FROM myoprosthesis.split_units u JOIN myoprosthesis.signal_provenance p ON p.signal_id = u.signal_id JOIN myoprosthesis.artifacts a ON a.id = p.artifact_id WHERE u.manifest_id = %s AND u.role = 'source_train'", (result["manifest_id"],)).fetchone()[0]
            lines = (store.root / key).read_text(encoding="ascii").splitlines()
            self.assertEqual(101, len(lines))
            self.assertTrue(all(len(line.split(",")) == 4 for line in lines))
            row = connection.execute("SELECT evaluation_id FROM myoprosthesis.completed_evaluations WHERE evaluation_id = %s", (result["evaluation_id"],)).fetchone()
            self.assertEqual((result["evaluation_id"],), row)
            with psycopg.connect(os.environ["TEST_DATABASE_URL"], autocommit=True) as restarted:
                artifact = restarted.execute("SELECT a.storage_key, a.sha256, a.size_bytes FROM myoprosthesis.published_models m JOIN myoprosthesis.artifacts a ON a.id = m.artifact_id WHERE m.id = %s", (result["model_id"],)).fetchone()
                store.verify(StoredArtifact(*artifact))
            row = connection.execute("SELECT manifest_id, feature_config_id FROM myoprosthesis.runs WHERE id = (SELECT run_id FROM myoprosthesis.model_versions WHERE id = %s)", (result["model_id"],)).fetchone()
            failed_run = connection.execute("INSERT INTO myoprosthesis.runs(kind, manifest_id, feature_config_id, seed, parameter_schema_version, parameters, software_version) VALUES ('train', %s, %s, 1, 'synthetic-v1', '{}', 'failure-test') RETURNING id", row).fetchone()[0]
            connection.execute("UPDATE myoprosthesis.runs SET status = 'running', started_at = clock_timestamp() WHERE id = %s", (failed_run,))
            data = uuid.uuid4().bytes
            with self.assertRaises(psycopg.Error):
                publish_source_model(connection, store, failed_run, "lda", data)
            self.assertEqual(("running",), connection.execute("SELECT status FROM myoprosthesis.runs WHERE id = %s", (failed_run,)).fetchone())
            self.assertEqual((0,), connection.execute("SELECT count(*) FROM myoprosthesis.model_versions WHERE run_id = %s", (failed_run,)).fetchone())
            orphans = store.find_orphans(referenced_local_keys(connection), 0)
            self.assertEqual(1, len(orphans))
            self.assertTrue((store.root / orphans[0]).is_file())


if __name__ == "__main__":
    unittest.main()
