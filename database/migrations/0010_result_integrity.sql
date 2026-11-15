CREATE OR REPLACE FUNCTION myoprosthesis.guard_run_input() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r myoprosthesis.runs%ROWTYPE; u myoprosthesis.split_units%ROWTYPE;
BEGIN
    IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'Run inputs are immutable'; END IF;
    SELECT * INTO r FROM myoprosthesis.runs WHERE id = NEW.run_id FOR UPDATE;
    SELECT * INTO u FROM myoprosthesis.split_units WHERE id = NEW.split_unit_id;
    IF r.status IS DISTINCT FROM 'queued' OR u.manifest_id IS DISTINCT FROM r.manifest_id OR
       NOT ((r.kind IN ('train', 'adapt') AND u.role IN ('source_train', 'target_calibration')) OR
            (r.kind = 'evaluate' AND u.role = 'target_test')) THEN
        RAISE EXCEPTION 'Run input role or manifest is incompatible';
    END IF;
    RETURN NEW;
END $$;

CREATE FUNCTION myoprosthesis.guard_result_row() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r_id bigint; r_state text;
BEGIN
    IF TG_TABLE_NAME IN ('model_versions', 'evaluations') THEN
        IF TG_OP = 'INSERT' THEN r_id := NEW.run_id; ELSE r_id := OLD.run_id; END IF;
        IF TG_OP = 'UPDATE' AND NEW.run_id <> OLD.run_id THEN RAISE EXCEPTION 'Result run cannot be changed'; END IF;
    ELSE
        IF TG_OP = 'INSERT' THEN
            SELECT run_id INTO r_id FROM myoprosthesis.evaluations WHERE id = NEW.evaluation_id;
        ELSE
            SELECT run_id INTO r_id FROM myoprosthesis.evaluations WHERE id = OLD.evaluation_id;
            IF TG_OP = 'UPDATE' AND NEW.evaluation_id <> OLD.evaluation_id THEN RAISE EXCEPTION 'Evaluation cannot be changed'; END IF;
        END IF;
    END IF;
    SELECT status INTO r_state FROM myoprosthesis.runs WHERE id = r_id FOR UPDATE;
    IF r_state IS DISTINCT FROM 'running' THEN RAISE EXCEPTION 'Results may only change while the run is running'; END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_model_result BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.model_versions
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_result_row();
CREATE TRIGGER guard_evaluation_result BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.evaluations
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_result_row();
CREATE TRIGGER guard_metric_result BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.evaluation_metrics
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_result_row();
CREATE TRIGGER guard_confusion_result BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.confusion_counts
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_result_row();

CREATE FUNCTION myoprosthesis.guard_model_input_roles() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE model myoprosthesis.model_versions%ROWTYPE;
BEGIN
    IF NEW.status = 'succeeded' AND NEW.kind IN ('train', 'adapt') THEN
        SELECT * INTO model FROM myoprosthesis.model_versions WHERE run_id = NEW.id;
        IF model.condition = 'source_only' AND EXISTS (
            SELECT 1 FROM myoprosthesis.run_inputs i JOIN myoprosthesis.split_units u ON u.id = i.split_unit_id
            WHERE i.run_id = NEW.id AND u.role <> 'source_train'
        ) THEN RAISE EXCEPTION 'Source-only model cannot use target data'; END IF;
        IF model.condition = 'target_only' AND EXISTS (
            SELECT 1 FROM myoprosthesis.run_inputs i JOIN myoprosthesis.split_units u ON u.id = i.split_unit_id
            JOIN myoprosthesis.calibration_subsets c ON c.id = model.calibration_subset_id
            WHERE i.run_id = NEW.id AND (u.role <> 'target_calibration' OR u.participant_id <> c.participant_id)
        ) THEN RAISE EXCEPTION 'Target-only model has incompatible inputs'; END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER zz_guard_model_input_roles BEFORE UPDATE ON myoprosthesis.runs
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_model_input_roles();

CREATE FUNCTION myoprosthesis.guard_used_feature_config() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM myoprosthesis.runs WHERE feature_config_id = OLD.id) THEN
        RAISE EXCEPTION 'A feature configuration referenced by a run is immutable';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_used_feature_config BEFORE UPDATE OR DELETE ON myoprosthesis.feature_configs
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_used_feature_config();
