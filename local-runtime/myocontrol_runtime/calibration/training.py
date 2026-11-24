"""Personal, recording-disjoint LDA fitting using only local labelled data."""
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import uuid

import numpy as np

from ..processing.features import FEATURES, CENTERED_PREPROCESSING, extract_features
from ..recognition.classifier import Classifier
from ..signals import signal_digest

CLASSES = ["rest", "fist", "finger_spread"]
TRIM_SECONDS = 1
SHRINKAGE = 0.1


def fit_lda(features, labels):
    """Fit regularized pooled-covariance LDA; fold train-only scaling into weights."""
    center = features.mean(axis=0)
    scale = features.std(axis=0)
    scale[scale < 1e-12] = 1
    standardized = (features - center) / scale
    means = np.array([standardized[labels == code].mean(axis=0) for code in CLASSES])
    residuals = np.concatenate([
        standardized[labels == code] - means[index] for index, code in enumerate(CLASSES)
    ])
    covariance = residuals.T @ residuals / (len(features) - len(CLASSES))
    target = max(float(np.trace(covariance) / covariance.shape[0]), 1e-8)
    covariance = (1 - SHRINKAGE) * covariance + SHRINKAGE * target * np.eye(covariance.shape[0])
    scaled_weights = np.linalg.solve(covariance, means.T).T
    weights = scaled_weights / scale
    intercepts = -0.5 * np.sum(means * scaled_weights, axis=1) + math.log(1 / len(CLASSES))
    intercepts -= weights @ center
    return weights, intercepts


