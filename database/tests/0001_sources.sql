-- Execute on a disposable database after applying migration 0001.
BEGIN;
INSERT INTO myoprosthesis.datasets (name) VALUES ('synthetic');
INSERT INTO myoprosthesis.dataset_versions (dataset_id, version)
SELECT id, '1' FROM myoprosthesis.datasets WHERE name = 'synthetic';
INSERT INTO myoprosthesis.participants (pseudonym) VALUES ('test-participant');
DO $$
BEGIN
    BEGIN
        INSERT INTO myoprosthesis.participants (pseudonym) VALUES ('test-participant');
        RAISE EXCEPTION 'duplicate participant was accepted';
    EXCEPTION WHEN unique_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO myoprosthesis.artifacts (storage_namespace, storage_key, media_type, size_bytes, sha256)
        VALUES ('test', 'invalid', 'application/octet-stream', -1, repeat('0', 64));
        RAISE EXCEPTION 'negative size was accepted';
    EXCEPTION WHEN check_violation THEN NULL;
    END;
    BEGIN
        INSERT INTO myoprosthesis.recordings (session_id, artifact_id, sample_rate_hz, sample_count)
        VALUES (-1, -1, 1000, 10);
        RAISE EXCEPTION 'invalid foreign keys were accepted';
    EXCEPTION WHEN foreign_key_violation THEN NULL;
    END;
END $$;
ROLLBACK;
