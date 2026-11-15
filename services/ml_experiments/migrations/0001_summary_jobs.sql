CREATE SCHEMA ml_experiments;
CREATE TABLE ml_experiments.signal_summary_jobs (
    id uuid PRIMARY KEY,
    split_id uuid NOT NULL,
    status varchar(20) NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    split_checksum varchar(64),
    result jsonb,
    error varchar(100),
    CHECK ((status = 'running' AND result IS NULL AND error IS NULL AND split_checksum IS NULL) OR
           (status = 'succeeded' AND result IS NOT NULL AND error IS NULL AND split_checksum ~ '^[0-9a-f]{64}$') OR
           (status = 'failed' AND result IS NULL AND error IS NOT NULL AND split_checksum IS NULL))
);
