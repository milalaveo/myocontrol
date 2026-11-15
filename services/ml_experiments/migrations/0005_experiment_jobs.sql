ALTER TABLE ml_experiments.source_lda_runs DROP CONSTRAINT source_lda_runs_status_check;
ALTER TABLE ml_experiments.source_lda_runs DROP CONSTRAINT source_lda_runs_check;
ALTER TABLE ml_experiments.source_lda_runs ADD COLUMN started_at timestamptz;
ALTER TABLE ml_experiments.source_lda_runs ADD COLUMN heartbeat_at timestamptz;
ALTER TABLE ml_experiments.source_lda_runs ADD COLUMN idempotency_key varchar(100) UNIQUE;
ALTER TABLE ml_experiments.source_lda_runs ADD COLUMN correlation_id varchar(64) NOT NULL DEFAULT 'legacy';

CREATE OR REPLACE FUNCTION ml_experiments.guard_source_lda_run() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' OR OLD.status IN ('succeeded', 'failed', 'interrupted') THEN
        RAISE EXCEPTION 'Completed experiment runs are immutable';
    END IF;
    IF (NEW.id, NEW.manifest_id, NEW.target_participant_id, NEW.created_at, NEW.idempotency_key, NEW.correlation_id) IS DISTINCT FROM
       (OLD.id, OLD.manifest_id, OLD.target_participant_id, OLD.created_at, OLD.idempotency_key, OLD.correlation_id) THEN
        RAISE EXCEPTION 'Experiment identity is immutable';
    END IF;
    IF NOT ((OLD.status = 'queued' AND NEW.status = 'running') OR
            (OLD.status = 'running' AND NEW.status IN ('running', 'succeeded', 'failed', 'interrupted'))) THEN
        RAISE EXCEPTION 'Invalid experiment run transition';
    END IF;
    IF OLD.status = 'running' AND NEW.status = 'running' AND
       ((NEW.started_at, NEW.completed_at, NEW.model, NEW.metrics, NEW.snapshot, NEW.error, NEW.manifest_checksum, NEW.model_checksum)
        IS DISTINCT FROM (OLD.started_at, OLD.completed_at, OLD.model, OLD.metrics, OLD.snapshot, OLD.error, OLD.manifest_checksum, OLD.model_checksum) OR
        NEW.heartbeat_at IS NULL OR NEW.heartbeat_at < OLD.heartbeat_at) THEN
        RAISE EXCEPTION 'Invalid experiment heartbeat';
    END IF;
    RETURN NEW;
END $$;

-- Preserve old completed rows; previously running jobs become recoverable on worker startup.
ALTER TABLE ml_experiments.source_lda_runs DISABLE TRIGGER guard_source_lda_run;
UPDATE ml_experiments.source_lda_runs SET started_at = created_at, heartbeat_at = created_at WHERE status = 'running';
ALTER TABLE ml_experiments.source_lda_runs ENABLE TRIGGER guard_source_lda_run;

ALTER TABLE ml_experiments.source_lda_runs ADD CONSTRAINT source_lda_runs_status_v2
    CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'interrupted'));
ALTER TABLE ml_experiments.source_lda_runs ADD CONSTRAINT source_lda_runs_state_v2 CHECK (
    (status = 'queued' AND started_at IS NULL AND heartbeat_at IS NULL AND completed_at IS NULL AND manifest_checksum IS NULL AND snapshot IS NULL AND model IS NULL AND metrics IS NULL AND error IS NULL) OR
    (status = 'running' AND started_at IS NOT NULL AND heartbeat_at IS NOT NULL AND completed_at IS NULL AND manifest_checksum IS NULL AND snapshot IS NULL AND model IS NULL AND metrics IS NULL AND error IS NULL) OR
    (status = 'succeeded' AND completed_at IS NOT NULL AND manifest_checksum IS NOT NULL AND manifest_checksum ~ '^[0-9a-f]{64}$' AND snapshot IS NOT NULL AND model IS NOT NULL AND metrics IS NOT NULL AND error IS NULL) OR
    (status IN ('failed', 'interrupted') AND completed_at IS NOT NULL AND snapshot IS NULL AND model IS NULL AND metrics IS NULL AND error IS NOT NULL)
);
CREATE INDEX source_lda_runs_queue ON ml_experiments.source_lda_runs(created_at) WHERE status = 'queued';
CREATE INDEX source_lda_runs_heartbeat ON ml_experiments.source_lda_runs(heartbeat_at) WHERE status = 'running';
