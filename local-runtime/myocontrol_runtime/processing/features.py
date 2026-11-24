import numpy as np

CENTERED_PREPROCESSING = "window-dc-v1"

NORMALIZED_PREPROCESSING = "window-dc-common-rms-v1"
NORMALIZATION_FLOOR = 1e-12

FEATURES = ["mav", "rms", "waveform_length", "zero_crossings", "slope_sign_changes"]


def extract_features(samples, channels=4, preprocessing="none"):
    values = np.asarray(samples, dtype=np.float64)
    if (
        values.ndim != 2
        or channels not in {2, 4}
        or values.shape[1] != channels
        or len(values) < 3
        or not np.isfinite(values).all()
    ):
        raise ValueError(f"Expected a finite {channels}-channel feature window")
    if preprocessing == CENTERED_PREPROCESSING:
        values = values - values.mean(axis=0, keepdims=True)
    elif preprocessing == NORMALIZED_PREPROCESSING:
        # Common scaling preserves inter-channel energy ratios. It deliberately
        # removes absolute energy, including the usual rest-versus-activity cue.
        values = values - values.mean(axis=0, keepdims=True)
        scale = float(np.sqrt(np.mean(values**2)))
        values = values / scale if scale > NORMALIZATION_FLOOR else np.zeros_like(values)
    elif preprocessing != "none":
        raise ValueError("Unsupported feature preprocessing")
    result = []
    for channel in values.T:
        delta = np.diff(channel)
        result.extend(
            (
                np.mean(np.abs(channel)),
                np.sqrt(np.mean(channel**2)),
                np.sum(np.abs(delta)),
                np.count_nonzero(channel[:-1] * channel[1:] < 0),
                np.count_nonzero(delta[:-1] * delta[1:] < 0),
            )
        )
    return np.asarray(result)
