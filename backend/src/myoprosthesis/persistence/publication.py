"""Publish verified source-only model artifacts in a database transaction."""

from .artifacts import LocalArtifactStore


def publish_source_model(connection, store: LocalArtifactStore, run_id: int, family: str, data: bytes) -> int:
    """Publish a model and complete a running job; connection must be idle.

    A failed database transaction may leave an unreferenced content-addressed file.
    The caller must not pass untrusted pickle data to a model loader.
    """
    if family not in {"lda", "svm", "mlp"}:
        raise ValueError("Unsupported model family")
    artifact = store.put(data)
    with connection.transaction():
        with connection.cursor() as cursor:
            cursor.execute("SELECT status FROM myoprosthesis.runs WHERE id = %s FOR UPDATE", (run_id,))
            row = cursor.fetchone()
            if row is None or row[0] != "running":
                raise ValueError("Model run must exist and be running")
            cursor.execute(
                """INSERT INTO myoprosthesis.artifacts
                   (storage_namespace, storage_key, media_type, size_bytes, sha256)
                   VALUES ('local', %s, 'application/octet-stream', %s, %s)
                   ON CONFLICT (storage_namespace, storage_key) DO NOTHING""",
                (artifact.key, artifact.size_bytes, artifact.sha256),
            )
            cursor.execute(
                "SELECT id, size_bytes, sha256 FROM myoprosthesis.artifacts WHERE storage_namespace = 'local' AND storage_key = %s",
                (artifact.key,),
            )
            artifact_id, size, digest = cursor.fetchone()
            if size != artifact.size_bytes or digest != artifact.sha256:
                raise ValueError("Stored artifact metadata does not match its content")
            store.verify(artifact)
            cursor.execute(
                "INSERT INTO myoprosthesis.artifact_verifications (artifact_id, verified_sha256) VALUES (%s, %s) ON CONFLICT (artifact_id) DO NOTHING",
                (artifact_id, artifact.sha256),
            )
            cursor.execute(
                "INSERT INTO myoprosthesis.model_versions (run_id, family, condition, artifact_id) VALUES (%s, %s, 'source_only', %s) RETURNING id",
                (run_id, family, artifact_id),
            )
            model_id = cursor.fetchone()[0]
            cursor.execute("UPDATE myoprosthesis.runs SET status = 'succeeded', finished_at = clock_timestamp() WHERE id = %s", (run_id,))
            return model_id


def referenced_local_keys(connection) -> set[str]:
    """Return DB references for reconciliation against a consistent query snapshot."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT storage_key FROM myoprosthesis.artifacts WHERE storage_namespace = 'local'")
        return {row[0] for row in cursor}
