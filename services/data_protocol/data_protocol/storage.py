"""Immutable local storage for uploaded signal payloads."""

import hashlib
import os
from pathlib import Path
import tempfile


def save_signal(data: bytes) -> str:
    root_name = os.environ.get("DATA_ARTIFACT_ROOT")
    if not root_name:
        raise RuntimeError("DATA_ARTIFACT_ROOT is required")
    root = Path(root_name).resolve()
    root.mkdir(parents=True, exist_ok=True)
    checksum = hashlib.sha256(data).hexdigest()
    target = root / checksum
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=root, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            pass
        if hashlib.sha256(target.read_bytes()).hexdigest() != checksum:
            raise ValueError("Stored signal checksum mismatch")
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
    return checksum


def read_signal(checksum: str) -> bytes:
    root_name = os.environ.get("DATA_ARTIFACT_ROOT")
    if not root_name:
        raise RuntimeError("DATA_ARTIFACT_ROOT is required")
    if len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
        raise ValueError("Invalid signal checksum")
    data = (Path(root_name).resolve() / checksum).read_bytes()
    if hashlib.sha256(data).hexdigest() != checksum:
        raise ValueError("Stored signal checksum mismatch")
    return data
