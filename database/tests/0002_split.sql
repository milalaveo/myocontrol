BEGIN;
DO $$
DECLARE p bigint; sig bigint; m bigint; bad bigint; unit bigint; v_checksum text;
BEGIN
    INSERT INTO myoprosthesis.participants(pseudonym) VALUES ('split-test') RETURNING id INTO p;
    INSERT INTO myoprosthesis.canonical_signals(identity_scheme, identity_value, participant_id, sample_count)
        VALUES ('synthetic-v1', 'signal', p, 1000) RETURNING id INTO sig;
    INSERT INTO myoprosthesis.split_manifests(name, version) VALUES ('good', 1) RETURNING id INTO m;
    INSERT INTO myoprosthesis.split_participants VALUES (m, p, 'target');
    INSERT INTO myoprosthesis.split_units(manifest_id, participant_id, category, signal_id, start_sample, end_sample, role)
        VALUES (m, p, 'target', sig, 0, 500, 'target_calibration') RETURNING id INTO unit;
    INSERT INTO myoprosthesis.split_units(manifest_id, participant_id, category, signal_id, start_sample, end_sample, role)
        VALUES (m, p, 'target', sig, 500, 1000, 'target_test');
    CALL myoprosthesis.freeze_manifest(m);
    SELECT checksum INTO v_checksum FROM myoprosthesis.split_manifests WHERE id = m;
    IF length(v_checksum) <> 64 THEN RAISE EXCEPTION 'Missing checksum'; END IF;
    BEGIN
        UPDATE myoprosthesis.split_units SET end_sample = 400 WHERE id = unit;
        RAISE EXCEPTION 'Frozen membership was modified';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Frozen membership was modified' THEN RAISE; END IF;
    END;
    BEGIN
        UPDATE myoprosthesis.canonical_signals SET sample_count = 50 WHERE id = sig;
        RAISE EXCEPTION 'Referenced signal was modified';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Referenced signal was modified' THEN RAISE; END IF;
    END;
    INSERT INTO myoprosthesis.split_manifests(name, version) VALUES ('bad', 1) RETURNING id INTO bad;
    INSERT INTO myoprosthesis.split_participants VALUES (bad, p, 'target');
    INSERT INTO myoprosthesis.split_units(manifest_id, participant_id, category, signal_id, start_sample, end_sample, role)
        VALUES (bad, p, 'target', sig, 0, 600, 'target_calibration'), (bad, p, 'target', sig, 500, 1000, 'target_test');
    IF NOT EXISTS (SELECT 1 FROM myoprosthesis.split_conflicts(bad)) THEN RAISE EXCEPTION 'Overlap not detected'; END IF;
    BEGIN
        CALL myoprosthesis.freeze_manifest(bad);
        RAISE EXCEPTION 'Overlapping split was frozen';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Overlapping split was frozen' THEN RAISE; END IF;
    END;
END $$;
ROLLBACK;
