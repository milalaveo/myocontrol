"""Check selection versus segment modification on a disposable database."""
import os
import threading
import time
import uuid

import psycopg


def main():
    dsn = os.environ["TEST_DATABASE_URL"]
    token = uuid.uuid4().hex
    with psycopg.connect(dsn) as connection:
        participant = connection.execute("INSERT INTO myoprosthesis.participants(pseudonym) VALUES (%s) RETURNING id", (token,)).fetchone()[0]
        signal = connection.execute("INSERT INTO myoprosthesis.canonical_signals(identity_scheme, identity_value, participant_id, sample_count) VALUES ('test', %s, %s, 100) RETURNING id", (token, participant)).fetchone()[0]
        gesture = connection.execute("INSERT INTO myoprosthesis.gestures(code, description) VALUES (%s, 'test') RETURNING id", (token,)).fetchone()[0]
        segment = connection.execute("INSERT INTO myoprosthesis.labelled_segments(signal_id, gesture_id, repetition_key, start_sample, end_sample) VALUES (%s, %s, 'rep', 0, 10) RETURNING id", (signal, gesture)).fetchone()[0]
        manifest = connection.execute("INSERT INTO myoprosthesis.split_manifests(name, version) VALUES (%s, 1) RETURNING id", (token,)).fetchone()[0]
        connection.execute("INSERT INTO myoprosthesis.split_participants VALUES (%s, %s, 'target')", (manifest, participant))
        connection.execute("INSERT INTO myoprosthesis.split_units(manifest_id, participant_id, category, signal_id, start_sample, end_sample, role) VALUES (%s, %s, 'target', %s, 0, 50, 'target_calibration')", (manifest, participant, signal))
        connection.execute("CALL myoprosthesis.freeze_manifest(%s)", (manifest,))
        subset = connection.execute("INSERT INTO myoprosthesis.calibration_subsets(manifest_id, participant_id, budget_per_gesture, selection_version) VALUES (%s, %s, 1, 'test') RETURNING id", (manifest, participant)).fetchone()[0]

    outcome = []
    started = threading.Event()
    with psycopg.connect(dsn) as selector:
        selector.execute("INSERT INTO myoprosthesis.calibration_items VALUES (%s, %s)", (subset, segment))

        def edit():
            try:
                with psycopg.connect(dsn) as connection:
                    connection.execute("SET LOCAL lock_timeout = '5s'")
                    connection.execute("SELECT set_config('application_name', %s, true)", (token,))
                    started.set()
                    connection.execute("UPDATE myoprosthesis.labelled_segments SET end_sample = 20 WHERE id = %s", (segment,))
                outcome.append("accepted")
            except psycopg.Error as error:
                outcome.append(error.diag.message_primary)

        thread = threading.Thread(target=edit)
        thread.start()
        assert started.wait(5)
        with psycopg.connect(dsn) as observer:
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline:
                if observer.execute("SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE application_name = %s AND wait_event_type = 'Lock')", (token,)).fetchone()[0]:
                    break
                time.sleep(0.05)
            else:
                raise AssertionError("Segment edit did not wait for selection")
        selector.commit()
        thread.join(10)
        assert not thread.is_alive()
    assert len(outcome) == 1 and "selected segment" in outcome[0], outcome
    print("Concurrent segment selection/edit check passed.")


if __name__ == "__main__":
    main()
