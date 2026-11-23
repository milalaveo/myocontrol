# Database Data Dictionary

## Accepted target versus existing schema

The accepted [ADR-001](../docs/ARCHITECTURE_DECISIONS.md) now has additive persistence migrations: `identity/0001`, `data_protocol/0006`, `ml_experiments/0007` and `recognition/0003`. They add operator/client/session records, publication provenance/receipts, a generic run/model/package/evaluation registry and desktop reports. See the [teacher guide](README_TEACHER.md), [current logical diagrams](SERVICE_MODEL.md) and [generated service dictionary](SERVICE_DATA_DICTIONARY.md). HTTP identity, authenticated worker APIs and actual Electron synchronization remain application work; schema support does not establish a completed runtime.

This dictionary describes the tables and views created by the SQL migrations in this repository. It covers both the original `myoprosthesis` schema and the current service-owned schemas. PostgreSQL types are shown as declared in the migrations. Primary keys, foreign keys, unique constraints and important checks are listed where they define the data model.

## Which schema is used

The Docker migrator installs `identity`, `data_protocol`, `ml_experiments` and `recognition`. Existing HTTP services use the earlier Data/ML/Recognition tables; the additive registry/identity tables are ready at the persistence layer but not yet wired into the new application contracts. The original `myoprosthesis` schema belongs to the earlier single-application backend and is migrated separately with Alembic. The schemas are not yet a data migration path from one another. The Compose database also contains `public.service_schema_migrations`, which records service migration names and checksums.

## Current schema coverage

The current service database has **28 business tables** across `identity`, `data_protocol`, `ml_experiments` and `recognition`. [SERVICE_DATA_DICTIONARY.md](SERVICE_DATA_DICTIONARY.md) contains every current service column, key, CHECK and index, generated from the migrated database. The tables below retain detailed descriptions of the compatible pre-registry path and the 31-table historical backend. They are not a claim that the new registry is used by existing HTTP endpoints.

## Service schemas

### `data_protocol`

