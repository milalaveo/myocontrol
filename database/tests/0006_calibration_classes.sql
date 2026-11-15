BEGIN;
DO $$
DECLARE p bigint; sig bigint; m bigint; g1 bigint; g2 bigint; a bigint; b bigint; subset bigint; gs bigint;
BEGIN
    INSERT INTO myoprosthesis.participants(pseudonym) VALUES ('classes-test') RETURNING id INTO p;
    INSERT INTO myoprosthesis.canonical_signals(identity_scheme, identity_value, participant_id, sample_count)
        VALUES ('synthetic', 'classes-test', p, 100) RETURNING id INTO sig;
    INSERT INTO myoprosthesis.gestures(code, description) VALUES ('classes-rest', 'Rest') RETURNING id INTO g1;
    INSERT INTO myoprosthesis.gestures(code, description) VALUES ('classes-fist', 'Fist') RETURNING id INTO g2;
    INSERT INTO myoprosthesis.gesture_sets(name, version) VALUES ('classes-test', 1) RETURNING id INTO gs;
    INSERT INTO myoprosthesis.gesture_set_members VALUES (gs, g1, true), (gs, g2, false);
    INSERT INTO myoprosthesis.labelled_segments(signal_id, gesture_id, repetition_key, start_sample, end_sample)
        VALUES (sig, g1, 'rest', 0, 10) RETURNING id INTO a;
    INSERT INTO myoprosthesis.labelled_segments(signal_id, gesture_id, repetition_key, start_sample, end_sample)
        VALUES (sig, g2, 'fist', 10, 20) RETURNING id INTO b;
    INSERT INTO myoprosthesis.split_manifests(name, version) VALUES ('classes-test', 1) RETURNING id INTO m;
    INSERT INTO myoprosthesis.split_participants VALUES (m, p, 'target');
    INSERT INTO myoprosthesis.split_units(manifest_id, participant_id, category, signal_id, start_sample, end_sample, role)
        VALUES (m, p, 'target', sig, 0, 50, 'target_calibration');
    CALL myoprosthesis.freeze_manifest(m);
    INSERT INTO myoprosthesis.calibration_subsets(manifest_id, participant_id, budget_per_gesture, selection_version, gesture_set_id)
        VALUES (m, p, 1, 'v1', gs) RETURNING id INTO subset;
    INSERT INTO myoprosthesis.calibration_items VALUES (subset, a);
    BEGIN
        UPDATE myoprosthesis.calibration_subsets SET state = 'frozen' WHERE id = subset;
        RAISE EXCEPTION 'Missing gesture accepted';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Missing gesture accepted' THEN RAISE; END IF;
    END;
    INSERT INTO myoprosthesis.calibration_items VALUES (subset, b);
    UPDATE myoprosthesis.calibration_subsets SET state = 'frozen' WHERE id = subset;
    IF (SELECT count(*) FROM myoprosthesis.calibration_samples WHERE subset_id = subset) <> 2 THEN
        RAISE EXCEPTION 'Missing per-class sample summary';
    END IF;
    BEGIN
        DELETE FROM myoprosthesis.gesture_set_members WHERE gesture_set_id = gs AND gesture_id = g1;
        RAISE EXCEPTION 'Frozen gesture set changed';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Frozen gesture set changed' THEN RAISE; END IF;
    END;
END $$;
ROLLBACK;
