"""Versioned HTTP client for the Data and Protocol service."""

import os
import hashlib
import json

import httpx


class DataServiceError(Exception):
    pass


def source_signal(split_id, correlation_id):
    url = os.environ.get("DATA_SERVICE_URL")
    if not url:
        raise DataServiceError("Data service address is not configured")
    try:
        with httpx.Client(base_url=url, timeout=httpx.Timeout(5.0, connect=2.0), headers={"X-Correlation-ID": correlation_id}) as client:
            response = client.get(f"/v1/synthetic-splits/{split_id}")
            response.raise_for_status()
            split = response.json()
            response = client.get(f"/v1/recordings/{split['source_recording_id']}/signal")
            response.raise_for_status()
            signal = response.json()
        if not signal.get("samples") or any(len(row) != 4 for row in signal["samples"]):
            raise DataServiceError("Invalid source signal")
        return split, signal
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise DataServiceError("Data service unavailable or returned invalid data") from error


def research_inputs(manifest_id, target_participant_id, correlation_id):
    """Load a frozen snapshot and verify selected source and target artifacts."""
    url = os.environ.get("DATA_SERVICE_URL")
    if not url:
        raise DataServiceError("Data service address is not configured")
    try:
        with httpx.Client(base_url=url, timeout=httpx.Timeout(5.0, connect=2.0), headers={"X-Correlation-ID": correlation_id}) as client:
            response = client.get(f"/v1/research-manifests/{manifest_id}/snapshot")
            response.raise_for_status()
            snapshot = response.json()
            if snapshot["state"] != "frozen" or str(snapshot["id"]) != str(manifest_id):
                raise DataServiceError("Manifest is not frozen")
            signals = {}
            verified_checksums = {}
            for unit in snapshot["units"]:
                if unit["role"] != "source_train" and not (unit["role"] == "target_test" and str(unit["participant_id"]) == str(target_participant_id)):
                    continue
                recording_id = str(unit["recording_id"])
                if recording_id not in signals:
                    response = client.get(f"/v1/recordings/{recording_id}/signal")
                    response.raise_for_status()
                    signal = response.json()
                    payload = json.dumps({"format": "four-channel-v1", "sample_rate_hz": signal["sample_rate_hz"], "samples": signal["samples"]},
                                         sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
                    if hashlib.sha256(payload).hexdigest() != unit["artifact_sha256"]:
                        raise DataServiceError("Signal checksum mismatch")
                    signals[recording_id] = signal
                    verified_checksums[recording_id] = unit["artifact_sha256"]
                signal = signals[recording_id]
                if (verified_checksums[recording_id] != unit["artifact_sha256"] or
                    str(signal["participant_id"]) != str(unit["participant_id"]) or
                    float(signal["sample_rate_hz"]) != float(unit["sample_rate_hz"]) or
                    len(signal["samples"]) != unit["sample_count"]):
                    raise DataServiceError("Signal metadata does not match manifest")
        return snapshot, signals
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise DataServiceError("Research inputs are unavailable or invalid") from error
