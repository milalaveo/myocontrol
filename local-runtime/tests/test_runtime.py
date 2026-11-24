import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from myocontrol_runtime.acquisition.bitalino_source import BitalinoSource
from myocontrol_runtime.engine import Engine
from myocontrol_runtime.processing.features import extract_features, NORMALIZED_PREPROCESSING
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

    def model(self, channels=4):
        path = self.directory / "lda.json"
        config = {
            "version": f"time-domain-{channels}ch-v1",
            "channels": channels,
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
                    "coefficients": [[0] * (channels * 5)],
                    "intercepts": [1],
                    "feature_config": config,
                }
            )
        )
        return path

    def test_selected_model_survives_restart_without_original_file(self):
        path = self.model()
        engine = Engine(self.directory, lambda *_: None)
        try:
            selected = engine.load_model(path)
        finally:
            engine.close()
        path.unlink()
        restored = Engine(self.directory, lambda *_: None)
        try:
            self.assertEqual(restored.status()["model"], selected)
            self.assertIn("Saved model loaded", restored.status()["recognition"])
            restored.classifier.prepare(META)
            self.assertEqual(
                restored.classifier.feed([[0] * 4] * 200)[0]["command"], "neutral"
            )
        finally:
            restored.close()

    def test_clear_model_persists_across_restart(self):
        engine = Engine(self.directory, lambda *_: None)
        try:
            engine.load_model(self.model())
            engine.clear_model()
            self.assertIsNone(engine.status()["model"])
            self.assertFalse(engine.model_selection.path.exists())
        finally:
            engine.close()
        restored = Engine(self.directory, lambda *_: None)
        try:
            self.assertIsNone(restored.status()["model"])
        finally:
            restored.close()

    def test_invalid_import_keeps_previous_saved_and_active_model(self):
        engine = Engine(self.directory, lambda *_: None)
        try:
            selected = engine.load_model(self.model())
            invalid = self.directory / "invalid.json"
            invalid.write_text("{}", encoding="utf-8")
            with self.assertRaises(ValueError):
                engine.load_model(invalid)
            self.assertEqual(engine.status()["model"], selected)
            self.assertEqual(engine.model_selection.restore().summary(), selected)
        finally:
            engine.close()

    def test_failed_model_write_keeps_previous_selection(self):
        engine = Engine(self.directory, lambda *_: None)
        try:
            selected = engine.load_model(self.model())
            previous = engine.model_selection.path.read_bytes()
            with patch(
                "myocontrol_runtime.recognition.selection.os.replace",
                side_effect=OSError("disk unavailable"),
            ):
                with self.assertRaises(OSError):
                    engine.load_model(self.model())
            self.assertEqual(engine.status()["model"], selected)
            self.assertEqual(engine.model_selection.path.read_bytes(), previous)
            self.assertEqual(list(self.directory.glob(".model-*")), [])
        finally:
            engine.close()

    def test_corrupt_saved_model_does_not_block_startup_and_can_be_cleared(self):
        saved = self.directory / "selected-model.json"
        saved.write_text("broken JSON", encoding="utf-8")
        engine = Engine(self.directory, lambda *_: None)
        try:
            self.assertIsNone(engine.status()["model"])
            self.assertIn("could not be loaded", engine.status()["recognition"])
            engine.clear_model()
            self.assertFalse(saved.exists())
        finally:
            engine.close()

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

    def test_two_channel_features_preserve_channel_major_order(self):
        import numpy as np

        samples = [[1, 2], [-2, 2], [3, 2]]
        actual = extract_features(samples, channels=2)
        np.testing.assert_allclose(actual, [2, np.sqrt(14 / 3), 8, 2, 1, 2, 2, 0, 0, 0])
        four_channel = [row + [0, 0] for row in samples]
        np.testing.assert_array_equal(actual, extract_features(four_channel)[:10])
        with self.assertRaises(ValueError):
            extract_features(four_channel, channels=2)

    def test_two_channel_inference_mapping_and_saved_model(self):
        path = self.model(channels=2)
        body = json.loads(path.read_text(encoding="utf-8"))
        body["feature_config"].update(channel_map=[0, 1], units="adc_counts")
        body["coefficients"] = [[1] + [0] * 9]
        body["intercepts"] = [-1]
        path.write_text(json.dumps(body), encoding="utf-8")
        metadata = {**META, "channel_map": [0, 1], "source_kind": "device", "units": "adc_counts"}
        engine = Engine(self.directory, lambda *_: None)
        try:
            engine.load_model(path)
        finally:
            engine.close()
        path.unlink()
        restored = Engine(self.directory, lambda *_: None)
        try:
            model = restored.classifier
            self.assertEqual(model.summary()["channels"], 2)
            model.prepare(metadata)
            self.assertEqual(model.feed([[2, 0]] * 200)[0]["gesture"], "rest")
            model.prepare(metadata)
            self.assertEqual(model.feed([[0, 0]] * 200)[0]["gesture"], "fist")
            for mismatch in (
                {**metadata, "channel_map": [1, 0]},
                {**metadata, "channel_map": [2, 3]},
                {**metadata, "units": "mV"},
                {**metadata, "sample_rate_hz": 100},
                {**metadata, "channel_map": [0, 1, 2, 3]},
            ):
                with self.assertRaises(ValueError):
                    model.prepare(mismatch)
            restored.clear_model()
            self.assertIsNone(restored.model_selection.restore())
        finally:
            restored.close()

    def test_model_contract_does_not_allow_relabelling_four_as_two_channels(self):
        path = self.model()
        original = json.loads(path.read_text(encoding="utf-8"))
        original["feature_config"]["channels"] = 2
        path.write_text(json.dumps(original), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "feature contract"):
            Classifier(path)
        original["feature_config"]["version"] = "time-domain-2ch-v1"
        path.write_text(json.dumps(original), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "10 features"):
            Classifier(path)

    def test_invalid_model_channel_mapping_is_rejected(self):
        path = self.model(channels=2)
        body = json.loads(path.read_text(encoding="utf-8"))
        for mapping in ([0, 0], [0], [0, 6], [True, 1]):
            body["feature_config"]["channel_map"] = mapping
            path.write_text(json.dumps(body), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "channel mapping"):
                Classifier(path)

    def test_normalized_features_remove_dc_and_common_scale_not_channel_ratio(self):
        import numpy as np

        samples = np.array([[1, 2], [-2, -4], [3, 6], [-1, -2]], dtype=float)
        options = {"channels": 2, "preprocessing": NORMALIZED_PREPROCESSING}
        features = extract_features(samples, **options)
        shifted_scaled = extract_features(samples * 200 + [514, 508], **options)
        np.testing.assert_allclose(features, shifted_scaled, rtol=1e-12, atol=1e-12)
        self.assertAlmostEqual(features[6] / features[1], 2)
        np.testing.assert_array_equal(extract_features([[514, 508]] * 200, **options), [0] * 10)
        with self.assertRaises(ValueError):
            extract_features(samples, channels=2, preprocessing="unknown")

    def test_experimental_model_uses_declared_input_units_and_warning(self):
        path = self.model(channels=2)
        body = json.loads(path.read_text(encoding="utf-8"))
        body["experimental"] = True
        body["feature_config"].update(
            version="time-domain-2ch-dc-common-rms-v1",
            preprocessing=NORMALIZED_PREPROCESSING,
            normalization_floor=1e-12,
            channel_map=[0, 1],
            units="window-normalized",
            input_units=["ADC counts", "dataset-native"],
        )
        path.write_text(json.dumps(body), encoding="utf-8")
        engine = Engine(self.directory, lambda *_: None)
        metadata = {**META, "channel_map": [0, 1], "source_kind": "device", "units": "ADC counts"}
        try:
            engine.load_model(path)
            self.assertIn("unvalidated", engine.status()["recognition"])
            enabled, message = engine.prepare_recognition(metadata)
            self.assertTrue(enabled)
            self.assertIn("Experimental", message)
            self.assertTrue(engine.classifier.summary()["experimental"])
            self.assertEqual(engine.classifier.feed([[514, 508]] * 200)[0]["command"], "neutral")
            engine.classifier.prepare({**metadata, "source_kind": "dataset", "units": "dataset-native"})
            with self.assertRaises(ValueError):
                engine.classifier.prepare({**metadata, "units": "mV"})
            with self.assertRaises(ValueError):
                engine.classifier.prepare({**metadata, "units": "dataset-native"})
        finally:
            engine.close()
        restored = Engine(self.directory, lambda *_: None)
        try:
            self.assertIn("unvalidated", restored.status()["recognition"])
        finally:
            restored.close()
        body["experimental"] = False
        path.write_text(json.dumps(body), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "experimental"):
            Classifier(path)

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
