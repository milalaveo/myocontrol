import hashlib
import unittest
from unittest.mock import Mock, patch

import redis

from recognition.model_cache import CACHE_SECONDS, cache_model, read_cached_model


class ModelCacheTests(unittest.TestCase):
    def test_verified_cache_hit_and_corruption(self):
        payload = b'{"family":"lda"}'
        digest = hashlib.sha256(payload).hexdigest()
        client = Mock()
        client.get.return_value = digest.encode() + b"\n" + payload
        with patch("recognition.model_cache.cache_client", return_value=client):
            self.assertEqual((payload, digest), read_cached_model("model-1"))
            cache_model("model-1", payload, digest)
            self.assertEqual(CACHE_SECONDS, client.set.call_args.kwargs["ex"])
            client.get.return_value = digest.encode() + b"\nmodified"
            self.assertIsNone(read_cached_model("model-1"))
            client.get.side_effect = redis.ConnectionError("offline")
            self.assertIsNone(read_cached_model("model-1"))


if __name__ == "__main__":
    unittest.main()