| Table | Column | PostgreSQL type | Keys and rules | Meaning |
|---|---|---|---|---|
| `participants` | `id` | `uuid` | PK | Participant identifier. |
| | `pseudonym` | `varchar(100)` | NOT NULL, UNIQUE; identifier format check | Pseudonymous participant label. |
| `recordings` | `id` | `uuid` | PK | Recording identifier. |
| | `participant_id` | `uuid` | FK → `participants.id`, NOT NULL | Owner participant. |
| | `sample_rate_hz` | `numeric` | NOT NULL; positive and at most 100000 | Sampling frequency in hertz. |
| | `sample_count` | `integer` | NOT NULL; 1–10000 | Number of samples in the recording. |
| | `artifact_sha256` | `varchar(64)` | NOT NULL; lowercase SHA-256 format | Hash identifying the stored signal artifact. |
| `protocol_versions` | `id` | `uuid` | PK | Protocol version identifier. |
| | `name` | `varchar(120)` | NOT NULL | Protocol name. |
| | `version` | `integer` | NOT NULL; positive; UNIQUE with `name` | Protocol version number. |
| | `gesture_codes` | `text[]` | NOT NULL; non-empty; includes `rest`; unique valid codes enforced by trigger | Gesture classes permitted by the protocol. |
| `labelled_segments` | `id` | `uuid` | PK | Labelled segment identifier. |
| | `recording_id` | `uuid` | FK → `recordings.id`, NOT NULL | Recording containing the segment. |
| | `gesture_code` | `text` | NOT NULL; identifier format check | Gesture label. |
| | `repetition_key` | `text` | NOT NULL; non-empty; UNIQUE with `recording_id` | Repetition identity within a recording. |
| | `start_sample` | `bigint` | NOT NULL; non-negative | Inclusive start sample. |
| | `end_sample` | `bigint` | NOT NULL; greater than `start_sample` | Exclusive end sample. |
| `research_manifests` | `id` | `uuid` | PK | Research split manifest identifier. |
| | `protocol_id` | `uuid` | FK → `protocol_versions.id`, NOT NULL | Protocol governing the manifest. |
| | `name` | `varchar(120)` | NOT NULL; UNIQUE with `version` | Manifest name. |
| | `version` | `integer` | NOT NULL; positive | Manifest version. |
| | `state` | `text` | NOT NULL; `draft` or `frozen` | Whether manifest membership can still be edited. |
| | `checksum` | `varchar(64)` | Nullable in draft; required SHA-256 when frozen | Frozen manifest content checksum. |
| | `frozen_at` | `timestamptz` | Nullable in draft; required when frozen | Freeze timestamp. |
| `manifest_participants` | `manifest_id` | `uuid` | PK part; FK → `research_manifests.id` | Manifest membership. |
| | `participant_id` | `uuid` | PK part; FK → `participants.id` | Participant assigned to the manifest. |
| | `category` | `text` | NOT NULL; `source`, `development` or `target`; UNIQUE with manifest and participant | Participant-level data category. |
| `manifest_units` | `id` | `uuid` | PK | Split unit identifier. |
| | `manifest_id` | `uuid` | Composite FK → `manifest_participants` | Parent manifest. |
| | `participant_id` | `uuid` | Composite FK → `manifest_participants` | Unit participant. |
| | `category` | `text` | Composite FK; constrained with `role` | Participant category. |
| | `segment_id` | `uuid` | FK → `labelled_segments.id`, NOT NULL | Segment assigned to this unit. |
| | `role` | `text` | NOT NULL; role/category compatibility check; UNIQUE with manifest, segment and role | `source_train`, `development_validation`, `target_calibration` or `target_test`. |
| `synthetic_splits` | `id` | `uuid` | PK | Identifier for a synthetic split fixture. |
| | `source_recording_id` | `uuid` | NOT NULL; FK → `recordings.id` | Source training recording. |
| | `test_recording_id` | `uuid` | NOT NULL; FK → `recordings.id`; different from source | Held-out test recording. |
| | `checksum` | `varchar(64)` | NOT NULL; SHA-256 format | Immutable split checksum computed by a trigger. |
| `calibration_subsets` | `id` | `uuid` | PK | Calibration subset identifier. |
| | `manifest_id` | `uuid` | Composite FK → `manifest_participants` | Frozen research manifest. |
| | `participant_id` | `uuid` | Composite FK → `manifest_participants` | Target participant. |
| | `category` | `text` | NOT NULL; default and check `target` | Required target category. |
| | `selection_version` | `text` | NOT NULL; non-empty | Calibration selection algorithm/version label. |
| | `budget_per_gesture` | `integer` | NOT NULL; positive | Required number of calibration units per class. |
| | `state` | `text` | NOT NULL; `draft` or `frozen` | Subset editability state. |
| | — | — | UNIQUE (`manifest_id`, `participant_id`, `selection_version`, `budget_per_gesture`) | Prevents duplicate subset definitions. |
| `calibration_items` | `subset_id` | `uuid` | PK part; FK → `calibration_subsets.id` | Parent subset. |
| | `unit_id` | `uuid` | PK part; FK → `manifest_units.id` | Selected target calibration unit. |

The `calibration_durations` view reports unique selected signal duration in seconds per subset and gesture, merging overlapping sample intervals for the same artifact.

### `ml_experiments`

