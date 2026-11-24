import os
import unittest
import uuid
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
from gateway.identity import principal
from gateway.main import app, requests_by_client


class DesktopBoundaryTests(unittest.TestCase):
    def setUp(self):
        requests_by_client.clear()
        self.actor = {
            "operator_id": uuid.uuid4(),
            "client_id": uuid.uuid4(),
            "scope": "desktop",
            "role": "operator",
        }
        app.dependency_overrides[principal] = lambda: self.actor
        self.addCleanup(app.dependency_overrides.clear)
        environment = patch.dict(
            os.environ,
            {
                "CLOUD_INTERNAL_KEY": "test-internal-key-" * 3,
                "DATA_SERVICE_URL": "http://data",
                "GATEWAY_REQUESTS_PER_MINUTE": "1000",
                "GATEWAY_USERNAME": "dev",
                "GATEWAY_PASSWORD": "dev-only",
            },
        )
        environment.start()
        self.addCleanup(environment.stop)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.transport = AsyncMock()
        self.transport.__aenter__.return_value.request.return_value = httpx.Response(
            200, json={"items": [], "next_offset": None}
        )
        transport_patch = patch(
            "gateway.desktop.httpx.AsyncClient", return_value=self.transport
        )
        transport_patch.start()
        self.addCleanup(transport_patch.stop)

    def test_literal_recordings_route_and_trusted_headers(self):
        result = self.client.get(
            "/cloud/v1/recordings?limit=1",
            headers={
                "X-Operator-ID": str(uuid.uuid4()),
                "X-Client-ID": str(uuid.uuid4()),
                "X-Cloud-Key": "spoof",
            },
        )
        self.assertEqual(result.status_code, 200, result.text)
        forwarded = self.transport.__aenter__.return_value.request.call_args
        self.assertEqual(
            forwarded.args[:2], ("GET", "http://data/v1/client-recordings")
        )
        self.assertEqual(
            forwarded.kwargs["headers"]["X-Operator-ID"], str(self.actor["operator_id"])
        )
        self.assertEqual(
            forwarded.kwargs["headers"]["X-Client-ID"], str(self.actor["client_id"])
        )
        self.assertEqual(forwarded.kwargs["params"], {"limit": 1, "offset": 0})
        self.assertEqual(result.headers["Cache-Control"], "no-store")
        self.assertEqual(
            self.client.get("/cloud/v1/recordings?limit=101").status_code, 422
        )

    def test_publication_requires_desktop_and_nonreviewer(self):
        for changes in (
            {"scope": "web"},
            {"scope": "training_worker"},
            {"client_id": None},
            {"role": "reviewer"},
        ):
            previous = dict(self.actor)
            self.actor.update(changes)
            self.assertEqual(
                self.client.post("/cloud/v1/recordings", json={}).status_code, 403
            )
            self.actor.update(previous)
        self.transport.__aenter__.return_value.request.return_value = httpx.Response(
            201, json={"id": str(uuid.uuid4())}
        )
        self.assertEqual(
            self.client.post("/cloud/v1/recordings", json={}).status_code, 201
        )
        self.assertEqual(
            self.client.post(
                "/cloud/v1/recordings", content=b"x" * 2_000_001
            ).status_code,
            413,
        )

    def test_signal_and_upstream_failures(self):
        identifier = uuid.uuid4()
        self.client.get(f"/cloud/v1/recordings/{identifier}/signal")
        forwarded = self.transport.__aenter__.return_value.request.call_args
        self.assertEqual(
            forwarded.args[1], f"http://data/v1/client-recordings/{identifier}/signal"
        )
        for error, status in (
            (httpx.ReadTimeout("test"), 504),
            (httpx.ConnectError("test"), 502),
        ):
            self.transport.__aenter__.return_value.request.side_effect = error
            self.assertEqual(
                self.client.get("/cloud/v1/recordings").status_code, status
            )
        with patch.dict(os.environ, {"CLOUD_INTERNAL_KEY": ""}):
            self.assertEqual(self.client.get("/cloud/v1/recordings").status_code, 503)
        self.assertEqual(
            self.client.get(
                "/data/v1/client-recordings", auth=("dev", "dev-only")
            ).status_code,
            403,
        )
