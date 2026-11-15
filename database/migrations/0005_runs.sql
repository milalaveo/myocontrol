-- This is the initial run and result schema. Publication and compatibility rules
-- must be completed before this schema is used for research.
CREATE TABLE myoprosthesis.feature_configs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (length(trim(name)) > 0),
    version integer NOT NULL CHECK (version > 0),
    schema_version text NOT NULL CHECK (length(trim(schema_version)) > 0),
    parameters jsonb NOT NULL CHECK (jsonb_typeof(parameters) = 'object'),
    UNIQUE (name, version)
);

CREATE TABLE myoprosthesis.runs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind text NOT NULL CHECK (kind IN ('train', 'adapt', 'evaluate')),
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'interrupted')),
    manifest_id bigint NOT NULL REFERENCES myoprosthesis.split_manifests(id) ON DELETE RESTRICT,
    feature_config_id bigint NOT NULL REFERENCES myoprosthesis.feature_configs(id) ON DELETE RESTRICT,
    seed bigint NOT NULL,
    parameter_schema_version text NOT NULL CHECK (length(trim(parameter_schema_version)) > 0),
    parameters jsonb NOT NULL CHECK (jsonb_typeof(parameters) = 'object'),
    software_version text NOT NULL CHECK (length(trim(software_version)) > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at timestamptz,
    finished_at timestamptz,
    failure_reason text,
    CHECK (started_at IS NULL OR started_at >= created_at),
    CHECK (finished_at IS NULL OR (started_at IS NOT NULL AND finished_at >= started_at)),
    CHECK ((status = 'queued' AND started_at IS NULL AND finished_at IS NULL) OR
           (status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL) OR
           (status IN ('succeeded', 'failed', 'interrupted') AND started_at IS NOT NULL AND finished_at IS NOT NULL)),
    CHECK (status NOT IN ('failed', 'interrupted') OR (failure_reason IS NOT NULL AND length(trim(failure_reason)) > 0))
);

CREATE FUNCTION myoprosthesis.guard_run_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'queued' THEN RAISE EXCEPTION 'New runs must be queued'; END IF;
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
    IF NOT ((OLD.status = 'queued' AND NEW.status = 'running') OR
            (OLD.status = 'running' AND NEW.status IN ('succeeded', 'failed', 'interrupted'))) THEN
        RAISE EXCEPTION 'Invalid run transition: % to %', OLD.status, NEW.status;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_run_transition BEFORE INSERT OR UPDATE ON myoprosthesis.runs
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_run_transition();

CREATE TABLE myoprosthesis.model_versions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id bigint NOT NULL UNIQUE REFERENCES myoprosthesis.runs(id) ON DELETE RESTRICT,
    family text NOT NULL CHECK (family IN ('lda', 'svm', 'mlp')),
    condition text NOT NULL CHECK (condition IN ('source_only', 'personalised', 'target_only')),
    artifact_id bigint NOT NULL REFERENCES myoprosthesis.artifacts(id) ON DELETE RESTRICT,
    parent_model_id bigint REFERENCES myoprosthesis.model_versions(id) ON DELETE RESTRICT,
    calibration_subset_id bigint REFERENCES myoprosthesis.calibration_subsets(id) ON DELETE RESTRICT,
    CHECK ((condition = 'source_only' AND parent_model_id IS NULL AND calibration_subset_id IS NULL) OR
           (condition = 'personalised' AND parent_model_id IS NOT NULL AND calibration_subset_id IS NOT NULL) OR
           (condition = 'target_only' AND parent_model_id IS NULL AND calibration_subset_id IS NOT NULL))
);

CREATE TABLE myoprosthesis.evaluations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id bigint NOT NULL UNIQUE REFERENCES myoprosthesis.runs(id) ON DELETE RESTRICT,
    model_id bigint NOT NULL REFERENCES myoprosthesis.model_versions(id) ON DELETE RESTRICT,
    participant_id bigint NOT NULL REFERENCES myoprosthesis.participants(id) ON DELETE RESTRICT
);

CREATE TABLE myoprosthesis.evaluation_metrics (
    evaluation_id bigint NOT NULL REFERENCES myoprosthesis.evaluations(id) ON DELETE RESTRICT,
    metric text NOT NULL CHECK (metric IN ('macro_f1', 'accuracy', 'rest_false_activation_rate')),
    value numeric CHECK (value BETWEEN 0 AND 1),
    missing_reason text,
    numerator bigint CHECK (numerator >= 0),
    denominator bigint CHECK (denominator > 0),
    PRIMARY KEY (evaluation_id, metric),
    CHECK ((value IS NOT NULL AND missing_reason IS NULL) OR
           (value IS NULL AND missing_reason IS NOT NULL AND length(trim(missing_reason)) > 0)),
    CHECK ((numerator IS NULL AND denominator IS NULL) OR
           (numerator IS NOT NULL AND denominator IS NOT NULL AND numerator <= denominator))
);

CREATE TABLE myoprosthesis.confusion_counts (
    evaluation_id bigint NOT NULL REFERENCES myoprosthesis.evaluations(id) ON DELETE RESTRICT,
    actual_gesture_id bigint NOT NULL REFERENCES myoprosthesis.gestures(id) ON DELETE RESTRICT,
    predicted_gesture_id bigint NOT NULL REFERENCES myoprosthesis.gestures(id) ON DELETE RESTRICT,
    count bigint NOT NULL CHECK (count >= 0),
    PRIMARY KEY (evaluation_id, actual_gesture_id, predicted_gesture_id)
);
