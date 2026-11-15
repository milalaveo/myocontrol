"""Independent implementation of the versioned recognition feature contract."""

import time

import numpy as np


def recognition_features(window):
    values = np.asarray(window, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 4 or len(values) < 3 or not np.isfinite(values).all():
        raise ValueError("Invalid four-channel window")
    output = []
    for column in range(4):
        channel = values[:, column]
        differences = channel[1:] - channel[:-1]
        output.extend((np.mean(np.abs(channel)), np.sqrt(np.mean(channel ** 2)), np.sum(np.abs(differences)),
                       np.count_nonzero(channel[:-1] * channel[1:] < 0),
                       np.count_nonzero(differences[:-1] * differences[1:] < 0)))
    return np.asarray(output, dtype=np.float64)


def replay(model, signal):
    config = model["feature_config"]
    if (model["family"] != "lda" or config.get("version") != "time-domain-4ch-v1" or
        config.get("order") != "channel-major" or config.get("channels") != 4 or
        config.get("features") != ["mav", "rms", "waveform_length", "zero_crossings", "slope_sign_changes"] or
        config.get("window_ms") != 200 or config.get("step_ms") != 100 or
        config.get("zc_threshold") != 0 or config.get("ssc_threshold") != 0 or config.get("filter") != "none"):
        raise ValueError("Unsupported model feature contract")
    rate = float(signal["sample_rate_hz"])
    if not rate.is_integer() or rate != float(config["sample_rate_hz"]):
        raise ValueError("Recording sample rate does not match the model")
    samples = signal["samples"]
    size, step = round(rate * 0.2), round(rate * 0.1)
    if size < 3 or step < 1 or len(samples) < size:
        raise ValueError("Recording is shorter than one feature window")
    coefficients = np.asarray(model["coefficients"], dtype=np.float64)
    intercepts = np.asarray(model["intercepts"], dtype=np.float64)
    classes = model["classes"]
    expected_rows = 1 if len(classes) == 2 else len(classes)
    if len(classes) < 2 or "rest" not in classes or coefficients.shape != (expected_rows, 20) or intercepts.shape != (expected_rows,) or not np.isfinite(coefficients).all() or not np.isfinite(intercepts).all():
        raise ValueError("Incompatible model parameters")
    windows = []
    elapsed_ns = []
    for start in range(0, len(samples) - size + 1, step):
        begin = time.perf_counter_ns()
        features = recognition_features(samples[start:start + size])
        scores = coefficients @ features + intercepts
        index = int(scores[0] > 0) if len(classes) == 2 else int(np.argmax(scores))
        gesture = classes[index]
        elapsed_ns.append(time.perf_counter_ns() - begin)
        windows.append({"start_sample": start, "gesture": gesture, "command": "neutral" if gesture == "rest" else gesture})
    return {"feature_version": config["version"], "predictions": windows,
            "prediction_count": len(windows), "processing_p95_ms": float(np.percentile(elapsed_ns, 95) / 1_000_000),
            "timing_scope": "feature extraction and prediction only; excludes input buffering and rendering"}
