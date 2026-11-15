import unittest
import uuid
from unittest.mock import MagicMock, Mock, patch

from ml_experiments.outbox_worker import publish_one


class OutboxTests(unittest.TestCase):
    def test_confirmed_publish_marks_event_and_empty_queue_is_idle(self):
        event_id = uuid.uuid4()
        event = {"id": event_id, "payload": {"event_id": str(event_id), "correlation_id": "trace"}}
        database = MagicMock()
        database.execute.return_value.mappings.return_value.one_or_none.return_value = event
        manager = MagicMock()
        manager.__enter__.return_value = database
        channel = Mock()
        with patch("ml_experiments.outbox_worker.session_factory", return_value=lambda: manager):
            self.assertTrue(publish_one(channel))
        self.assertEqual(1, channel.basic_publish.call_count)
        self.assertTrue(channel.basic_publish.call_args.kwargs["mandatory"])
        self.assertEqual(2, database.execute.call_count)
        database.reset_mock()
        database.execute.return_value.mappings.return_value.one_or_none.return_value = None
        with patch("ml_experiments.outbox_worker.session_factory", return_value=lambda: manager):
            self.assertFalse(publish_one(channel))


if __name__ == "__main__":
    unittest.main()
