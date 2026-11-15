BEGIN;
DO $$
DECLARE p bigint; sig bigint; m bigint; g bigint; a bigint; b bigint; low_budget bigint; high_budget bigint;
BEGIN
    INSERT INTO myoprosthesis.participants(pseudonym) VALUES ('nesting-test') RETURNING id INTO p;
    INSERT INTO myoprosthesis.canonical_signals(identity_scheme, identity_value, participant_id, sample_count)
        VALUES ('synthetic', 'nesting-test', p, 100) RETURNING id INTO sig;
    INSERT INTO myoprosthesis.gestures(code, description) VALUES ('nesting-rest', 'Synthetic') RETURNING id INTO g;
    INSERT INTO myoprosthesis.labelled_segments(signal_id, gesture_id, repetition_key, start_sample, end_sample)
        VALUES (sig, g, 'a', 0, 10) RETURNING id INTO a;
    INSERT INTO myoprosthesis.labelled_segments(signal_id, gesture_id, repetition_key, start_sample, end_sample)
        VALUES (sig, g, 'b', 10, 20) RETURNING id INTO b;
    INSERT INTO myoprosthesis.split_manifests(name, version) VALUES ('nesting-test', 1) RETURNING id INTO m;
    INSERT INTO myoprosthesis.split_participants VALUES (m, p, 'target');
    INSERT INTO myoprosthesis.split_units(manifest_id, participant_id, category, signal_id, start_sample, end_sample, role)
        VALUES (m, p, 'target', sig, 0, 50, 'target_calibration');
    CALL myoprosthesis.freeze_manifest(m);
    INSERT INTO myoprosthesis.calibration_subsets(manifest_id, participant_id, budget_per_gesture, selection_version)
        VALUES (m, p, 1, 'v1') RETURNING id INTO low_budget;
    INSERT INTO myoprosthesis.calibration_items VALUES (low_budget, a);
    UPDATE myoprosthesis.calibration_subsets SET state = 'frozen' WHERE id = low_budget;
    INSERT INTO myoprosthesis.calibration_subsets(manifest_id, participant_id, budget_per_gesture, selection_version)
        VALUES (m, p, 2, 'v1') RETURNING id INTO high_budget;
    INSERT INTO myoprosthesis.calibration_items VALUES (high_budget, b);
    BEGIN
        UPDATE myoprosthesis.calibration_subsets SET state = 'frozen' WHERE id = high_budget;
        RAISE EXCEPTION 'Independent non-nested subset accepted';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Independent non-nested subset accepted' THEN RAISE; END IF;
    END;
END $$;
ROLLBACK;
