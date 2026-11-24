import platform
import threading
import time

from .acquisition.bitalino_source import BitalinoSource
from .calibration.selection import summarize
from .recognition.classifier import Classifier
from .signals import DEFAULT_CHANNELS, read_signal, validate_samples
from .storage.store import Store
from .sync.client import CloudClient, CloudError
from .sync.worker import SyncWorker


class Engine:
    def __init__(self, directory, emit, source_factory=BitalinoSource):
        self.store = Store(directory)
        self.emit = emit
        self.source_factory = source_factory
        self.sync = SyncWorker(self.store, emit)
        self.lock = threading.RLock()
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.thread = None
        self.classifier = None
        self.state = {
            "state": "idle",
            "mode": None,
            "recording_id": None,
            "sample_count": 0,
            "command": "neutral",
            "message": "Ready",
            "recognition": "No model selected",
        }

    def status(self):
        with self.lock:
            return {
                **self.state,
                "model": self.classifier.summary() if self.classifier else None,
                "cloud": self.sync.status(),
                "platform": platform.system(),
            }

    def publish(self, **values):
        with self.lock:
            self.state.update(values)
            status = self.status()
        self.emit("status", status)
        return status

    def require_idle(self):
        if self.thread and self.thread.is_alive():
            raise ValueError("Stop the current session first")

    def import_recording(self, path, participant_key="local-import"):
        self.require_idle()
        metadata, samples = read_signal(path)
        identifier = self.store.create(metadata, participant_key)
        for start in range(0, len(samples), 1000):
            self.store.append(identifier, start, samples[start : start + 1000])
        row = self.store.finish(identifier, "completed", "Imported recording")
        self.emit("recordings", {})
        return row

    def load_model(self, path):
        self.require_idle()
        self.classifier = Classifier(path)
        self.publish(
            recognition="Model loaded; input compatibility is checked at session start"
        )
        return self.classifier.summary()

    def clear_model(self):
        self.require_idle()
        self.classifier = None
        return self.publish(command="neutral", recognition="No model selected")

    def prepare_recognition(self, metadata):
        if self.classifier:
            try:
                self.classifier.prepare(metadata)
                return True, "Compatible feature contract"
            except ValueError as error:
                return False, str(error)
        return False, "No model selected"

    def start_capture(
        self,
        address,
        participant_key,
        sample_rate_hz=1000,
        channels=None,
        duration_seconds=10,
        purpose="research",
        gesture=None,
    ):
        self.require_idle()
        channels = list(DEFAULT_CHANNELS) if channels is None else channels
        if (
            type(duration_seconds) not in {int, float}
            or not 1 <= duration_seconds <= 1800
        ):
            raise ValueError("Recording duration must be 1–1800 seconds")
        source = self.source_factory(address, sample_rate_hz, channels)
        metadata = {
            "sample_rate_hz": float(sample_rate_hz),
            "channel_map": source.channels,
            "source_kind": "device",
            "source_name": "BITalino",
            "source_version": "bitalino-python-1.2.6",
            "units": "ADC counts",
        }
        identifier = self.store.create(metadata, participant_key, purpose, gesture)
        self.stop_event.clear()
        self.pause_event.clear()
        self.publish(
            state="connecting",
            mode="capture",
            recording_id=identifier,
            sample_count=0,
            command="neutral",
            message="Connecting to BITalino",
            metadata=metadata,
        )
        self.thread = threading.Thread(
            target=self.capture,
            args=(source, identifier, metadata, duration_seconds),
            name="acquisition",
            daemon=True,
        )
        self.thread.start()
        return self.status()

    def preview(self, identifier, start, metadata, samples, recognition):
        stride = max(1, len(samples) // 100)
        self.emit(
            "signal",
            {
                "recording_id": identifier,
                "start_sample": start,
                "sample_stride": stride,
                "sample_rate_hz": metadata["sample_rate_hz"],
                "channel_map": metadata["channel_map"],
                "samples": samples[::stride],
                "sample_count": start + len(samples),
            },
        )
        if (
            recognition
            and not self.stop_event.is_set()
            and not self.pause_event.is_set()
        ):
            for prediction in self.classifier.feed(samples):
                if self.stop_event.is_set() or self.pause_event.is_set():
                    break
                self.emit("prediction", {"recording_id": identifier, **prediction})

    def capture(self, source, identifier, metadata, duration):
        status, reason = "completed", "Requested duration completed"
        offset = 0
        try:
            source.open()
            recognition, message = self.prepare_recognition(metadata)
            self.publish(
                state="running", message="Recording from BITalino", recognition=message
            )
            target_count = round(duration * metadata["sample_rate_hz"])
            while not self.stop_event.is_set() and offset < target_count:
                samples = validate_samples(source.read(), len(metadata["channel_map"]))[
                    : target_count - offset
                ]
                self.store.append(identifier, offset, samples)
                self.preview(identifier, offset, metadata, samples, recognition)
                offset += len(samples)
                with self.lock:
                    self.state["sample_count"] = offset
            if self.stop_event.is_set():
                status, reason = "stopped", "Operator stopped acquisition"
        except Exception as error:
            status, reason = "failed", str(error)[:300]
        finally:
            try:
                source.close()
            except Exception:
                status, reason = (
                    "failed",
                    "Device could not be closed cleanly; reconnect explicitly",
                )
            try:
                self.store.finish(identifier, status, reason)
            except Exception:
                status, reason = (
                    "failed",
                    "Local storage could not finalize the recording; restart to recover stored samples",
                )
            self.publish(
                state="failed" if status == "failed" else "idle",
                command="neutral",
                message=reason,
                sample_count=offset,
            )
            self.emit("recordings", {})

    def start_replay(self, recording_id):
        self.require_idle()
        row = self.store.get(recording_id)
        if not row["sample_count"]:
            raise ValueError("The recording contains no samples")
        self.stop_event.clear()
        self.pause_event.clear()
        recognition, message = self.prepare_recognition(row["metadata"])
        self.publish(
            state="running",
            mode="replay",
            recording_id=recording_id,
            sample_count=0,
            command="neutral",
            message="Replaying local recording",
            metadata=row["metadata"],
            recognition=message,
        )
        self.thread = threading.Thread(
            target=self.replay,
            args=(row, recognition),
            name="recording-replay",
            daemon=True,
        )
        self.thread.start()
        return self.status()

    def replay(self, row, recognition):
        offset = 0
        step = max(1, round(row["metadata"]["sample_rate_hz"] / 10))
        try:
            for chunk in self.store.chunks(row["id"]):
                for start in range(0, len(chunk), step):
                    while self.pause_event.is_set() and not self.stop_event.is_set():
                        self.stop_event.wait(0.05)
                    if self.stop_event.is_set():
                        return
                    samples = chunk[start : start + step]
                    self.preview(
                        row["id"], offset, row["metadata"], samples, recognition
                    )
                    offset += len(samples)
                    with self.lock:
                        self.state["sample_count"] = offset
                    if self.stop_event.wait(
                        len(samples) / row["metadata"]["sample_rate_hz"]
                    ):
                        return
        except Exception as error:
            self.publish(state="failed", command="neutral", message=str(error)[:300])
            return
        finally:
            if self.state["state"] != "failed":
                self.publish(
                    state="idle",
                    command="neutral",
                    message=(
                        "Replay stopped"
                        if self.stop_event.is_set()
                        else "Replay completed"
                    ),
                    sample_count=offset,
                )

    def stop(self):
        self.stop_event.set()
        self.pause_event.clear()
        if self.thread and self.thread.is_alive():
            self.publish(
                state="stopping", command="neutral", message="Stopping local session"
            )
            self.thread.join(4)
        return self.status()

    def pause(self):
        if self.state["mode"] != "replay" or self.state["state"] != "running":
            raise ValueError("Only running replay can be paused")
        self.pause_event.set()
        return self.publish(state="paused", command="neutral", message="Replay paused")

    def resume(self):
        if self.state["state"] != "paused":
            raise ValueError("Replay is not paused")
        self.pause_event.clear()
        return self.publish(state="running", message="Replaying local recording")

    def recordings(self):
        rows = self.store.list()
        return {"items": rows, "calibration": summarize(rows)}

    def cloud_login(self, base, email, password):
        if (
            not isinstance(email, str)
            or not 3 <= len(email) <= 320
            or not isinstance(password, str)
            or not 1 <= len(password) <= 1024
        ):
            raise ValueError("Enter a valid email and password")
        web = CloudClient(base)
        access = web.call(
            "POST", "/auth/v1/sessions", {"email": email, "password": password}
        )
        web.token = access["access_token"]
        try:
            issued = web.call(
                "POST",
                "/auth/v1/clients",
                {
                    "kind": "desktop",
                    "name": "MyoControl Desktop",
                    "platform": platform.system() + "-" + platform.machine(),
                },
            )
        finally:
            try:
                web.call("DELETE", "/auth/v1/sessions/current")
            except CloudError:
                pass
        credentials = {
            "base": base,
            "token": issued["access_token"],
            "operator_id": access["operator"]["id"],
            "display_name": access["operator"]["display_name"],
            "client_id": issued["client_id"],
            "expires_at": issued["expires_at"],
        }
        self.sync.configure(credentials)
        self.emit("cloud", {"state": "connected"})
        return credentials

    def cloud_logout(self):
        credentials = self.sync.credentials
        if credentials:
            try:
                CloudClient(credentials["base"], credentials["token"]).call(
                    "DELETE", "/auth/v1/sessions/current"
                )
            except CloudError as error:
                if error.status != 401:
                    raise
        self.sync.configure(None)
        self.emit("cloud", {"state": "disconnected"})
        return {"connected": False}

    def queue_upload(self, recording_id):
        credentials = self.sync.credentials
        if not credentials:
            raise ValueError("Sign in to bind this upload to your operator account")
        self.store.queue(recording_id, credentials["operator_id"])
        self.sync.wake.set()
        return self.sync.status()

    def close(self):
        self.stop()
        self.sync.close()
