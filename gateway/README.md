# Cloud access and development gateway

API reference: [versioned OpenAPI JSON](gateway/openapi.json), [Getting Started and integration tutorials](../api/README.md). The gateway serves the complete client contract at `/docs`, `/redoc` and `/openapi.json`. CI validates stored specifications and all body examples.


The gateway owns HTTP access to the `identity` schema. Cloud clients never receive PostgreSQL credentials. General training executes on a local workstation; calibration/live recognition execute inside Electron.

## Configure and create an operator

Add distinct random secrets to your untracked `.env`:

```dotenv
IDENTITY_DB_PASSWORD=replace-with-a-unique-long-password
CLOUD_INTERNAL_KEY=replace-with-a-random-secret-of-at-least-32-characters
```

The migrator provisions `identity_service_login` with access to `identity` only. Gateway uses this login; ML uses its separate schema login. The internal key is shared only between gateway and ML, which must remain on a private service network. Keep HTTPS at the public cloud boundary. Do not send these secrets to browser, Electron or workers.

```powershell
docker compose up -d --build gateway ml-experiments
docker compose exec gateway python -m gateway.identity operator@example.org "Operator name"
```

The CLI prompts twice for a password (12+ characters) and returns only the new operator UUID. Optional `--role reviewer` or `--role administrator` sets the account role. There is no public registration endpoint. No default operator/password is created. Role `reviewer` may read its own registry but cannot provision computing clients; cross-operator reviewer delegation is not implemented.

## Public account API

| Method | Route | Behaviour |
| --- | --- | --- |
| POST | `/auth/v1/sessions` | `{email,password}` → opaque bearer token, expiry and operator summary. |
| GET | `/auth/v1/me` | Validate bearer session; return actor/scope/client/expiry. |
| DELETE | `/auth/v1/sessions/current` | Revoke current session. |
| POST | `/auth/v1/clients` | Web session provisions `{kind,name,platform}`; kind is `desktop` or `training_worker`. Returns scoped token once. |
| GET | `/auth/v1/clients` | Web session lists own clients without credentials. |
| DELETE | `/auth/v1/clients/{id}` | Web session revokes own client and invalidates its sessions. |

Argon2id password hashes and SHA-256 digests of high-entropy session tokens are persisted; raw tokens are not. Web tokens last eight hours, client tokens thirty days. Every request checks expiry, operator state, session revocation and client state. Disabling an account or revoking a client invalidates existing access immediately. Tokens and authenticated responses are marked `Cache-Control: no-store`. Browser tokens stay in memory; desktop credential storage and offline grants are separate requirements.

## Cloud registry API

`GET /cloud/v1/{runs|models|results}` and `GET /cloud/v1/{runs|models|results}/{uuid}` require a bearer session. All roles/scopes currently read only their own operator's records. Lists accept `limit` (1–100, default 50) and `offset` (default 0), returning `{items,next_offset}`. Result detail includes confusion counts. Foreign IDs return 404. No lease digests or raw storage paths are exposed. Browser-supplied internal identity headers are ignored; the gateway supplies its validated context to ML.

This is the first read-only cloud slice. Generic run submission, claim/heartbeat/result publication, verified package upload/download and terminal desktop-report synchronization are not implemented yet. Recording synchronization is implemented separately at `/cloud/v1/recordings`; see the [recording tutorial](../api/tutorials/DESKTOP_RECORDINGS.md). The existing synthetic LDA worker still processes its original development tables via direct DB access. It is not a remote workstation delivery mechanism.

## Legacy development routes

`/data/v1/...`, `/experiments/v1/...` and `/recognition/v1/...` retain separate HTTP Basic authentication using `GATEWAY_USERNAME` and `GATEWAY_PASSWORD`. These are development endpoints, without per-operator ownership checks, and must not be exposed as cloud tenant APIs. Their Swagger pages are `/data/docs`, `/experiments/docs`, `/recognition/docs`. Basic access cannot proxy the new ML registry. Gateway liveness/metrics remain available for infrastructure checks.

The rate limit defaults to 60 requests/minute per IP, including failed authentication, and applies to both access surfaces. It is process-local and resets on restart. Only a proxy at `GATEWAY_TRUSTED_PROXY_IP` may supply `X-Real-IP`. Distributed limits, password recovery, token renewal, cross-operator sharing and production deployment are outstanding.

## Verify

After the [isolated database review](../database/README_TEACHER.md), set `CLOUD_TEST_DATABASE_URL` to the migrated `myocontrol_review_*` database (SQLAlchemy `postgresql+psycopg://` URL), include `gateway` and `services/ml_experiments` on `PYTHONPATH`, and run:

```powershell
python -m unittest discover -s gateway/tests -p 'test_*.py' -v
```

The cloud suite refuses other database names and seeds synthetic fixtures only. CI runs it during coverage checks against a disposable PostgreSQL 18 database. It covers login/revocation, scope restrictions, disabled/expired accounts, ownership filtering, pagination, published models, confusion counts and internal-header spoofing. Without `CLOUD_TEST_DATABASE_URL`, cloud DB tests are explicitly skipped while legacy gateway tests still run.
