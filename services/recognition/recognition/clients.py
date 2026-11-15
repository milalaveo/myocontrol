import hashlib
import json
import os

import httpx

from .model_cache import cache_model, read_cached_model


class DependencyError(Exception):
    pass


def load_inputs(model_run_id, recording_id, correlation_id):
    ml_url, data_url = os.environ.get("ML_SERVICE_URL"), os.environ.get("DATA_SERVICE_URL")
    if not ml_url or not data_url:
        raise DependencyError("Service addresses are not configured")
    try:
        with httpx.Client(timeout=httpx.Timeout(5.0, connect=2.0), headers={"X-Correlation-ID": correlation_id}) as client:
            cached = read_cached_model(model_run_id)
            if cached:
                model_bytes, checksum = cached
                model = json.loads(model_bytes)
            else:
                model_response = client.get(f"{ml_url}/v1/source-lda-experiments/{model_run_id}/model")
                model_response.raise_for_status()
                checksum = model_response.headers["X-Artifact-SHA256"]
                model_bytes = model_response.content
                if hashlib.sha256(model_bytes).hexdigest() != checksum:
                    raise DependencyError("Model checksum mismatch")
                model = model_response.json()
                cache_model(model_run_id, model_bytes, checksum)
            metadata_response = client.get(f"{data_url}/v1/recordings/{recording_id}")
            metadata_response.raise_for_status()
            metadata = metadata_response.json()
            signal_response = client.get(f"{data_url}/v1/recordings/{recording_id}/signal")
            signal_response.raise_for_status()
            signal = signal_response.json()
            payload = json.dumps({"format": "four-channel-v1", "sample_rate_hz": signal["sample_rate_hz"], "samples": signal["samples"]},
                                 sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
            if hashlib.sha256(payload).hexdigest() != metadata["artifact_sha256"] or len(signal["samples"]) != metadata["sample_count"]:
                raise DependencyError("Signal checksum or sample count mismatch")
            return model, checksum, signal
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as error:
        raise DependencyError("A dependency is unavailable or returned invalid data") from error
