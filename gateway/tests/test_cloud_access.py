"""Cloud HTTP boundary against a migrated, disposable PostgreSQL database."""

import os
import unittest
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from gateway import identity
from gateway.main import app, requests_by_client


@unittest.skipUnless(
    os.environ.get("CLOUD_TEST_DATABASE_URL"),
    "Set CLOUD_TEST_DATABASE_URL to a migrated myocontrol_review_* database",
)
class CloudAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ml_experiments.registry import router
        from ml_experiments.db import get_session

        cls.ml_app = FastAPI()
        cls.ml_app.include_router(router)
        cls.get_session = staticmethod(get_session)
        cls.db = create_engine(os.environ["CLOUD_TEST_DATABASE_URL"])
        with cls.db.connect() as c:
            if (
                not c.execute(text("SELECT current_database()"))
                .scalar_one()
                .startswith("myocontrol_review_")
            ):
                raise RuntimeError("Refusing to seed a non-review database")
        cls.sessions = sessionmaker(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.db.dispose()

    def setUp(self):
        requests_by_client.clear()
        self.env = patch.dict(
            os.environ,
            {
                "GATEWAY_REQUESTS_PER_MINUTE": "1000",
                "CLOUD_INTERNAL_KEY": "test-key-" * 8,
                "ML_SERVICE_URL": "http://ml",
                "GATEWAY_USERNAME": "dev",
                "GATEWAY_PASSWORD": "dev-only",
            },
        )
        self.env.start()
        self.addCleanup(self.env.stop)
        self.identity_engine = patch("gateway.identity.engine", return_value=self.db)
        self.identity_engine.start()
        self.addCleanup(self.identity_engine.stop)
        self.email = f"{uuid.uuid4()}@example.test"
        self.owner = identity.create_operator(
            self.email, "HTTP test", "review-only-password"
        )

        def session():
            with self.sessions() as s:
                yield s

        self.ml_app.dependency_overrides[self.get_session] = session
        self.addCleanup(self.ml_app.dependency_overrides.clear)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.ml = TestClient(self.ml_app)
        self.addCleanup(self.ml.close)

    def login(self):
        response = self.client.post(
            "/auth/v1/sessions",
            json={"email": self.email.upper(), "password": "review-only-password"},
        )
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual("no-store", response.headers["cache-control"])
        return response.json()["access_token"]

    def headers(self, token=None):
        return {"Authorization": "Bearer " + (token or self.login())}

    def seed_run(self, owner):
        with self.db.begin() as c:
            return c.execute(
                text("""INSERT INTO ml_experiments.experiment_runs
                (operator_id,submission_key,kind,family,condition,execution_location,manifest_id,manifest_sha256,
                feature_contract,input_snapshot,parameters,seed,software_version)
                VALUES (:owner,:key,'source_train','lda','source_only','local_workstation',:manifest,:hash,
                '{"version":"fixture-v1"}','{}','{}',1,'http-test') RETURNING id"""),
                {
                    "owner": owner,
                    "key": str(uuid.uuid4()),
                    "manifest": uuid.uuid4(),
                    "hash": "a" * 64,
                },
            ).scalar_one()

    def ml_headers(self):
        return {"X-Cloud-Key": "test-key-" * 8, "X-Operator-ID": str(self.owner)}

    def test_login_digest_and_logout(self):
        token = self.login()
        headers = self.headers(token)
        self.assertEqual(
            str(self.owner),
            self.client.get("/auth/v1/me", headers=headers).json()["operator_id"],
        )
        with self.db.connect() as c:
            stored = c.execute(
                text(
                    "SELECT token_sha256 FROM identity.access_sessions WHERE operator_id=:id"
                ),
                {"id": self.owner},
            ).scalar_one()
        self.assertEqual(identity.digest(token), stored)
        self.assertNotEqual(token, stored)
        self.assertEqual(
            204,
            self.client.delete(
                "/auth/v1/sessions/current", headers=headers
            ).status_code,
        )
        self.assertEqual(
            401, self.client.get("/auth/v1/me", headers=headers).status_code
        )
        self.assertEqual(401, self.client.get("/auth/v1/me").status_code)
        self.assertEqual(
            401,
            self.client.get(
                "/auth/v1/me", headers={"Authorization": "Bearer short"}
            ).status_code,
        )

    def test_wrong_unknown_and_disabled_account(self):
        for email in (self.email, "missing@example.test"):
            self.assertEqual(
                401,
                self.client.post(
                    "/auth/v1/sessions", json={"email": email, "password": "wrong"}
                ).status_code,
            )
        headers = self.headers()
        with self.db.begin() as c:
            c.execute(
                text("UPDATE identity.operators SET state='disabled' WHERE id=:id"),
                {"id": self.owner},
            )
        self.assertEqual(
            401, self.client.get("/auth/v1/me", headers=headers).status_code
        )
        self.assertEqual(
            401,
            self.client.post(
                "/auth/v1/sessions",
                json={"email": self.email, "password": "review-only-password"},
            ).status_code,
        )

    def test_browser_cookie_restores_session_and_requires_header_for_mutations(self):
        token = self.login()
        cookie = self.client.cookies.get(identity.COOKIE_NAME)
        self.assertEqual(token, cookie)
        result = self.client.get("/auth/v1/me")
        self.assertEqual(200, result.status_code, result.text)
        self.assertEqual(str(self.owner), result.json()["operator_id"])
        self.assertEqual("no-store", result.headers["cache-control"])
        self.assertEqual(
            403, self.client.delete("/auth/v1/sessions/current").status_code
        )
        self.assertEqual(
            204,
            self.client.delete(
                "/auth/v1/sessions/current", headers={"X-MyoControl-Web": "1"}
            ).status_code,
        )
        self.assertIsNone(self.client.cookies.get(identity.COOKIE_NAME))
        self.assertEqual(401, self.client.get("/auth/v1/me").status_code)

    def test_browser_login_header_cookie_flags_and_client_scope(self):
        body = {"email": self.email, "password": "review-only-password"}
        self.assertEqual(
            403,
            self.client.post(
                "/auth/v1/sessions",
                json=body,
                headers={"Origin": "http://untrusted.example"},
            ).status_code,
        )
        result = self.client.post(
            "/auth/v1/sessions",
            json=body,
            headers={"Origin": "http://testserver", "X-MyoControl-Web": "1"},
        )
        self.assertEqual(200, result.status_code, result.text)
        header = result.headers["set-cookie"]
        for flag in ("HttpOnly", "SameSite=strict", "Max-Age=28800", "Path=/"):
            self.assertIn(flag, header)
        issued = self.client.post(
            "/auth/v1/clients",
            json={"kind": "desktop", "name": "Test desktop", "platform": "test"},
            headers=self.headers(result.json()["access_token"]),
        )
        self.assertEqual(201, issued.status_code, issued.text)
        self.client.cookies.clear()
        self.client.cookies.set(identity.COOKIE_NAME, issued.json()["access_token"])
        self.assertEqual(401, self.client.get("/auth/v1/me").status_code)
        with patch.dict(os.environ, {"WEB_SESSION_SECURE": "true"}):
            self.assertIn(
                "Secure",
                self.client.post("/auth/v1/sessions", json=body).headers["set-cookie"],
            )

    def test_expired_session_and_database_failure(self):
        token = uuid.uuid4().hex + uuid.uuid4().hex
        with self.db.begin() as c:
            c.execute(
                text(
                    """INSERT INTO identity.access_sessions(operator_id,token_sha256,scope,issued_at,expires_at)
                VALUES (:id,:hash,'web',clock_timestamp()-interval '2 hours',clock_timestamp()-interval '1 hour')"""
                ),
                {"id": self.owner, "hash": identity.digest(token)},
            )
        self.assertEqual(
            401, self.client.get("/auth/v1/me", headers=self.headers(token)).status_code
        )
        from sqlalchemy.exc import OperationalError

        with patch(
            "gateway.identity.engine",
            side_effect=OperationalError("hidden", {}, Exception("hidden")),
        ):
            response = self.client.get("/auth/v1/me", headers=self.headers(token))
            self.assertEqual(503, response.status_code)
            self.assertNotIn("hidden", response.text)

    def test_client_scope_owner_revocation_and_no_token_listing(self):
        headers = self.headers()
        for kind in ("training_worker", "desktop"):
            response = self.client.post(
                "/auth/v1/clients",
                headers=headers,
                json={"kind": kind, "name": "Test machine", "platform": "test"},
            )
            self.assertEqual(201, response.status_code, response.text)
            body = response.json()
            token_headers = self.headers(body["access_token"])
            self.assertEqual(
                kind,
                self.client.get("/auth/v1/me", headers=token_headers).json()["scope"],
            )
            self.assertEqual(
                403,
                self.client.get("/auth/v1/clients", headers=token_headers).status_code,
            )
            listing = self.client.get("/auth/v1/clients", headers=headers)
            self.assertNotIn(body["access_token"], listing.text)
            self.assertEqual(
                204,
                self.client.delete(
                    f'/auth/v1/clients/{body["client_id"]}', headers=headers
                ).status_code,
            )
            self.assertEqual(
                401, self.client.get("/auth/v1/me", headers=token_headers).status_code
            )
        self.assertEqual(
            404,
            self.client.delete(
                f"/auth/v1/clients/{uuid.uuid4()}", headers=headers
            ).status_code,
        )
        self.assertEqual(
            422,
            self.client.post(
                "/auth/v1/clients",
                headers=headers,
                json={"kind": "desktop", "name": " ", "platform": "test"},
            ).status_code,
        )

    def test_reviewer_cannot_provision_clients(self):
        with self.db.begin() as c:
            c.execute(
                text("UPDATE identity.operators SET role='reviewer' WHERE id=:id"),
                {"id": self.owner},
            )
        self.assertEqual(
            403,
            self.client.post(
                "/auth/v1/clients",
                headers=self.headers(),
                json={"kind": "training_worker", "name": "No", "platform": "test"},
            ).status_code,
        )

    def test_owner_filter_pagination_and_hidden_leases(self):
        first = self.seed_run(self.owner)
        self.seed_run(self.owner)
        foreign = self.seed_run(uuid.uuid4())
        headers = self.ml_headers()
        listing = self.ml.get("/v1/registry/runs?limit=1", headers=headers)
        self.assertEqual(200, listing.status_code, listing.text)
        self.assertEqual(1, listing.json()["next_offset"])
        self.assertEqual(
            1,
            len(
                self.ml.get(
                    "/v1/registry/runs?offset=1&limit=1", headers=headers
                ).json()["items"]
            ),
        )
        self.assertEqual(
            404,
            self.ml.get(f"/v1/registry/runs/{foreign}", headers=headers).status_code,
        )
        detail = self.ml.get(f"/v1/registry/runs/{first}", headers=headers)
        self.assertEqual(200, detail.status_code)
        self.assertNotIn("lease_sha256", detail.text)
        self.assertEqual(
            422, self.ml.get("/v1/registry/runs?limit=101", headers=headers).status_code
        )
        for collection in ("models", "results"):
            self.assertEqual(
                [],
                self.ml.get(f"/v1/registry/{collection}", headers=headers).json()[
                    "items"
                ],
            )
        self.assertEqual(
            404, self.ml.get("/v1/registry/missing", headers=headers).status_code
        )
        self.assertEqual(
            404,
            self.ml.get(f"/v1/registry/missing/{first}", headers=headers).status_code,
        )

    def test_registry_denies_direct_and_basic_access(self):
        self.assertEqual(401, self.ml.get("/v1/registry/runs").status_code)
        self.assertEqual(
            401,
            self.ml.get(
                "/v1/registry/runs",
                headers={**self.ml_headers(), "X-Cloud-Key": "wrong"},
            ).status_code,
        )
        self.assertEqual(
            403,
            self.client.get(
                "/experiments/v1/registry/runs", auth=("dev", "dev-only")
            ).status_code,
        )
        with patch.dict(os.environ, {"CLOUD_INTERNAL_KEY": ""}):
            self.assertEqual(
                503,
                self.ml.get("/v1/registry/runs", headers=self.ml_headers()).status_code,
            )
            self.assertEqual(
                503,
                self.client.get("/cloud/v1/runs", headers=self.headers()).status_code,
            )

    def test_gateway_uses_verified_owner_and_forwards_pagination(self):
        run = self.seed_run(self.owner)
        transport = AsyncMock()

        async def forward(url, *, params, headers):
            result = self.ml.get(
                url.replace("http://ml", ""), params=params, headers=headers
            )
            return httpx.Response(result.status_code, content=result.content)

        transport.__aenter__.return_value.get.side_effect = forward
        headers = {
            **self.headers(),
            "X-Operator-ID": str(uuid.uuid4()),
            "X-Cloud-Key": "spoof",
        }
        with patch("gateway.cloud.httpx.AsyncClient", return_value=transport):
            result = self.client.get(f"/cloud/v1/runs/{run}", headers=headers)
            self.assertEqual(200, result.status_code, result.text)
            self.assertEqual(
                422,
                self.client.get(
                    "/cloud/v1/runs?limit=101", headers=headers
                ).status_code,
            )
            listed = self.client.get(
                f"/cloud/v1/runs?item_id={uuid.uuid4()}", headers=headers
            )
            self.assertIn("items", listed.json())
            listing = self.client.get("/cloud/v1/runs?limit=1", headers=headers)
            self.assertEqual(str(run), listing.json()["items"][0]["id"])
            self.assertEqual(
                404, self.client.get("/cloud/v1/secret", headers=headers).status_code
            )
            self.assertEqual(
                422,
                self.client.get(
                    "/cloud/v1/runs/not-a-uuid", headers=headers
                ).status_code,
            )
        for cause, status in (
            (httpx.ReadTimeout("test"), 504),
            (httpx.ConnectError("test"), 502),
        ):
            transport.__aenter__.return_value.get.side_effect = cause
            with patch("gateway.cloud.httpx.AsyncClient", return_value=transport):
                self.assertEqual(
                    status,
                    self.client.get("/cloud/v1/runs", headers=headers).status_code,
                )

    def test_published_models_and_confusion_matrix_detail(self):
        # Reuse scientific fixture builders, keeping HTTP assertions independent.
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "db_fixtures",
            Path(__file__).resolve().parents[2]
            / "database/tests/test_cloud_database.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        fixture = module.CloudDatabaseTests()
        dsn = os.environ["CLOUD_TEST_DATABASE_URL"].replace(
            "postgresql+psycopg://", "postgresql://"
        )
        with patch.dict(os.environ, {"TEST_DATABASE_URL": dsn}):
            fixture.setUp()
        try:
            model = fixture.source_model()
            run, evaluation = fixture.evaluation(model)
            fixture.c.execute(
                "SELECT ml_experiments.finish_experiment(%s,%s,%s,'succeeded')",
                (run, fixture.client, module.HASH),
            )
            fixture.c.commit()
            own = {**self.ml_headers(), "X-Operator-ID": str(fixture.operator)}
            self.assertEqual(
                1, len(self.ml.get("/v1/registry/models", headers=own).json()["items"])
            )
            self.assertEqual(
                200,
                self.ml.get(f"/v1/registry/models/{model}", headers=own).status_code,
            )
            self.assertEqual(
                1, len(self.ml.get("/v1/registry/results", headers=own).json()["items"])
            )
            result = self.ml.get(f"/v1/registry/results/{evaluation}", headers=own)
            self.assertEqual(200, result.status_code, result.text)
            self.assertEqual(4, len(result.json()["confusion_counts"]))
            for collection, item in (("models", model), ("results", evaluation)):
                self.assertEqual(
                    404,
                    self.ml.get(
                        f"/v1/registry/{collection}/{item}", headers=self.ml_headers()
                    ).status_code,
                )
        finally:
            fixture.tearDown()
