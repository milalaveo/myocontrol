"""An atomic, profile-local copy of the last explicitly imported model."""
import base64
import json
import os
from pathlib import Path
import tempfile

from .classifier import Classifier


class ModelSelection:
    def __init__(self, directory):
        self.path = Path(directory) / "selected-model.json"

    def restore(self):
        if not self.path.exists():
            return None
        if self.path.stat().st_size > 12 * 1024 * 1024:
            raise ValueError("Saved model is too large")
        snapshot = json.loads(self.path.read_bytes())
        if snapshot.get("version") != 1:
            raise ValueError("Unsupported saved model format")
        name = snapshot["name"]
        if not isinstance(name, str) or not name or len(name) > 255:
            raise ValueError("Invalid saved model name")
        payload = base64.b64decode(snapshot["payload"], validate=True)
        return Classifier.from_bytes(payload, name)

    def import_model(self, path):
        source = Path(path)
        if source.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Model JSON must be smaller than 8 MiB")
        payload = source.read_bytes()
        model = Classifier.from_bytes(payload, source.name)
        snapshot = {
            "version": 1,
            "name": source.name,
            "payload": base64.b64encode(payload).decode("ascii"),
        }
        descriptor, temporary = tempfile.mkstemp(prefix=".model-", dir=self.path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as output:
                json.dump(snapshot, output, ensure_ascii=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return model

    def clear(self):
        self.path.unlink(missing_ok=True)
