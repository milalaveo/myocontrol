"""Best-effort cache for immutable, checksum-verified model bytes."""

import hashlib
import logging
import os

import redis

logger = logging.getLogger("recognition.cache")
CACHE_SECONDS = 300


def cache_client():
    host = os.environ.get("REDIS_HOST")
    if not host:
        return None
    return redis.Redis(host=host, port=int(os.environ.get("REDIS_PORT", "6379")),
                       password=os.environ.get("REDIS_PASSWORD"), socket_connect_timeout=1, socket_timeout=1)


def read_cached_model(run_id):
    try:
        client = cache_client()
        value = client.get(f"model:v1:{run_id}") if client else None
        if not value:
            return None
        checksum, payload = value.split(b"\n", 1)
        if len(checksum) != 64 or hashlib.sha256(payload).hexdigest().encode("ascii") != checksum:
            logger.warning("cached_model_checksum_mismatch")
            return None
        return payload, checksum.decode("ascii")
    except (redis.RedisError, ValueError, UnicodeDecodeError):
        logger.warning("model_cache_unavailable")
        return None


def cache_model(run_id, payload, checksum):
    try:
        client = cache_client()
        if client:
            client.set(f"model:v1:{run_id}", checksum.encode("ascii") + b"\n" + payload, ex=CACHE_SECONDS)
    except (redis.RedisError, ValueError, UnicodeEncodeError):
        logger.warning("model_cache_unavailable")
