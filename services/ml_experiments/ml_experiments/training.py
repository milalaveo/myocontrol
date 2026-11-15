"""Source-only LDA training and target-test evaluation."""

import numpy as np
import sklearn
from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

from .features import FEATURE_NAMES, FEATURE_VERSION, segment_windows


def train_source_lda(snapshot, signals, target_participant_id):
    classes = snapshot["gesture_codes"]
    if len(classes) < 2 or "rest" not in classes or len(set(classes)) != len(classes):
        raise ValueError("Protocol requires at least two distinct classes including rest")
    train_x, train_y, test_x, test_y = [], [], [], []
    selected_target = str(target_participant_id)
    source_participants = set()
    sample_rates = set()
    for unit in snapshot["units"]:
        if unit["role"] == "source_train":
            source_participants.add(str(unit["participant_id"]))
        if unit["role"] != "source_train" and not (unit["role"] == "target_test" and str(unit["participant_id"]) == selected_target):
            continue
        signal = signals[str(unit["recording_id"])]
        sample_rates.add(float(unit["sample_rate_hz"]))
        windows = segment_windows(signal["samples"], unit["start_sample"], unit["end_sample"], float(unit["sample_rate_hz"]))
        if not windows:
            raise ValueError("A selected segment is shorter than the feature window")
        x, y = (train_x, train_y) if unit["role"] == "source_train" else (test_x, test_y)
        x.extend(windows)
        y.extend([unit["gesture_code"]] * len(windows))
    if selected_target in source_participants:
        raise ValueError("Target participant cannot be used for source training")
    if len(sample_rates) != 1:
        raise ValueError("Selected recordings must use the same sample rate")
    if not test_x or set(train_y) != set(classes):
        raise ValueError("Source training must contain every protocol class and target test must not be empty")
    model = LinearDiscriminantAnalysis(solver="lsqr", shrinkage="auto")
    model.fit(np.asarray(train_x), train_y)
    predicted = model.predict(np.asarray(test_x))
    matrix = confusion_matrix(test_y, predicted, labels=classes).tolist()
    rest_total = sum(label == "rest" for label in test_y)
    false_rest = sum(actual == "rest" and guess != "rest" for actual, guess in zip(test_y, predicted))
    feature_config = {"version": FEATURE_VERSION, "channels": 4, "order": "channel-major", "features": list(FEATURE_NAMES),
                      "window_ms": 200, "step_ms": 100, "zc_threshold": 0, "ssc_threshold": 0,
                      "filter": "none", "sample_rate_hz": next(iter(sample_rates)), "fit_roles": ["source_train"]}
    return {
        "model": {"family": "lda", "solver": "lsqr", "shrinkage": "auto", "classes": model.classes_.tolist(),
                  "coefficients": model.coef_.tolist(), "intercepts": model.intercept_.tolist(),
                  "feature_config": feature_config, "sklearn_version": sklearn.__version__},
        "metrics": {"accuracy": float(accuracy_score(test_y, predicted)),
                    "macro_f1": float(f1_score(test_y, predicted, labels=classes, average="macro", zero_division=0)),
                    "rest_false_activation_rate": false_rest / rest_total if rest_total else None,
                    "rest_false_activation_missing_reason": None if rest_total else "No rest windows in target test",
                    "class_order": classes, "confusion_matrix": matrix,
                    "training_windows": len(train_y), "test_windows": len(test_y)},
    }
