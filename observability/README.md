# Local observability

The optional Compose `observability` profile starts Prometheus, Grafana, Alertmanager, Jaeger and Loki. Prometheus scrapes the four HTTP processes. The Grafana dashboard contains availability, experiment completion and recognition processing metrics. Recognition's p95 covers feature extraction and prediction only; it excludes window accumulation, transport and rendering.

Before starting Compose, set the database, gateway and RabbitMQ environment variables described in the root README. To enable the observability profile, additionally set `GRAFANA_PASSWORD`, `OTEL_SDK_DISABLED=false` and `OTEL_LOGS_EXPORTER=otlp`, then run:

```powershell
docker compose --profile observability up -d --build
```

Local interfaces are Grafana at `http://127.0.0.1:3001`, Prometheus at `http://127.0.0.1:9090` and Jaeger at `http://127.0.0.1:16686`. Grafana's default username is `admin`, unless `GRAFANA_USER` is set. Use the configured `GRAFANA_PASSWORD`. Do not share credentials.

HTTP traces use OpenTelemetry and Jaeger. Structured application logs are exported via OTLP to Loki when telemetry is enabled. Traces and logs may contain pseudonymous IDs and request paths; do not expose or retain them without an approved policy. Jaeger's local traces are in memory. Alertmanager currently has a local receiver only: external email or messaging notifications are TBD. Database and infrastructure metrics beyond application/process metrics are also TBD.

After running the synthetic end-to-end flow, verify the local telemetry pipeline with:

```powershell
Get-Content -Raw observability/check_telemetry.py | docker compose exec -T gateway python -
```

The script checks service availability in Prometheus, a distributed ML trace involving gateway and data service, and gateway logs in Loki. This single-node setup is for development, not a secure or highly available production deployment.
