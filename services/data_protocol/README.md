# Data and Protocol Service

API reference: [versioned OpenAPI JSON](data_protocol/openapi.json), [Getting Started and integration tutorials](../../api/README.md). The gateway serves the complete client contract at `/docs`, `/redoc` and `/openapi.json`. CI validates stored specifications and all body examples.


## Database extension available

The additive SQL migrations and [database acceptance tests](../../database/README_TEACHER.md) now provide identity persistence (separate schema), source/publication metadata, generic ML registry/leases/packages/evaluations and terminal desktop reports in their owning schemas. Existing endpoints still use their original tables; this does not automatically implement new cloud or Electron contracts.

## Accepted data placement

[ADR-001](../../docs/ARCHITECTURE_DECISIONS.md) makes cloud APIs/storage authoritative for published research metadata and permitted artifacts. Electron collects/validates local calibration/recording data and uploads pending records idempotently. The local training worker obtains permitted frozen inputs through APIs. Neither client connects directly to PostgreSQL.

Cloud operator authorization, robust provenance/publication and synchronization contracts are requirements; the current synthetic-only service below does not yet provide them. Research participants remain separate from operator accounts.

This service provides PostgreSQL-backed participant, four-channel recording, protocol, labelled segment, split and calibration APIs. It is not production-ready and must be used only with synthetic data in a trusted local environment.

Install `requirements.txt`. Set `DATA_DATABASE_URL` to a SQLAlchemy `postgresql+psycopg` URL, set `DATA_ARTIFACT_ROOT` to a controlled local directory, and apply the SQL files in `migrations/` in order to a disposable PostgreSQL database. From this directory run:

```powershell
python -m uvicorn data_protocol.main:app --host 127.0.0.1 --port 8001
```

Interactive API documentation is at `http://127.0.0.1:8001/docs`. Create a participant using `POST /v1/participants`, then submit the returned ID and a four-channel array to `POST /v1/recordings`. Recording files are stored under `DATA_ARTIFACT_ROOT` using a SHA-256 filename; a failed database write can leave an orphan file. Sample counts are limited to 10,000 per request. Use only synthetic data.

The API supports an immutable full-recording source/test split for simple synthetic checks, and versioned research manifests with participant roles, labelled segments and calibration budgets. It rejects overlapping roles when original signal content has the same checksum. This is not a complete cross-source identity solution: transformed duplicates and unknown participant identity are not resolved. The independent `data_protocol` schema is not connected to the legacy `myoprosthesis` schema; migration of existing records requires a separate, tested plan. Dataset licensing, source versions, full recording provenance and a tested DB2 importer are TBD. It has no authentication or rate limiting of its own; do not expose it outside a trusted network.

For a minimal recording request, first create a participant, then use its returned ID in:

```json
{
  "participant_id": "replace-with-participant-id",
  "sample_rate_hz": 1000,
  "samples": [[1, 2, 3, 4], [3, 4, 5, 6]]
}
```

Use another participant and different samples for the test recording. Submit both recording IDs to the synthetic split endpoint. This simplified split does not establish the data provenance required for experiments.
