import os
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from recognition.clients import DependencyError
from recognition.main import app


@unittest.skipUnless(os.getenv("RECOGNITION_DATABASE_URL"), "A migrated disposable database is required")
class RecognitionApiTests(unittest.TestCase):
    def test_dependency_failure_records_neutral(self):
        with TestClient(app) as client:
            self.assertEqual(200, client.get("/health/ready").status_code)
            self.assertIn("recognition_requests_total", client.get("/metrics/").text)
            with patch("recognition.main.load_inputs", side_effect=DependencyError("unavailable")):
                response = client.post("/v1/replay-sessions", json={"model_run_id": str(uuid.uuid4()), "recording_id": str(uuid.uuid4())})
            self.assertEqual(201, response.status_code, response.text)
            body = response.json()
            self.assertEqual("failed", body["status"])
            self.assertEqual("neutral", body["result"]["command"])
            self.assertEqual(body, client.get("/v1/replay-sessions/" + body["id"]).json())


if __name__ == "__main__":
    unittest.main()
