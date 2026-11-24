import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from myocontrol_runtime.acquisition.bitalino_source import BitalinoSource
from myocontrol_runtime.engine import Engine
from myocontrol_runtime.recognition.classifier import Classifier
from myocontrol_runtime.signals import read_signal, validate_samples
from myocontrol_runtime.storage.store import Store
from myocontrol_runtime.sync.client import CloudError, validate_url

ROOT = Path(__file__).resolve().parents[2]
META = {
    "sample_rate_hz": 1000.0,
    "channel_map": [0, 1, 2, 3],
    "source_kind": "synthetic",
    "source_name": "test",
    "source_version": "1",
    "units": "arbitrary",
}


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def recording(self, store, count=2400, metadata=None):
        identifier = store.create(metadata or META, "test-participant")
        width = len((metadata or META)["channel_map"])
        for start in range(0, count, 1000):
            store.append(
                identifier,
                start,
                [[float(i)] * width for i in range(start, min(start + 1000, count))],
            )
        return store.finish(identifier, "completed", "test")

    def test_export_import_preserves_actual_two_channel_width(self):
        store = Store(self.directory)
        row = self.recording(store, metadata={**META, "channel_map": [2, 5]})
        path = self.directory / "export.json"
        store.export(row["id"], path)
        metadata, samples = read_signal(path)
        self.assertEqual(metadata["channel_map"], [2, 5])
        self.assertEqual(len(samples), 2400)
        self.assertTrue(all(len(sample) == 2 for sample in samples))
        self.assertEqual(json.loads(path.read_text())["original_sha256"], row["sha256"])

    def test_store_rejects_discontinuity_and_recovers_interrupted_session(self):
        store = Store(self.directory)
        identifier = store.create(META, "participant")
        store.append(identifier, 0, [[1, 2, 3, 4]])
        with self.assertRaises(ValueError):
            store.append(identifier, 0, [[1, 2, 3, 4]])
        recovered = Store(self.directory).get(identifier)
        self.assertEqual(recovered["status"], "interrupted")
        self.assertEqual(recovered["sample_count"], 1)

    def test_outbox_chunks_exactly_and_keeps_ids_on_retry(self):
        store = Store(self.directory)
        row = self.recording(store, 10001)
        store.queue(row["id"], "operator-a")
        entries = sorted(store.outbox("operator-a"), key=lambda item: item["offset"])
        self.assertEqual(
            [len(store.upload_body(item)["samples"]) for item in entries], [10000, 1]
        )
        self.assertEqual(store.upload_body(entries[1])["original_start_sample"], 10000)
        self.assertEqual(store.upload_body(entries[1])["samples"], [[10000.0] * 4])
        store.queue(row["id"], "operator-a")
        self.assertEqual(len(store.outbox("operator-a")), 2)
        with self.assertRaises(ValueError):
            store.queue(row["id"], "operator-b")
        self.assertEqual(store.outbox("operator-b"), [])

    def test_invalid_samples_are_rejected(self):
        for samples in ([[float("nan")] * 4], [[True] * 4], [[1, 2]]):
            with self.assertRaises(ValueError):
                validate_samples(samples, 4)

    def test_import_defaults_to_four_channels(self):
        path = self.directory / "signal.json"
        path.write_text(json.dumps({"sample_rate_hz": 1000, "samples": [[1, 2, 3, 4]]}))
        self.assertEqual(read_signal(path)[0]["channel_map"], [0, 1, 2, 3])
        path.write_text(json.dumps({"sample_rate_hz": 1000, "samples": [[1, 2]]}))
        with self.assertRaises(ValueError):
            read_signal(path)

    def model(self):
        path = self.directory / "lda.json"
        config = {
            "version": "time-domain-4ch-v1",
            "channels": 4,
            "order": "channel-major",
            "features": [
                "mav",
                "rms",
                "waveform_length",
                "zero_crossings",
                "slope_sign_changes",
            ],
            "window_ms": 200,
            "step_ms": 100,
            "zc_threshold": 0,
            "ssc_threshold": 0,
            "filter": "none",
            "sample_rate_hz": 1000,
        }
        path.write_text(
            json.dumps(
                {
                    "family": "lda",
                    "classes": ["fist", "rest"],
                    "coefficients": [[0] * 20],
                    "intercepts": [1],
                    "feature_config": config,
                }
            )
        )
        return path

    def test_classifier_windowing_and_device_contract_gate(self):
        classifier = Classifier(self.model())
        classifier.prepare(META)
        self.assertEqual(classifier.feed([[0] * 4] * 199), [])
        self.assertEqual(classifier.feed([[0] * 4])[0]["command"], "neutral")
        self.assertEqual(classifier.feed([[0] * 4] * 100)[0]["start_sample"], 100)
        with self.assertRaisesRegex(ValueError, "mapping"):
            classifier.prepare({**META, "source_kind": "device"})
        with self.assertRaises(ValueError):
            classifier.prepare({**META, "channel_map": [0, 1]})

    def test_low_rate_model_rejected_without_zero_step_loop(self):
        path = self.model()
        body = json.loads(path.read_text())
        body["feature_config"]["sample_rate_hz"] = 1
        path.write_text(json.dumps(body))
        with self.assertRaises(ValueError):
            Classifier(path)

    def test_default_capture_is_four_channels_and_failure_closes_device(self):
        captured = {}

        class Source:
            def __init__(self, address, rate, channels):
                captured.update(address=address, rate=rate, channels=channels)
                self.channels = channels

            def open(self):
                raise OSError("device disconnected")

            def close(self):
                captured["closed"] = True

        engine = Engine(self.directory, lambda *_: None, source_factory=Source)
        try:
            engine.start_capture("COM5", "participant")
            engine.thread.join(2)
            self.assertEqual(captured["channels"], [0, 1, 2, 3])
            self.assertEqual(captured["rate"], 1000)
            self.assertTrue(captured["closed"])
            self.assertEqual(engine.status()["command"], "neutral")
            self.assertEqual(engine.recordings()["items"][0]["status"], "failed")
        finally:
            engine.close()

    def test_sdk_sequence_and_channel_order(self):
        class SDK:
            def __init__(self, address, timeout):
                self.started = False
                self.rows = [[15, 0, 0, 0, 0, 10, 20], [0, 0, 0, 0, 0, 11, 21]]

            def start(self, rate, channels):
                self.started = True

            def read(self, count):
                return self.rows

            def stop(self):
                self.started = False

            def close(self):
                pass

        source = BitalinoSource("COM5", 1000, [3, 1], SDK)
        source.open()
        self.assertEqual(source.channels, [1, 3])
        self.assertEqual(source.read(), [[10.0, 20.0], [11.0, 21.0]])
        with self.assertRaisesRegex(ValueError, "discontinuity"):
            source.read()
        source.close()

    def test_sync_retries_server_error_and_stops_on_conflict(self):
        engine = Engine(self.directory, lambda *_: None)
        try:
            engine.sync.close()
            row = self.recording(engine.store, 10)
            engine.store.queue(row["id"], "operator-a")
            engine.sync.configure(
                {
                    "base": "http://localhost:8000",
                    "token": "test",
                    "operator_id": "operator-a",
                    "expires_at": "2099-01-01T00:00:00Z",
                }
            )
            with patch(
                "myocontrol_runtime.sync.worker.CloudClient.call",
                side_effect=CloudError("unavailable", 503),
            ):
                engine.sync.once()
            entry = engine.store.outbox("operator-a")[0]
            self.assertEqual(entry["state"], "pending")
            self.assertGreater(entry["next_attempt"], time.time())
            engine.store.retry("operator-a")
            with patch(
                "myocontrol_runtime.sync.worker.CloudClient.call",
                side_effect=CloudError("conflict", 409),
            ):
                engine.sync.once()
            self.assertEqual(engine.store.outbox("operator-a")[0]["state"], "conflict")
            engine.store.retry("operator-a")
            self.assertEqual(engine.store.outbox("operator-a")[0]["state"], "conflict")
        finally:
            engine.close()

    def test_remote_cloud_requires_https(self):
        self.assertEqual(
            validate_url("http://localhost:8000/"), "http://localhost:8000"
        )
        for value in (
            "http://remote.example",
            "https://user:secret@example.com",
            "https://example.com/?token=x",
        ):
            with self.assertRaises(ValueError):
                validate_url(value)


if __name__ == "__main__":
    unittest.main()
