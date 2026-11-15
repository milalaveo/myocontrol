"""Cross-service golden vectors without a shared feature implementation."""

import unittest

import numpy as np

from ml_experiments.features import extract_features
from recognition.inference import recognition_features


class FeatureContractTests(unittest.TestCase):
    def test_independent_feature_implementations_match(self):
        vectors = [
            [[0, 1, -1, 2], [1, -1, 1, 0], [-2, 2, 0, -2], [3, -3, 2, 1]],
            [[0, 0, 0, 0]] * 20,
            [[(i % 7) - 3, i * 0.01, (-1) ** i, 0] for i in range(200)],
        ]
        for window in vectors:
            np.testing.assert_allclose(extract_features(window), recognition_features(window), rtol=1e-12, atol=1e-12)


if __name__ == "__main__":
    unittest.main()
