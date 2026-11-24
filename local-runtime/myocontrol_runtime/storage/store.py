from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import uuid

from ..signals import canonical, signal_digest


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, directory):
        self.directory = Path(directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / "recordings.sqlite3"
        with self.connect() as connection:
            connection.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS recordings (
                    id TEXT PRIMARY KEY, metadata TEXT NOT NULL, participant_key TEXT NOT NULL,
                    purpose TEXT NOT NULL, gesture TEXT, created_at TEXT NOT NULL, ended_at TEXT,
                    status TEXT NOT NULL, sample_count INTEGER NOT NULL DEFAULT 0,
                    sha256 TEXT, reason TEXT, operator_id TEXT
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    recording_id TEXT NOT NULL REFERENCES recordings(id), start_sample INTEGER NOT NULL,
                    samples TEXT NOT NULL, PRIMARY KEY(recording_id,start_sample)
                );
                CREATE TABLE IF NOT EXISTS outbox (
                    id TEXT PRIMARY KEY, recording_id TEXT NOT NULL REFERENCES recordings(id),
                    operator_id TEXT NOT NULL, offset INTEGER NOT NULL, state TEXT NOT NULL DEFAULT 'pending',
                    attempts INTEGER NOT NULL DEFAULT 0, next_attempt REAL NOT NULL DEFAULT 0,
                    error TEXT, receipt TEXT, UNIQUE(recording_id,offset)
                );
                PRAGMA user_version=1;
            """)
            connection.execute(
                "UPDATE recordings SET status='interrupted', ended_at=?, reason='Runtime stopped before recording completed' WHERE status='recording'",
                (now(),),
            )
            connection.execute(
                "UPDATE outbox SET state='pending' WHERE state='sending'"
            )

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create(self, metadata, participant_key, purpose="research", gesture=None):
        if (
            not isinstance(participant_key, str)
            or not 1 <= len(participant_key.strip()) <= 100
        ):
            raise ValueError("Enter a participant pseudonym (1–100 characters)")
        if purpose not in {"research", "calibration"}:
            raise ValueError("Invalid recording purpose")
        if purpose == "calibration" and gesture not in {
            "rest",
            "fist",
            "finger_spread",
            "wrist_flexion",
            "wrist_extension",
        }:
            raise ValueError("Choose the gesture for this calibration repetition")
        identifier = str(uuid.uuid4())
        with self.connect() as connection:
            connection.execute(
                "INSERT INTO recordings(id,metadata,participant_key,purpose,gesture,created_at,status) VALUES (?,?,?,?,?,?,'recording')",
                (
                    identifier,
                    canonical(metadata),
                    participant_key.strip(),
                    purpose,
                    gesture,
                    now(),
                ),
            )
        return identifier

    def append(self, identifier, start, samples):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT sample_count,status FROM recordings WHERE id=?", (identifier,)
            ).fetchone()
            if (
                row is None
                or row["status"] != "recording"
                or row["sample_count"] != start
            ):
                raise ValueError("Recording continuity check failed")
            connection.execute(
                "INSERT INTO chunks VALUES (?,?,?)",
                (identifier, start, canonical(samples)),
            )
            connection.execute(
                "UPDATE recordings SET sample_count=sample_count+? WHERE id=?",
                (len(samples), identifier),
            )

    def get(self, identifier):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM recordings WHERE id=?", (identifier,)
            ).fetchone()
        if row is None:
            raise ValueError("Local recording not found")
        return {**dict(row), "metadata": json.loads(row["metadata"])}

    def list(self):
        with self.connect() as connection:
            ids = [
                row[0]
                for row in connection.execute(
                    "SELECT id FROM recordings ORDER BY created_at DESC LIMIT 200"
                )
            ]
        return [self.get(identifier) for identifier in ids]

    def chunks(self, identifier):
        with self.connect() as connection:
            cursor = connection.execute(
                "SELECT samples FROM chunks WHERE recording_id=? ORDER BY start_sample",
                (identifier,),
            )
            for row in cursor:
                yield json.loads(row[0])

    def finish(self, identifier, status, reason):
        if status not in {"completed", "stopped", "failed", "interrupted"}:
            raise ValueError("Invalid terminal recording status")
        row = self.get(identifier)
        digest = signal_digest(row["metadata"], self.chunks(identifier))
        with self.connect() as connection:
            connection.execute(
                "UPDATE recordings SET status=?, ended_at=?, reason=?, sha256=? WHERE id=? AND status='recording'",
                (status, now(), reason, digest, identifier),
            )
        return self.get(identifier)

    def export(self, identifier, destination):
        row = self.get(identifier)
        if row["status"] == "recording":
            raise ValueError("Stop recording before exporting")
        path = Path(destination)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=".myocontrol-", suffix=".partial", dir=path.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        header = {
            "format": "myocontrol-signal-v1",
            **row["metadata"],
            "recording_id": identifier,
            "purpose": row["purpose"],
            "gesture": row["gesture"],
            "status": row["status"],
            "original_sha256": row["sha256"],
        }
        try:
            with temporary.open("w", encoding="utf-8") as output:
                output.write(canonical(header)[:-1] + ',"samples":[')
                first = True
                for chunk in self.chunks(identifier):
                    for sample in chunk:
                        if not first:
                            output.write(",")
                        output.write(canonical(sample))
                        first = False
                output.write("]}")
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return {"id": identifier, "sample_count": row["sample_count"]}

    def queue(self, identifier, operator_id):
        row = self.get(identifier)
        if row["status"] not in {"completed", "stopped"} or row["sample_count"] == 0:
            raise ValueError(
                "Only completed or stopped nonempty recordings can be synchronized"
            )
        if row["operator_id"] and row["operator_id"] != operator_id:
            raise ValueError("This recording belongs to a different operator")
        with self.connect() as connection:
            connection.execute(
                "UPDATE recordings SET operator_id=? WHERE id=?",
                (operator_id, identifier),
            )
            for offset in range(0, row["sample_count"], 10000):
                local_id = str(uuid.uuid5(uuid.UUID(identifier), f"samples:{offset}"))
                connection.execute(
                    "INSERT INTO outbox(id,recording_id,operator_id,offset) VALUES (?,?,?,?) ON CONFLICT(recording_id,offset) DO NOTHING",
                    (local_id, identifier, operator_id, offset),
                )

    def upload_body(self, entry):
        row = self.get(entry["recording_id"])
        samples, position = [], 0
        for chunk in self.chunks(row["id"]):
            end = position + len(chunk)
            if end > entry["offset"] and position < entry["offset"] + 10000:
                samples.extend(
                    chunk[
                        max(0, entry["offset"] - position) : entry["offset"]
                        + 10000
                        - position
                    ]
                )
            position = end
            if position >= entry["offset"] + 10000:
                break
        return {
            "local_recording_id": entry["id"],
            "participant_key": row["participant_key"],
            **row["metadata"],
            "original_signal_key": row["id"],
            "original_sha256": row["sha256"],
            "original_start_sample": entry["offset"],
            "samples": samples,
            "purpose": row["purpose"],
            "gesture_code": row["gesture"],
        }

    def pending(self, operator_id, timestamp):
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM outbox WHERE operator_id=? AND state='pending' AND next_attempt<=? ORDER BY rowid LIMIT 1",
                (operator_id, timestamp),
            ).fetchone()
        return dict(row) if row else None

    def update_outbox(
        self, identifier, state, attempts, next_attempt=0, error=None, receipt=None
    ):
        with self.connect() as connection:
            connection.execute(
                "UPDATE outbox SET state=?,attempts=?,next_attempt=?,error=?,receipt=? WHERE id=?",
                (
                    state,
                    attempts,
                    next_attempt,
                    error,
                    canonical(receipt) if receipt else None,
                    identifier,
                ),
            )

    def outbox(self, operator_id=None):
        with self.connect() as connection:
            rows = (
                connection.execute(
                    "SELECT * FROM outbox WHERE operator_id=? ORDER BY rowid DESC LIMIT 200",
                    (operator_id,),
                ).fetchall()
                if operator_id
                else []
            )
        return [
            {
                **dict(row),
                "receipt": json.loads(row["receipt"]) if row["receipt"] else None,
            }
            for row in rows
        ]

    def retry(self, operator_id):
        with self.connect() as connection:
            connection.execute(
                "UPDATE outbox SET state='pending',next_attempt=0,error=NULL WHERE operator_id=? AND state IN ('pending','auth_required')",
                (operator_id,),
            )
