-- A verification record is an application attestation, not a filesystem check.
CREATE TABLE myoprosthesis.artifact_verifications (
    artifact_id bigint PRIMARY KEY REFERENCES myoprosthesis.artifacts(id) ON DELETE RESTRICT,
    verified_sha256 char(64) NOT NULL CHECK (verified_sha256 ~ '^[0-9a-f]{64}$'),
    verified_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE FUNCTION myoprosthesis.validate_artifact_verification() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM myoprosthesis.artifacts WHERE id = NEW.artifact_id AND sha256 = NEW.verified_sha256 FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Artifact checksum does not match'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER validate_artifact_verification BEFORE INSERT OR UPDATE ON myoprosthesis.artifact_verifications
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.validate_artifact_verification();

CREATE TABLE myoprosthesis.run_inputs (
    run_id bigint NOT NULL REFERENCES myoprosthesis.runs(id) ON DELETE RESTRICT,
    split_unit_id bigint NOT NULL REFERENCES myoprosthesis.split_units(id) ON DELETE RESTRICT,
    PRIMARY KEY (run_id, split_unit_id)
);
CREATE FUNCTION myoprosthesis.guard_run_input() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r myoprosthesis.runs%ROWTYPE; u myoprosthesis.split_units%ROWTYPE;
BEGIN
    IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'Run inputs are immutable'; END IF;
    SELECT * INTO r FROM myoprosthesis.runs WHERE id = NEW.run_id FOR UPDATE;
    SELECT * INTO u FROM myoprosthesis.split_units WHERE id = NEW.split_unit_id;
    IF r.status IS DISTINCT FROM 'queued' OR u.manifest_id IS DISTINCT FROM r.manifest_id OR
       NOT ((r.kind = 'train' AND u.role = 'source_train') OR
            (r.kind = 'adapt' AND u.role IN ('source_train', 'target_calibration')) OR
            (r.kind = 'evaluate' AND u.role = 'target_test')) THEN
        RAISE EXCEPTION 'Run input role or manifest is incompatible';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_run_input BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.run_inputs
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_run_input();

CREATE FUNCTION myoprosthesis.guard_published_artifact() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM myoprosthesis.artifact_verifications WHERE artifact_id = OLD.id) THEN
        RAISE EXCEPTION 'Verified artifact metadata is immutable';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_verified_artifact BEFORE UPDATE OR DELETE ON myoprosthesis.artifacts
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_published_artifact();

CREATE FUNCTION myoprosthesis.guard_verification_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Artifact verification records are immutable';
END $$;
CREATE TRIGGER guard_verification_change BEFORE UPDATE OR DELETE ON myoprosthesis.artifact_verifications
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_verification_change();

CREATE FUNCTION myoprosthesis.validate_run_publication() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE model myoprosthesis.model_versions%ROWTYPE; evaluation myoprosthesis.evaluations%ROWTYPE;
BEGIN
    IF NEW.status <> 'succeeded' OR OLD.status = 'succeeded' THEN RETURN NEW; END IF;
    IF NOT EXISTS (SELECT 1 FROM myoprosthesis.run_inputs WHERE run_id = NEW.id) THEN
        RAISE EXCEPTION 'Successful run requires explicit input units';
    END IF;
    IF NEW.kind IN ('train', 'adapt') THEN
        SELECT * INTO model FROM myoprosthesis.model_versions WHERE run_id = NEW.id;
        IF NOT FOUND OR NOT EXISTS (SELECT 1 FROM myoprosthesis.artifact_verifications WHERE artifact_id = model.artifact_id) THEN
            RAISE EXCEPTION 'Successful model run requires a verified artifact';
        END IF;
        IF (NEW.kind = 'adapt') <> (model.condition = 'personalised') THEN
            RAISE EXCEPTION 'Model condition does not match run kind';
        END IF;
        IF model.calibration_subset_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM myoprosthesis.calibration_subsets c
            WHERE c.id = model.calibration_subset_id AND c.manifest_id = NEW.manifest_id AND c.state = 'frozen'
        ) THEN RAISE EXCEPTION 'Model requires a compatible frozen calibration subset'; END IF;
        IF model.parent_model_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM myoprosthesis.model_versions parent JOIN myoprosthesis.runs parent_run ON parent.run_id = parent_run.id
            WHERE parent.id = model.parent_model_id AND parent.condition = 'source_only' AND parent.family = model.family
              AND parent_run.status = 'succeeded' AND parent_run.manifest_id = NEW.manifest_id
              AND parent_run.feature_config_id = NEW.feature_config_id
        ) THEN RAISE EXCEPTION 'Incompatible parent model'; END IF;
    ELSE
        SELECT * INTO evaluation FROM myoprosthesis.evaluations WHERE run_id = NEW.id;
        IF NOT FOUND OR NOT EXISTS (
            SELECT 1 FROM myoprosthesis.model_versions m JOIN myoprosthesis.runs model_run ON model_run.id = m.run_id
            WHERE m.id = evaluation.model_id AND model_run.status = 'succeeded'
              AND model_run.manifest_id = NEW.manifest_id AND model_run.feature_config_id = NEW.feature_config_id
        ) THEN RAISE EXCEPTION 'Evaluation requires a compatible completed model'; END IF;
        IF EXISTS (SELECT 1 FROM myoprosthesis.run_inputs i JOIN myoprosthesis.split_units u ON u.id = i.split_unit_id
                   WHERE i.run_id = NEW.id AND u.participant_id <> evaluation.participant_id) OR
           EXISTS (SELECT id FROM myoprosthesis.split_units WHERE manifest_id = NEW.manifest_id
                   AND participant_id = evaluation.participant_id AND role = 'target_test'
                   EXCEPT SELECT split_unit_id FROM myoprosthesis.run_inputs WHERE run_id = NEW.id) THEN
            RAISE EXCEPTION 'Evaluation must use the complete frozen target test';
        END IF;
        IF (SELECT count(*) FROM myoprosthesis.evaluation_metrics WHERE evaluation_id = evaluation.id) <> 3 THEN
            RAISE EXCEPTION 'Evaluation requires all metrics, including explicit missing reasons';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER z_validate_run_publication BEFORE UPDATE ON myoprosthesis.runs
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.validate_run_publication();

CREATE VIEW myoprosthesis.completed_evaluations AS
SELECT e.id AS evaluation_id, e.participant_id, e.model_id, r.manifest_id, r.feature_config_id,
       r.id AS run_id, r.software_version, r.seed
FROM myoprosthesis.evaluations e JOIN myoprosthesis.runs r ON r.id = e.run_id
WHERE r.status = 'succeeded';
