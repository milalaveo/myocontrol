-- Additive registry: existing source_lda_runs/API remain unchanged.
CREATE TABLE ml_experiments.artifacts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id uuid NOT NULL,
    storage_key text NOT NULL UNIQUE CHECK (length(btrim(storage_key)) > 0),
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes > 0),
    media_type text NOT NULL CHECK (length(btrim(media_type)) > 0),
    state text NOT NULL DEFAULT 'staged' CHECK (state IN ('staged', 'verified')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    verified_at timestamptz,
    CHECK ((state = 'staged' AND verified_at IS NULL) OR (state = 'verified' AND verified_at IS NOT NULL))
);
CREATE FUNCTION ml_experiments.guard_registry_artifact() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.state = 'verified' THEN RAISE EXCEPTION 'Verified artifact metadata is immutable'; END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    IF (NEW.id, NEW.operator_id, NEW.created_at) IS DISTINCT FROM (OLD.id, OLD.operator_id, OLD.created_at) THEN
        RAISE EXCEPTION 'Artifact identity is immutable';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_registry_artifact BEFORE UPDATE OR DELETE ON ml_experiments.artifacts
FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_registry_artifact();

CREATE TABLE ml_experiments.experiment_runs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id uuid NOT NULL,
    submission_key text NOT NULL CHECK (length(btrim(submission_key)) BETWEEN 1 AND 120),
    retry_of_id uuid REFERENCES ml_experiments.experiment_runs(id) ON DELETE RESTRICT,
    kind text NOT NULL CHECK (kind IN ('source_train', 'personalise', 'target_train', 'evaluate')),
    family text NOT NULL CHECK (family IN ('lda', 'svm', 'mlp')),
    condition text NOT NULL CHECK (condition IN ('source_only', 'personalised', 'target_only')),
    execution_location text NOT NULL CHECK (execution_location IN ('local_workstation', 'desktop')),
    manifest_id uuid NOT NULL,
    manifest_sha256 text NOT NULL CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
    target_participant_id uuid,
    calibration_subset_id uuid,
    parent_model_id uuid,
    evaluated_model_id uuid,
    feature_contract jsonb NOT NULL CHECK (jsonb_typeof(feature_contract) = 'object' AND feature_contract ? 'version'
        AND jsonb_typeof(feature_contract->'version') = 'string' AND length(btrim(feature_contract->>'version')) > 0),
    input_snapshot jsonb NOT NULL CHECK (jsonb_typeof(input_snapshot) = 'object'),
    parameters jsonb NOT NULL CHECK (jsonb_typeof(parameters) = 'object'),
    seed bigint NOT NULL,
    software_version text NOT NULL CHECK (length(btrim(software_version)) > 0),
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'interrupted')),
    worker_client_id uuid,
    lease_sha256 text CHECK (lease_sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at timestamptz,
    heartbeat_at timestamptz,
    lease_expires_at timestamptz,
    completed_at timestamptz,
    error text,
    UNIQUE (operator_id, submission_key),
    CHECK ((condition = 'source_only' AND calibration_subset_id IS NULL) OR
        (condition <> 'source_only' AND calibration_subset_id IS NOT NULL AND target_participant_id IS NOT NULL)),
    CHECK ((kind = 'source_train' AND condition = 'source_only' AND execution_location = 'local_workstation') OR
           (kind = 'personalise' AND condition = 'personalised') OR
           (kind = 'target_train' AND condition = 'target_only') OR kind = 'evaluate'),
    CHECK ((kind = 'personalise' AND parent_model_id IS NOT NULL) OR (kind <> 'personalise' AND parent_model_id IS NULL)),
    CHECK ((kind = 'evaluate' AND evaluated_model_id IS NOT NULL AND target_participant_id IS NOT NULL) OR
           (kind <> 'evaluate' AND evaluated_model_id IS NULL)),
    CHECK ((status = 'queued' AND started_at IS NULL AND heartbeat_at IS NULL AND lease_expires_at IS NULL
              AND worker_client_id IS NULL AND lease_sha256 IS NULL AND completed_at IS NULL AND error IS NULL) OR
           (status <> 'queued' AND worker_client_id IS NOT NULL AND lease_sha256 IS NOT NULL
              AND started_at IS NOT NULL AND heartbeat_at IS NOT NULL AND lease_expires_at IS NOT NULL
              AND heartbeat_at >= started_at AND lease_expires_at > heartbeat_at
              AND ((status = 'running' AND completed_at IS NULL AND error IS NULL) OR
                   (status = 'succeeded' AND completed_at IS NOT NULL AND completed_at >= started_at AND error IS NULL) OR
                   (status IN ('failed', 'interrupted') AND completed_at IS NOT NULL AND completed_at >= started_at
                    AND error IS NOT NULL AND length(btrim(error)) > 0))))
);
CREATE INDEX experiment_runs_queue ON ml_experiments.experiment_runs(operator_id, execution_location, created_at) WHERE status = 'queued';
CREATE INDEX experiment_runs_stale ON ml_experiments.experiment_runs(lease_expires_at) WHERE status = 'running';
CREATE INDEX experiment_runs_history ON ml_experiments.experiment_runs(operator_id, created_at DESC);

