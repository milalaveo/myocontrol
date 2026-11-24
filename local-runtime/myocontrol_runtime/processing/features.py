import numpy as np

FEATURES = ["mav", "rms", "waveform_length", "zero_crossings", "slope_sign_changes"]


def extract_features(samples):
    values = np.asarray(samples, dtype=np.float64)
    if (
        values.ndim != 2
        or values.shape[1] != 4
        or len(values) < 3
        or not np.isfinite(values).all()
    ):
        raise ValueError("Expected a finite four-channel feature window")
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
