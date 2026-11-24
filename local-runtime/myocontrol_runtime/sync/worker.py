from datetime import datetime, timezone
import hashlib
import threading
import time
from uuid import UUID

from .client import CloudClient, CloudError
from ..signals import canonical


class SyncWorker:
    def __init__(self, store, emit):
        self.store = store
        self.emit = emit
        self.credentials = None
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.closed = threading.Event()
        self.thread = threading.Thread(target=self.run, name="cloud-sync", daemon=True)
        self.thread.start()

    def configure(self, credentials):
        if credentials:
            CloudClient(credentials["base"], credentials["token"])
        with self.lock:
            self.credentials = credentials
        if credentials:
            self.store.retry(credentials["operator_id"])
        self.wake.set()

    def status(self):
        with self.lock:
            credentials = self.credentials
        return {
            "connected": credentials is not None,
            "operator_id": credentials["operator_id"] if credentials else None,
            "entries": self.store.outbox(
                credentials["operator_id"] if credentials else None
            ),
        }

    def once(self):
        with self.lock:
            credentials = self.credentials
        if not credentials:
            return False
        if datetime.fromisoformat(
            credentials["expires_at"].replace("Z", "+00:00")
        ) <= datetime.now(timezone.utc):
            self.emit(
                "cloud",
                {
                    "state": "auth_required",
                    "message": "Cloud session expired; sign in to synchronize",
                },
            )
            self.configure(None)
            return False
        entry = self.store.pending(credentials["operator_id"], time.time())
        if not entry:
            return False
        attempts = entry["attempts"] + 1
        self.store.update_outbox(entry["id"], "sending", attempts)
        try:
            body = self.store.upload_body(entry)
            receipt = CloudClient(credentials["base"], credentials["token"]).call(
                "POST", "/cloud/v1/recordings", body
            )
            try:
                UUID(receipt["id"])
                UUID(receipt["recording_id"])
                datetime.fromisoformat(receipt["received_at"].replace("Z", "+00:00"))
                if (
                    receipt["local_recording_id"] != entry["id"]
                    or receipt["payload_sha256"]
                    != hashlib.sha256(canonical(body).encode()).hexdigest()
                ):
                    raise ValueError("Receipt does not acknowledge this exact upload")
            except (TypeError, KeyError, ValueError):
                raise CloudError(
                    "Cloud receipt was invalid; publication will be retried", 502
                ) from None
            self.store.update_outbox(entry["id"], "synced", attempts, receipt=receipt)
        except CloudError as error:
            if error.status in {401, 403}:
                state = "auth_required"
            elif 400 <= error.status < 500 and error.status != 429:
                state = "conflict" if error.status == 409 else "rejected"
            else:
                state = "pending"
            self.store.update_outbox(
                entry["id"],
                state,
                attempts,
                time.time() + (error.retry_after or min(300, 2 ** min(attempts, 8))),
                str(error),
            )
            if state == "auth_required":
                self.emit("cloud", {"state": state, "message": str(error)})
                self.configure(None)
        except Exception:
            self.store.update_outbox(
                entry["id"],
                "rejected",
                attempts,
                error="Local upload validation failed; export and inspect this recording",
            )
        self.emit("sync", self.status())
        return True

    def run(self):
        while not self.closed.is_set():
            try:
                worked = self.once()
            except Exception:
                self.emit(
                    "cloud",
                    {
                        "state": "error",
                        "message": "Synchronization paused after a local storage error",
                    },
                )
                worked = False
            if not worked:
                self.wake.wait(1)
                self.wake.clear()

    def close(self):
        self.closed.set()
        self.wake.set()
        self.thread.join(6)
