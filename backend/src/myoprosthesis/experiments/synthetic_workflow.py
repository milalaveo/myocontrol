"""Rehearse the database and artifact path with explicitly synthetic data."""

import hashlib
import uuid

from myoprosthesis.persistence.publication import publish_source_model


def run_synthetic_rehearsal(connection, store):
    """Create a synthetic input, frozen split, mock model and mock evaluation.

    This exercises persistence only: no classifier is trained and the placeholder
    metrics are not experimental results. Use a disposable database and store.
    """
    token = uuid.uuid4().hex
    def synthetic_signal(label):
        rows = ["ch0,ch1,ch2,ch3"]
        for sample in range(100):
            values = hashlib.sha256(f"{token}:{label}:{sample}".encode("ascii")).digest()
            rows.append(",".join(str(values[channel] - 128) for channel in range(4)))
        return ("\n".join(rows) + "\n").encode("ascii")

    signal_artifacts = [store.put(synthetic_signal(label)) for label in ("source", "target")]
    with connection.transaction():
        with connection.cursor() as c:
            def insert(query, params=()):
                c.execute(query, params)
                return c.fetchone()[0]

            dataset = insert("INSERT INTO myoprosthesis.datasets(name) VALUES (%s) RETURNING id", (f"synthetic-{token}",))
            version = insert("INSERT INTO myoprosthesis.dataset_versions(dataset_id, version) VALUES (%s, '1') RETURNING id", (dataset,))
            source = insert("INSERT INTO myoprosthesis.participants(pseudonym) VALUES (%s) RETURNING id", (f"source-{token}",))
            target = insert("INSERT INTO myoprosthesis.participants(pseudonym) VALUES (%s) RETURNING id", (f"target-{token}",))
            c.execute("INSERT INTO myoprosthesis.participant_source_ids(participant_id, dataset_version_id, source_id) VALUES (%s, %s, 'source'), (%s, %s, 'target')", (source, version, target, version))
            signals = []
            for (participant, label), signal_artifact in zip(((source, "source"), (target, "target")), signal_artifacts):
                c.execute("INSERT INTO myoprosthesis.artifacts(storage_namespace, storage_key, media_type, size_bytes, sha256) VALUES ('local', %s, 'text/csv', %s, %s) ON CONFLICT (storage_namespace, storage_key) DO NOTHING", (signal_artifact.key, signal_artifact.size_bytes, signal_artifact.sha256))
                c.execute("SELECT id, size_bytes, sha256 FROM myoprosthesis.artifacts WHERE storage_namespace = 'local' AND storage_key = %s", (signal_artifact.key,))
                artifact, size, digest = c.fetchone()
                if (size, digest) != (signal_artifact.size_bytes, signal_artifact.sha256):
                    raise ValueError("Signal artifact metadata mismatch")
                session = insert("INSERT INTO myoprosthesis.recording_sessions(participant_id, dataset_version_id, mode, status, started_at, ended_at) VALUES (%s, %s, 'import', 'completed', now(), now()) RETURNING id", (participant, version))
                signal = insert("INSERT INTO myoprosthesis.canonical_signals(identity_scheme, identity_value, participant_id, sample_count) VALUES ('synthetic-v1', %s, %s, 100) RETURNING id", (f"{token}-{label}", participant))
                c.execute("INSERT INTO myoprosthesis.signal_provenance VALUES (%s, %s, 100, 'synthetic-v1')", (signal, artifact))
                recording = insert("INSERT INTO myoprosthesis.recordings(session_id, artifact_id, source_external_key, sample_rate_hz, sample_count, canonical_signal_id) VALUES (%s, %s, %s, 100, 100, %s) RETURNING id", (session, artifact, label, signal))
                c.execute("INSERT INTO myoprosthesis.source_recording_keys VALUES (%s, %s, %s)", (version, label, recording))
                for position in range(4):
                    c.execute("INSERT INTO myoprosthesis.recording_channels(recording_id, position, source_channel_id) VALUES (%s, %s, %s)", (recording, position, str(position)))
                signals.append(signal)
            gesture = insert("INSERT INTO myoprosthesis.gestures(code, description) VALUES (%s, 'Synthetic rest') RETURNING id", (f"rest-{token}",))
            c.execute("INSERT INTO myoprosthesis.labelled_segments(signal_id, gesture_id, repetition_key, start_sample, end_sample) VALUES (%s, %s, 'synthetic-rest', 0, 100), (%s, %s, 'synthetic-rest', 0, 100)", (signals[0], gesture, signals[1], gesture))
            gesture_set = insert("INSERT INTO myoprosthesis.gesture_sets(name, version) VALUES (%s, 1) RETURNING id", (f"synthetic-{token}",))
            c.execute("INSERT INTO myoprosthesis.gesture_set_members VALUES (%s, %s, true)", (gesture_set, gesture))
            protocol = insert("INSERT INTO myoprosthesis.protocol_versions(name, version, gesture_set_id, schema_version, configuration) VALUES (%s, 1, %s, 'synthetic-v1', %s::jsonb) RETURNING id", (f"synthetic-{token}", gesture_set, '{"synthetic": true}'))
            manifest = insert("INSERT INTO myoprosthesis.split_manifests(name, version, protocol_id) VALUES (%s, 1, %s) RETURNING id", (f"synthetic-{token}", protocol))
            c.execute("INSERT INTO myoprosthesis.split_participants VALUES (%s, %s, 'source'), (%s, %s, 'target')", (manifest, source, manifest, target))
            train_unit = insert("INSERT INTO myoprosthesis.split_units(manifest_id, participant_id, category, signal_id, start_sample, end_sample, role) VALUES (%s, %s, 'source', %s, 0, 100, 'source_train') RETURNING id", (manifest, source, signals[0]))
            test_unit = insert("INSERT INTO myoprosthesis.split_units(manifest_id, participant_id, category, signal_id, start_sample, end_sample, role) VALUES (%s, %s, 'target', %s, 0, 100, 'target_test') RETURNING id", (manifest, target, signals[1]))
            c.execute("CALL myoprosthesis.freeze_manifest(%s)", (manifest,))
            config = insert("INSERT INTO myoprosthesis.feature_configs(name, version, schema_version, parameters) VALUES (%s, 1, 'synthetic-v1', %s::jsonb) RETURNING id", (f"synthetic-{token}", '{"synthetic": true}'))
            training = insert("INSERT INTO myoprosthesis.runs(kind, manifest_id, feature_config_id, seed, parameter_schema_version, parameters, software_version) VALUES ('train', %s, %s, 0, 'synthetic-v1', %s::jsonb, 'synthetic-rehearsal') RETURNING id", (manifest, config, '{"synthetic": true}'))
            c.execute("INSERT INTO myoprosthesis.run_inputs VALUES (%s, %s)", (training, train_unit))
            c.execute("UPDATE myoprosthesis.runs SET status = 'running', started_at = clock_timestamp() WHERE id = %s", (training,))

    model = publish_source_model(connection, store, training, "lda", b"synthetic-placeholder-model-v1")
    with connection.transaction():
        with connection.cursor() as c:
            c.execute("INSERT INTO myoprosthesis.runs(kind, manifest_id, feature_config_id, seed, parameter_schema_version, parameters, software_version) VALUES ('evaluate', %s, %s, 0, 'synthetic-v1', %s::jsonb, 'synthetic-rehearsal') RETURNING id", (manifest, config, '{"synthetic": true}'))
            evaluation_run = c.fetchone()[0]
            c.execute("INSERT INTO myoprosthesis.run_inputs VALUES (%s, %s)", (evaluation_run, test_unit))
            c.execute("UPDATE myoprosthesis.runs SET status = 'running', started_at = clock_timestamp() WHERE id = %s", (evaluation_run,))
            c.execute("INSERT INTO myoprosthesis.evaluations(run_id, model_id, participant_id) VALUES (%s, %s, %s) RETURNING id", (evaluation_run, model, target))
            evaluation = c.fetchone()[0]
            c.execute("INSERT INTO myoprosthesis.evaluation_metrics(evaluation_id, metric, missing_reason) VALUES (%s, 'macro_f1', 'synthetic rehearsal'), (%s, 'accuracy', 'synthetic rehearsal'), (%s, 'rest_false_activation_rate', 'synthetic rehearsal')", (evaluation, evaluation, evaluation))
            c.execute("INSERT INTO myoprosthesis.confusion_counts VALUES (%s, %s, %s, 0)", (evaluation, gesture, gesture))
            c.execute("UPDATE myoprosthesis.runs SET status = 'succeeded', finished_at = clock_timestamp() WHERE id = %s", (evaluation_run,))
    return {"manifest_id": manifest, "model_id": model, "evaluation_id": evaluation, "synthetic": True}


def main():
    import argparse
    import json
    import os
    from pathlib import Path

    import psycopg
    from myoprosthesis.persistence.artifacts import LocalArtifactStore

    parser = argparse.ArgumentParser(description="Run a synthetic persistence rehearsal on a disposable database.")
    parser.add_argument("--store", type=Path, required=True, help="Local artifact storage directory")
    args = parser.parse_args()
    dsn = os.environ.get("TEST_DATABASE_URL")
    if not dsn:
        parser.error("Set TEST_DATABASE_URL to a disposable PostgreSQL database")
    with psycopg.connect(dsn, autocommit=True) as connection:
        print(json.dumps(run_synthetic_rehearsal(connection, LocalArtifactStore(args.store))))


if __name__ == "__main__":
    main()
