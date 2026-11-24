# Tutorial: integrate an operator and local client

## Goal and prerequisites

Use an operator account to authenticate, read its cloud records, issue a scoped local-client token, revoke it and log out. Complete [Getting Started](../GETTING_STARTED.md) first. Use a normal `operator` or `administrator` account; a `reviewer` cannot register clients.

Every step below is performed by:

```powershell
python api/tutorial.py cloud --email expert@example.test
```

It prompts for the operator password, keeps tokens in memory and never prints them. The source is [api/tutorial.py](../tutorial.py), requiring only Python's standard library. Examples below show the HTTP exchanges so another client can implement the same flow.

## 1. Sign in

Send `POST http://127.0.0.1:8000/auth/v1/sessions` with `Content-Type: application/json`:

```json
{"email":"expert@example.test","password":"YOUR_OPERATOR_PASSWORD"}
```

Expected HTTP **200**:

```json
{
  "access_token":"OPAQUE_TOKEN_RETURNED_BY_SERVER",
  "token_type":"bearer",
  "expires_at":"2026-11-24T18:00:00Z",
  "operator":{"id":"00000000-0000-4000-8000-000000000011","display_name":"API expert","role":"operator"}
}
```

UUIDs and timestamps here are illustrative; retain the actual returned values. An incorrect password returns **401** `{"detail":"Invalid email or password"}`. Do not put a password/token in a URL or commit it to a configuration file.

## 2. Validate the session

Send `GET /auth/v1/me` with:

```http
Authorization: Bearer OPAQUE_TOKEN_RETURNED_BY_SERVER
```

Expected **200** includes `operator_id`, `display_name`, `role`, `scope:"web"`, `client_id:null` and `expires_at`. An expired/revoked session returns **401**. Operator identity is not a research participant ID.

## 3. Read records and follow pagination

With the same bearer header:

```http
GET /cloud/v1/runs?limit=25&offset=0
GET /cloud/v1/models?limit=25&offset=0
GET /cloud/v1/results?limit=25&offset=0
```

Each returns **200**. For a fresh account:

```json
{"items":[],"next_offset":null}
```

When `next_offset` is an integer, request that offset until it becomes null. For an existing record, use its returned `id` with `GET /cloud/v1/models/{id}` (or the corresponding runs/results path). Foreign/nonexistent IDs return **404**. Result detail adds `confusion_counts`; absent rest observations remain N/A rather than zero false activation.

An empty registry does not require running the legacy LDA tutorial: its development records belong to a separate API and are not automatically published into the cloud generic registry.

## 4. Provision a scoped local client

Using the **web bearer session**, send `POST /auth/v1/clients`:

```json
{"kind":"training_worker","name":"Tutorial workstation","platform":"tutorial"}
```

Expected **201**:

```json
{
  "client_id":"00000000-0000-4000-8000-000000000014",
  "access_token":"NEW_CLIENT_TOKEN_RETURNED_ONCE",
  "token_type":"bearer",
  "expires_at":"2026-12-24T10:00:00Z",
  "scope":"training_worker"
}
```

Call `GET /auth/v1/me` with the **new client token** and confirm `scope:"training_worker"` and the returned client ID. Client credentials can read their operator's cloud registry but cannot provision more clients. `GET /auth/v1/clients` with a client token returns **403** `Web session required`; with the original web token it returns the account's client list without raw tokens.

Provisioning credentials does not start training or prove a completed remote-worker implementation. Remote claim/heartbeat/publication contracts are not advertised as existing endpoints.

## 5. Revoke the client

With the **original web token**, send `DELETE /auth/v1/clients/{returned-client-id}`. Expected **204**, with no body.

Call `GET /auth/v1/me` again with the revoked client token. Expected **401** `Session expired or revoked`. This verifies that revocation is checked by the server rather than hidden by the UI. A foreign client ID returns **404**; revocation cannot be undone.

## 6. Log out

With the web token, send `DELETE /auth/v1/sessions/current`. Expected **204**. Reusing that token with `GET /auth/v1/me` now returns **401**.

Expected executable tutorial output:

```text
Signed in; scope=web
runs: 0 item(s), next_offset=None
models: 0 item(s), next_offset=None
results: 0 item(s), next_offset=None
Client token scope and immediate revocation verified; no token was printed.
Logout verified: revoked web token receives HTTP 401.
```

Registry counts vary with the account. The tutorial leaves an auditable revoked client record and revokes its issued sessions. Its cleanup attempts revocation even when an integration step fails.