| Table | Column | PostgreSQL type | Keys and rules | Meaning |
|---|---|---|---|---|
| `signal_summary_jobs` | `id` | `uuid` | PK | Summary job identifier. |
| | `split_id` | `uuid` | NOT NULL; external reference owned by Data & Protocol | Source split identifier. |
| | `status` | `varchar(20)` | NOT NULL; `running`, `succeeded` or `failed` | Job state. |
| | `split_checksum` | `varchar(64)` | Nullable; SHA-256 required for success | Split snapshot checksum. |
| | `result` | `jsonb` | Nullable; required for success | Computed summary result. |
| | `error` | `varchar(100)` | Nullable; required for failure | Failure description. |
| `source_lda_runs` | `id` | `uuid` | PK | Experiment job/model run identifier. |
| | `manifest_id` | `uuid` | NOT NULL; external reference to Data & Protocol | Frozen manifest used by the run. |
| | `target_participant_id` | `uuid` | NOT NULL; external participant reference | Held-out target participant. |
| | `status` | `varchar(20)` | NOT NULL; `queued`, `running`, `succeeded`, `failed` or `interrupted` | Experiment job state. |
| | `manifest_checksum` | `varchar(64)` | Nullable; SHA-256 required on success | Frozen input manifest checksum. |
| | `snapshot` | `jsonb` | Nullable; required on success | Immutable input/provenance snapshot. |
| | `model` | `jsonb` | Nullable; required on success | Serialized model artifact. |
| | `metrics` | `jsonb` | Nullable; required on success | Evaluation metrics and results. |
| | `error` | `text` | Nullable; required for failed/interrupted states | Failure or interruption reason. |
| | `created_at` | `timestamptz` | NOT NULL, default current timestamp | Job creation time. |
| | `completed_at` | `timestamptz` | Nullable; required for terminal states | Job completion time. |
| | `model_checksum` | `varchar(64)` | Nullable; SHA-256 format | Model artifact checksum. |
| | `started_at` | `timestamptz` | Nullable | Worker start time. |
| | `heartbeat_at` | `timestamptz` | Nullable | Latest worker heartbeat. |
| | `idempotency_key` | `varchar(100)` | Nullable, UNIQUE | Client key preventing duplicate submissions. |
| | `correlation_id` | `varchar(64)` | NOT NULL, default `legacy` | Request correlation identifier. |
| | `trace_context` | `jsonb` | NOT NULL, default `{}`; must be a JSON object | Trace context propagated to asynchronous processing. |
| `outbox_events` | `id` | `uuid` | PK | Outbox event identifier. |
| | `run_id` | `uuid` | FK → `source_lda_runs.id`, NOT NULL, UNIQUE | Run that produced the event. |
| | `event_type` | `varchar(100)` | NOT NULL; currently `ModelPublished` | Domain event name. |
| | `payload` | `jsonb` | NOT NULL | Event body. |
| | `created_at` | `timestamptz` | NOT NULL, default current timestamp | Event creation time. |
| | `published_at` | `timestamptz` | Nullable | Broker publish confirmation time. |

### `recognition`

| Table | Column | PostgreSQL type | Keys and rules | Meaning |
|---|---|---|---|---|
| `replay_sessions` | `id` | `uuid` | PK | Replay session identifier. |
| | `model_run_id` | `uuid` | NOT NULL; external reference to ML Experiments | Published model run used for replay. |
| | `recording_id` | `uuid` | NOT NULL; external reference to Data & Protocol | Recording replayed. |
| | `status` | `varchar(20)` | NOT NULL; `running`, `succeeded` or `failed` | Replay state. |
| | `model_checksum` | `varchar(64)` | Nullable; SHA-256 format on success | Verified model checksum. |
| | `result` | `jsonb` | Nullable; required for terminal states | Replay output and timing summary. |
| | `error` | `varchar(200)` | Nullable; required on failure | Replay failure reason. |
| `model_events` | `event_id` | `uuid` | PK | Broker event identifier; provides consumer idempotency. |
| | `model_run_id` | `uuid` | NOT NULL; external ML reference | Published model run. |
| | `manifest_id` | `uuid` | NOT NULL; external Data & Protocol reference | Model's source manifest. |
| | `correlation_id` | `varchar(64)` | NOT NULL | Correlation identifier propagated with the event. |
| | `received_at` | `timestamptz` | NOT NULL, default current timestamp | Event receipt time. |

## Original `myoprosthesis` schema

These tables are created by `database/migrations/` and are used by the earlier backend. The service Compose deployment does not migrate or query this schema. Later migrations add columns and constraints; descriptions below show the final shape after applying all revisions through `head`.

