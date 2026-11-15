"""End-to-end HTTP check against two running synthetic services."""

import os
import subprocess
import time
import unittest
import uuid

import httpx


@unittest.skipUnless(os.getenv("DATA_SERVICE_URL") and os.getenv("ML_SERVICE_URL"), "Two running service URLs are required")
class SyntheticFlowTests(unittest.TestCase):
    @staticmethod
    def client():
        username, password = os.getenv("TEST_GATEWAY_USERNAME"), os.getenv("TEST_GATEWAY_PASSWORD")
        auth = (username, password) if username and password else None
        # CI runners may define HTTP(S)_PROXY; local Compose traffic must bypass it.
        return httpx.Client(timeout=45, auth=auth, trust_env=False)

    def test_recordings_split_and_computed_job(self):
        data_url = os.environ["DATA_SERVICE_URL"]
        ml_url = os.environ["ML_SERVICE_URL"]
        token = uuid.uuid4().hex
        with self.client() as client:
            participants = []
            for role in ("source", "target"):
                response = client.post(f"{data_url}/v1/participants", json={"pseudonym": f"{role}-{token}"})
                self.assertEqual(201, response.status_code, response.text)
                participants.append(response.json()["id"])
            recordings = []
            for participant, samples in zip(participants, ([[1, 2, 3, 4], [3, 4, 5, 6]], [[8, 9, 10, 11]])):
                response = client.post(f"{data_url}/v1/recordings", json={"participant_id": participant, "sample_rate_hz": 1000, "samples": samples})
                self.assertEqual(201, response.status_code, response.text)
                recordings.append(response.json()["id"])
            response = client.post(f"{data_url}/v1/synthetic-splits", json={"source_recording_id": recordings[0], "test_recording_id": recordings[1]})
            self.assertEqual(201, response.status_code, response.text)
            split = response.json()
            response = client.post(f"{ml_url}/v1/synthetic-signal-summary-jobs", json={"split_id": split["id"]})
            self.assertEqual(201, response.status_code, response.text)
            job = response.json()
            self.assertEqual("succeeded", job["status"])
            self.assertEqual(split["checksum"], job["split_checksum"])
            self.assertEqual([2, 3, 4, 5], job["result"]["channel_means"])
            self.assertEqual(job, client.get(f"{ml_url}/v1/synthetic-signal-summary-jobs/{job['id']}").json())

    def test_real_lda_training_and_target_evaluation(self):
        data_url = os.environ["DATA_SERVICE_URL"]
        ml_url = os.environ["ML_SERVICE_URL"]
        token = uuid.uuid4().hex

        def signal(base):
            return [[base + (i % 7) * 0.01 + channel * 0.02 for channel in range(4)] for i in range(400)]

        with self.client() as client:
            def post(url, payload):
                response = client.post(url, json=payload)
                self.assertEqual(201, response.status_code, response.text)
                return response.json()

            source = post(f"{data_url}/v1/participants", {"pseudonym": f"lda-src-{token}"})
            target = post(f"{data_url}/v1/participants", {"pseudonym": f"lda-tgt-{token}"})
            protocol = post(f"{data_url}/v1/protocols", {"name": f"lda-{token}", "version": 1, "gesture_codes": ["rest", "fist"]})
            manifest = post(f"{data_url}/v1/research-manifests", {"name": f"lda-{token}", "version": 1, "protocol_id": protocol["id"]})
            url = f"{data_url}/v1/research-manifests/{manifest['id']}"
            for person, category in ((source, "source"), (target, "target")):
                post(url + "/participants", {"participant_id": person["id"], "category": category})
            for person, category, gesture, base in ((source, "source", "rest", 1), (source, "source", "fist", 10),
                                                     (target, "target", "rest", 1.1), (target, "target", "fist", 10.1)):
                recording = post(f"{data_url}/v1/recordings", {"participant_id": person["id"], "sample_rate_hz": 1000, "samples": signal(base)})
                segment = post(f"{data_url}/v1/segments", {"recording_id": recording["id"], "gesture_code": gesture,
                               "repetition_key": "one", "start_sample": 0, "end_sample": 400})
                post(url + "/units", {"participant_id": person["id"], "category": category, "segment_id": segment["id"],
                                       "role": "source_train" if category == "source" else "target_test"})
            response = client.post(url + "/freeze")
            self.assertEqual(200, response.status_code, response.text)
            frozen = response.json()
            response = client.post(f"{ml_url}/v1/source-lda-experiments", json={"manifest_id": manifest["id"], "target_participant_id": target["id"]})
            self.assertEqual(202, response.status_code, response.text)
            run_id = response.json()["id"]
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                response = client.get(f"{ml_url}/v1/source-lda-experiments/{run_id}")
                self.assertEqual(200, response.status_code, response.text)
                run = response.json()
                if run["status"] not in ("queued", "running"):
                    break
                time.sleep(0.5)
            else:
                self.fail("LDA job did not complete")
            self.assertEqual("succeeded", run["status"], run.get("error"))
            self.assertEqual(frozen["checksum"], run["manifest_checksum"])
            self.assertEqual(1.0, run["metrics"]["accuracy"])
            self.assertEqual(6, run["metrics"]["training_windows"])
            self.assertEqual(6, run["metrics"]["test_windows"])
            self.assertEqual(run, client.get(f"{ml_url}/v1/source-lda-experiments/{run['id']}").json())
            if os.getenv("RECOGNITION_SERVICE_URL"):
                recognition_url = os.environ["RECOGNITION_SERVICE_URL"]
                replay = post(f"{recognition_url}/v1/replay-sessions", {"model_run_id": run["id"], "recording_id": recording["id"]})
                self.assertEqual("succeeded", replay["status"], replay.get("error"))
                self.assertEqual(run["model_checksum"], replay["model_checksum"])
                self.assertEqual(3, replay["result"]["prediction_count"])
                self.assertTrue(all(item["gesture"] == "fist" for item in replay["result"]["predictions"]))
                container = os.getenv("TEST_ML_CONTAINER")
                if container:
                    subprocess.run(["docker", "pause", container], check=True, capture_output=True, timeout=20)
                    try:
                        offline = post(f"{recognition_url}/v1/replay-sessions", {"model_run_id": run["id"], "recording_id": recording["id"]})
                        self.assertEqual("succeeded", offline["status"], offline.get("error"))
                        self.assertEqual(replay["model_checksum"], offline["model_checksum"])
                    finally:
                        subprocess.run(["docker", "unpause", container], check=True, capture_output=True, timeout=20)
                if os.getenv("EXPECT_MODEL_EVENT") == "1":
                    deadline = time.monotonic() + 20
                    while time.monotonic() < deadline:
                        event = client.get(f"{recognition_url}/v1/available-models/{run['id']}")
                        if event.status_code == 200:
                            break
                        self.assertEqual(404, event.status_code, event.text)
                        time.sleep(0.5)
                    else:
                        self.fail("Published model event was not received")
                    self.assertEqual(run["id"], event.json()["model_run_id"])


if __name__ == "__main__":
    unittest.main()
