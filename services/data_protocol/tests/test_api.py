"""HTTP/database integration checks; requires a disposable PostgreSQL database."""

import os
import tempfile
import unittest
import uuid

from fastapi.testclient import TestClient

from data_protocol.main import app


@unittest.skipUnless(os.getenv("DATA_DATABASE_URL"), "DATA_DATABASE_URL must point to a migrated test database")
class ParticipantApiTests(unittest.TestCase):
    def test_create_read_validation_and_conflict(self):
        with TestClient(app) as client:
            self.assertEqual(200, client.get("/health/live").status_code)
            self.assertEqual(200, client.get("/health/ready").status_code)
            self.assertIn("data_protocol_requests_total", client.get("/metrics/").text)
            code = f"synthetic-{uuid.uuid4().hex}"
            created = client.post("/v1/participants", json={"pseudonym": code}, headers={"X-Correlation-ID": "test-123"})
            self.assertEqual(201, created.status_code, created.text)
            self.assertEqual("test-123", created.headers["X-Correlation-ID"])
            participant = created.json()
            self.assertEqual(code, participant["pseudonym"])
            self.assertEqual(participant, client.get(f"/v1/participants/{participant['id']}").json())
            self.assertEqual(409, client.post("/v1/participants", json={"pseudonym": code}).status_code)
            self.assertEqual(422, client.post("/v1/participants", json={"pseudonym": "invalid value"}).status_code)
            self.assertEqual(404, client.get(f"/v1/participants/{uuid.uuid4()}").status_code)
            self.assertEqual(422, client.get("/v1/participants?limit=101").status_code)
            with tempfile.TemporaryDirectory() as directory:
                previous = os.environ.get("DATA_ARTIFACT_ROOT")
                os.environ["DATA_ARTIFACT_ROOT"] = directory
                try:
                    payload = {"participant_id": participant["id"], "sample_rate_hz": 1000,
                               "samples": [[1, 2, 3, 4], [2, 3, 4, 5]]}
                    recording = client.post("/v1/recordings", json=payload)
                    self.assertEqual(201, recording.status_code, recording.text)
                    self.assertEqual(2, recording.json()["sample_count"])
                    self.assertEqual(recording.json(), client.get("/v1/recordings/" + recording.json()["id"]).json())
                    payload["samples"] = [[1, 2, 3]]
                    self.assertEqual(422, client.post("/v1/recordings", json=payload).status_code)
                    other = client.post("/v1/participants", json={"pseudonym": "target-" + uuid.uuid4().hex}).json()
                    target = client.post("/v1/recordings", json={"participant_id": other["id"], "sample_rate_hz": 1000,
                                                                  "samples": [[9, 8, 7, 6]]}).json()
                    split_payload = {"source_recording_id": recording.json()["id"], "test_recording_id": target["id"]}
                    split = client.post("/v1/synthetic-splits", json=split_payload)
                    self.assertEqual(201, split.status_code, split.text)
                    self.assertEqual(64, len(split.json()["checksum"]))
                    self.assertEqual(split.json(), client.get("/v1/synthetic-splits/" + split.json()["id"]).json())
                    duplicate = client.post("/v1/recordings", json={"participant_id": other["id"], "sample_rate_hz": 1000,
                                                                     "samples": [[1, 2, 3, 4], [2, 3, 4, 5]]}).json()
                    self.assertEqual(409, client.post("/v1/synthetic-splits", json={"source_recording_id": recording.json()["id"],
                                                                                     "test_recording_id": duplicate["id"]}).status_code)
                    protocol = client.post("/v1/protocols", json={"name": "test-" + uuid.uuid4().hex, "version": 1, "gesture_codes": ["rest"]})
                    self.assertEqual(201, protocol.status_code, protocol.text)
                    segments = []
                    for rec in (recording.json(), target):
                        response = client.post("/v1/segments", json={"recording_id": rec["id"], "gesture_code": "rest",
                                                                      "repetition_key": "one", "start_sample": 0,
                                                                      "end_sample": rec["sample_count"]})
                        self.assertEqual(201, response.status_code, response.text)
                        segments.append(response.json()["id"])
                    manifest = client.post("/v1/research-manifests", json={"name": "test-" + uuid.uuid4().hex,
                                           "version": 1, "protocol_id": protocol.json()["id"]})
                    self.assertEqual(201, manifest.status_code, manifest.text)
                    manifest_url = "/v1/research-manifests/" + manifest.json()["id"]
                    for person, category, segment, role in ((participant, "source", segments[0], "source_train"),
                                                             (other, "target", segments[1], "target_test")):
                        assignment = {"participant_id": person["id"], "category": category}
                        response = client.post(manifest_url + "/participants", json=assignment)
                        self.assertEqual(201, response.status_code, response.text)
                        response = client.post(manifest_url + "/units", json={**assignment, "segment_id": segment, "role": role})
                        self.assertEqual(201, response.status_code, response.text)
                    calibration_recording = client.post("/v1/recordings", json={"participant_id": other["id"], "sample_rate_hz": 1000,
                        "samples": [[42, 1, 0, 0], [43, 1, 0, 0]]}).json()
                    calibration_segment = client.post("/v1/segments", json={"recording_id": calibration_recording["id"],
                        "gesture_code": "rest", "repetition_key": "calibration", "start_sample": 0, "end_sample": 2}).json()
                    calibration_unit_response = client.post(manifest_url + "/units", json={"participant_id": other["id"],
                        "category": "target", "segment_id": calibration_segment["id"], "role": "target_calibration"})
                    self.assertEqual(201, calibration_unit_response.status_code, calibration_unit_response.text)
                    calibration_unit = calibration_unit_response.json()
                    frozen = client.post(manifest_url + "/freeze")
                    self.assertEqual(200, frozen.status_code, frozen.text)
                    self.assertEqual("frozen", frozen.json()["state"])
                    self.assertEqual(64, len(frozen.json()["checksum"]))
                    snapshot = client.get(manifest_url + "/snapshot")
                    self.assertEqual(200, snapshot.status_code)
                    self.assertEqual(frozen.json()["checksum"], snapshot.json()["checksum"])
                    self.assertEqual({"source_train", "target_test", "target_calibration"}, {unit["role"] for unit in snapshot.json()["units"]})
                    self.assertEqual(409, client.post(manifest_url + "/participants", json={"participant_id": other["id"], "category": "target"}).status_code)
                    subset = client.post("/v1/calibration-subsets", json={"manifest_id": manifest.json()["id"],
                        "participant_id": other["id"], "selection_version": "test-v1", "budget_per_gesture": 1})
                    self.assertEqual(201, subset.status_code, subset.text)
                    subset_url = "/v1/calibration-subsets/" + subset.json()["id"]
                    item = client.post(subset_url + "/items", json={"unit_id": calibration_unit["id"]})
                    self.assertEqual(201, item.status_code, item.text)
                    self.assertEqual(200, client.post(subset_url + "/freeze").status_code)
                    result = client.get(subset_url).json()
                    self.assertEqual("frozen", result["state"])
                    self.assertAlmostEqual(0.002, float(result["durations"][0]["unique_seconds"]))
                finally:
                    if previous is None:
                        os.environ.pop("DATA_ARTIFACT_ROOT", None)
                    else:
                        os.environ["DATA_ARTIFACT_ROOT"] = previous
            self.assertIn("/v1/participants", client.get("/openapi.json").json()["paths"])


if __name__ == "__main__":
    unittest.main()
