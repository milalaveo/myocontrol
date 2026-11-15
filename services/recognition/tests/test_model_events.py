import json
import os
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

from sqlalchemy import text

from recognition.db import session_factory
from recognition.model_events import handle


@unittest.skipUnless(os.getenv("RECOGNITION_DATABASE_URL"), "A migrated disposable database is required")
class ModelEventTests(unittest.TestCase):
    def test_duplicate_is_idempotent_and_invalid_goes_to_dead_letter(self):
        channel = Mock()
        event_id = uuid.uuid4()
        event = {"event_id": str(event_id), "event_type": "ModelPublished", "schema_version": 1,
                 "model_run_id": str(uuid.uuid4()), "manifest_id": str(uuid.uuid4()), "correlation_id": "test-trace"}
        for tag in (1, 2):
            handle(channel, SimpleNamespace(delivery_tag=tag), None, json.dumps(event).encode())
        with session_factory()() as session:
            count = session.execute(text("SELECT count(*) FROM recognition.model_events WHERE event_id = :id"), {"id": event_id}).scalar_one()
        self.assertEqual(1, count)
        self.assertEqual(2, channel.basic_ack.call_count)
        handle(channel, SimpleNamespace(delivery_tag=3), None, b"invalid-json")
        channel.basic_nack.assert_called_once_with(delivery_tag=3, requeue=False)

    def test_transient_failure_is_retried_then_dead_lettered(self):
        channel = Mock()
        event = {"event_id": str(uuid.uuid4()), "event_type": "ModelPublished", "schema_version": 1,
                 "model_run_id": str(uuid.uuid4()), "manifest_id": str(uuid.uuid4()), "correlation_id": "trace"}
        with patch("recognition.model_events.session_factory", side_effect=RuntimeError("database down")), patch("recognition.model_events.time.sleep"):
            handle(channel, SimpleNamespace(delivery_tag=1), SimpleNamespace(headers={}), json.dumps(event).encode())
            self.assertEqual(1, channel.basic_publish.call_args.kwargs["properties"].headers["x-attempt"])
            channel.basic_ack.assert_called_once_with(delivery_tag=1)
            handle(channel, SimpleNamespace(delivery_tag=2), SimpleNamespace(headers={"x-attempt": 2}), json.dumps(event).encode())
            channel.basic_nack.assert_called_once_with(delivery_tag=2, requeue=False)


if __name__ == "__main__":
    unittest.main()
