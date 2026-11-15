BEGIN;
DO $$
DECLARE p bigint; sig bigint; m bigint; g bigint; a bigint; b bigint; t bigint; s1 bigint; s2 bigint; invalid bigint;
BEGIN
    INSERT INTO myoprosthesis.participants(pseudonym) VALUES ('calibration-test') RETURNING id INTO p;
    INSERT INTO myoprosthesis.canonical_signals(identity_scheme, identity_value, participant_id, sample_count)
        VALUES ('synthetic', 'calibration-test', p, 1000) RETURNING id INTO sig;
    INSERT INTO myoprosthesis.gestures(code, description) VALUES ('test-rest', 'Synthetic rest') RETURNING id INTO g;
    INSERT INTO myoprosthesis.labelled_segments(signal_id, gesture_id, repetition_key, start_sample, end_sample)
        VALUES (sig, g, 'one', 0, 100) RETURNING id INTO a;
    INSERT INTO myoprosthesis.labelled_segments(signal_id, gesture_id, repetition_key, start_sample, end_sample)
        VALUES (sig, g, 'two', 100, 200) RETURNING id INTO b;
    INSERT INTO myoprosthesis.labelled_segments(signal_id, gesture_id, repetition_key, start_sample, end_sample)
        VALUES (sig, g, 'test', 600, 700) RETURNING id INTO t;
    INSERT INTO myoprosthesis.split_manifests(name, version) VALUES ('calibration-test', 1) RETURNING id INTO m;
    INSERT INTO myoprosthesis.split_participants VALUES (m, p, 'target');
    INSERT INTO myoprosthesis.split_units(manifest_id, participant_id, category, signal_id, start_sample, end_sample, role)
        VALUES (m, p, 'target', sig, 0, 500, 'target_calibration'), (m, p, 'target', sig, 500, 1000, 'target_test');
    CALL myoprosthesis.freeze_manifest(m);
    INSERT INTO myoprosthesis.calibration_subsets(manifest_id, participant_id, budget_per_gesture, selection_version)
        VALUES (m, p, 1, 'v1') RETURNING id INTO s1;
    INSERT INTO myoprosthesis.calibration_items VALUES (s1, a);
    UPDATE myoprosthesis.calibration_subsets SET state = 'frozen' WHERE id = s1;
    INSERT INTO myoprosthesis.calibration_subsets(manifest_id, participant_id, budget_per_gesture, selection_version, parent_id)
        VALUES (m, p, 2, 'v1', s1) RETURNING id INTO s2;
    INSERT INTO myoprosthesis.calibration_items VALUES (s2, a), (s2, b);
    UPDATE myoprosthesis.calibration_subsets SET state = 'frozen' WHERE id = s2;
    INSERT INTO myoprosthesis.calibration_subsets(manifest_id, participant_id, budget_per_gesture, selection_version, parent_id)
        VALUES (m, p, 3, 'v1', s1) RETURNING id INTO invalid;
    INSERT INTO myoprosthesis.calibration_items VALUES (invalid, b);
    BEGIN
        UPDATE myoprosthesis.calibration_subsets SET state = 'frozen' WHERE id = invalid;
        RAISE EXCEPTION 'Non-nested subset accepted';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Non-nested subset accepted' THEN RAISE; END IF;
    END;
    BEGIN
        INSERT INTO myoprosthesis.calibration_items VALUES (invalid, t);
        RAISE EXCEPTION 'Test segment accepted';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Test segment accepted' THEN RAISE; END IF;
    END;
    BEGIN
        DELETE FROM myoprosthesis.calibration_items WHERE subset_id = s1;
        RAISE EXCEPTION 'Frozen subset modified';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Frozen subset modified' THEN RAISE; END IF;
    END;
END $$;
ROLLBACK;
