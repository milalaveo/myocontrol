# Errors, access and response conventions

## Access boundaries

| Routes | Authentication | Authorization |
| --- | --- | --- |
| `POST /auth/v1/sessions` | Operator email/password in JSON | Active account; unknown, wrong-password and disabled cases share one error. |
| `/auth/v1/me`, `DELETE /auth/v1/sessions/current`, `/cloud/v1/...` | Opaque bearer token or HttpOnly browser cookie | Valid, unexpired, unrevoked session and active operator/client; research reads are owner-filtered. |
| `/auth/v1/clients...` | Web bearer session or browser cookie | Own clients only; reviewer accounts cannot create clients. |
| `/data/...`, `/experiments/...`, `/recognition/...` | Separate development HTTP Basic | Shared development access; not a tenant-safe cloud API. |
| Direct `/v1/registry/...` inside ML | Private `X-Cloud-Key` plus gateway-verified `X-Operator-ID` | Only trusted gateway context; operator filter on every query. Public clients do not receive this key. |
| Gateway `/health/live`, `/metrics/`, `/docs`, `/redoc`, `/openapi.json` | No account required | Operational/reference surfaces; domain readiness checks stay private or behind Basic proxy. |

The bearer token is opaque, not JWT. Web sessions last eight hours; registered client sessions last thirty days. Disabled operators and revoked clients invalidate existing sessions immediately. No offline authorization or token renewal flow is implemented. Use TLS when deploying remotely; these setup instructions bind host-facing development ports to loopback.

## Error bodies

Application errors normally use:

```json
{"detail":"Registry item not found"}
```

Database/unexpected failures may add `correlation_id`. All normal gateway/service API responses carry `X-Correlation-ID`; provide `X-Correlation-ID: tutorial-request-1` to propagate a valid identifier. Prometheus/documentation infrastructure is not a research JSON API.

Framework validation errors use a **detail array**:

```json
{"detail":[{"loc":["path","item_id"],"msg":"Input should be a valid UUID","type":"uuid_parsing"}]}
```

Explicit application validation can use a **detail string** with the same HTTP 422 status. Client code must accept both shapes. Never log a complete login payload or bearer header; validation payloads can contain submitted values.

## Status codes and exact application messages

| Status | Conditions and messages |
| --- | --- |
| 200 | Read/completed synchronous operation. Inspect the business `status` of jobs/replays; HTTP success alone is not scientific success. |
| 201 | Resource/job/replay record created. A synchronous summary/replay can be persisted as `failed`; inspect `error`. |
| 202 | Legacy LDA job accepted; poll `Location`. Work may still fail or be interrupted. |
| 204 | Session/client revoked; the response has no JSON body. |
| 401 | `Invalid email or password`; `Sign in required`; `Session expired or revoked`; `Invalid credentials`; framework `Not authenticated` / `Invalid authentication credentials`; internal `Trusted gateway context required`. Reauthenticate with the correct mechanism. |
| 403 | `Web session required`; `Reviewer access is read-only`; `Use operator-authenticated cloud routes`. Do not substitute internal headers for an operator session. |
| 404 | `Participant not found`; `Recording not found`; `Split not found`; `Referenced record not found`; `Draft manifest not found`; `Manifest not found`; `Frozen manifest not found`; `Draft calibration subset not found`; `Calibration subset not found`; `Job not found`; `Experiment not found`; `Published model not found`; `Replay session not found`; `Model event not received`; `Client not found`; `Collection not found`; `Registry item not found`; `Route not found`. Foreign client/registry IDs deliberately return 404. |
| 409 | `Pseudonym already exists`; `Source and test recordings overlap`; `Operation conflicts with split constraints`; `Idempotency key belongs to a different request`. Inspect immutable membership/input rules; do not retry a changed request with the same idempotency key. |
| 413 | `Request body is too large` at the development proxy (2,000,000 bytes); frontend nginx also limits request bodies to 2 MB and can return a non-JSON proxy error. |
| 422 | Pydantic field/path/query validation; `Invalid idempotency key`; `Name and platform must not be blank`. Correct the request instead of retrying unchanged. |
| 429 | `Rate limit exceeded`. Gateway default is 60 requests/minute per client IP, including failed login; honor `Retry-After` seconds. Limits are process-local. |
| 500 | `Internal server error`. Keep the correlation ID and investigate server logs; stack traces are not part of the public response. |
| 502 | `Service unavailable`; `Registry unavailable`; `Invalid service API document`. A dependency/proxy failed. |
| 503 | `Database operation failed`; `Operator access unavailable`; `Operator access is not configured`; `Cloud registry is not configured`; `Signal artifact missing or invalid`; `Gateway credentials are not configured`; `Gateway rate limit is invalid`; `Service address is not configured`. Check credentials, readiness and artifacts. |
| 504 | `Service request timed out`; `Registry request timed out`. Retry safe reads after resolving the dependency; avoid duplicate writes. |

## Pagination, repeat requests and artifacts

- Cloud collections return `{items,next_offset}`. `limit` is 1–100, default 50; `offset` is nonnegative. `next_offset=null` ends pagination. The older Data participant/recording lists return arrays and use `limit`/`offset` without a total count.
- `Idempotency-Key` is supported by legacy LDA submission only. Identical input/key returns the same job; changed input/key is a 409. Do not assume other POSTs are idempotent. Tutorial-generated pseudonyms/names use a unique suffix to permit independent reruns.
- A frozen manifest and frozen calibration membership cannot be edited. Create a new version instead of modifying published inputs. Operator identities are distinct from participant identities.
- Artifact SHA-256 applies to **exact response bytes**. Hash before JSON parsing/reserialization. The public proxy preserves `X-Artifact-SHA256` and the legacy run response exposes `model_checksum`.
- `rest_false_activation_rate=null` with `rest_missing_reason` (or legacy `rest_false_activation_missing_reason`) means N/A, not a measured zero. Recognition `processing_p95_ms` covers feature extraction/prediction only, not end-to-end sensor/display latency.
- Unsupported methods/routes can also produce standard framework/proxy HTTP errors. The OpenAPI files document the implemented operations, their expected application errors and gateway failures; future worker/upload/synchronization contracts are not advertised as working endpoints.

Browser sessions use the HttpOnly `myocontrol_web_session` cookie (`SameSite=Strict`, eight-hour lifetime). Cookie-authenticated mutations require `X-MyoControl-Web: 1`; sign-in requests carrying Origin require it too. Missing headers return 403. The SPA sends same-origin credentials and restores through `/auth/v1/me` after reload. Set `WEB_SESSION_SECURE=true` for HTTPS deployments behind TLS termination. Bearer desktop/worker clients remain supported independently.
