CREATE TABLE data_protocol.recordings (
    id uuid PRIMARY KEY,
    participant_id uuid NOT NULL REFERENCES data_protocol.participants(id) ON DELETE RESTRICT,
    sample_rate_hz numeric NOT NULL CHECK (sample_rate_hz > 0 AND sample_rate_hz <= 100000),
    sample_count integer NOT NULL CHECK (sample_count BETWEEN 1 AND 10000),
    artifact_sha256 varchar(64) NOT NULL CHECK (artifact_sha256 ~ '^[0-9a-f]{64}$')
);
