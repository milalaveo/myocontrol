import unittest

import numpy as np

from recognition.inference import recognition_features, replay


class RecognitionFeatureTests(unittest.TestCase):
    def test_feature_contract_and_incompatible_model(self):
        result = recognition_features([[1] * 4, [-1] * 4, [1] * 4])
        self.assertEqual(20, len(result))
        np.testing.assert_allclose(result[:5], [1, 1, 4, 2, 1])
        with self.assertRaises(ValueError):
            replay({"family": "lda", "feature_config": {"version": "unknown"}}, {"sample_rate_hz": 1000, "samples": []})

    def test_binary_replay_and_input_validation(self):
        config = {"version": "time-domain-4ch-v1", "order": "channel-major", "channels": 4,
                  "features": ["mav", "rms", "waveform_length", "zero_crossings", "slope_sign_changes"],
                  "window_ms": 200, "step_ms": 100, "zc_threshold": 0, "ssc_threshold": 0,
                  "filter": "none", "sample_rate_hz": 1000}
        model = {"family": "lda", "feature_config": config, "classes": ["fist", "rest"],
                 "coefficients": [[0.0] * 20], "intercepts": [1.0]}
        signal = {"sample_rate_hz": 1000, "samples": [[1, 2, 3, 4]] * 400}
        result = replay(model, signal)
        self.assertEqual(3, result["prediction_count"])
        self.assertTrue(all(item["command"] == "neutral" for item in result["predictions"]))
        with self.assertRaises(ValueError):
            replay(model, {**signal, "sample_rate_hz": 500})
        with self.assertRaises(ValueError):
            recognition_features([[float("nan")] * 4] * 3)


if __name__ == "__main__":
    unittest.main()