def atomic_json(path, body):
    descriptor, temporary = tempfile.mkstemp(prefix=".calibration-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(body, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def train_personal(store, recording_ids):
    if (
        not isinstance(recording_ids, list) or not 15 <= len(recording_ids) <= 60
        or any(not isinstance(identifier, str) for identifier in recording_ids)
        or len(set(recording_ids)) != len(recording_ids)
    ):
        raise ValueError("Select 5–20 distinct completed repetitions per gesture (15–60 recordings)")
    recordings = [store.get(identifier) for identifier in recording_ids]
    first = recordings[0]
    metadata = first["metadata"]
    channels = len(metadata["channel_map"])
    rate = metadata["sample_rate_hz"]
    if channels not in {2, 4} or rate != 1000 or metadata["units"] != "ADC counts":
        raise ValueError("Personal calibration requires 2 or 4 BITalino channels at 1000 Hz in ADC counts")
    by_class = {code: [] for code in CLASSES}
    hashes = set()
    for row in recordings:
        if (
            row["participant_key"] != first["participant_key"]
            or row["metadata"] != metadata
        ):
            raise ValueError("Use recordings from one participant with identical device/channel settings")
        if (
            row["purpose"] != "calibration" or row["gesture"] not in CLASSES
            or row["status"] != "completed" or metadata["source_kind"] != "device"
            or metadata["source_name"] != "BITalino"
        ):
            raise ValueError("Use completed BITalino calibration repetitions labelled rest, fist or finger_spread")
        if not 4 * rate <= row["sample_count"] <= 30 * rate:
            raise ValueError("Each repetition must be 4–30 seconds; the recommended duration is 6 seconds")
        if row["sha256"] in hashes:
            raise ValueError("Identical recordings cannot be reused as separate repetitions")
        hashes.add(row["sha256"])
        chunks = list(store.chunks(row["id"]))
        samples = np.asarray([sample for chunk in chunks for sample in chunk], dtype=float)
        if (
            samples.shape != (row["sample_count"], channels)
            or not np.isfinite(samples).all()
            or signal_digest(metadata, chunks) != row["sha256"]
        ):
            raise ValueError("A selected recording failed its sample/integrity checks")
        if np.any(samples < 0) or np.any(samples > 1023):
            raise ValueError("A selected recording has samples outside the ADC range")
        if np.any(np.mean((samples <= 0) | (samples >= 1023), axis=0) > 0.01):
            raise ValueError("A selected recording has more than 1% ADC clipping; recollect it")
        if np.any(samples.std(axis=0) < 1e-9):
            raise ValueError("A selected recording has a constant channel; check the sensor and recollect it")
        trim = int(TRIM_SECONDS * rate)
        window, step = round(rate * 0.2), round(rate * 0.1)
        # Windows never cross a recording or a trimmed label boundary.
        features = np.array([
            extract_features(samples[start:start + window], channels, CENTERED_PREPROCESSING)
            for start in range(trim, len(samples) - trim - window + 1, step)
        ])
        by_class[row["gesture"]].append((row, features))
    if any(not 5 <= len(rows) <= 20 for rows in by_class.values()):
        raise ValueError("Select at least 5 and at most 20 repetitions for EACH of rest, fist and finger_spread")
    splits = {"train": [], "test": []}
    for rows in by_class.values():
        rows.sort(key=lambda item: (item[0]["created_at"], item[0]["id"]))
        test_count = max(1, math.ceil(len(rows) * 0.2))
        splits["train"].extend(rows[:-test_count])
        splits["test"].extend(rows[-test_count:])

    def matrix(role):
        rows = splits[role]
        return np.concatenate([features for _, features in rows]), np.concatenate([
            np.repeat(row["gesture"], len(features)) for row, features in rows
        ])

    train_x, train_y = matrix("train")
    test_x, test_y = matrix("test")
    # Equal window counts per class; deterministic sampling uses TRAIN data only.
    count = min(int(np.sum(train_y == code)) for code in CLASSES)
    rng = np.random.default_rng(7)
    chosen = np.concatenate([
        rng.choice(np.flatnonzero(train_y == code), count, replace=False) for code in CLASSES
    ])
    weights, intercepts = fit_lda(train_x[chosen], train_y[chosen])
    predicted = np.argmax(test_x @ weights.T + intercepts, axis=1)
    truth = np.array([CLASSES.index(code) for code in test_y])
    confusion = np.zeros((3, 3), dtype=int)
    np.add.at(confusion, (truth, predicted), 1)
    recall = np.diag(confusion) / confusion.sum(axis=1)
    assessment = {
        "participant_key": first["participant_key"],
        "class_order": CLASSES, "confusion_matrix": confusion.tolist(),
        "accuracy": float(np.mean(truth == predicted)),
        "balanced_accuracy": float(recall.mean()),
        "rest_false_activation_rate": float(1 - recall[0]),
        "train_repetitions": {code: sum(row["gesture"] == code for row, _ in splits["train"]) for code in CLASSES},
        "test_repetitions": {code: sum(row["gesture"] == code for row, _ in splits["test"]) for code in CLASSES},
        "test_windows": len(test_y), "training_windows_per_class": count,
        "scope": "Held-out whole repetitions from this selection; not an independent session or clinical validation",
    }
    model_id = str(uuid.uuid4())
    training = {
        "kind": "personal-calibration-v1", "model_id": model_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "assessment": assessment, "trim_seconds_each_edge": TRIM_SECONDS,
        "label_source": "Operator-labelled whole repetitions, excluding trimmed edges",
        "shrinkage": SHRINKAGE, "scaling": "Train-only feature standardization folded into exported coefficients",
        "split": "Latest ceil(20%) whole recordings per class held out; no refit on test recordings",
        "seed": 7, "numpy_version": np.__version__,
        "recordings": {role: [
            {"id": row["id"], "sha256": row["sha256"], "gesture": row["gesture"], "windows": len(features)}
            for row, features in rows
        ] for role, rows in splits.items()},
        "limitations": ["Labels are operator supplied", "Placement/contact changes may invalidate performance", "No unknown-gesture rejection or confidence calibration"],
    }
    model = {
        "family": "lda", "classes": CLASSES,
        "coefficients": weights.tolist(), "intercepts": intercepts.tolist(),
        "feature_config": {
            "version": f"time-domain-{channels}ch-dc-v1", "channels": channels,
            "channel_map": metadata["channel_map"], "units": metadata["units"],
            "sample_rate_hz": rate, "preprocessing": CENTERED_PREPROCESSING,
            "order": "channel-major", "features": FEATURES, "window_ms": 200, "step_ms": 100,
            "zc_threshold": 0, "ssc_threshold": 0, "filter": "none",
        },
        "training": training,
    }
    Classifier.from_bytes(json.dumps(model, allow_nan=False).encode("utf-8"), "personal.json")
    directory = store.directory / "models"
    directory.mkdir(exist_ok=True)
    path = directory / f"personal-{model_id}.json"
    atomic_json(path, model)
    atomic_json(directory / f"personal-{model_id}-report.json", {
        **training, "model_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    })
    return path, assessment
