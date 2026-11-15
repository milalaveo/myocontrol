# Local server deployment

`compose.server.yaml` is an optional TLS reverse proxy for a server that has a public DNS name and reachable ports 80 and 443. It has not been deployed. Confirm server ownership, firewall configuration, institution data rules and the `172.30.246.0/24` Docker subnet before use. The base application is still a research prototype and must not be used for real participant data until access control and data policies are complete.

The base Compose environment variables are documented in the root README. In addition, set `PUBLIC_HOST` to the server domain and `ACME_EMAIL` to an address for certificate notices. Caddy requests and renews a certificate; the domain must resolve to the server and certificate validation must be possible. With a private-only server, use an institution-approved VPN or certificate setup instead of assuming public ACME access.

Once the environment and deployment are approved, a manual command is:

```powershell
docker compose -f compose.yaml -f compose.server.yaml up -d --build
```

The gateway trusts the forwarded client IP only from the Caddy container's fixed address. Other forwarded headers are ignored for rate limiting. The local gateway still uses one configured HTTP Basic account, an in-memory rate limiter and no per-user authorization; these are not sufficient for a production multi-user environment. Monitoring endpoints remain bound to loopback when the observability profile is enabled. Do not expose PostgreSQL, RabbitMQ, Redis, Loki or service containers directly.

**TBD:** exact server address, DNS/firewall and certificate policy, operator accounts and access model, deployment runner, immutable image versions, backups, retention, alert recipient, and a reviewed rollback procedure. The image publication workflow is manual and is not an automatic deployment pipeline.
