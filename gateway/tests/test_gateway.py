import os
import unittest
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

from gateway.main import app, requests_by_client


class GatewayTests(unittest.TestCase):
    def test_model_download_preserves_bytes_and_digest(self):
        artifact = b'{"family":"lda"}'
        transport = AsyncMock()
        transport.__aenter__.return_value.request.return_value = httpx.Response(
            200, content=artifact, headers={"X-Artifact-SHA256": "a" * 64}
        )
        with patch.dict(os.environ, {"ML_SERVICE_URL": "http://ml"}), patch(
            "gateway.main.httpx.AsyncClient", return_value=transport
        ), TestClient(app) as client:
            response = client.get(
                "/experiments/v1/source-lda-experiments/00000000-0000-4000-8000-000000000001/model",
                auth=("tester", "test-only"),
            )
        self.assertEqual(artifact, response.content)
        self.assertEqual("a" * 64, response.headers["X-Artifact-SHA256"])

    def setUp(self):
        requests_by_client.clear()
        self.environment = patch.dict(
            os.environ,
            {
                "GATEWAY_USERNAME": "tester",
                "GATEWAY_PASSWORD": "test-only",
                "DATA_SERVICE_URL": "http://data",
                "GATEWAY_REQUESTS_PER_MINUTE": "1",
            },
        )
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def test_auth_routing_correlation_and_limit(self):
        transport = AsyncMock()
        transport.__aenter__.return_value.request.return_value = httpx.Response(
            200, json={"id": "example"}
        )
        with patch("gateway.main.httpx.AsyncClient", return_value=transport), TestClient(
            app
        ) as client:
            response = client.get(
                "/data/v1/participants",
                auth=("tester", "test-only"),
                headers={"X-Correlation-ID": "test-id"},
            )
            self.assertEqual(200, response.status_code)
            self.assertEqual("test-id", response.headers["X-Correlation-ID"])
            self.assertEqual("example", response.json()["id"])
            self.assertEqual(
                429, client.get("/data/v1/participants", auth=("tester", "test-only")).status_code
            )

    def test_service_errors_and_invalid_configuration(self):
        with patch.dict(os.environ, {"GATEWAY_REQUESTS_PER_MINUTE": "100"}), TestClient(
            app
        ) as client:
            self.assertEqual(200, client.get("/health/live").status_code)
            self.assertIn("gateway_requests_total", client.get("/metrics/").text)
            self.assertEqual(
                401, client.get("/data/v1/participants", auth=("tester", "wrong")).status_code
            )
            self.assertEqual(
                404, client.get("/unknown/v1/test", auth=("tester", "test-only")).status_code
            )
            self.assertEqual(
                503, client.get("/recognition/v1/test", auth=("tester", "test-only")).status_code
            )
            self.assertEqual(
                200, client.get("/data/docs", auth=("tester", "test-only")).status_code
            )
            with patch.dict(os.environ, {"GATEWAY_REQUESTS_PER_MINUTE": "invalid"}):
                self.assertEqual(
                    503, client.get("/data/v1/test", auth=("tester", "test-only")).status_code
                )
            requests_by_client.clear()
            transport = AsyncMock()
            transport.__aenter__.return_value.request.side_effect = httpx.ReadTimeout("timeout")
            with patch("gateway.main.httpx.AsyncClient", return_value=transport):
                self.assertEqual(
                    504, client.get("/data/v1/test", auth=("tester", "test-only")).status_code
                )
            requests_by_client.clear()
            transport.__aenter__.return_value.request.side_effect = httpx.ConnectError("offline")
            with patch("gateway.main.httpx.AsyncClient", return_value=transport):
                self.assertEqual(
                    502, client.get("/data/v1/test", auth=("tester", "test-only")).status_code
                )

    def test_failed_authentication_is_rate_limited(self):
        with TestClient(app) as client:
            self.assertEqual(401, client.get("/data/v1/participants").status_code)
            response = client.get("/data/v1/participants", auth=("tester", "wrong"))
            self.assertEqual(429, response.status_code)
            self.assertIn("retry-after", response.headers)

    def test_openapi_server_prefix(self):
        transport = AsyncMock()
        transport.__aenter__.return_value.request.return_value = httpx.Response(
            200, json={"openapi": "3.1.0", "paths": {}}
        )
        with patch("gateway.main.httpx.AsyncClient", return_value=transport), TestClient(
            app
        ) as client:
            response = client.get("/data/openapi.json", auth=("tester", "test-only"))
            self.assertEqual([{"url": "/data"}], response.json()["servers"])

    def test_only_configured_proxy_can_supply_client_address(self):
        transport = AsyncMock()
        transport.__aenter__.return_value.request.return_value = httpx.Response(200, json={})
        with patch("gateway.main.httpx.AsyncClient", return_value=transport), TestClient(
            app
        ) as client:
            with patch.dict(os.environ, {"GATEWAY_TRUSTED_PROXY_IP": "testclient"}):
                self.assertEqual(
                    200,
                    client.get(
                        "/data/v1/test",
                        auth=("tester", "test-only"),
                        headers={"X-Real-IP": "192.0.2.1"},
                    ).status_code,
                )
                self.assertEqual(
                    200,
                    client.get(
                        "/data/v1/test",
                        auth=("tester", "test-only"),
                        headers={"X-Real-IP": "192.0.2.2"},
                    ).status_code,
                )
            requests_by_client.clear()
            with patch.dict(os.environ, {"GATEWAY_TRUSTED_PROXY_IP": "192.0.2.50"}):
                self.assertEqual(
                    200,
                    client.get(
                        "/data/v1/test",
                        auth=("tester", "test-only"),
                        headers={"X-Real-IP": "192.0.2.1"},
                    ).status_code,
                )
                self.assertEqual(
                    429,
                    client.get(
                        "/data/v1/test",
                        auth=("tester", "test-only"),
                        headers={"X-Real-IP": "192.0.2.2"},
                    ).status_code,
                )


if __name__ == "__main__":
    unittest.main()
