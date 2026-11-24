# Getting Started

## Prerequisites

- Git, Docker Engine/Desktop with Compose v2 and a working Linux-container engine.
- Python 3.12 to generate local settings and run the dependency-free tutorials. Docker supplies service dependencies and PostgreSQL 18; Node.js is not needed for the Docker deployment.
- Loopback ports 8000 (gateway), 3000 (optional frontend) and 5434 (PostgreSQL). Set the corresponding `GATEWAY_PORT`, `FRONTEND_PORT` or `POSTGRES_PORT` variable if a port is occupied.

Run commands from the repository root. The examples below use PowerShell; the Python/Docker commands also work in a POSIX shell.

## 1. Get the project

```powershell
git clone https://github.com/milalaveo/myocontrol.git
cd myocontrol
```

For an existing checkout, use its current configuration rather than creating another database volume or replacing credentials.

## 2. Create private settings

```powershell
python scripts/setup_local.py
```

The helper creates an ignored `.env` with distinct random passwords and an internal gateway key. It never prints credentials and refuses to overwrite an existing file. The development Basic username is `development`; its generated password remains in `.env`. Operator credentials are created separately in step 4.

For an existing `.env`, ensure it includes all variables required by [compose.yaml](../compose.yaml), particularly `IDENTITY_DB_PASSWORD` and a `CLOUD_INTERNAL_KEY` of at least 32 characters. Existing database/broker volume passwords cannot be changed by merely editing the environment. Do not commit `.env`, actual passwords, bearer tokens or research artifacts.

## 3. Start the application

```powershell
docker compose --profile ui up -d --build --wait --wait-timeout 180
docker compose --profile ui ps
```

The migrator applies the service migrations and provisions isolated database logins. APIs start after migration/readiness checks. The standard development Compose also starts the legacy local experiment worker, broker/cache and event consumers. General training in this development arrangement executes on the machine running Compose; this is not the target remote workstation delivery mechanism.

Check liveness:

```powershell
curl.exe --fail http://127.0.0.1:8000/health/live
```

Expected HTTP 200:

```json
{"status":"live"}
```

The cloud UI is at [localhost:3000](http://127.0.0.1:3000). API calls use [localhost:8000](http://127.0.0.1:8000). Database/domain-service credentials are never passed to a browser or client.

## 4. Create an operator

```powershell
docker compose exec gateway python -m gateway.identity expert@example.test "API expert"
```

Enter a password of 12–1024 characters twice when prompted. The command prints the new operator UUID only. Use this email/password for the cloud UI and the login API. No built-in account exists, and the development Basic password is not an operator password. The default operator role can provision its own test clients; a `reviewer` role cannot do so.

## 5. Open the API reference

- **[Swagger UI](http://127.0.0.1:8000/docs)** — primary complete gateway reference with interactive calls.
- **[ReDoc](http://127.0.0.1:8000/redoc)** — alternate reference view.
- **[OpenAPI JSON](http://127.0.0.1:8000/openapi.json)** — the same contract stored in [gateway/gateway/openapi.json](../gateway/gateway/openapi.json).
- Private-service documentation through the gateway: `/data/docs`, `/experiments/docs`, `/recognition/docs`. These entry pages require development Basic credentials; use the complete gateway reference for host-side authenticated Try It Out calls.

In Swagger, call `POST /auth/v1/sessions` with the account from step 4. Copy the returned `access_token` into **Authorize → OperatorBearer**. Supply the token only; Swagger adds the `Bearer` prefix. Then call `/auth/v1/me` or `/cloud/v1/models`. Fresh accounts receive `{"items":[],"next_offset":null}`.

For `/data/...`, `/experiments/...` and `/recognition/...`, authorize **HTTPBasic** with the separate development credentials from `.env`. Those legacy routes have no per-operator ownership checks and belong on the local/private development boundary. Do not use `CLOUD_INTERNAL_KEY` in a public client.

## 6. Run the integration tutorials

```powershell
python api/tutorial.py cloud --email expert@example.test
python api/tutorial.py synthetic --env-file .env
```

The first prompts for the operator password and verifies access, client-token scope/revocation and logout. The second creates synthetic development research records and verifies a manifest → LDA job → artifact → replay chain. It does not read measured participant data or upload a dataset. Details and expected responses: [cloud tutorial](tutorials/CLOUD_ACCESS.md), [research tutorial](tutorials/SYNTHETIC_RESEARCH.md).

## Stop and diagnose

```powershell
docker compose --profile ui logs --tail 100 gateway migrate data-protocol ml-experiments recognition experiment-worker
docker compose --profile ui stop
```

Stopping preserves volumes. Use the response's `X-Correlation-ID` when investigating an API failure. A 503 is a service/configuration/readiness failure; an empty successful registry is not. If a job stays queued, verify the development experiment worker rather than repeatedly creating new jobs. See [errors and boundaries](ERRORS.md).
