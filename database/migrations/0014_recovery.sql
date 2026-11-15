ALTER TABLE myoprosthesis.runs ADD COLUMN heartbeat_at timestamptz;

CREATE OR REPLACE FUNCTION myoprosthesis.guard_run_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'queued' OR NEW.heartbeat_at IS NOT NULL THEN RAISE EXCEPTION 'New runs must be queued'; END IF;
        IF NOT EXISTS (SELECT 1 FROM myoprosthesis.split_manifests WHERE id = NEW.manifest_id AND state = 'frozen') THEN
            RAISE EXCEPTION 'Run requires a frozen manifest';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.status IN ('succeeded', 'failed', 'interrupted') THEN RAISE EXCEPTION 'Terminal runs are immutable'; END IF;
    IF (NEW.kind, NEW.manifest_id, NEW.feature_config_id, NEW.seed, NEW.parameter_schema_version, NEW.parameters, NEW.software_version, NEW.created_at)
       IS DISTINCT FROM (OLD.kind, OLD.manifest_id, OLD.feature_config_id, OLD.seed, OLD.parameter_schema_version, OLD.parameters, OLD.software_version, OLD.created_at) THEN
        RAISE EXCEPTION 'Run configuration is immutable';
    END IF;
    IF OLD.status = 'running' AND NEW.status = 'running' THEN
        IF (NEW.started_at, NEW.finished_at, NEW.failure_reason) IS DISTINCT FROM (OLD.started_at, OLD.finished_at, OLD.failure_reason)
           OR NEW.heartbeat_at IS NULL OR NEW.heartbeat_at < OLD.started_at
           OR (OLD.heartbeat_at IS NOT NULL AND NEW.heartbeat_at < OLD.heartbeat_at) THEN
            RAISE EXCEPTION 'Invalid heartbeat update';
        END IF;
        RETURN NEW;
    END IF;
    IF NOT ((OLD.status = 'queued' AND NEW.status = 'running') OR
            (OLD.status = 'running' AND NEW.status IN ('succeeded', 'failed', 'interrupted'))) THEN
        RAISE EXCEPTION 'Invalid run transition: % to %', OLD.status, NEW.status;
    END IF;
    IF NEW.heartbeat_at IS NOT NULL AND (NEW.started_at IS NULL OR NEW.heartbeat_at < NEW.started_at) THEN
        RAISE EXCEPTION 'Heartbeat precedes run start';
    END IF;
    RETURN NEW;
END $$;

CREATE PROCEDURE myoprosthesis.interrupt_stale_runs(p_cutoff timestamptz) LANGUAGE plpgsql AS $$
BEGIN
    IF p_cutoff IS NULL OR p_cutoff > clock_timestamp() THEN RAISE EXCEPTION 'Cutoff must be in the past'; END IF;
    UPDATE myoprosthesis.runs SET status = 'interrupted', finished_at = clock_timestamp(), failure_reason = 'Worker heartbeat expired'
    WHERE status = 'running' AND COALESCE(heartbeat_at, started_at) < p_cutoff;
END $$;

CREATE TABLE myoprosthesis.run_idempotency_keys (
    operation text NOT NULL CHECK (length(trim(operation)) > 0),
    idempotency_key text NOT NULL CHECK (length(trim(idempotency_key)) > 0),
    run_id bigint NOT NULL UNIQUE REFERENCES myoprosthesis.runs(id) ON DELETE RESTRICT,
    PRIMARY KEY (operation, idempotency_key)
);
CREATE FUNCTION myoprosthesis.immutable_run_idempotency_key() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Idempotency keys are immutable';
END $$;
CREATE TRIGGER immutable_run_idempotency_key BEFORE UPDATE OR DELETE ON myoprosthesis.run_idempotency_keys
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.immutable_run_idempotency_key();