CREATE TABLE ml_experiments.model_versions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL UNIQUE REFERENCES ml_experiments.experiment_runs(id) ON DELETE RESTRICT,
    artifact_id uuid NOT NULL REFERENCES ml_experiments.artifacts(id) ON DELETE RESTRICT,
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 160),
    adaptation_method text NOT NULL DEFAULT 'none'
        CHECK (adaptation_method IN ('none', 'lda_statistics', 'svm_weighted', 'mlp_replay')),
    state text NOT NULL DEFAULT 'draft' CHECK (state IN ('draft', 'published')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at timestamptz,
    CHECK ((state = 'draft' AND published_at IS NULL) OR (state = 'published' AND published_at IS NOT NULL))
);
ALTER TABLE ml_experiments.experiment_runs ADD FOREIGN KEY (parent_model_id) REFERENCES ml_experiments.model_versions(id) ON DELETE RESTRICT;
ALTER TABLE ml_experiments.experiment_runs ADD FOREIGN KEY (evaluated_model_id) REFERENCES ml_experiments.model_versions(id) ON DELETE RESTRICT;

CREATE TABLE ml_experiments.model_classes (
    model_id uuid NOT NULL REFERENCES ml_experiments.model_versions(id) ON DELETE RESTRICT,
    code text NOT NULL CHECK (code ~ '^[A-Za-z0-9_-]{1,100}$'),
    position integer NOT NULL CHECK (position >= 0),
    PRIMARY KEY (model_id, code),
    UNIQUE (model_id, position)
);
CREATE TABLE ml_experiments.model_package_items (
    model_id uuid NOT NULL REFERENCES ml_experiments.model_versions(id) ON DELETE RESTRICT,
    purpose text NOT NULL CHECK (purpose IN ('source_statistics', 'source_pool', 'replay_pool', 'configuration')),
    artifact_id uuid NOT NULL REFERENCES ml_experiments.artifacts(id) ON DELETE RESTRICT,
    PRIMARY KEY (model_id, purpose)
);
CREATE INDEX model_package_artifact ON ml_experiments.model_package_items(artifact_id);

CREATE FUNCTION ml_experiments.guard_model_members() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE k uuid; state_value text;
BEGIN
    FOR k IN SELECT DISTINCT x FROM unnest(ARRAY[
        CASE WHEN TG_OP <> 'INSERT' THEN OLD.model_id END,
        CASE WHEN TG_OP <> 'DELETE' THEN NEW.model_id END]) x WHERE x IS NOT NULL ORDER BY x LOOP
        SELECT state INTO state_value FROM ml_experiments.model_versions WHERE id = k FOR UPDATE;
        IF state_value IS DISTINCT FROM 'draft' THEN RAISE EXCEPTION 'Published package/class membership is immutable'; END IF;
    END LOOP;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_model_classes BEFORE INSERT OR UPDATE OR DELETE ON ml_experiments.model_classes
FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_model_members();
CREATE TRIGGER guard_model_package_items BEFORE INSERT OR UPDATE OR DELETE ON ml_experiments.model_package_items
FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_model_members();

CREATE FUNCTION ml_experiments.guard_model_version() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r ml_experiments.experiment_runs%ROWTYPE; a ml_experiments.artifacts%ROWTYPE; required_purpose text;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        IF OLD.state = 'published' THEN RAISE EXCEPTION 'Published models are immutable'; END IF;
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        IF (NEW.id, NEW.run_id, NEW.created_at) IS DISTINCT FROM (OLD.id, OLD.run_id, OLD.created_at) THEN
            RAISE EXCEPTION 'Model identity is immutable';
        END IF;
    ELSIF NEW.state <> 'draft' THEN RAISE EXCEPTION 'Create a draft package before publishing';
    END IF;
    SELECT * INTO STRICT r FROM ml_experiments.experiment_runs WHERE id = NEW.run_id;
    IF r.kind = 'evaluate' THEN RAISE EXCEPTION 'An evaluation cannot produce a model'; END IF;
    IF NEW.state = 'published' THEN
        IF r.status <> 'succeeded' THEN RAISE EXCEPTION 'Model publication requires a successful run'; END IF;
        SELECT * INTO STRICT a FROM ml_experiments.artifacts WHERE id = NEW.artifact_id;
        IF a.state <> 'verified' OR a.operator_id <> r.operator_id THEN RAISE EXCEPTION 'Model artifact is unverified or belongs to another operator'; END IF;
        IF (SELECT count(*) FROM ml_experiments.model_classes WHERE model_id = NEW.id) < 2 OR NOT EXISTS (
            SELECT 1 FROM ml_experiments.model_classes WHERE model_id = NEW.id AND code = 'rest'
        ) THEN RAISE EXCEPTION 'Model class mapping requires at least two classes including rest'; END IF;
        IF EXISTS (SELECT 1 FROM ml_experiments.model_package_items i JOIN ml_experiments.artifacts x ON x.id = i.artifact_id
                   WHERE i.model_id = NEW.id AND (x.state <> 'verified' OR x.operator_id <> r.operator_id)) THEN
            RAISE EXCEPTION 'Package contains unverified or foreign artifacts';
        END IF;
        required_purpose := CASE NEW.adaptation_method WHEN 'lda_statistics' THEN 'source_statistics'
            WHEN 'svm_weighted' THEN 'source_pool' WHEN 'mlp_replay' THEN 'replay_pool' END;
        IF NEW.adaptation_method <> 'none' AND NEW.adaptation_method <> (CASE r.family
            WHEN 'lda' THEN 'lda_statistics' WHEN 'svm' THEN 'svm_weighted' WHEN 'mlp' THEN 'mlp_replay' END) THEN
            RAISE EXCEPTION 'Adaptation method does not match model family';
        END IF;
        IF required_purpose IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ml_experiments.model_package_items
            WHERE model_id = NEW.id AND purpose = required_purpose) THEN RAISE EXCEPTION 'Required adaptation material is missing'; END IF;
        IF r.parent_model_id IS NOT NULL AND EXISTS (
            (SELECT code FROM ml_experiments.model_classes WHERE model_id = r.parent_model_id
             EXCEPT SELECT code FROM ml_experiments.model_classes WHERE model_id = NEW.id)
            UNION ALL
            (SELECT code FROM ml_experiments.model_classes WHERE model_id = NEW.id
             EXCEPT SELECT code FROM ml_experiments.model_classes WHERE model_id = r.parent_model_id)
        ) THEN RAISE EXCEPTION 'Personal model class mapping differs from parent'; END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_model_version BEFORE INSERT OR UPDATE OR DELETE ON ml_experiments.model_versions
FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_model_version();

CREATE TABLE ml_experiments.evaluations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id uuid NOT NULL UNIQUE REFERENCES ml_experiments.experiment_runs(id) ON DELETE RESTRICT,
    model_id uuid NOT NULL REFERENCES ml_experiments.model_versions(id) ON DELETE RESTRICT,
    accuracy double precision NOT NULL CHECK (accuracy BETWEEN 0 AND 1),
    macro_f1 double precision NOT NULL CHECK (macro_f1 BETWEEN 0 AND 1),
    rest_false_activation_rate double precision CHECK (rest_false_activation_rate BETWEEN 0 AND 1),
    rest_missing_reason text,
    UNIQUE (id, model_id),
    CHECK ((rest_false_activation_rate IS NOT NULL AND rest_missing_reason IS NULL) OR
           (rest_false_activation_rate IS NULL AND rest_missing_reason IS NOT NULL AND length(btrim(rest_missing_reason)) > 0))
);
CREATE TABLE ml_experiments.confusion_counts (
    evaluation_id uuid NOT NULL,
    model_id uuid NOT NULL,
    actual_class text NOT NULL,
    predicted_class text NOT NULL,
    count bigint NOT NULL CHECK (count >= 0),
    PRIMARY KEY (evaluation_id, actual_class, predicted_class),
    FOREIGN KEY (evaluation_id, model_id) REFERENCES ml_experiments.evaluations(id, model_id) ON DELETE RESTRICT,
    FOREIGN KEY (model_id, actual_class) REFERENCES ml_experiments.model_classes(model_id, code) ON DELETE RESTRICT,
    FOREIGN KEY (model_id, predicted_class) REFERENCES ml_experiments.model_classes(model_id, code) ON DELETE RESTRICT
);
CREATE FUNCTION ml_experiments.guard_evaluation_members() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE run_key uuid; eval_key uuid; run_state text;
BEGIN
    IF TG_TABLE_NAME = 'evaluations' THEN
        run_key := CASE WHEN TG_OP = 'DELETE' THEN OLD.run_id ELSE NEW.run_id END;
        IF TG_OP = 'UPDATE' AND (NEW.id, NEW.run_id, NEW.model_id) IS DISTINCT FROM (OLD.id, OLD.run_id, OLD.model_id) THEN
            RAISE EXCEPTION 'Evaluation identity is immutable';
        END IF;
    ELSE
        IF TG_OP = 'UPDATE' AND (NEW.evaluation_id, NEW.model_id) IS DISTINCT FROM (OLD.evaluation_id, OLD.model_id) THEN
            RAISE EXCEPTION 'Confusion cell identity cannot move';
        END IF;
        eval_key := CASE WHEN TG_OP = 'DELETE' THEN OLD.evaluation_id ELSE NEW.evaluation_id END;
        SELECT run_id INTO run_key FROM ml_experiments.evaluations WHERE id = eval_key;
    END IF;
    SELECT status INTO run_state FROM ml_experiments.experiment_runs WHERE id = run_key FOR UPDATE;
    IF run_state IS DISTINCT FROM 'running' THEN RAISE EXCEPTION 'Evaluation inputs are editable only during their run'; END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_registry_evaluation BEFORE INSERT OR UPDATE OR DELETE ON ml_experiments.evaluations
FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_evaluation_members();
CREATE TRIGGER guard_registry_confusion BEFORE INSERT OR UPDATE OR DELETE ON ml_experiments.confusion_counts
FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_evaluation_members();

