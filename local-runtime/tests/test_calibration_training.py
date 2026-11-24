import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from myocontrol_runtime.calibration.training import train_personal
from myocontrol_runtime.engine import Engine
from myocontrol_runtime.recognition.classifier import Classifier
from myocontrol_runtime.signals import canonical, signal_digest
from myocontrol_runtime.storage.store import Store

META = {"sample_rate_hz": 1000, "channel_map": [0, 1], "units": "ADC counts",
        "source_kind": "device", "source_name": "BITalino", "source_version": "test"}


class PersonalCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = Store(self.temporary.name)
        self.ids = []
        rng = np.random.default_rng(4)
        for gesture, amplitude in [("rest", [1.5, 1.5]), ("fist", [6, 8]), ("finger_spread", [3, 24])]:
            for repetition in range(10):
                signal = np.rint(512 + rng.normal(size=(4000, 2)) * amplitude).tolist()
                identifier = self.store.create(META, "p1", "calibration", gesture)
                self.store.append(identifier, 0, signal)
                self.store.finish(identifier, "completed", "test")
                self.ids.append(identifier)

    def test_training_holdout_runtime_and_persistent_selection(self):
        engine = Engine(self.temporary.name, lambda *_: None)
        self.addCleanup(engine.close)
        result = engine.train_personal_model(self.ids)
        assessment = result["assessment"]
        self.assertEqual(assessment["train_repetitions"], {"rest": 8, "fist": 8, "finger_spread": 8})
        self.assertEqual(assessment["test_repetitions"], {"rest": 2, "fist": 2, "finger_spread": 2})
        self.assertGreater(assessment["balanced_accuracy"], .95)
        loaded = engine.model_selection.restore()
        self.assertEqual(loaded.summary(), engine.classifier.summary())
        loaded.prepare(META)
        path = next((self.store.directory / "models").glob("*-report.json"))
        report = json.loads(path.read_text(encoding="utf-8"))
        train_ids = {row["id"] for row in report["recordings"]["train"]}
        test_ids = {row["id"] for row in report["recordings"]["test"]}
        self.assertFalse(train_ids & test_ids)
        self.assertEqual(len(train_ids), 24)
        confusion = np.zeros((3, 3), dtype=int)
        classes = assessment["class_order"]
        for row in report["recordings"]["test"]:
            loaded.prepare(META)
            samples = [sample for chunk in self.store.chunks(row["id"]) for sample in chunk][1000:-1000]
            for prediction in loaded.feed(samples):
                confusion[classes.index(row["gesture"]), classes.index(prediction["gesture"])] += 1
        self.assertEqual(confusion.tolist(), assessment["confusion_matrix"])
        engine.clear_model()
        self.assertIsNone(engine.model_selection.restore())

    def test_test_samples_do_not_change_fitted_weights(self):
        path, _ = train_personal(self.store, self.ids)
        original = json.loads(path.read_text(encoding="utf-8"))
        held_out = original["training"]["recordings"]["test"][0]["id"]
        samples = np.random.default_rng(42).integers(400, 620, (4000, 2)).tolist()
        with self.store.connect() as connection:
            connection.execute("UPDATE chunks SET samples=? WHERE recording_id=?", (canonical(samples), held_out))
            connection.execute("UPDATE recordings SET sha256=? WHERE id=?", (signal_digest(META, [samples]), held_out))
        changed_path, _ = train_personal(self.store, self.ids)
        changed = json.loads(changed_path.read_text(encoding="utf-8"))
        self.assertEqual(original["coefficients"], changed["coefficients"])
        self.assertEqual(original["intercepts"], changed["intercepts"])

    def test_rejected_selection_keeps_previous_model_and_cannot_train_while_busy(self):
        engine = Engine(self.temporary.name, lambda *_: None)
        self.addCleanup(engine.close)
        engine.train_personal_model(self.ids)
        previous = engine.classifier.summary()
        with self.assertRaises(ValueError):
            engine.train_personal_model(self.ids[:-1] + [self.ids[0]])
        with self.store.connect() as connection:
            connection.execute("UPDATE recordings SET purpose='research' WHERE id=?", (self.ids[0],))
        with self.assertRaisesRegex(ValueError, "calibration repetitions"):
            engine.train_personal_model(self.ids)
        self.assertEqual(engine.classifier.summary(), previous)
        self.assertEqual(engine.model_selection.restore().summary(), previous)
        class Busy:
            def is_alive(self):
                return True
        engine.thread = Busy()
        with self.assertRaisesRegex(ValueError, "Stop the current session"):
            engine.train_personal_model(self.ids)
        engine.thread = None
