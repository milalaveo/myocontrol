CREATE FUNCTION myoprosthesis.validate_condition_inputs() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE model myoprosthesis.model_versions%ROWTYPE; target_id bigint;
BEGIN
    IF NEW.status <> 'succeeded' OR NEW.kind NOT IN ('train', 'adapt') THEN RETURN NEW; END IF;
    SELECT * INTO model FROM myoprosthesis.model_versions WHERE run_id = NEW.id;
    IF model.calibration_subset_id IS NOT NULL THEN
        SELECT participant_id INTO target_id FROM myoprosthesis.calibration_subsets WHERE id = model.calibration_subset_id;
        IF NOT EXISTS (SELECT 1 FROM myoprosthesis.run_inputs i JOIN myoprosthesis.split_units u ON u.id = i.split_unit_id
                       WHERE i.run_id = NEW.id AND u.role = 'target_calibration' AND u.participant_id = target_id) OR
           EXISTS (SELECT 1 FROM myoprosthesis.run_inputs i JOIN myoprosthesis.split_units u ON u.id = i.split_unit_id
                   WHERE i.run_id = NEW.id AND u.role = 'target_calibration' AND u.participant_id <> target_id) THEN
            RAISE EXCEPTION 'Calibration inputs must belong to the subset participant';
        END IF;
        IF EXISTS (
            SELECT 1 FROM myoprosthesis.run_calibration_items ci JOIN myoprosthesis.labelled_segments s ON s.id = ci.segment_id
            WHERE ci.run_id = NEW.id AND NOT EXISTS (
                SELECT 1 FROM myoprosthesis.run_inputs i JOIN myoprosthesis.split_units u ON u.id = i.split_unit_id
                WHERE i.run_id = NEW.id AND u.signal_id = s.signal_id AND u.role = 'target_calibration'
                  AND s.start_sample >= u.start_sample AND s.end_sample <= u.end_sample)
        ) THEN RAISE EXCEPTION 'Calibration segment is not covered by declared run inputs'; END IF;
    END IF;
    IF model.condition = 'personalised' AND NOT EXISTS (
        SELECT 1 FROM myoprosthesis.run_inputs i JOIN myoprosthesis.split_units u ON u.id = i.split_unit_id
        WHERE i.run_id = NEW.id AND u.role = 'source_train'
    ) THEN RAISE EXCEPTION 'Personalised run requires source inputs'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER zzzz_validate_condition_inputs BEFORE UPDATE ON myoprosthesis.runs
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.validate_condition_inputs();

CREATE FUNCTION myoprosthesis.validate_evaluation_class_set() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE ev myoprosthesis.evaluations%ROWTYPE; set_id bigint; expected bigint; actual bigint; subset_participant bigint;
BEGIN
    IF NEW.status <> 'succeeded' OR NEW.kind <> 'evaluate' THEN RETURN NEW; END IF;
    SELECT * INTO ev FROM myoprosthesis.evaluations WHERE run_id = NEW.id;
    SELECT p.gesture_set_id INTO set_id FROM myoprosthesis.split_manifests m
      JOIN myoprosthesis.protocol_versions p ON p.id = m.protocol_id WHERE m.id = NEW.manifest_id;
    SELECT count(*) INTO expected FROM myoprosthesis.gesture_set_members WHERE gesture_set_id = set_id;
    IF expected = 0 THEN RAISE EXCEPTION 'Evaluation requires a fixed gesture set'; END IF;
    SELECT count(*) INTO actual FROM myoprosthesis.confusion_counts WHERE evaluation_id = ev.id;
    IF actual <> expected * expected OR EXISTS (
        SELECT 1 FROM myoprosthesis.confusion_counts c WHERE c.evaluation_id = ev.id AND
        (NOT EXISTS (SELECT 1 FROM myoprosthesis.gesture_set_members gm WHERE gm.gesture_set_id = set_id AND gm.gesture_id = c.actual_gesture_id)
         OR NOT EXISTS (SELECT 1 FROM myoprosthesis.gesture_set_members gm WHERE gm.gesture_set_id = set_id AND gm.gesture_id = c.predicted_gesture_id))
    ) THEN RAISE EXCEPTION 'Confusion matrix must contain every gesture pair in the protocol'; END IF;
    SELECT c.participant_id INTO subset_participant FROM myoprosthesis.model_versions model
      JOIN myoprosthesis.calibration_subsets c ON c.id = model.calibration_subset_id WHERE model.id = ev.model_id;
    IF subset_participant IS NOT NULL AND subset_participant <> ev.participant_id THEN
        RAISE EXCEPTION 'Model calibration participant does not match evaluation target';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER zzzz_validate_evaluation_class_set BEFORE UPDATE ON myoprosthesis.runs
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.validate_evaluation_class_set();