| Table | Columns (type; `*` marks primary key) | Foreign keys and purpose |
|---|---|---|
| `datasets` | `id bigint*`, `name text` | Dataset catalog; `name` is unique. |
| `dataset_versions` | `id bigint*`, `dataset_id bigint`, `version text`, `usage_notes text` | Versioned source metadata; dataset FK; unique dataset/version. |
| `participants` | `id bigint*`, `pseudonym text` | Pseudonymous participant records. |
| `participant_source_ids` | `id bigint*`, `participant_id bigint`, `dataset_version_id bigint`, `source_id text` | Maps source participant identifiers to project participants; both FKs; source ID and participant unique within dataset version. |
| `artifacts` | `id bigint*`, `storage_namespace text`, `storage_key text`, `media_type text`, `size_bytes bigint`, `sha256 char(64)`, `created_at timestamptz` | Artifact metadata and checksum; unique storage namespace/key. |
| `artifact_verifications` | `artifact_id bigint*`, `verified_sha256 char(64)`, `verified_at timestamptz` | Immutable verification record for an artifact. |
| `recording_sessions` | `id bigint*`, `participant_id bigint`, `dataset_version_id bigint`, `mode text`, `status text`, `started_at timestamptz`, `ended_at timestamptz`, `stop_reason text` | Imported or live acquisition session; participant and optional dataset version FKs. |
| `recordings` | `id bigint*`, `session_id bigint`, `artifact_id bigint`, `source_external_key text`, `sample_rate_hz numeric`, `sample_count bigint`, `canonical_signal_id bigint` | Signal recording; session, artifact and optional canonical signal FKs. |
| `recording_channels` | `id bigint*`, `recording_id bigint`, `position integer`, `source_channel_id text`, `electrode_description text` | Channel layout for a recording; recording FK; unique position and source channel per recording. |
| `canonical_signals` | `id bigint*`, `identity_scheme text`, `identity_value text`, `participant_id bigint`, `sample_count bigint` | Canonical signal identity and participant ownership; identity scheme/value unique. |
| `source_recording_keys` | `dataset_version_id bigint*`, `external_key text*`, `recording_id bigint` | Stable mapping of source recording keys; recording unique. |
| `gestures` | `id bigint*`, `code text`, `description text` | Gesture label catalog; code unique. |
| `labelled_segments` | `id bigint*`, `signal_id bigint`, `gesture_id bigint`, `repetition_key text`, `start_sample bigint`, `end_sample bigint` | Labelled sample intervals; signal and gesture FKs; signal/repetition unique. |
| `split_manifests` | `id bigint*`, `name text`, `version integer`, `state text`, `checksum char(64)`, `frozen_at timestamptz`, `protocol_id bigint` | Versioned frozen split; optional protocol FK (required to freeze by integrity trigger). |
| `split_participants` | `manifest_id bigint*`, `participant_id bigint*`, `category text` | Participant allocation to source/development/target categories. |
| `split_units` | `id bigint*`, `manifest_id bigint`, `participant_id bigint`, `category text`, `signal_id bigint`, `start_sample bigint`, `end_sample bigint`, `role text` | Sample interval assigned to a split role; composite FKs enforce participant/category and signal ownership. |
| `gesture_sets` | `id bigint*`, `name text`, `version integer` | Versioned class set. |
| `gesture_set_members` | `gesture_set_id bigint*`, `gesture_id bigint*`, `is_rest boolean` | Gestures included in a class set; composite primary key. |
| `protocol_versions` | `id bigint*`, `name text`, `version integer`, `gesture_set_id bigint`, `schema_version text`, `configuration jsonb` | Immutable versioned experimental protocol; gesture set FK; unique name/version. |
| `calibration_subsets` | `id bigint*`, `manifest_id bigint`, `participant_id bigint`, `category text`, `budget_per_gesture integer`, `selection_version text`, `parent_id bigint`, `state text`, `gesture_set_id bigint` | Target calibration selection; manifest participant, parent subset and gesture set references. |
| `calibration_items` | `subset_id bigint*`, `segment_id bigint*` | Segment membership in calibration subset. |
| `feature_configs` | `id bigint*`, `name text`, `version integer`, `schema_version text`, `parameters jsonb` | Versioned feature extraction configuration. |
| `runs` | `id bigint*`, `kind text`, `status text`, `manifest_id bigint`, `feature_config_id bigint`, `seed bigint`, `parameter_schema_version text`, `parameters jsonb`, `software_version text`, `created_at timestamptz`, `started_at timestamptz`, `finished_at timestamptz`, `failure_reason text`, `heartbeat_at timestamptz` | Experiment execution state and immutable configuration; manifest and feature configuration FKs. |
| `run_inputs` | `run_id bigint*`, `split_unit_id bigint*` | Explicit split units consumed by a run. |
| `run_calibration_items` | `run_id bigint*`, `segment_id bigint*` | Calibration segments consumed by a model run. |
| `run_idempotency_keys` | `operation text*`, `idempotency_key text*`, `run_id bigint` | Idempotent run submission mapping; run unique. |
| `model_versions` | `id bigint*`, `run_id bigint`, `family text`, `condition text`, `artifact_id bigint`, `parent_model_id bigint`, `calibration_subset_id bigint` | Model provenance and artifact reference; run unique; optional parent and calibration references. |
| `evaluations` | `id bigint*`, `run_id bigint`, `model_id bigint`, `participant_id bigint` | Evaluation record linked to run, model and target participant. |
| `evaluation_metrics` | `evaluation_id bigint*`, `metric text*`, `value numeric`, `missing_reason text`, `numerator bigint`, `denominator bigint` | Metric value or explicit missing reason, with optional numerator/denominator. |
| `confusion_counts` | `evaluation_id bigint*`, `actual_gesture_id bigint*`, `predicted_gesture_id bigint*`, `count bigint` | Confusion matrix cells. |
| `signal_provenance` | `signal_id bigint*`, `artifact_id bigint`, `sample_rate_hz numeric`, `identity_method_version text` | Canonical signal FK (primary key), artifact FK, positive finite sample rate and versioned signal identity method. |

