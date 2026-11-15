"""Content-addressed local artifact storage and non-destructive reconciliation."""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import tempfile
import time


@dataclass(frozen=True)
class StoredArtifact:
    key: str
    sha256: str
    size_bytes: int


class LocalArtifactStore:
    """Store immutable files on a single, locally controlled filesystem."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.objects = self.root / "objects"
        self.staging = self.root / "staging"
        self.objects.mkdir(parents=True, exist_ok=True)
        self.staging.mkdir(parents=True, exist_ok=True)

    def put(self, data: bytes) -> StoredArtifact:
        digest = hashlib.sha256(data).hexdigest()
        key = f"objects/{digest[:2]}/{digest}"
        target = self.root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.staging, delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError:
                pass
            artifact = StoredArtifact(key, digest, len(data))
            self.verify(artifact)
            return artifact
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)

    def verify(self, artifact: StoredArtifact) -> None:
        expected_key = f"objects/{artifact.sha256[:2]}/{artifact.sha256}"
        if artifact.key != expected_key or len(artifact.sha256) != 64 or any(c not in "0123456789abcdef" for c in artifact.sha256):
            raise ValueError("Invalid content-addressed artifact key")
        path = self.root / expected_key
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                size += len(chunk)
                digest.update(chunk)
        if size != artifact.size_bytes or digest.hexdigest() != artifact.sha256:
            raise ValueError(f"Artifact checksum or size mismatch: {artifact.key}")

    def find_orphans(self, referenced_keys: set[str], minimum_age_seconds: float = 3600) -> list[str]:
        """List unreferenced objects older than the grace period; never delete files."""
        if minimum_age_seconds < 0:
            raise ValueError("minimum_age_seconds must be nonnegative")
        cutoff = time.time() - minimum_age_seconds
        return sorted(
            path.relative_to(self.root).as_posix()
            for path in self.objects.glob("*/*")
            if path.is_file() and not path.is_symlink()
            and path.relative_to(self.root).as_posix() not in referenced_keys
            and path.stat().st_mtime <= cutoff
        )

    def find_abandoned_staging(self, minimum_age_seconds: float = 3600) -> list[str]:
        """List old staging files without deleting them or assuming a writer is dead."""
        if minimum_age_seconds < 0:
            raise ValueError("minimum_age_seconds must be nonnegative")
        cutoff = time.time() - minimum_age_seconds
        return sorted(path.relative_to(self.root).as_posix() for path in self.staging.iterdir()
                      if path.is_file() and not path.is_symlink() and path.stat().st_mtime <= cutoff)
