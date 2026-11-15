BEGIN;
DO $$
DECLARE p bigint; sig bigint; m bigint; artifact bigint; gesture bigint; gs bigint; segment bigint; subset bigint; seconds numeric;
BEGIN
    INSERT INTO myoprosthesis.participants(pseudonym) VALUES ('provenance-test') RETURNING id INTO p;
    INSERT INTO myoprosthesis.artifacts(storage_namespace, storage_key, media_type, size_bytes, sha256)
        VALUES ('test', 'source', 'application/octet-stream', 100, repeat('a', 64)) RETURNING id INTO artifact;
    INSERT INTO myoprosthesis.canonical_signals(identity_scheme, identity_value, participant_id, sample_count)
        VALUES ('synthetic', 'provenance-test', p, 100) RETURNING id INTO sig;
    INSERT INTO myoprosthesis.split_manifests(name, version) VALUES ('provenance-test', 1) RETURNING id INTO m;
    INSERT INTO myoprosthesis.split_participants VALUES (m, p, 'target');
    INSERT INTO myoprosthesis.split_units(manifest_id, participant_id, category, signal_id, start_sample, end_sample, role)
        VALUES (m, p, 'target', sig, 0, 100, 'target_calibration');
    BEGIN
        CALL myoprosthesis.freeze_manifest(m);
        RAISE EXCEPTION 'Missing provenance accepted';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Missing provenance accepted' THEN RAISE; END IF;
    END;
    INSERT INTO myoprosthesis.signal_provenance VALUES (sig, artifact, 10, 'synthetic-v1');
    CALL myoprosthesis.freeze_manifest(m);
    BEGIN
        UPDATE myoprosthesis.artifacts SET sha256 = repeat('b', 64) WHERE id = artifact;
        RAISE EXCEPTION 'Referenced artifact was modified';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Referenced artifact was modified' THEN RAISE; END IF;
    END;
    INSERT INTO myoprosthesis.gestures(code, description) VALUES ('provenance-rest', 'rest') RETURNING id INTO gesture;
    INSERT INTO myoprosthesis.gesture_sets(name, version) VALUES ('provenance-set', 1) RETURNING id INTO gs;
    INSERT INTO myoprosthesis.gesture_set_members VALUES (gs, gesture, true);
    INSERT INTO myoprosthesis.labelled_segments(signal_id, gesture_id, repetition_key, start_sample, end_sample)
        VALUES (sig, gesture, 'one', 0, 20) RETURNING id INTO segment;
    INSERT INTO myoprosthesis.calibration_subsets(manifest_id, participant_id, budget_per_gesture, selection_version, gesture_set_id)
        VALUES (m, p, 1, 'v1', gs) RETURNING id INTO subset;
    INSERT INTO myoprosthesis.calibration_items VALUES (subset, segment);
    UPDATE myoprosthesis.calibration_subsets SET state = 'frozen' WHERE id = subset;
    SELECT unique_seconds INTO seconds FROM myoprosthesis.calibration_durations WHERE subset_id = subset;
    IF seconds <> 2 THEN RAISE EXCEPTION 'Unexpected duration: %', seconds; END IF;
END $$;
ROLLBACK;