For clarity, the original-schema rows above list every final table column. The table definitions in SQL also impose the following primary and composite keys: `split_participants(manifest_id, participant_id)`, `gesture_set_members(gesture_set_id, gesture_id)`, `calibration_items(subset_id, segment_id)`, `evaluation_metrics(evaluation_id, metric)`, `confusion_counts(evaluation_id, actual_gesture_id, predicted_gesture_id)`, `run_inputs(run_id, split_unit_id)`, `run_calibration_items(run_id, segment_id)`, and `run_idempotency_keys(operation, idempotency_key)`. Other `id` columns marked `*` are primary keys. Unique and foreign key constraints are declared in the corresponding migration files.

Read-only views are `reviewer_metrics`, `published_models`, `completed_evaluations`, `calibration_samples`, and `calibration_durations`; their projected columns are defined by the `CREATE VIEW` statements in `database/migrations/`.

## Migration source of truth

### Migration bookkeeping

| Table | Column | PostgreSQL type | Keys and rules | Meaning |
|---|---|---|---|---|
| `public.service_schema_migrations` | `service` | `text` | NOT NULL; composite PK with `name` | Service owning the migration. |
| | `name` | `text` | NOT NULL; composite PK with `service` | Applied SQL filename. |
| | `checksum` | `char(64)` | NOT NULL | SHA-256 of normalized migration source. |
| | `applied_at` | `timestamptz` | NOT NULL; default current timestamp | Application timestamp. |

Alembic separately creates `public.alembic_version` with `version_num varchar(32)` as its primary key to track the original schema revision.

- Original backend: `database/alembic.ini`, `database/migrations/` and `database/schema.sql`.
- Local Compose services: `services/data_protocol/migrations/`, `services/ml_experiments/migrations/`, `services/recognition/migrations/`; applied by `services/migrator/migrate.py`.
- Migration order, constraints, trigger behavior and exact view projections are defined by the SQL. This document is a reader-friendly index and must be updated when a migration changes the schema.
