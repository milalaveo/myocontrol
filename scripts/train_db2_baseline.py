"""Fit an exploratory, within-subject DB2 LDA and export an Electron replay package."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
import zipfile

import numpy as np
import scipy
from scipy.io import loadmat
from scipy.signal import resample_poly
import sklearn
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    confusion_matrix,
    f1_score,
)

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services/ml_experiments"))
sys.path.insert(0, str(ROOT / "local-runtime"))
from ml_experiments.features import FEATURE_NAMES, FEATURE_VERSION, segment_windows
from myocontrol_runtime.recognition.classifier import Classifier
from myocontrol_runtime.signals import read_signal

MEMBER = "DB2_s1/S1_E1_A1.mat"
CHANNELS = [0, 2, 4, 6]
GESTURES = {
    0: "rest",
    5: "finger_spread",
    6: "fist",
    13: "wrist_flexion",
    14: "wrist_extension",
}
TRAIN_REPS = {1, 2, 3, 4}
TEST_REPS = {5, 6}
RATE = 1000
SEED = 7


def save_json(path, body):
    path.write_text(
        json.dumps(body, allow_nan=False, indent=2) + "\n", encoding="utf-8"
    )


def collect_intervals(emg, labels, repetitions):
    boundaries = np.r_[
        0,
        np.flatnonzero(
            (labels[1:] != labels[:-1]) | (repetitions[1:] != repetitions[:-1])
        )
        + 1,
        len(labels),
    ]
    intervals = []
    for index, (start, end) in enumerate(zip(boundaries[:-1], boundaries[1:])):
        label, repetition = int(labels[start]), int(repetitions[start])
        if label not in GESTURES or repetition not in TRAIN_REPS | TEST_REPS:
            continue
        if label == 0:
            if index + 1 >= len(boundaries) - 1:
                continue
            next_start = boundaries[index + 1]
            if (
                int(labels[next_start]) not in set(GESTURES) - {0}
                or int(repetitions[next_start]) != repetition
            ):
                continue
        # Trim transitions and resample each interval independently, before windowing.
        first, last = int(start) + 400, int(end) - 400
        if last - first < 400:
            continue
        samples = resample_poly(
            emg[first:last, CHANNELS].astype(np.float64), 1, 2, axis=0
        )
        intervals.append(
            {
                "gesture": GESTURES[label],
                "source_label": label,
                "repetition": repetition,
                "source_start": first,
                "source_end": last,
                "samples": samples,
            }
        )
    return intervals


def feature_rows(intervals, repetitions):
    rows, targets, membership = [], [], []
    for interval in intervals:
        if interval["repetition"] not in repetitions:
            continue
        samples = interval["samples"]
        features = segment_windows(samples, 0, len(samples), RATE)
        rows.extend(features)
        targets.extend([interval["gesture"]] * len(features))
        membership.append(
            {
                key: interval[key]
                for key in (
                    "gesture",
                    "source_label",
                    "repetition",
                    "source_start",
                    "source_end",
                )
            }
        )
        membership[-1]["window_count"] = len(features)
    return np.asarray(rows), np.asarray(targets), membership


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--archive", type=Path, default=ROOT / "data/raw/ninapro-db2/DB2_s1.zip"
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/artifacts/db2-s1-lda-baseline"
    )
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit(
            "Output already exists; select a new --output directory to preserve previous results"
        )
    started = time.perf_counter()
    with args.archive.open("rb") as stream:
        archive_sha = hashlib.file_digest(stream, "sha256").hexdigest()
    with zipfile.ZipFile(args.archive) as archive:
        with archive.open(MEMBER) as stream:
            member_sha = hashlib.file_digest(stream, "sha256").hexdigest()
        with archive.open(MEMBER) as stream:
            data = loadmat(
                stream,
                variable_names=[
                    "emg",
                    "restimulus",
                    "rerepetition",
                    "subject",
                    "exercise",
                ],
            )
    emg = data["emg"]
    labels, repetitions = data["restimulus"].ravel(), data["rerepetition"].ravel()
    if int(data["subject"].item()) != 1 or int(data["exercise"].item()) != 1:
        raise ValueError("Expected DB2 subject S1, exercise E1")
    if (
        emg.ndim != 2
        or emg.shape[1] != 12
        or len(labels) != len(emg)
        or len(repetitions) != len(emg)
        or not np.isfinite(emg).all()
    ):
        raise ValueError("Unexpected or non-finite DB2 data")
    intervals = collect_intervals(emg, labels, repetitions)
    train_x, train_y, train_membership = feature_rows(intervals, TRAIN_REPS)
    test_x, test_y, test_membership = feature_rows(intervals, TEST_REPS)
    classes = list(GESTURES.values())
    if set(train_y) != set(classes) or set(test_y) != set(classes):
        raise ValueError("All five classes must occur in both repetition splits")
    for training in train_membership:
        for test in test_membership:
            if max(training["source_start"], test["source_start"]) < min(
                training["source_end"], test["source_end"]
            ):
                raise ValueError("Training and test source intervals overlap")
    counts = {label: int(np.sum(train_y == label)) for label in classes}
    per_class = min(counts.values())
    rng = np.random.default_rng(SEED)
    selected = np.concatenate(
        [
            rng.choice(np.flatnonzero(train_y == label), per_class, replace=False)
            for label in classes
        ]
    )
    model = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
    model.fit(train_x[selected], train_y[selected])
    predicted = model.predict(test_x)
    feature_config = {
        "version": FEATURE_VERSION,
        "channels": 4,
        "channel_map": CHANNELS,
        "units": "unspecified",
        "order": "channel-major",
        "features": list(FEATURE_NAMES),
        "window_ms": 200,
        "step_ms": 100,
        "zc_threshold": 0,
        "ssc_threshold": 0,
        "filter": "none",
        "sample_rate_hz": RATE,
        "fit_roles": ["within_subject_train"],
    }
    provenance = {
        "dataset": "Ninapro DB2",
        "source_url": "https://ninapro.hevs.ch/instructions/DB2.html",
        "archive_sha256": archive_sha,
        "member": MEMBER,
        "member_sha256": member_sha,
        "subject": 1,
        "exercise": 1,
        "source_channels_one_based": [channel + 1 for channel in CHANNELS],
        "source_sample_rate_hz": 2000,
        "output_sample_rate_hz": RATE,
        "preprocessing": "Independent scipy.signal.resample_poly(up=1,down=2) per labelled interval after trimming 200 ms at each edge. No amplitude normalization or unit conversion.",
        "source_units": "unspecified; retained dataset-native amplitude",
        "labels": GESTURES,
        "label_field": "restimulus",
        "repetition_field": "rerepetition",
        "split": "within_subject_repetition_holdout",
        "train_repetitions": sorted(TRAIN_REPS),
        "test_repetitions": sorted(TEST_REPS),
        "seed": SEED,
        "usage": "Exploratory offline replay; not a cross-user result or a validated BITalino model",
    }
    body = {
        "family": "lda",
        "solver": "lsqr",
        "shrinkage": "auto",
        "classes": model.classes_.tolist(),
        "coefficients": model.coef_.tolist(),
        "intercepts": model.intercept_.tolist(),
        "feature_config": feature_config,
        "sklearn_version": sklearn.__version__,
        "training": provenance,
    }
    args.output.mkdir(parents=True)
    model_path = args.output / "model.json"
    save_json(model_path, body)
    imported = Classifier(model_path)
    runtime_predictions = []
    for interval in intervals:
        if interval["repetition"] in TEST_REPS:
            imported.prepare(
                {
                    "sample_rate_hz": RATE,
                    "channel_map": CHANNELS,
                    "units": "unspecified",
                    "source_kind": "dataset",
                }
            )
            runtime_predictions.extend(
                item["gesture"] for item in imported.feed(interval["samples"].tolist())
            )
    if runtime_predictions != predicted.tolist():
        raise ValueError(
            "Electron runtime predictions differ from the trained classifier"
        )
    matrix = confusion_matrix(test_y, predicted, labels=classes)
    rest = test_y == "rest"
    metrics = {
        "accuracy": float(accuracy_score(test_y, predicted)),
        "balanced_accuracy": float(balanced_accuracy_score(test_y, predicted)),
        "macro_f1": float(
            f1_score(
                test_y, predicted, labels=classes, average="macro", zero_division=0
            )
        ),
        "rest_false_activation_rate": float(np.mean(predicted[rest] != "rest")),
        "class_order": classes,
        "confusion_matrix": matrix.tolist(),
        "train_windows_before_balancing": counts,
        "train_windows_per_class_used": per_class,
        "training_windows": len(selected),
        "test_windows": len(test_y),
        "test_support": {label: int(np.sum(test_y == label)) for label in classes},
        "recall_per_class": {
            label: float(matrix[index, index] / matrix[index].sum())
            for index, label in enumerate(classes)
        },
    }
    replay_samples, annotations = [], []
    for interval in intervals:
        if interval["repetition"] != 5:
            continue
        start = len(replay_samples)
        replay_samples.extend(interval["samples"].tolist())
        annotations.append(
            {
                "start_sample": start,
                "end_sample": len(replay_samples),
                "gesture": interval["gesture"],
                "original_start_sample": interval["source_start"],
                "original_end_sample": interval["source_end"],
            }
        )
    replay_path = args.output / "test-replay.json"
    replay = {
        "format": "myocontrol-signal-v1",
        "sample_rate_hz": RATE,
        "channel_map": CHANNELS,
        "source_kind": "dataset",
        "source_name": "Ninapro DB2 held-out replay montage",
        "source_version": "S1-E1-repetition-5",
        "units": "unspecified",
        "samples": replay_samples,
        "annotations": annotations,
        "note": "Concatenated held-out intervals with cuts; boundary-crossing replay windows are excluded from reported test metrics.",
    }
    replay_path.write_text(
        json.dumps(replay, allow_nan=False, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    metadata, replay_data = read_signal(replay_path)
    imported.prepare(metadata)
    preview_predictions = imported.feed(replay_data)
    if not preview_predictions:
        raise ValueError("Replay produced no predictions")
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provenance": provenance,
        "metrics": metrics,
        "train_intervals": train_membership,
        "test_intervals": test_membership,
        "model_sha256": hashlib.sha256(model_path.read_bytes()).hexdigest(),
        "replay_sha256": hashlib.sha256(replay_path.read_bytes()).hexdigest(),
        "runtime_parity_verified": True,
        "replay_seconds": len(replay_samples) / RATE,
        "software": {
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "sklearn": sklearn.__version__,
        },
        "elapsed_seconds": time.perf_counter() - started,
    }
    save_json(args.output / "report.json", report)
    (args.output / "README.md").write_text(
        "# Ninapro DB2 S1 exploratory LDA\n\n"
        "Import model.json using Acquisition > Import model in Electron. Import test-replay.json under Recordings, then Replay.\n\n"
        "Five classes: rest, finger spread, fist, wrist flexion, wrist extension. Four DB2 ring electrodes (1,3,5,7), resampled from 2000 to 1000 Hz.\n\n"
        "Training: subject S1/E1 repetitions 1-4; held-out test: repetitions 5-6. Labels/repetitions are refined restimulus/rerepetition. Windows stay within trimmed intervals. Training classes are balanced using a fixed seed; test windows are not balanced. Rest intervals are restricted to those immediately preceding selected gestures.\n\n"
        "The replay concatenates repetition-5 intervals and contains cuts. Boundary-crossing montage windows are not included in the report metrics.\n\n"
        "This is a within-subject development baseline. It does not establish cross-user recognition, scientific final-test performance, calibration effectiveness or BITalino compatibility. Dataset-native amplitude units remain unspecified. Model and data contracts intentionally differ from raw BITalino ADC counts.\n\n"
        "Exact source intervals, digests, software versions and metrics are in report.json. Source data and derived outputs remain outside version control.\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "output": str(args.output),
                "metrics": metrics,
                "runtime_parity_verified": True,
                "replay_seconds": report["replay_seconds"],
                "elapsed_seconds": report["elapsed_seconds"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
