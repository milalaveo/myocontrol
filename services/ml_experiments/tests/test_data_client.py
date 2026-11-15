import hashlib
import json
import os
import unittest
import uuid
from unittest.mock import patch

import httpx

from ml_experiments.data_client import DataServiceError, research_inputs, source_signal


class DataClientTests(unittest.TestCase):
    def setUp(self):
        self.manifest = str(uuid.uuid4())
        self.target = str(uuid.uuid4())
        self.source = str(uuid.uuid4())
        self.recording = str(uuid.uuid4())
        self.signal = {"participant_id": self.source, "sample_rate_hz": 1000.0, "samples": [[1.0, 2.0, 3.0, 4.0]]}
        payload = {"format": "four-channel-v1", "sample_rate_hz": self.signal["sample_rate_hz"], "samples": self.signal["samples"]}
        self.digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        self.snapshot = {"id": self.manifest, "state": "frozen", "units": [{"role": "source_train", "participant_id": self.source,
            "recording_id": self.recording, "artifact_sha256": self.digest, "sample_rate_hz": 1000, "sample_count": 1},
            {"role": "target_calibration", "participant_id": self.target, "recording_id": str(uuid.uuid4())}]}
        self.requests = []

    def make_client(self):
        real_client = httpx.Client

        def handler(request):
            self.requests.append(request.url.path)
            if request.url.path.endswith("/snapshot"):
                return httpx.Response(200, json=self.snapshot)
            if request.url.path.endswith("/signal"):
                return httpx.Response(200, json=self.signal)
            return httpx.Response(404)

        return lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs)

    def test_verified_inputs_exclude_calibration_and_detect_corruption(self):
        with patch.dict(os.environ, {"DATA_SERVICE_URL": "http://data"}), patch("ml_experiments.data_client.httpx.Client", side_effect=self.make_client()):
            snapshot, signals = research_inputs(self.manifest, self.target, "trace")
            self.assertEqual(self.snapshot, snapshot)
            self.assertEqual([self.recording], list(signals))
            self.assertEqual(2, len(self.requests))
            self.signal["samples"][0][0] = 9
            with self.assertRaises(DataServiceError):
                research_inputs(self.manifest, self.target, "trace")

    def test_missing_service_and_invalid_split(self):
        with patch.dict(os.environ, {"DATA_SERVICE_URL": ""}):
            with self.assertRaises(DataServiceError):
                source_signal(uuid.uuid4(), "trace")
        with patch.dict(os.environ, {"DATA_SERVICE_URL": "http://data"}), patch("ml_experiments.data_client.httpx.Client", side_effect=self.make_client()):
            self.snapshot["state"] = "draft"
            with self.assertRaises(DataServiceError):
                research_inputs(self.manifest, self.target, "trace")


if __name__ == "__main__":
    unittest.main()
