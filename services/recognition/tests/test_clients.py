import hashlib
import json
import os
import unittest
import uuid
from unittest.mock import patch

import httpx

from recognition.clients import DependencyError, load_inputs


class ClientTests(unittest.TestCase):
    def test_checksums_and_dependency_failure(self):
        model = b'{"family":"lda"}'
        signal = {"participant_id": str(uuid.uuid4()), "sample_rate_hz": 1000.0, "samples": [[1.0, 2.0, 3.0, 4.0]]}
        payload = {"format": "four-channel-v1", "sample_rate_hz": signal["sample_rate_hz"], "samples": signal["samples"]}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        bad_checksum = [False]

        def handler(request):
            if request.url.path.endswith("/model"):
                checksum = "0" * 64 if bad_checksum[0] else hashlib.sha256(model).hexdigest()
                return httpx.Response(200, content=model, headers={"X-Artifact-SHA256": checksum})
            if request.url.path.endswith("/signal"):
                return httpx.Response(200, json=signal)
            return httpx.Response(200, json={"artifact_sha256": digest, "sample_count": 1})

        real_client = httpx.Client
        factory = lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs)
        with patch.dict(os.environ, {"ML_SERVICE_URL": "http://ml", "DATA_SERVICE_URL": "http://data", "REDIS_HOST": ""}), patch("recognition.clients.httpx.Client", side_effect=factory):
            loaded, checksum, received = load_inputs(uuid.uuid4(), uuid.uuid4(), "trace")
            self.assertEqual({"family": "lda"}, loaded)
            self.assertEqual(hashlib.sha256(model).hexdigest(), checksum)
            self.assertEqual(signal, received)
            bad_checksum[0] = True
            with self.assertRaises(DependencyError):
                load_inputs(uuid.uuid4(), uuid.uuid4(), "trace")


if __name__ == "__main__":
    unittest.main()
