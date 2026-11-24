from collections import deque
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from ..processing.features import FEATURES, extract_features


class Classifier:
    def __init__(self, path):
        path = Path(path)
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Model JSON must be smaller than 8 MiB")
        payload = path.read_bytes()
        body = json.loads(payload)
        config = body.get("feature_config", {})
        expected = {
            "version": "time-domain-4ch-v1",
            "channels": 4,
            "order": "channel-major",
            "features": FEATURES,
            "window_ms": 200,
            "step_ms": 100,
            "zc_threshold": 0,
            "ssc_threshold": 0,
            "filter": "none",
        }
        if body.get("family") != "lda" or any(
            config.get(key) != value for key, value in expected.items()
        ):
            raise ValueError(
                "Unsupported model feature contract; expected time-domain-4ch-v1 LDA"
            )
        self.classes = body.get("classes", [])
        self.coefficients = np.asarray(body.get("coefficients"), dtype=float)
        self.intercepts = np.asarray(body.get("intercepts"), dtype=float)
        rows = 1 if len(self.classes) == 2 else len(self.classes)
        if (
            len(self.classes) < 2
            or "rest" not in self.classes
            or len(set(self.classes)) != len(self.classes)
            or self.coefficients.shape != (rows, 20)
            or self.intercepts.shape != (rows,)
            or not np.isfinite(self.coefficients).all()
            or not np.isfinite(self.intercepts).all()
        ):
            raise ValueError("Incompatible classifier parameters")
        self.config = config
        rate = config.get("sample_rate_hz")
        if (
            type(rate) not in {int, float}
            or not np.isfinite(rate)
            or not 15 <= rate <= 100000
        ):
            raise ValueError(
                "Model sample rate must produce a window of at least three samples"
            )
        self.sha256 = hashlib.sha256(payload).hexdigest()
        self.name = path.name
        self.buffer = deque()
        self.position = 0

    def prepare(self, metadata):
        if len(metadata["channel_map"]) != 4 or metadata[
            "sample_rate_hz"
        ] != self.config.get("sample_rate_hz"):
            raise ValueError("Recording channels/sample rate do not match the model")
        if metadata["source_kind"] == "device" and (
            self.config.get("channel_map") != metadata["channel_map"]
            or self.config.get("units") != metadata["units"]
        ):
            raise ValueError(
                "Device inference requires a model with matching declared channel mapping and units"
            )
        self.size = round(metadata["sample_rate_hz"] * 0.2)
        self.step = round(metadata["sample_rate_hz"] * 0.1)
        self.buffer.clear()
        self.position = 0

    def feed(self, samples):
        self.buffer.extend(samples)
        predictions = []
        while len(self.buffer) >= self.size:
            window = [self.buffer[i] for i in range(self.size)]
            started = time.perf_counter_ns()
            scores = self.coefficients @ extract_features(window) + self.intercepts
            index = (
                int(scores[0] > 0) if len(self.classes) == 2 else int(np.argmax(scores))
            )
            gesture = self.classes[index]
            predictions.append(
                {
                    "start_sample": self.position,
                    "gesture": gesture,
                    "command": "neutral" if gesture == "rest" else gesture,
                    "processing_ms": (time.perf_counter_ns() - started) / 1_000_000,
                }
            )
            for _ in range(self.step):
                self.buffer.popleft()
            self.position += self.step
        return predictions

    def summary(self):
        return {
            "name": self.name,
            "sha256": self.sha256,
            "classes": self.classes,
            "feature_version": self.config["version"],
            "sample_rate_hz": self.config["sample_rate_hz"],
        }