CREATE FUNCTION ml_experiments.guard_experiment_run() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent_run ml_experiments.experiment_runs%ROWTYPE;
BEGIN
    IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Run history cannot be deleted'; END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'queued' THEN RAISE EXCEPTION 'Submit queued runs before claiming'; END IF;
        IF NEW.parent_model_id IS NOT NULL THEN
            SELECT r.* INTO parent_run FROM ml_experiments.model_versions m JOIN ml_experiments.experiment_runs r ON r.id = m.run_id
            WHERE m.id = NEW.parent_model_id AND m.state = 'published';
            IF NOT FOUND OR (parent_run.operator_id, parent_run.family, parent_run.condition, parent_run.manifest_id, parent_run.manifest_sha256, parent_run.feature_contract)
                IS DISTINCT FROM (NEW.operator_id, NEW.family, 'source_only'::text, NEW.manifest_id, NEW.manifest_sha256, NEW.feature_contract) THEN
                RAISE EXCEPTION 'Incompatible source parent';
            END IF;
        END IF;
        IF NEW.retry_of_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ml_experiments.experiment_runs
            WHERE id = NEW.retry_of_id AND operator_id = NEW.operator_id AND status IN ('failed', 'interrupted')) THEN
            RAISE EXCEPTION 'Retry must reference a failed/interrupted run of the same operator';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.status IN ('succeeded', 'failed', 'interrupted') THEN RAISE EXCEPTION 'Terminal runs are immutable'; END IF;
    IF (to_jsonb(NEW) - ARRAY['status','worker_client_id','lease_sha256','started_at','heartbeat_at','lease_expires_at','completed_at','error'])
        IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['status','worker_client_id','lease_sha256','started_at','heartbeat_at','lease_expires_at','completed_at','error']) THEN
        RAISE EXCEPTION 'Run inputs are immutable';
    END IF;
    IF OLD.status = 'queued' THEN
        IF NEW.status <> 'running' THEN RAISE EXCEPTION 'A queued run must be claimed'; END IF;
    ELSE
        IF (NEW.worker_client_id, NEW.lease_sha256, NEW.started_at) IS DISTINCT FROM (OLD.worker_client_id, OLD.lease_sha256, OLD.started_at) THEN
            RAISE EXCEPTION 'Lease identity is immutable; retries require a new run';
        END IF;
        IF NEW.status NOT IN ('running', 'succeeded', 'failed', 'interrupted') THEN RAISE EXCEPTION 'Invalid run transition'; END IF;
        IF NEW.status <> 'interrupted' AND OLD.lease_expires_at <= clock_timestamp() THEN RAISE EXCEPTION 'Worker lease expired'; END IF;
        IF NEW.heartbeat_at < OLD.heartbeat_at OR NEW.lease_expires_at < OLD.lease_expires_at THEN RAISE EXCEPTION 'Heartbeat cannot move backwards'; END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_experiment_run BEFORE INSERT OR UPDATE OR DELETE ON ml_experiments.experiment_runs
FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_experiment_run();

-- Deferred consistency permits atomic run success + model publication in one transaction.
CREATE FUNCTION ml_experiments.validate_run_output() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r ml_experiments.experiment_runs%ROWTYPE; e ml_experiments.evaluations%ROWTYPE;
    mr ml_experiments.experiment_runs%ROWTYPE; n bigint; total numeric; diagonal numeric;
    rest_total numeric; rest_false numeric; calculated_f1 numeric;
