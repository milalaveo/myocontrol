import os
import tempfile
import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
from data_protocol.main import app


@unittest.skipUnless(
    os.getenv("DATA_DATABASE_URL"), "Requires a migrated disposable PostgreSQL"
)
class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.environment = patch.dict(
            os.environ,
            {
                "CLOUD_INTERNAL_KEY": "publication-test-" * 4,
                "DATA_ARTIFACT_ROOT": self.directory.name,
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.headers = {
            "X-Cloud-Key": "publication-test-" * 4,
            "X-Operator-ID": str(uuid.uuid4()),
            "X-Client-ID": str(uuid.uuid4()),
        }
        self.body = {
            "local_recording_id": str(uuid.uuid4()),
            "participant_key": "test-participant",
            "sample_rate_hz": 1000,
            "channel_map": [0, 1, 2, 3],
            "samples": [[1, 2, 3, 4], [2, 3, 4, 5]],
            "source_kind": "synthetic",
            "source_name": "test",
            "source_version": "1",
            "units": "arbitrary",
            "original_signal_key": str(uuid.uuid4()),
            "original_sha256": "a" * 64,
            "original_start_sample": 200,
        }

    def publish(self, body=None, headers=None):
        return self.client.post(
            "/v1/client-recordings",
            json=body or self.body,
            headers=headers or self.headers,
        )

    def test_publication_retry_client_rotation_and_conflicting_payload(self):
        first = self.publish()
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(self.publish().json(), first.json())
        rotated = {**self.headers, "X-Client-ID": str(uuid.uuid4())}
        self.assertEqual(self.publish(headers=rotated).json(), first.json())
        self.assertEqual(
            self.publish({**self.body, "samples": [[9, 8, 7, 6]]}).status_code, 409
        )
        items = self.client.get("/v1/client-recordings", headers=self.headers).json()[
            "items"
        ]
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["original_start_sample"], 200)
        self.assertEqual(items[0]["original_end_sample"], 202)

    def test_two_channel_roundtrip_and_foreign_owner_isolation(self):
        body = {**self.body, "channel_map": [2, 5], "samples": [[1.5, 2.5], [3.5, 4.5]]}
        result = self.publish(body)
        self.assertEqual(result.status_code, 201, result.text)
        identifier = result.json()["recording_id"]
        signal = self.client.get(
            f"/v1/client-recordings/{identifier}/signal", headers=self.headers
        )
        self.assertEqual(signal.status_code, 200, signal.text)
        self.assertEqual(signal.json()["samples"], body["samples"])
        self.assertEqual(signal.json()["channel_map"], [2, 5])
        foreign = {**self.headers, "X-Operator-ID": str(uuid.uuid4())}
        self.assertEqual(
            self.client.get("/v1/client-recordings", headers=foreign).json()["items"],
            [],
        )
        self.assertEqual(
            self.client.get(
                f"/v1/client-recordings/{identifier}/signal", headers=foreign
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.get(f"/v1/recordings/{identifier}/signal").status_code, 409
        )
        row = self.client.get("/v1/client-recordings", headers=self.headers).json()[
            "items"
        ][0]
        from pathlib import Path

        (Path(self.directory.name) / row["artifact_sha256"]).write_text("corrupted")
        self.assertEqual(
            self.client.get(
                f"/v1/client-recordings/{identifier}/signal", headers=self.headers
            ).status_code,
            503,
        )

    def test_boundary_validation_and_read_without_client(self):
        self.assertEqual(self.client.get("/v1/client-recordings").status_code, 401)
        self.assertEqual(
            self.publish(headers={**self.headers, "X-Cloud-Key": "spoof"}).status_code,
            401,
        )
        read_headers = {
            key: value for key, value in self.headers.items() if key != "X-Client-ID"
        }
        self.assertEqual(
            self.client.get("/v1/client-recordings", headers=read_headers).status_code,
            200,
        )
        self.assertEqual(self.publish(headers=read_headers).status_code, 403)
        for changes in (
            {"channel_map": [0, 0, 2, 3]},
            {"samples": [[1, 2]]},
            {"purpose": "calibration"},
            {"participant_key": " "},
            {"source_kind": "unknown"},
        ):
            with self.subTest(changes=changes):
                self.assertEqual(
                    self.publish({**self.body, **changes}).status_code, 422
                )
        self.assertEqual(
            self.client.get(
                "/v1/client-recordings?limit=101", headers=self.headers
            ).status_code,
            422,
        )
        with patch.dict(os.environ, {"CLOUD_INTERNAL_KEY": ""}):
            self.assertEqual(
                self.client.get(
                    "/v1/client-recordings", headers=self.headers
                ).status_code,
                503,
            )

    def test_calibration_label_is_stored_as_a_segment(self):
        result = self.publish(
            {**self.body, "purpose": "calibration", "gesture_code": "rest"}
        )
        self.assertEqual(result.status_code, 201, result.text)
        from data_protocol.db import get_session
        from sqlalchemy import text

        with next(get_session()) as session:
            row = session.execute(
                text(
                    "SELECT gesture_code,start_sample,end_sample FROM data_protocol.labelled_segments WHERE recording_id=:id"
                ),
                {"id": result.json()["recording_id"]},
            ).one()
        self.assertEqual(tuple(row), ("rest", 0, 2))
