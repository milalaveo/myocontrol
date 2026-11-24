import hashlib
import json
import math
from pathlib import Path

MAX_IMPORT_BYTES = 64 * 1024 * 1024
DEFAULT_CHANNELS = [0, 1, 2, 3]


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def validate_samples(samples, channel_count):
    if not isinstance(samples, list) or not samples:
        raise ValueError("The recording contains no samples")
    result = []
    for row in samples:
        if not isinstance(row, (list, tuple)) or len(row) != channel_count:
            raise ValueError("Sample width does not match the channel mapping")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in row
        ):
            raise ValueError("Samples must contain finite numeric values")
        result.append([float(value) for value in row])
    return result


def read_signal(path):
    path = Path(path)
    if path.stat().st_size > MAX_IMPORT_BYTES:
        raise ValueError("Import is limited to 64 MiB per recording")
    with path.open(encoding="utf-8") as stream:
        body = json.load(stream)
    rate = body.get("sample_rate_hz")
    if (
        isinstance(rate, bool)
        or not isinstance(rate, (int, float))
        or not math.isfinite(rate)
        or not 1 <= rate <= 100000
    ):
        raise ValueError("Invalid sample rate")
    channels = body.get("channel_map", DEFAULT_CHANNELS)
    if (
        not isinstance(channels, list)
        or not 1 <= len(channels) <= 6
        or len(set(channels)) != len(channels)
        or any(type(c) is not int or not 0 <= c <= 11 for c in channels)
    ):
        raise ValueError("Invalid ordered channel mapping")
    samples = validate_samples(body.get("samples"), len(channels))
    source_kind = body.get("source_kind", "dataset")
    if source_kind not in {"synthetic", "dataset", "device"}:
        raise ValueError("Invalid source kind")
    metadata = {
        "sample_rate_hz": float(rate),
        "channel_map": channels,
        "source_kind": source_kind,
        "source_name": body.get("source_name", "local-import"),
        "source_version": body.get("source_version", "1"),
        "units": body.get("units", "unspecified"),
    }
    for key in ("source_name", "source_version", "units"):
        if (
            not isinstance(metadata[key], str)
            or not 1 <= len(metadata[key].strip()) <= 120
        ):
            raise ValueError(f"Invalid {key}")
    return metadata, samples


def signal_digest(metadata, chunks):
    digest = hashlib.sha256(
        (
            canonical(
                {
                    key: metadata[key]
                    for key in ("sample_rate_hz", "channel_map", "units")
                }
            )
            + "\n"
        ).encode()
    )
    for chunk in chunks:
        for row in chunk:
            digest.update((canonical(row) + "\n").encode())
    return digest.hexdigest()