BEGIN
    SELECT * INTO STRICT r FROM ml_experiments.experiment_runs WHERE id = NEW.id;
    IF r.status <> 'succeeded' THEN RETURN NULL; END IF;
    IF r.kind <> 'evaluate' THEN
        IF NOT EXISTS (SELECT 1 FROM ml_experiments.model_versions WHERE run_id = r.id AND state = 'published') THEN
            RAISE EXCEPTION 'Successful fitting run requires a published model';
        END IF;
        RETURN NULL;
    END IF;
    SELECT * INTO e FROM ml_experiments.evaluations WHERE run_id = r.id AND model_id = r.evaluated_model_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Successful evaluation requires matching metrics'; END IF;
    SELECT x.* INTO mr FROM ml_experiments.model_versions m JOIN ml_experiments.experiment_runs x ON x.id = m.run_id
    WHERE m.id = e.model_id AND m.state = 'published';
    IF NOT FOUND OR (mr.operator_id, mr.family, mr.condition, mr.manifest_id, mr.manifest_sha256, mr.feature_contract, mr.calibration_subset_id)
        IS DISTINCT FROM (r.operator_id, r.family, r.condition, r.manifest_id, r.manifest_sha256, r.feature_contract, r.calibration_subset_id) THEN
        RAISE EXCEPTION 'Evaluation model and frozen conditions are incompatible';
    END IF;
    IF mr.target_participant_id IS NOT NULL AND mr.target_participant_id <> r.target_participant_id THEN RAISE EXCEPTION 'Model target mismatch'; END IF;
    SELECT count(*) INTO n FROM ml_experiments.model_classes WHERE model_id = e.model_id;
    IF (SELECT count(*) FROM ml_experiments.confusion_counts WHERE evaluation_id = e.id) <> n*n THEN
        RAISE EXCEPTION 'Confusion matrix must contain every class pair including zeros';
    END IF;
    SELECT sum(count), sum(count) FILTER (WHERE actual_class = predicted_class),
        coalesce(sum(count) FILTER (WHERE actual_class = 'rest'),0),
        coalesce(sum(count) FILTER (WHERE actual_class = 'rest' AND predicted_class <> 'rest'),0)
    INTO total, diagonal, rest_total, rest_false FROM ml_experiments.confusion_counts WHERE evaluation_id = e.id;
    IF total <= 0 THEN RAISE EXCEPTION 'Evaluation requires test windows'; END IF;
    SELECT avg(CASE WHEN actual_n + predicted_n = 0 THEN 0 ELSE 2*true_n/(actual_n+predicted_n) END)
    INTO calculated_f1 FROM (
        SELECT c.code,
            coalesce(sum(x.count) FILTER (WHERE x.actual_class = c.code),0)::numeric actual_n,
            coalesce(sum(x.count) FILTER (WHERE x.predicted_class = c.code),0)::numeric predicted_n,
            coalesce(sum(x.count) FILTER (WHERE x.actual_class = c.code AND x.predicted_class = c.code),0)::numeric true_n
        FROM ml_experiments.model_classes c CROSS JOIN ml_experiments.confusion_counts x
        WHERE c.model_id = e.model_id AND x.evaluation_id = e.id GROUP BY c.code
    ) counts;
    IF abs(e.accuracy - coalesce(diagonal,0)/total) > 1e-9 OR abs(e.macro_f1-calculated_f1) > 1e-9 THEN
        RAISE EXCEPTION 'Metrics disagree with confusion counts';
    END IF;
    IF (rest_total = 0 AND e.rest_false_activation_rate IS NOT NULL) OR
       (rest_total > 0 AND (e.rest_false_activation_rate IS NULL OR abs(e.rest_false_activation_rate-rest_false/rest_total) > 1e-9)) THEN
        RAISE EXCEPTION 'Rest false-activation metric is inconsistent';
    END IF;
    RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER validate_run_output AFTER INSERT OR UPDATE ON ml_experiments.experiment_runs
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ml_experiments.validate_run_output();

