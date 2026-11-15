"""Exercise manifest lock ordering against a disposable PostgreSQL database."""

import os
import threading
import time
import uuid

import psycopg


def main():
    dsn = os.environ["TEST_DATABASE_URL"]
    token = uuid.uuid4().hex
    with psycopg.connect(dsn) as connection:
        with connection.cursor() as cursor:
            cursor.execute("INSERT INTO myoprosthesis.participants(pseudonym) VALUES (%s) RETURNING id", (token,))
            participant = cursor.fetchone()[0]
            cursor.execute("INSERT INTO myoprosthesis.canonical_signals(identity_scheme, identity_value, participant_id, sample_count) VALUES ('test', %s, %s, 100) RETURNING id", (token, participant))
            signal = cursor.fetchone()[0]
            cursor.execute("INSERT INTO myoprosthesis.split_manifests(name, version) VALUES (%s, 1) RETURNING id", (token,))
            manifest = cursor.fetchone()[0]
            cursor.execute("INSERT INTO myoprosthesis.split_participants VALUES (%s, %s, 'target')", (manifest, participant))
            cursor.execute("INSERT INTO myoprosthesis.split_units(manifest_id, participant_id, category, signal_id, start_sample, end_sample, role) VALUES (%s, %s, 'target', %s, 0, 50, 'target_calibration')", (manifest, participant, signal))

    attempted = threading.Event()
    outcome = []
    with psycopg.connect(dsn) as freezer:
        freezer.execute("CALL myoprosthesis.freeze_manifest(%s)", (manifest,))

        def mutate():
            try:
                with psycopg.connect(dsn, connect_timeout=5) as connection:
                    connection.execute("SET LOCAL lock_timeout = '5s'")
                    connection.execute("SELECT set_config('application_name', %s, true)", (token,))
                    attempted.set()
                    connection.execute("INSERT INTO myoprosthesis.split_units(manifest_id, participant_id, category, signal_id, start_sample, end_sample, role) VALUES (%s, %s, 'target', %s, 50, 100, 'target_test')", (manifest, participant, signal))
                outcome.append("accepted")
            except psycopg.Error as error:
                outcome.append(error.diag.message_primary)

        thread = threading.Thread(target=mutate)
        thread.start()
        assert attempted.wait(5), "Mutation did not start"
        deadline = time.monotonic() + 3
        with psycopg.connect(dsn) as observer:
            while time.monotonic() < deadline:
                waiting = observer.execute("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE application_name = %s AND wait_event_type = 'Lock')", (token,)).fetchone()[0]
                if waiting:
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("Mutation did not wait for the manifest lock")
        freezer.commit()
        thread.join(10)
        assert not thread.is_alive(), "Mutation did not finish"
    assert len(outcome) == 1 and "not an editable draft" in outcome[0], outcome
    with psycopg.connect(dsn) as connection:
        state, count = connection.execute("SELECT state, (SELECT count(*) FROM myoprosthesis.split_units WHERE manifest_id = %s) FROM myoprosthesis.split_manifests WHERE id = %s", (manifest, manifest)).fetchone()
        assert (state, count) == ("frozen", 1), (state, count)

    # Mutation holds the manifest lock first; freeze must see its committed overlap.
    with psycopg.connect(dsn) as connection:
        second = connection.execute("INSERT INTO myoprosthesis.split_manifests(name, version) VALUES (%s, 1) RETURNING id", (token + '-reverse',)).fetchone()[0]
        connection.execute("INSERT INTO myoprosthesis.split_participants VALUES (%s, %s, 'target')", (second, participant))
        connection.execute("INSERT INTO myoprosthesis.split_units(manifest_id, participant_id, category, signal_id, start_sample, end_sample, role) VALUES (%s, %s, 'target', %s, 0, 60, 'target_calibration')", (second, participant, signal))
    outcome.clear()
    attempted.clear()
    with psycopg.connect(dsn) as writer:
        writer.execute("INSERT INTO myoprosthesis.split_units(manifest_id, participant_id, category, signal_id, start_sample, end_sample, role) VALUES (%s, %s, 'target', %s, 50, 100, 'target_test')", (second, participant, signal))

        def freeze():
            try:
                with psycopg.connect(dsn, connect_timeout=5) as connection:
                    connection.execute("SET LOCAL lock_timeout = '5s'")
                    connection.execute("SELECT set_config('application_name', %s, true)", (token + '-reverse',))
                    attempted.set()
                    connection.execute("CALL myoprosthesis.freeze_manifest(%s)", (second,))
                outcome.append("accepted")
            except psycopg.Error as error:
                outcome.append(error.diag.message_primary)

        thread = threading.Thread(target=freeze)
        thread.start()
        assert attempted.wait(5)
        deadline = time.monotonic() + 3
        with psycopg.connect(dsn) as observer:
            while time.monotonic() < deadline:
                if observer.execute("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE application_name = %s AND wait_event_type = 'Lock')", (token + '-reverse',)).fetchone()[0]:
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("Freeze did not wait for the manifest lock")
        writer.commit()
        thread.join(10)
        assert not thread.is_alive()
    assert len(outcome) == 1 and "conflicting units" in outcome[0], outcome
    print("Concurrent freeze/mutation check passed.")


if __name__ == "__main__":
    main()
