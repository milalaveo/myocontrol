import unittest

import numpy as np

from ml_experiments.features import extract_features, segment_windows
from ml_experiments.training import train_source_lda


class FeatureAndTrainingTests(unittest.TestCase):
    def test_feature_order_and_values(self):
        window = [[1, 1, 1, 1], [-1, -1, -1, -1], [1, 1, 1, 1]]
        features = extract_features(window)
        self.assertEqual(20, len(features))
        np.testing.assert_allclose(features[:5], [1, 1, 4, 2, 1])
        self.assertEqual([], segment_windows([[0] * 4] * 10, 0, 10, 1000))

    def test_training_uses_only_source_and_fixed_target(self):
        def signal(base):
            return {"samples": [[base + (i % 7) * 0.01 + channel * 0.02 for channel in range(4)] for i in range(400)]}

        signals = {"source-rest": signal(1), "source-fist": signal(10), "target-rest": signal(1.1), "target-fist": signal(10.1)}
        units = []
        for recording, role, participant, gesture in (
            ("source-rest", "source_train", "source", "rest"),
            ("source-fist", "source_train", "source", "fist"),
            ("target-rest", "target_test", "target", "rest"),
            ("target-fist", "target_test", "target", "fist"),
        ):
            units.append({"recording_id": recording, "role": role, "participant_id": participant,
                          "gesture_code": gesture, "start_sample": 0, "end_sample": 400, "sample_rate_hz": 1000})
        snapshot = {"gesture_codes": ["rest", "fist"], "units": units}
        result = train_source_lda(snapshot, signals, "target")
        self.assertEqual(1.0, result["metrics"]["accuracy"])
        self.assertEqual(6, result["metrics"]["training_windows"])
        self.assertEqual(6, result["metrics"]["test_windows"])
        altered = dict(signals)
        altered["target-rest"] = signal(50)
        changed = train_source_lda(snapshot, altered, "target")
        self.assertEqual(result["model"]["coefficients"], changed["model"]["coefficients"])
        with self.assertRaises(ValueError):
            train_source_lda(snapshot, signals, "source")


if __name__ == "__main__":
    unittest.main()
