import importlib
import json
from pathlib import Path
import sys
import unittest

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from api.build_specs import build, validate_contract


class ApiContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contracts = build()
        cls.gateway = cls.contracts[ROOT / "gateway/gateway/openapi.json"]

    def test_every_stored_contract_and_example_matches_the_sources(self):
        for path, spec in self.contracts.items():
            with self.subTest(path=str(path)):
                self.assertGreater(validate_contract(spec), 0)
                self.assertEqual(spec, json.loads(path.read_text(encoding="utf-8")))

    def test_public_security_and_concrete_routes_match_the_gateway_boundaries(self):
        paths = self.gateway["paths"]
        self.assertNotIn("/{service}/{path}", paths)
        self.assertNotIn("/cloud/v1/{collection}", paths)
        self.assertNotIn("/experiments/v1/registry/{collection}", paths)
        for collection in ("runs", "models", "results"):
            self.assertEqual(
                [{"OperatorBearer": []}, {"WebSession": []}],
                paths[f"/cloud/v1/{collection}"]["get"]["security"],
            )
        self.assertEqual(
            [{"HTTPBasic": []}], paths["/data/v1/participants"]["post"]["security"]
        )
        self.assertFalse(paths["/auth/v1/sessions"]["post"].get("security"))
        exported = json.dumps(self.gateway["components"]["schemas"])
        for private_field in (
            "password_hash",
            "token_sha256",
            "lease_sha256",
            "storage_key",
        ):
            self.assertNotIn(private_field, exported)

    def test_live_documentation_serves_the_exact_versioned_specifications(self):
        for path, spec in self.contracts.items():
            package = path.parent.name
            app = importlib.import_module(package + ".main").app
            with self.subTest(package=package), TestClient(app) as client:
                self.assertEqual(spec, client.get("/openapi.json").json())
                self.assertEqual(200, client.get("/docs").status_code)
                self.assertEqual(200, client.get("/redoc").status_code)

    def test_model_download_contract_preserves_the_digest_header(self):
        operation = self.gateway["paths"][
            "/experiments/v1/source-lda-experiments/{run_id}/model"
        ]["get"]
        self.assertIn("X-Artifact-SHA256", operation["responses"]["200"]["headers"])
        self.assertNotIn(
            "content",
            self.gateway["paths"]["/auth/v1/sessions/current"]["delete"]["responses"][
                "204"
            ],
        )


if __name__ == "__main__":
    unittest.main()
