import tempfile
import unittest
import os
import time
from pathlib import Path

from myoprosthesis.persistence.artifacts import LocalArtifactStore


class ArtifactStoreTests(unittest.TestCase):
    def test_deduplication_corruption_and_orphan_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LocalArtifactStore(Path(directory))
            first = store.put(b"synthetic")
            self.assertEqual(first, store.put(b"synthetic"))
            old = time.time() - 10
            os.utime(store.root / first.key, (old, old))
            self.assertEqual([], store.find_orphans({first.key}, 0))
            self.assertEqual([first.key], store.find_orphans(set(), 0))
            (store.staging / "interrupted").write_bytes(b"partial")
            os.utime(store.staging / "interrupted", (old, old))
            self.assertEqual(["staging/interrupted"], store.find_abandoned_staging(0))
            (store.root / first.key).write_bytes(b"changed")
            with self.assertRaises(ValueError):
                store.verify(first)
            with self.assertRaises(ValueError):
                store.put(b"synthetic")


if __name__ == "__main__":
    unittest.main()
