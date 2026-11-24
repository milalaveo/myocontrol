from collections import deque
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from ..processing.features import (
    FEATURES, CENTERED_PREPROCESSING, NORMALIZED_PREPROCESSING, NORMALIZATION_FLOOR, extract_features,
)


class Classifier:
    def __init__(self, path):
        path = Path(path)
        if path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Model JSON must be smaller than 8 MiB")
        self._load(path.read_bytes(), path.name)

    @classmethod
    def from_bytes(cls, payload, name):
        model = cls.__new__(cls)
        model._load(payload, name)
        return model

    def _load(self, payload, name):
        if len(payload) > 8 * 1024 * 1024:
            raise ValueError("Model JSON must be smaller than 8 MiB")
        body = json.loads(payload)
        config = body.get("feature_config", {})
        channels = config.get("channels")
        if type(channels) is not int or channels not in {2, 4}:
            raise ValueError("LDA models must declare 2 or 4 measured channels")
        preprocessing = config.get("preprocessing", "none")
        normalized = preprocessing == NORMALIZED_PREPROCESSING
        if preprocessing not in {"none", CENTERED_PREPROCESSING, NORMALIZED_PREPROCESSING}:
            raise ValueError("Unsupported model preprocessing")
        expected = {
            "version": (
                "time-domain-2ch-dc-common-rms-v1" if normalized
                else f"time-domain-{channels}ch-dc-v1" if preprocessing == CENTERED_PREPROCESSING
                else f"time-domain-{channels}ch-v1"
            ),
            "channels": channels,
            "order": "channel-major",
            "features": FEATURES,
            "window_ms": 200,
            "step_ms": 100,
            "zc_threshold": 0,
            "ssc_threshold": 0,
            "filter": "none",
        }
        if normalized and (
            channels != 2
            or body.get("experimental") is not True
            or config.get("normalization_floor") != NORMALIZATION_FLOOR
            or config.get("units") != "window-normalized"
            or config.get("input_units") != ["ADC counts", "dataset-native"]
        ):
            raise ValueError("Invalid experimental normalized model contract")
        self.experimental = body.get("experimental") is True
        if body.get("family") != "lda" or any(
            config.get(key) != value for key, value in expected.items()
        ):
            raise ValueError(
                "Unsupported model feature contract for declared channels/preprocessing"
            )
        mapping = config.get("channel_map")
        if mapping is not None and (
            not isinstance(mapping, list)
            or len(mapping) != channels
            or any(type(channel) is not int or channel not in range(6) for channel in mapping)
            or len(set(mapping)) != channels
        ):
            raise ValueError("Model channel mapping must declare unique BITalino inputs")
        self.classes = body.get("classes", [])
        self.coefficients = np.asarray(body.get("coefficients"), dtype=float)
        self.intercepts = np.asarray(body.get("intercepts"), dtype=float)
        rows = 1 if len(self.classes) == 2 else len(self.classes)
        if (
            len(self.classes) < 2
            or "rest" not in self.classes
            or len(set(self.classes)) != len(self.classes)
            or self.coefficients.shape != (rows, channels * len(FEATURES))
            or self.intercepts.shape != (rows,)
            or not np.isfinite(self.coefficients).all()
            or not np.isfinite(self.intercepts).all()
        ):
            raise ValueError(
                f"Incompatible classifier parameters; expected {channels * len(FEATURES)} features"
            )
        self.training = body.get("training", {})
        if not isinstance(self.training, dict):
            self.training = {}
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
        self.name = name
        self.buffer = deque()
        self.position = 0

    def prepare(self, metadata):
        if len(metadata["channel_map"]) != self.config["channels"] or metadata[
            "sample_rate_hz"
        ] != self.config.get("sample_rate_hz"):
            raise ValueError(
                f"Model requires {self.config['channels']} channels at "
                f"{self.config['sample_rate_hz']} Hz; recording has "
                f"{len(metadata['channel_map'])} channels at {metadata['sample_rate_hz']} Hz"
            )
        if self.config.get("channel_map") is not None and (
            self.config["channel_map"] != metadata["channel_map"]
        ):
            raise ValueError("Recording channel mapping/order does not match the model")
        normalized = self.config.get("preprocessing") == NORMALIZED_PREPROCESSING
        if normalized and metadata["units"] not in self.config["input_units"]:
            raise ValueError("Input units are not supported by the experimental normalized model")
        if metadata["source_kind"] == "device" and (
            self.config.get("channel_map") != metadata["channel_map"]
            or (
                metadata["units"] != "ADC counts" if normalized
                else self.config.get("units") != metadata["units"]
            )
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
            scores = self.coefficients @ extract_features(
                window,
                channels=self.config["channels"],
                preprocessing=self.config.get("preprocessing", "none"),
            ) + self.intercepts
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
            "channels": self.config["channels"],
            "experimental": self.experimental,
            "preprocessing": self.config.get("preprocessing", "none"),
            "sample_rate_hz": self.config["sample_rate_hz"],
            "calibration": (
                self.training.get("assessment")
                if self.training.get("kind") == "personal-calibration-v1" else None
            ),
        }
