# Current Service Database — Logical Schemas

**Scope:** implemented additive migrations in `services/*/migrations`; historical `myoprosthesis` is documented separately. Tables below are database structure, not evidence of completed cloud APIs or Electron integration.

## Identity — cloud operators

```mermaid
erDiagram
    operators ||--o{ clients : registers
    operators ||--o{ access_sessions : authenticates
    clients o|--o{ access_sessions : scopes
    operators {
        uuid id PK
        text email UK
        text password_hash
        text role
        text state
    }
    clients {
        uuid id PK
        uuid operator_id FK
        text kind
        text state
    }
    access_sessions {
        uuid id PK
        uuid operator_id FK
        uuid client_id FK
        text token_sha256 UK
        text scope
        timestamptz expires_at
        timestamptz revoked_at
    }
```

Composite client/owner FK prevents a session from belonging to a different operator's device. Session scope must match the registered client kind. Credentials are digests/encoded hashes, not plaintext. Operator and client revocation remove sessions from `valid_session_ids`. HTTP token issuance and enforcement remain application work.

## Data & Protocol — existing research allocation and new publication provenance

```mermaid
erDiagram
    participants ||--o{ recordings : owns
    recordings ||--o{ labelled_segments : contains
    recordings ||--o| recording_provenance : describes
    recordings ||--o| client_publications : acknowledges
    recordings ||--o{ synthetic_splits : source_or_test
    protocol_versions ||--o{ research_manifests : governs
    research_manifests ||--o{ manifest_participants : assigns
    participants ||--o{ manifest_participants : participates
    manifest_participants ||--o{ manifest_units : allocates
    labelled_segments ||--o{ manifest_units : selects
    manifest_participants ||--o{ calibration_subsets : calibrates
    calibration_subsets ||--o{ calibration_items : contains
    manifest_units ||--o{ calibration_items : eligible_unit
```

`client_publications(operator_id, client_id, local_recording_id)` is unique. Identical retry returns the existing receipt; changed payload/recording is rejected. `recording_provenance` preserves source version, original identity/hash/coordinates and channel metadata. Legacy records are not automatically research-ready: the existing manifest format/checksums are not silently rewritten, and real-data identity/transformation validation still belongs to ingestion.

## ML Experiments — generic model and result registry

```mermaid
erDiagram
    experiment_runs ||--o| model_versions : produces
    experiment_runs ||--o| evaluations : evaluates
    experiment_runs o|--o{ experiment_runs : retry_of
    model_versions o|--o{ experiment_runs : source_parent
    model_versions o|--o{ experiment_runs : evaluated_model
    artifacts ||--o{ model_versions : stores
    model_versions ||--o{ model_classes : maps
    model_versions ||--o{ model_package_items : packages
    artifacts ||--o{ model_package_items : supplies
    model_versions ||--o{ evaluations : tested_model
    evaluations ||--o{ confusion_counts : reports
    model_classes ||--o{ confusion_counts : actual_class
    model_classes ||--o{ confusion_counts : predicted_class
```

This is distinct from the backwards-compatible `source_lda_runs`, `signal_summary_jobs` and `outbox_events` path. A successful generic fitting run and a published model commit atomically. Evaluation success requires a complete class-pair matrix and mathematically consistent accuracy/macro-F1/rest false-activation rate. The deferred constraint validates final transactional state.

All external identity/manifest/target/calibration UUIDs are checked through their owning APIs, not cross-service joins or cross-schema FKs. Model/run/artifact/class FKs shown here are within the ML boundary. Local workers have no direct database login. Lease identity/expiry gates completion; retries use a new run linked to the old attempt.

## Recognition — synchronized desktop reports

```mermaid
erDiagram
    desktop_sessions {
        uuid id PK
        uuid operator_id
        uuid client_id
        uuid local_session_id
        uuid model_version_id
        text model_sha256
        text mode
        text status
        boolean neutral_confirmed
        bigint prediction_count
        text payload_sha256
    }
    replay_sessions {
        uuid id PK
        uuid model_run_id
        uuid recording_id
        text status
    }
    model_events {
        uuid event_id PK
        uuid model_run_id
    }
```

There are no FKs between these three tables. `replay_sessions`/`model_events` are the existing development path; `desktop_sessions` stores immutable terminal client reports with unique client/session identity. Model/account/recording references are external and API-validated. Neutral confirmation records actual evidence; a failed confirmation is retained rather than invented as success.

## PNG exports

- [Identity](SERVICE_MODEL_IDENTITY.png)
- [Data and Protocol](SERVICE_MODEL_DATA.png)
- [Models and evaluations](SERVICE_MODEL_RESEARCH.png)
- [Desktop and legacy recognition](SERVICE_MODEL_RECOGNITION.png)

## Reading and reviewing

- [Teacher review README](README_TEACHER.md)
- [Generated service dictionary](SERVICE_DATA_DICTIONARY.md)
- [Generated service DDL](service_schema.sql)
- [Existing complete logical model](LOGICAL_MODEL.md)
- [Implementation and limitations](IMPLEMENTATION.md)
