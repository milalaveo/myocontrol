ALTER TABLE ml_experiments.source_lda_runs ADD COLUMN trace_context jsonb NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(trace_context) = 'object');

CREATE FUNCTION ml_experiments.guard_trace_context() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.trace_context IS DISTINCT FROM OLD.trace_context THEN
        RAISE EXCEPTION 'Experiment trace context is immutable';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_trace_context BEFORE UPDATE ON ml_experiments.source_lda_runs
FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_trace_context();
