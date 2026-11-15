"""Versioned time-domain features for four-channel sEMG windows."""

import numpy as np

FEATURE_VERSION = "time-domain-4ch-v1"
FEATURE_NAMES = ("mav", "rms", "waveform_length", "zero_crossings", "slope_sign_changes")


def extract_features(window):
    """Return channel-major MAV, RMS, WL, ZC and SSC with zero thresholds."""
    values = np.asarray(window, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] != 4 or values.shape[0] < 3 or not np.isfinite(values).all():
        raise ValueError("Expected a finite window with at least three four-channel samples")
    features = []
    for channel in values.T:
        delta = np.diff(channel)
        features.extend((
            np.mean(np.abs(channel)),
            np.sqrt(np.mean(channel * channel)),
            np.sum(np.abs(delta)),
            np.count_nonzero(channel[:-1] * channel[1:] < 0),
            np.count_nonzero(delta[:-1] * delta[1:] < 0),
        ))
    return np.asarray(features, dtype=np.float64)


def segment_windows(samples, start, end, sample_rate):
    """Yield 200 ms windows with a 100 ms step, wholly inside one labelled segment."""
    if not float(sample_rate).is_integer():
        raise ValueError("This feature version requires an integer sample rate")
    window = round(sample_rate * 0.2)
    step = round(sample_rate * 0.1)
    if window < 3 or step < 1 or start < 0 or end > len(samples) or end <= start:
        raise ValueError("Segment or sample rate is incompatible with feature configuration")
    return [extract_features(samples[position:position + window]) for position in range(start, end - window + 1, step)]
