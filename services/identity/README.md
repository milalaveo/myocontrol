# Cloud Identity Persistence

This directory contains the PostgreSQL migration for operator accounts, registered desktop/training clients and scoped access-session digests. The [gateway identity adapter](../../gateway/README.md) implements login and client provisioning against this schema; identity is not a fourth independently running business service.

The service migrator applies `migrations/0001_operators.sql` before the existing Data/ML/Recognition migrations. Application accounts are rows, not PostgreSQL users. Operator and participant identities remain separate.

- Encoded Argon2id password hashes only; application code must validate parameters, hash/verify passwords and never expose hashes.
- Opaque bearer tokens are represented by SHA-256 digests, issue/expiry times, scope and revocation.
- A registered desktop or worker belongs to one operator; the session's composite FK and trigger enforce that ownership and kind.
- Disabled operators and revoked clients/sessions are excluded from `valid_session_ids`; revoked clients/sessions cannot be reactivated.
- The identity role cannot query other service schemas; reviewer views expose no identity credentials.

`myocontrol_identity` is provisioned as a NOLOGIN group. `IDENTITY_DB_PASSWORD` additionally provisions `identity_service_login` through the migrator for the gateway adapter. Configure it together with `CLOUD_INTERNAL_KEY` to enable the cloud portal. Legacy domain routes retain separate development Basic auth. Offline desktop grants and remote worker job/publication contracts remain outstanding.

Review: [teacher guide](../../database/README_TEACHER.md), [dictionary](../../database/SERVICE_DATA_DICTIONARY.md), [logical schemas](../../database/SERVICE_MODEL.md).
