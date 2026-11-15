CREATE TABLE ml_experiments.source_lda_runs (
    id uuid PRIMARY KEY,
    manifest_id uuid NOT NULL,
    target_participant_id uuid NOT NULL,
    status varchar(20) NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    manifest_checksum varchar(64),
    snapshot jsonb,
    model jsonb,
    metrics jsonb,
    error text,
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at timestamptz,
    CHECK ((status = 'running' AND completed_at IS NULL AND manifest_checksum IS NULL AND snapshot IS NULL AND model IS NULL AND metrics IS NULL AND error IS NULL) OR
           (status = 'succeeded' AND completed_at IS NOT NULL AND manifest_checksum IS NOT NULL AND manifest_checksum ~ '^[0-9a-f]{64}$' AND snapshot IS NOT NULL AND model IS NOT NULL AND metrics IS NOT NULL AND error IS NULL) OR
           (status = 'failed' AND completed_at IS NOT NULL AND snapshot IS NULL AND model IS NULL AND metrics IS NULL AND error IS NOT NULL))
);

CREATE FUNCTION ml_experiments.guard_source_lda_run() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' OR OLD.status <> 'running' THEN
        RAISE EXCEPTION 'Completed experiment runs are immutable';
    END IF;
    IF (NEW.manifest_id, NEW.target_participant_id, NEW.created_at) IS DISTINCT FROM
       (OLD.manifest_id, OLD.target_participant_id, OLD.created_at) OR NEW.status NOT IN ('succeeded', 'failed') THEN
        RAISE EXCEPTION 'Invalid experiment run transition';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_source_lda_run BEFORE UPDATE OR DELETE ON ml_experiments.source_lda_runs
FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_source_lda_run();
