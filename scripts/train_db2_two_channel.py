"""Train an explicitly experimental, normalized two-channel Ninapro DB2 LDA.

No BITalino recordings are used to fit or select this model. Requires the
training dependencies in requirements-training.txt; does not install anything.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile

import numpy as np
import scipy
from scipy.io import loadmat
from scipy.signal import resample_poly
import sklearn
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import accuracy_score, balanced_accuracy_score, confusion_matrix, f1_score

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "local-runtime"))
from myocontrol_runtime.processing.features import (
    FEATURES, NORMALIZED_PREPROCESSING, NORMALIZATION_FLOOR, extract_features,
)
from myocontrol_runtime.recognition.classifier import Classifier
from myocontrol_runtime.recognition.selection import ModelSelection

SOURCE_CHANNELS = [8, 9]  # DB2 flexor/extensor digitorum, zero based.
INPUT_SLOTS = [0, 1]  # Explicit experimental A1/A2 mapping, not DB2 channel IDs.
GESTURES = {0: "rest", 5: "finger_spread", 6: "fist"}
RATE = 1000
TRAIN_REPETITIONS = {1, 2, 3, 4}
TEST_REPETITIONS = {5, 6}


def save(path, body):
    path.write_text(json.dumps(body, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def collect_intervals(emg, labels, repetitions):
    boundaries = np.r_[0, np.flatnonzero((labels[1:] != labels[:-1]) | (repetitions[1:] != repetitions[:-1])) + 1, len(labels)]
    result = []
    for index, (start, end) in enumerate(zip(boundaries[:-1], boundaries[1:])):
        label, repetition = int(labels[start]), int(repetitions[start])
        if label not in GESTURES or repetition not in TRAIN_REPETITIONS | TEST_REPETITIONS:
            continue
        # Keep rest segments immediately preceding one selected movement only.
        if label == 0:
            if index + 1 >= len(boundaries) - 1:
                continue
            following = boundaries[index + 1]
            if int(labels[following]) not in set(GESTURES) - {0} or int(repetitions[following]) != repetition:
                continue
        first, last = int(start) + 400, int(end) - 400
        if last - first < 400:
            continue
        samples = resample_poly(emg[first:last, SOURCE_CHANNELS].astype(np.float64), 1, 2, axis=0)
        result.append({"gesture": GESTURES[label], "label": label, "repetition": repetition,
                       "source_start": first, "source_end": last, "samples": samples})
    return result


def windows(samples):
    return np.asarray([
        extract_features(samples[start:start + 200], channels=2, preprocessing=NORMALIZED_PREPROCESSING)
        for start in range(0, len(samples) - 199, 100)
    ])


def feature_rows(intervals, repetitions):
    rows, labels, membership = [], [], []
    for interval in intervals:
        if interval["repetition"] not in repetitions:
            continue
        features = windows(interval["samples"])
        rows.extend(features)
        labels.extend([interval["gesture"]] * len(features))
        membership.append({**{key: interval[key] for key in ("gesture", "label", "repetition", "source_start", "source_end")}, "windows": len(features)})
    return np.asarray(rows), np.asarray(labels), membership


def train(mat, output):
    if output.exists():
        raise ValueError("Output exists; choose a fresh directory to preserve previous artifacts")
    with mat.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    body = loadmat(mat, variable_names=["emg", "restimulus", "rerepetition", "subject", "exercise"])
    if int(body["subject"].item()) != 1 or int(body["exercise"].item()) != 1:
        raise ValueError("This pilot expects Ninapro DB2 S1 E1")
    emg, labels, repetitions = body["emg"], body["restimulus"].ravel(), body["rerepetition"].ravel()
    if emg.ndim != 2 or emg.shape[1] != 12 or len(emg) != len(labels) or len(emg) != len(repetitions) or not np.isfinite(emg).all():
        raise ValueError("Invalid DB2 dimensions or samples")
    intervals = collect_intervals(emg, labels, repetitions)
    train_x, train_y, train_membership = feature_rows(intervals, TRAIN_REPETITIONS)
    test_x, test_y, test_membership = feature_rows(intervals, TEST_REPETITIONS)
    classes = sorted(GESTURES.values())
    if set(train_y) != set(classes) or set(test_y) != set(classes):
        raise ValueError("Every class must occur in both repetition splits")
    for left in train_membership:
        for right in test_membership:
            if max(left["source_start"], right["source_start"]) < min(left["source_end"], right["source_end"]):
                raise ValueError("Training and test source samples overlap")
    counts = {label: int(np.sum(train_y == label)) for label in classes}
    count = min(counts.values())
    rng = np.random.default_rng(7)
    selected = np.concatenate([rng.choice(np.flatnonzero(train_y == label), count, replace=False) for label in classes])
    fitted = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
    fitted.fit(train_x[selected], train_y[selected])
    predictions = fitted.predict(test_x)
    provenance = {
        "dataset": "Ninapro DB2", "source_url": "https://ninapro.hevs.ch/instructions/DB2.html",
        "member": "DB2_s1/S1_E1_A1.mat", "member_sha256": digest,
        "subject": 1, "exercise": 1,
        "source_channel_map_zero_based": SOURCE_CHANNELS,
        "source_channel_description": ["DB2 channel 9: flexor digitorum", "DB2 channel 10: extensor digitorum"],
        "target_channel_map_zero_based": INPUT_SLOTS,
        "target_mapping": "A1 inside forearm, A2 outside, confirmed by operator; exact muscle sites and device transfer remain unvalidated",
        "source_units": "dataset-native Delsys amplitude; no relabelling to ADC counts",
        "source_sample_rate_hz": 2000, "output_sample_rate_hz": RATE,
        "resampling": "Independent resample_poly(up=1,down=2) per labelled segment, trimming 200 ms at both edges",
        "preprocessing": NORMALIZED_PREPROCESSING,
        "split": "within-subject repetition holdout; split before window extraction",
        "train_repetitions": sorted(TRAIN_REPETITIONS), "test_repetitions": sorted(TEST_REPETITIONS),
        "labels": GESTURES, "label_field": "restimulus", "repetition_field": "rerepetition", "seed": 7,
        "uses_target_recordings": False,
        "limitations": [
            "No BITalino accuracy evaluation, fitting or target-domain parameter selection",
            "Different subjects, electrode sites, hardware and frequency responses",
            "Common window normalization removes absolute energy, weakening rest-versus-active detection",
            "DB2 holdout is same-subject source-domain only; overlapping windows within a repetition are correlated",
            "No unknown gesture rejection, confidence calibration, debounce or safety claim",
        ],
    }
    config = {
        "version": "time-domain-2ch-dc-common-rms-v1", "channels": 2,
        "channel_map": INPUT_SLOTS, "units": "window-normalized",
        "input_units": ["ADC counts", "dataset-native"],
        "preprocessing": NORMALIZED_PREPROCESSING, "normalization_floor": NORMALIZATION_FLOOR,
        "order": "channel-major", "features": FEATURES,
        "window_ms": 200, "step_ms": 100, "zc_threshold": 0, "ssc_threshold": 0,
        "filter": "none", "sample_rate_hz": RATE,
    }
    model = {"family": "lda", "experimental": True, "solver": "lsqr", "shrinkage": "auto",
             "classes": fitted.classes_.tolist(), "coefficients": fitted.coef_.tolist(),
             "intercepts": fitted.intercept_.tolist(), "feature_config": config, "training": provenance}
    output.mkdir(parents=True)
    model_path = output / "two-channel-experimental-model.json"
    save(model_path, model)
    imported = Classifier(model_path)
    metadata = {"sample_rate_hz": RATE, "channel_map": INPUT_SLOTS, "units": "dataset-native", "source_kind": "dataset"}
    runtime_predictions = []
    for interval in intervals:
        if interval["repetition"] in TEST_REPETITIONS:
            imported.prepare(metadata)
            runtime_predictions.extend(item["gesture"] for item in imported.feed(interval["samples"].tolist()))
    if runtime_predictions != predictions.tolist():
        raise ValueError("Runtime and sklearn predictions differ")
    imported.prepare({**metadata, "units": "ADC counts", "source_kind": "device"})
    with tempfile.TemporaryDirectory() as temporary:
        selection = ModelSelection(temporary)
        selection.import_model(model_path)
        restored = selection.restore()
        if restored.summary() != imported.summary():
            raise ValueError("Persisted model differs")
        selection.clear()
        if selection.restore() is not None:
            raise ValueError("Clear model did not remove persistent selection")
    matrix = confusion_matrix(test_y, predictions, labels=classes)
    rest = test_y == "rest"
    metrics = {
        "scope": "Source-domain DB2 S1 repetitions 5/6 only; NOT BITalino accuracy",
        "accuracy": float(accuracy_score(test_y, predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(test_y, predictions)),
        "macro_f1": float(f1_score(test_y, predictions, labels=classes, average="macro", zero_division=0)),
        "rest_false_activation_rate": float(np.mean(predictions[rest] != "rest")),
        "class_order": classes, "confusion_matrix": matrix.tolist(),
        "training_windows_before_balancing": counts, "training_windows_per_class": count,
        "test_support": {label: int(np.sum(test_y == label)) for label in classes},
    }
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "provenance": provenance,
              "metrics": metrics, "train_intervals": train_membership, "test_intervals": test_membership,
              "runtime_parity_verified": True, "live_contract_verified": True,
              "persistent_import_restore_clear_verified": True,
              "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
              "software": {"numpy": np.__version__, "scipy": scipy.__version__, "sklearn": sklearn.__version__}}
    save(output / "two-channel-training-report.json", report)
    (output / "README.txt").write_text(
        "EXPERIMENTAL Ninapro DB2 two-channel model\n\n"
        "Import two-channel-experimental-model.json in Acquisition > Import model. Select A1/A2, 1000 Hz.\n"
        "A1 is inside forearm and A2 outside. Connect the reference electrode as before.\n"
        "Classes: rest, fist, finger_spread. Live recognition must show the experimental warning.\n"
        "Trained only on DB2 S1/E1 channel 9/10, repetitions 1-4; tested on DB2 repetitions 5-6.\n"
        "The same DC-removal/common-RMS extractor runs during training and live. Raw source units were not renamed.\n"
        "No BITalino recordings were used for fitting. Normalization removes absolute rest energy.\n"
        "Source holdout scores do not predict BITalino accuracy. This is an exploratory visual experiment.\n"
        "The full reproducible provenance, intervals, software versions and limitations are in the JSON report.\n",
        encoding="utf-8", newline="\n")
    print(json.dumps({"model": str(model_path), "model_sha256": report["model_sha256"], "metrics": metrics,
                      "runtime_parity_verified": True, "persistent_selection_verified": True}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mat", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    arguments = parser.parse_args()
    train(arguments.mat, arguments.output)
