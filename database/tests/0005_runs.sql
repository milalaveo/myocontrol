BEGIN;
DO $$
DECLARE p bigint; sig bigint; m bigint; config bigint; run bigint;
BEGIN
    INSERT INTO myoprosthesis.participants(pseudonym) VALUES ('run-test') RETURNING id INTO p;
    INSERT INTO myoprosthesis.canonical_signals(identity_scheme, identity_value, participant_id, sample_count)
        VALUES ('synthetic', 'run-test', p, 100) RETURNING id INTO sig;
    INSERT INTO myoprosthesis.split_manifests(name, version) VALUES ('run-test', 1) RETURNING id INTO m;
    INSERT INTO myoprosthesis.split_participants VALUES (m, p, 'source');
    INSERT INTO myoprosthesis.split_units(manifest_id, participant_id, category, signal_id, start_sample, end_sample, role)
        VALUES (m, p, 'source', sig, 0, 100, 'source_train');
    CALL myoprosthesis.freeze_manifest(m);
    INSERT INTO myoprosthesis.feature_configs(name, version, schema_version, parameters)
        VALUES ('test', 1, 'v1', '{}') RETURNING id INTO config;
    INSERT INTO myoprosthesis.runs(kind, manifest_id, feature_config_id, seed, parameter_schema_version, parameters, software_version)
        VALUES ('train', m, config, 1, 'v1', '{}', 'test') RETURNING id INTO run;
    BEGIN
        UPDATE myoprosthesis.runs SET status = 'succeeded', started_at = now(), finished_at = now() WHERE id = run;
        RAISE EXCEPTION 'Invalid transition accepted';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Invalid transition accepted' THEN RAISE; END IF;
    END;
    UPDATE myoprosthesis.runs SET status = 'running', started_at = now() WHERE id = run;
    UPDATE myoprosthesis.runs SET status = 'failed', finished_at = now(), failure_reason = 'test' WHERE id = run;
    BEGIN
        UPDATE myoprosthesis.runs SET status = 'running', finished_at = NULL WHERE id = run;
        RAISE EXCEPTION 'Terminal run modified';
    EXCEPTION WHEN raise_exception THEN
        IF SQLERRM = 'Terminal run modified' THEN RAISE; END IF;
    END;
END $$;
ROLLBACK;
