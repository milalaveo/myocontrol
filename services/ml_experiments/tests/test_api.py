import os
import unittest
import uuid
import hashlib
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import text

from ml_experiments.data_client import DataServiceError
from ml_experiments.db import session_factory
from ml_experiments.main import app
from ml_experiments.experiment_worker import process


@unittest.skipUnless(os.getenv("ML_DATABASE_URL"), "ML_DATABASE_URL must point to a migrated test database")
class JobApiTests(unittest.TestCase):
    def test_summary_and_dependency_failure_are_persisted(self):
        with TestClient(app) as client:
            self.assertEqual(200, client.get("/health/ready").status_code)
            self.assertIn("ml_experiments_requests_total", client.get("/metrics/").text)
            split_id = uuid.uuid4()
            with patch("ml_experiments.main.source_signal", return_value=(
                {"checksum": "a" * 64}, {"samples": [[1, 2, 3, 4], [3, 4, 5, 6]]}
            )):
                response = client.post("/v1/synthetic-signal-summary-jobs", json={"split_id": str(split_id)})
            self.assertEqual(201, response.status_code, response.text)
            job = response.json()
            self.assertEqual("succeeded", job["status"])
            self.assertEqual([2, 3, 4, 5], job["result"]["channel_means"])
            self.assertEqual(job, client.get("/v1/synthetic-signal-summary-jobs/" + job["id"]).json())
            with patch("ml_experiments.main.source_signal", side_effect=DataServiceError("unavailable")):
                failed = client.post("/v1/synthetic-signal-summary-jobs", json={"split_id": str(uuid.uuid4())}).json()
            self.assertEqual("failed", failed["status"])
            self.assertEqual("unavailable", failed["error"])
            self.assertEqual(failed, client.get("/v1/synthetic-signal-summary-jobs/" + failed["id"]).json())

    def test_training_publishes_verified_model_and_failure(self):
        target_id = uuid.uuid4()
        manifest_id = uuid.uuid4()
        source_id = str(uuid.uuid4())
        def signal(base):
            return {"samples": [[base + (i % 7) * 0.01 + channel * 0.02 for channel in range(4)] for i in range(400)]}
        signals = {"source-rest": signal(1), "source-fist": signal(10), "target-rest": signal(1.1), "target-fist": signal(10.1)}
        units = []
        for recording, role, participant, gesture in (("source-rest", "source_train", source_id, "rest"),
                ("source-fist", "source_train", source_id, "fist"), ("target-rest", "target_test", str(target_id), "rest"),
                ("target-fist", "target_test", str(target_id), "fist")):
            units.append({"recording_id": recording, "role": role, "participant_id": participant, "gesture_code": gesture,
                          "start_sample": 0, "end_sample": 400, "sample_rate_hz": 1000})
        snapshot = {"gesture_codes": ["rest", "fist"], "units": units, "checksum": "a" * 64}
        body = {"manifest_id": str(manifest_id), "target_participant_id": str(target_id)}
        with TestClient(app) as client:
            key = uuid.uuid4().hex
            response = client.post("/v1/source-lda-experiments", json=body, headers={"Idempotency-Key": key})
            self.assertEqual(202, response.status_code, response.text)
            run_id = response.json()["id"]
            self.assertEqual("queued", response.json()["status"])
            self.assertEqual(run_id, client.post("/v1/source-lda-experiments", json=body, headers={"Idempotency-Key": key}).json()["id"])
            self.assertEqual(409, client.post("/v1/source-lda-experiments", json={**body, "manifest_id": str(uuid.uuid4())}, headers={"Idempotency-Key": key}).status_code)
            with session_factory()() as database:
                with database.begin():
                    database.execute(text("""UPDATE ml_experiments.source_lda_runs SET status = 'running',
                        started_at = clock_timestamp(), heartbeat_at = clock_timestamp() WHERE id = :id"""), {"id": uuid.UUID(run_id)})
            with patch("ml_experiments.experiment_worker.research_inputs", return_value=(snapshot, signals)):
                self.assertTrue(process(uuid.UUID(run_id)))
            run = client.get("/v1/source-lda-experiments/" + run_id).json()
            self.assertEqual("succeeded", run["status"])
            self.assertEqual(1.0, run["metrics"]["accuracy"])
            with session_factory()() as database:
                event = database.execute(text("SELECT payload, published_at FROM ml_experiments.outbox_events WHERE run_id = :id"), {"id": uuid.UUID(run["id"])}).one()
                self.assertEqual("ModelPublished", event.payload["event_type"])
                self.assertIsNone(event.published_at)
            artifact = client.get("/v1/source-lda-experiments/" + run["id"] + "/model")
            self.assertEqual(run["model_checksum"], hashlib.sha256(artifact.content).hexdigest())
            self.assertEqual(run, client.get("/v1/source-lda-experiments/" + run["id"]).json())
            failed_id = client.post("/v1/source-lda-experiments", json=body).json()["id"]
            with session_factory()() as database:
                with database.begin():
                    database.execute(text("""UPDATE ml_experiments.source_lda_runs SET status = 'running',
                        started_at = clock_timestamp(), heartbeat_at = clock_timestamp() WHERE id = :id"""), {"id": uuid.UUID(failed_id)})
            with patch("ml_experiments.experiment_worker.research_inputs", side_effect=DataServiceError("unavailable")):
                self.assertTrue(process(uuid.UUID(failed_id)))
            failed = client.get("/v1/source-lda-experiments/" + failed_id).json()
            self.assertEqual("failed", failed["status"])
            self.assertEqual(404, client.get("/v1/source-lda-experiments/" + failed["id"] + "/model").status_code)


if __name__ == "__main__":
    unittest.main()
