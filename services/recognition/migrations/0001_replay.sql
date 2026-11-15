CREATE SCHEMA recognition;
CREATE TABLE recognition.replay_sessions (
    id uuid PRIMARY KEY,
    model_run_id uuid NOT NULL,
    recording_id uuid NOT NULL,
    status varchar(20) NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    model_checksum varchar(64),
    result jsonb,
    error varchar(200),
    CHECK ((status = 'running' AND model_checksum IS NULL AND result IS NULL AND error IS NULL) OR
           (status = 'succeeded' AND model_checksum IS NOT NULL AND model_checksum ~ '^[0-9a-f]{64}$' AND result IS NOT NULL AND error IS NULL) OR
           (status = 'failed' AND result IS NOT NULL AND error IS NOT NULL))
);