CREATE FUNCTION ml_experiments.claim_experiment(p_operator uuid, p_worker uuid, p_lease_sha256 text, p_location text, p_seconds integer DEFAULT 120)
RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE k uuid; t timestamptz := clock_timestamp();
BEGIN
    IF p_seconds NOT BETWEEN 10 AND 3600 OR p_location NOT IN ('local_workstation','desktop') OR p_lease_sha256 !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'Invalid lease configuration';
    END IF;
    SELECT id INTO k FROM ml_experiments.experiment_runs
    WHERE operator_id = p_operator AND execution_location = p_location AND status = 'queued'
    ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT 1;
    IF k IS NULL THEN RETURN NULL; END IF;
    UPDATE ml_experiments.experiment_runs SET status = 'running', worker_client_id = p_worker,
        lease_sha256 = p_lease_sha256, started_at = t, heartbeat_at = t, lease_expires_at = t+make_interval(secs=>p_seconds)
    WHERE id = k;
    RETURN k;
END $$;
CREATE FUNCTION ml_experiments.heartbeat_experiment(p_run uuid, p_worker uuid, p_hash text, p_seconds integer DEFAULT 120)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    IF p_seconds NOT BETWEEN 10 AND 3600 THEN RAISE EXCEPTION 'Invalid lease duration'; END IF;
    UPDATE ml_experiments.experiment_runs SET heartbeat_at = clock_timestamp(),
        lease_expires_at = greatest(lease_expires_at, clock_timestamp()+make_interval(secs=>p_seconds))
    WHERE id = p_run AND status = 'running' AND worker_client_id = p_worker AND lease_sha256 = p_hash AND lease_expires_at > clock_timestamp();
    IF NOT FOUND THEN RAISE EXCEPTION 'Unknown, stale or unauthorized worker lease'; END IF;
END $$;
CREATE FUNCTION ml_experiments.finish_experiment(p_run uuid, p_worker uuid, p_hash text, p_status text, p_error text DEFAULT NULL)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    IF p_status NOT IN ('succeeded','failed') THEN RAISE EXCEPTION 'Invalid completion status'; END IF;
    UPDATE ml_experiments.experiment_runs SET status = p_status, completed_at = clock_timestamp(), error = p_error
    WHERE id = p_run AND status = 'running' AND worker_client_id = p_worker AND lease_sha256 = p_hash AND lease_expires_at > clock_timestamp();
    IF NOT FOUND THEN RAISE EXCEPTION 'Unknown, stale or unauthorized worker lease'; END IF;
END $$;
CREATE FUNCTION ml_experiments.interrupt_expired_experiments() RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
    UPDATE ml_experiments.experiment_runs SET status = 'interrupted', completed_at = clock_timestamp(), error = 'Worker lease expired'
    WHERE status = 'running' AND lease_expires_at <= clock_timestamp();
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END $$;

CREATE VIEW ml_experiments.published_models AS
SELECT m.id, m.name, m.run_id, r.operator_id, r.family, r.condition, r.parent_model_id, r.calibration_subset_id,
    r.manifest_id, r.manifest_sha256, r.feature_contract, m.adaptation_method, a.sha256, a.size_bytes, m.published_at
FROM ml_experiments.model_versions m JOIN ml_experiments.experiment_runs r ON r.id = m.run_id
JOIN ml_experiments.artifacts a ON a.id = m.artifact_id WHERE m.state = 'published' AND r.status = 'succeeded';
CREATE VIEW ml_experiments.reviewer_results AS
SELECT e.id, e.model_id, e.run_id, r.family, r.condition, r.manifest_id, r.manifest_sha256,
    r.target_participant_id, r.calibration_subset_id, r.feature_contract, r.seed, r.software_version,
    e.accuracy, e.macro_f1, e.rest_false_activation_rate, e.rest_missing_reason
FROM ml_experiments.evaluations e JOIN ml_experiments.experiment_runs r ON r.id = e.run_id
WHERE r.status = 'succeeded';
COMMENT ON COLUMN ml_experiments.experiment_runs.operator_id IS 'External identity reference. API validates active operator, client ownership and authorization before calling service-owned functions.';
COMMENT ON COLUMN ml_experiments.artifacts.verified_at IS 'Trusted storage verification attestation, not proof of bytes by PostgreSQL.';
