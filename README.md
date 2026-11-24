# Simulated Myoelectric Prosthesis

## Accepted deployment and delivery

The accepted target has three boundaries: **cloud storage/research APIs and adaptive web UI**, **general training on a powerful local workstation**, and **Electron for local calibration/adaptation and live recognition**. Operator accounts, models and experiment results are centrally stored. The desktop bundles Python/PLUX SDK and manages local processes; the training worker is separately reproducible.

See [accepted decisions](docs/ARCHITECTURE_DECISIONS.md), [deployment diagram](docs/DEPLOYMENT_ARCHITECTURE.md) and [design PRD](docs/DESIGN_PRD.md). Provider/sizing remain open. The Mac mini is an infrastructure option, not an architectural dependency. The commands below describe the existing single-host development environment; they do not deploy the complete accepted target.

A research prototype for recognising hand gestures from surface electromyography (sEMG), studying calibration with limited labelled data, and controlling a simulated hand.

## Project structure

- `backend/` — Python application, artifact storage and tests.
- `database/` — PostgreSQL schema, migrations, roles and database documentation.
- `frontend/` — operator interface.
- `experiments/` — experiment protocols and configurations.
- `data/` — local data and artifact storage guidance.
- `architecture/` — proposed service boundaries, deployment and migration plan.
- `services/` — independently packaged business services under development.
- `gateway/` — authenticated local entry point for the service APIs.
- `observability/` — optional local metrics, logs and tracing configuration.

## Current status

The repository contains a PostgreSQL schema, local artifact storage and early Data & Protocol, ML Experiments and Recognition services. A synthetic flow trains and evaluates a source-only LDA model and replays predictions through a gateway. Synthetic results are infrastructure checks, not evidence of recognition performance on measured EMG. See [architecture](architecture/README.md) and the service README files for the current scope and limitations.

The following work remains **TBD**:

- Import and validation of real recordings, including Ninapro DB2.
- Validation of signal processing, model training and evaluation on measured data, plus personalised and target-only models.
- Cloud deployment and further authorization of legacy domain routes, Electron packaging, local calibration/adaptation and live SDK integration, remote local-training worker contracts and synchronization.
- Final experimental protocol, deployment configuration and data retention policy.

Participant data, restricted datasets, credentials and generated artifacts must remain outside version control.

## Local services

Database review starts with the [teacher README](database/README_TEACHER.md): isolated setup, migration/upgrade checks and acceptance tests. Also see [current ER diagrams](database/SERVICE_MODEL.md), [generated service dictionary](database/SERVICE_DATA_DICTIONARY.md), [service DDL](database/service_schema.sql), [setup instructions](database/README.md) and the [historical/combined model](database/LOGICAL_MODEL.md). These documents distinguish the original schema from the schemas currently used by the local services.

Create a local `.env` file with the variables below before using Compose. Choose distinct passwords and do not commit this file. The database and RabbitMQ passwords initialize their respective volumes on first startup; changing the environment alone does not update an existing volume's credentials.

```powershell
@'
POSTGRES_PASSWORD=replace-with-a-unique-long-password
DATA_DB_PASSWORD=replace-with-another-unique-long-password
ML_DB_PASSWORD=replace-with-another-unique-long-password
RECOGNITION_DB_PASSWORD=replace-with-another-unique-long-password
IDENTITY_DB_PASSWORD=replace-with-another-unique-long-password
CLOUD_INTERNAL_KEY=replace-with-a-random-secret-of-at-least-32-characters
RABBITMQ_USER=myocontrol
RABBITMQ_PASSWORD=replace-with-another-unique-long-password
REDIS_PASSWORD=replace-with-another-unique-long-password
GATEWAY_USERNAME=operator
GATEWAY_PASSWORD=replace-with-another-unique-long-password
GRAFANA_PASSWORD=replace-with-another-unique-long-password
'@ | Set-Content -Encoding ascii .env
```

Edit the placeholder values before starting the services.

```powershell
docker compose up -d --build
```

The gateway is available on `http://127.0.0.1:8000`; service documentation is available at `/data/docs`, `/experiments/docs` and `/recognition/docs` after signing in with the gateway credentials. The development gateway uses HTTP Basic on loopback; a remote deployment requires TLS and a production access design. Use only synthetic data. The optional [observability profile](observability/README.md) starts monitoring and tracing locally.

Run `docker compose --profile observability stop` to stop the local services without deleting their volumes. Rebuild after changes using `docker compose --profile observability up -d --build`.

## Operator interface

Start the React interface with `docker compose --profile ui up -d --build` and open **http://127.0.0.1:3000**. The cloud portal signs in individual operators and reads their experiments, published models and completed evaluations from the new registry. Create an account using the [gateway setup](gateway/README.md); the shared development gateway password is not a portal account. Interactive signal/hand components remain in source for Electron reuse. See the [frontend guide](frontend/README.md) for implemented flows and remaining scope.
