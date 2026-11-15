BEGIN;
DO $$
DECLARE source_person bigint; target_person bigint; source_signal bigint; target_signal bigint;
        input_artifact bigint; model_artifact bigint; manifest bigint; train_unit bigint; test_unit bigint;
        config bigint; training bigint; evaluating bigint; model bigint; evaluation bigint;
        gesture bigint; gesture_set bigint; protocol bigint;
BEGIN
    INSERT INTO myoprosthesis.gestures(code, description) VALUES ('publication-rest', 'Rest') RETURNING id INTO gesture;
    INSERT INTO myoprosthesis.gesture_sets(name, version) VALUES ('publication-gestures', 1) RETURNING id INTO gesture_set;
    INSERT INTO myoprosthesis.gesture_set_members VALUES (gesture_set, gesture, true);
    INSERT INTO myoprosthesis.protocol_versions(name, version, gesture_set_id, schema_version, configuration)
        VALUES ('publication-protocol', 1, gesture_set, 'v1', '{}') RETURNING id INTO protocol;
    INSERT INTO myoprosthesis.participants(pseudonym) VALUES ('publication-source') RETURNING id INTO source_person;
    INSERT INTO myoprosthesis.participants(pseudonym) VALUES ('publication-target') RETURNING id INTO target_person;
    INSERT INTO myoprosthesis.artifacts(storage_namespace, storage_key, media_type, size_bytes, sha256)
        VALUES ('test', 'input-publication', 'application/octet-stream', 10, repeat('a', 64)) RETURNING id INTO input_artifact;
    INSERT INTO myoprosthesis.artifacts(storage_namespace, storage_key, media_type, size_bytes, sha256)
        VALUES ('test', 'model-publication', 'application/octet-stream', 10, repeat('b', 64)) RETURNING id INTO model_artifact;
    INSERT INTO myoprosthesis.canonical_signals(identity_scheme, identity_value, participant_id, sample_count)
        VALUES ('synthetic', 'publication-source', source_person, 100) RETURNING id INTO source_signal;
    INSERT INTO myoprosthesis.canonical_signals(identity_scheme, identity_value, participant_id, sample_count)
        VALUES ('synthetic', 'publication-target', target_person, 100) RETURNING id INTO target_signal;
    INSERT INTO myoprosthesis.signal_provenance VALUES (source_signal, input_artifact, 10, 'synthetic-v1'), (target_signal, input_artifact, 10, 'synthetic-v1');
    INSERT INTO myoprosthesis.split_manifests(name, version, protocol_id) VALUES ('publication-test', 1, protocol) RETURNING id INTO manifest;
    INSERT INTO myoprosthesis.split_participants VALUES (manifest, source_person, 'source'), (manifest, target_person, 'target');
    INSERT INTO myoprosthesis.split_units(manifest_id, participant_id, category, signal_id, start_sample, end_sample, role)
        VALUES (manifest, source_person, 'source', source_signal, 0, 100, 'source_train') RETURNING id INTO train_unit;
    INSERT INTO myoprosthesis.split_units(manifest_id, participant_id, category, signal_id, start_sample, end_sample, role)
        VALUES (manifest, target_person, 'target', target_signal, 0, 100, 'target_test') RETURNING id INTO test_unit;
    CALL myoprosthesis.freeze_manifest(manifest);
    INSERT INTO myoprosthesis.feature_configs(name, version, schema_version, parameters) VALUES ('publication-test', 1, 'v1', '{}') RETURNING id INTO config;
    INSERT INTO myoprosthesis.runs(kind, manifest_id, feature_config_id, seed, parameter_schema_version, parameters, software_version)
        VALUES ('train', manifest, config, 1, 'v1', '{}', 'test') RETURNING id INTO training;
    INSERT INTO myoprosthesis.run_inputs VALUES (training, train_unit);
    UPDATE myoprosthesis.runs SET status = 'running', started_at = now() WHERE id = training;
    INSERT INTO myoprosthesis.model_versions(run_id, family, condition, artifact_id) VALUES (training, 'lda', 'source_only', model_artifact) RETURNING id INTO model;
    BEGIN
        UPDATE myoprosthesis.runs SET status = 'succeeded', finished_at = now() WHERE id = training;
        RAISE EXCEPTION 'Unverified model was published';
    EXCEPTION WHEN raise_exception THEN IF SQLERRM = 'Unverified model was published' THEN RAISE; END IF; END;
    INSERT INTO myoprosthesis.artifact_verifications(artifact_id, verified_sha256) VALUES (model_artifact, repeat('b', 64));
    UPDATE myoprosthesis.runs SET status = 'succeeded', finished_at = now() WHERE id = training;
    BEGIN
        UPDATE myoprosthesis.model_versions SET family = 'svm' WHERE id = model;
        RAISE EXCEPTION 'Published model changed';
    EXCEPTION WHEN raise_exception THEN IF SQLERRM = 'Published model changed' THEN RAISE; END IF; END;
    INSERT INTO myoprosthesis.runs(kind, manifest_id, feature_config_id, seed, parameter_schema_version, parameters, software_version)
        VALUES ('evaluate', manifest, config, 1, 'v1', '{}', 'test') RETURNING id INTO evaluating;
    INSERT INTO myoprosthesis.run_inputs VALUES (evaluating, test_unit);
    UPDATE myoprosthesis.runs SET status = 'running', started_at = now() WHERE id = evaluating;
    INSERT INTO myoprosthesis.evaluations(run_id, model_id, participant_id) VALUES (evaluating, model, target_person) RETURNING id INTO evaluation;
    INSERT INTO myoprosthesis.evaluation_metrics(evaluation_id, metric, value) VALUES
        (evaluation, 'macro_f1', 0.5), (evaluation, 'accuracy', 0.5), (evaluation, 'rest_false_activation_rate', 0.2);
    UPDATE myoprosthesis.runs SET status = 'succeeded', finished_at = now() WHERE id = evaluating;
    IF NOT EXISTS (SELECT 1 FROM myoprosthesis.completed_evaluations WHERE evaluation_id = evaluation) THEN
        RAISE EXCEPTION 'Completed evaluation missing';
    END IF;
    BEGIN
        UPDATE myoprosthesis.evaluation_metrics SET value = 1 WHERE evaluation_id = evaluation AND metric = 'accuracy';
        RAISE EXCEPTION 'Published metric changed';
    EXCEPTION WHEN raise_exception THEN IF SQLERRM = 'Published metric changed' THEN RAISE; END IF; END;
END $$;
ROLLBACK;
