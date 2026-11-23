# Service Database — Generated Physical Dictionary

Generated from the migrated service schemas. No account/recording/result row data is exported.
Validated source server: PostgreSQL 16.3. Target CI uses PostgreSQL 18.

**Business tables:** 28. `public.service_schema_migrations` is bookkeeping and is listed separately in the main dictionary.

Semantic overview: [logical model](SERVICE_MODEL.md). Review workflow: [teacher README](README_TEACHER.md).

External operator/client/manifest/participant UUIDs in other service domains intentionally have no cross-schema FK. The owning API validates them; database roles are not per-operator HTTP authorization.

JSON contracts require API/runtime schema validation in addition to the structural database checks shown below.

## `data_protocol.calibration_items`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `subset_id` | `uuid` | NO |  | Calibration subset FK. |
| `unit_id` | `uuid` | NO |  | Eligible manifest unit FK. |

### Keys and constraints

- `calibration_items_pkey`: `PRIMARY KEY (subset_id, unit_id)`
- `calibration_items_subset_id_fkey`: `FOREIGN KEY (subset_id) REFERENCES data_protocol.calibration_subsets(id) ON DELETE RESTRICT`
- `calibration_items_unit_id_fkey`: `FOREIGN KEY (unit_id) REFERENCES data_protocol.manifest_units(id) ON DELETE RESTRICT`

### Indexes

- `CREATE UNIQUE INDEX calibration_items_pkey ON data_protocol.calibration_items USING btree (subset_id, unit_id)`

## `data_protocol.calibration_subsets`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO |  | Stable UUID primary identifier. |
| `manifest_id` | `uuid` | NO |  | Frozen research manifest ID; external Data & Protocol reference in ML. |
| `participant_id` | `uuid` | NO |  | Research participant reference. |
| `category` | `text` | NO | 'target'::text | Source/development/target participant allocation. |
| `selection_version` | `text` | NO |  | Nested calibration series identifier. |
| `budget_per_gesture` | `integer` | NO |  | Required distinct repeat count per class. |
| `state` | `text` | NO | 'draft'::text | Lifecycle/publication state constrained by CHECKs and triggers. |

### Keys and constraints

- `calibration_subsets_budget_per_gesture_check`: `CHECK ((budget_per_gesture > 0))`
- `calibration_subsets_category_check`: `CHECK ((category = 'target'::text))`
- `calibration_subsets_manifest_id_participant_id_category_fkey`: `FOREIGN KEY (manifest_id, participant_id, category) REFERENCES data_protocol.manifest_participants(manifest_id, participant_id, category) ON DELETE RESTRICT`
- `calibration_subsets_manifest_id_participant_id_selection_ve_key`: `UNIQUE (manifest_id, participant_id, selection_version, budget_per_gesture)`
- `calibration_subsets_pkey`: `PRIMARY KEY (id)`
- `calibration_subsets_selection_version_check`: `CHECK ((length(TRIM(BOTH FROM selection_version)) > 0))`
- `calibration_subsets_state_check`: `CHECK ((state = ANY (ARRAY['draft'::text, 'frozen'::text])))`

### Indexes

- `CREATE UNIQUE INDEX calibration_subsets_manifest_id_participant_id_selection_ve_key ON data_protocol.calibration_subsets USING btree (manifest_id, participant_id, selection_version, budget_per_gesture)`
- `CREATE UNIQUE INDEX calibration_subsets_pkey ON data_protocol.calibration_subsets USING btree (id)`

## `data_protocol.client_publications`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO | gen_random_uuid() | Stable UUID primary identifier. |
| `operator_id` | `uuid` | NO |  | Cloud operator reference; external to non-identity services, API-authorized. |
| `client_id` | `uuid` | NO |  | Registered client identity; external outside identity service. |
| `local_recording_id` | `uuid` | NO |  | Stable desktop recording UUID for idempotent publication. |
| `recording_id` | `uuid` | NO |  | Recording reference; FK inside Data & Protocol, external in Recognition. |
| `payload_sha256` | `text` | NO |  | Publication payload digest, verified/canonicalized by trusted API. |
| `received_at` | `timestamp with time zone` | NO | CURRENT_TIMESTAMP | Cloud receipt time. |

### Keys and constraints

- `client_publications_operator_id_client_id_local_recording_i_key`: `UNIQUE (operator_id, client_id, local_recording_id)`
- `client_publications_payload_sha256_check`: `CHECK ((payload_sha256 ~ '^[0-9a-f]{64}$'::text))`
- `client_publications_pkey`: `PRIMARY KEY (id)`
- `client_publications_recording_id_fkey`: `FOREIGN KEY (recording_id) REFERENCES data_protocol.recordings(id) ON DELETE RESTRICT`
- `client_publications_recording_id_key`: `UNIQUE (recording_id)`

### Indexes

- `CREATE UNIQUE INDEX client_publications_operator_id_client_id_local_recording_i_key ON data_protocol.client_publications USING btree (operator_id, client_id, local_recording_id)`
- `CREATE UNIQUE INDEX client_publications_pkey ON data_protocol.client_publications USING btree (id)`
- `CREATE UNIQUE INDEX client_publications_recording_id_key ON data_protocol.client_publications USING btree (recording_id)`

## `data_protocol.labelled_segments`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO |  | Stable UUID primary identifier. |
| `recording_id` | `uuid` | NO |  | Recording reference; FK inside Data & Protocol, external in Recognition. |
| `gesture_code` | `text` | NO |  | Canonical segment gesture. |
| `repetition_key` | `text` | NO |  | Repeat identity within a recording. |
| `start_sample` | `bigint` | NO |  | Inclusive local signal coordinate. |
| `end_sample` | `bigint` | NO |  | Exclusive local signal coordinate. |

### Keys and constraints

- `labelled_segments_check`: `CHECK ((end_sample > start_sample))`
- `labelled_segments_gesture_code_check`: `CHECK ((gesture_code ~ '^[A-Za-z0-9_-]{1,100}$'::text))`
- `labelled_segments_pkey`: `PRIMARY KEY (id)`
- `labelled_segments_recording_id_fkey`: `FOREIGN KEY (recording_id) REFERENCES data_protocol.recordings(id) ON DELETE RESTRICT`
- `labelled_segments_recording_id_repetition_key_key`: `UNIQUE (recording_id, repetition_key)`
- `labelled_segments_repetition_key_check`: `CHECK ((length(TRIM(BOTH FROM repetition_key)) > 0))`
- `labelled_segments_start_sample_check`: `CHECK ((start_sample >= 0))`

### Indexes

- `CREATE UNIQUE INDEX labelled_segments_pkey ON data_protocol.labelled_segments USING btree (id)`
- `CREATE UNIQUE INDEX labelled_segments_recording_id_repetition_key_key ON data_protocol.labelled_segments USING btree (recording_id, repetition_key)`

## `data_protocol.manifest_participants`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `manifest_id` | `uuid` | NO |  | Frozen research manifest ID; external Data & Protocol reference in ML. |
| `participant_id` | `uuid` | NO |  | Research participant reference. |
| `category` | `text` | NO |  | Source/development/target participant allocation. |

### Keys and constraints

- `manifest_participants_category_check`: `CHECK ((category = ANY (ARRAY['source'::text, 'development'::text, 'target'::text])))`
- `manifest_participants_manifest_id_fkey`: `FOREIGN KEY (manifest_id) REFERENCES data_protocol.research_manifests(id) ON DELETE RESTRICT`
- `manifest_participants_manifest_id_participant_id_category_key`: `UNIQUE (manifest_id, participant_id, category)`
- `manifest_participants_participant_id_fkey`: `FOREIGN KEY (participant_id) REFERENCES data_protocol.participants(id) ON DELETE RESTRICT`
- `manifest_participants_pkey`: `PRIMARY KEY (manifest_id, participant_id)`

### Indexes

- `CREATE UNIQUE INDEX manifest_participants_manifest_id_participant_id_category_key ON data_protocol.manifest_participants USING btree (manifest_id, participant_id, category)`
- `CREATE UNIQUE INDEX manifest_participants_pkey ON data_protocol.manifest_participants USING btree (manifest_id, participant_id)`

## `data_protocol.manifest_units`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO |  | Stable UUID primary identifier. |
| `manifest_id` | `uuid` | NO |  | Frozen research manifest ID; external Data & Protocol reference in ML. |
| `participant_id` | `uuid` | NO |  | Research participant reference. |
| `category` | `text` | NO |  | Source/development/target participant allocation. |
| `segment_id` | `uuid` | NO |  | Selected labelled segment FK. |
| `role` | `text` | NO |  | Application access role; separate from PostgreSQL service roles. |

### Keys and constraints

- `manifest_units_check`: `CHECK ((((category = 'source'::text) AND (role = 'source_train'::text)) OR ((category = 'development'::text) AND (role = 'development_validation'::text)) OR ((category = 'target'::text) AND (role = ANY (ARRAY['target_calibration'::text, 'target_test'::text])))))`
- `manifest_units_manifest_id_participant_id_category_fkey`: `FOREIGN KEY (manifest_id, participant_id, category) REFERENCES data_protocol.manifest_participants(manifest_id, participant_id, category) ON DELETE RESTRICT`
- `manifest_units_manifest_id_segment_id_role_key`: `UNIQUE (manifest_id, segment_id, role)`
- `manifest_units_pkey`: `PRIMARY KEY (id)`
- `manifest_units_role_check`: `CHECK ((role = ANY (ARRAY['source_train'::text, 'development_validation'::text, 'target_calibration'::text, 'target_test'::text])))`
- `manifest_units_segment_id_fkey`: `FOREIGN KEY (segment_id) REFERENCES data_protocol.labelled_segments(id) ON DELETE RESTRICT`

### Indexes

- `CREATE UNIQUE INDEX manifest_units_manifest_id_segment_id_role_key ON data_protocol.manifest_units USING btree (manifest_id, segment_id, role)`
- `CREATE UNIQUE INDEX manifest_units_pkey ON data_protocol.manifest_units USING btree (id)`

## `data_protocol.participants`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO |  | Stable UUID primary identifier. |
| `pseudonym` | `character varying(100)` | NO |  | Pseudonymous research participant code, not an application account. |

### Keys and constraints

- `participants_pkey`: `PRIMARY KEY (id)`
- `participants_pseudonym_format`: `CHECK (((pseudonym)::text ~ '^[A-Za-z0-9_-]{1,100}$'::text))`
- `participants_pseudonym_key`: `UNIQUE (pseudonym)`

### Indexes

- `CREATE UNIQUE INDEX participants_pkey ON data_protocol.participants USING btree (id)`
- `CREATE UNIQUE INDEX participants_pseudonym_key ON data_protocol.participants USING btree (pseudonym)`

## `data_protocol.protocol_versions`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO |  | Stable UUID primary identifier. |
| `name` | `character varying(120)` | NO |  | Readable label. |
| `version` | `integer` | NO |  | Positive immutable version number within its name. |
| `gesture_codes` | `text[]` | NO |  | Protocol class set including rest. |

### Keys and constraints

- `protocol_versions_gesture_codes_check`: `CHECK (((cardinality(gesture_codes) > 0) AND ('rest'::text = ANY (gesture_codes))))`
- `protocol_versions_name_version_key`: `UNIQUE (name, version)`
- `protocol_versions_pkey`: `PRIMARY KEY (id)`
- `protocol_versions_version_check`: `CHECK ((version > 0))`

### Indexes

- `CREATE UNIQUE INDEX protocol_versions_name_version_key ON data_protocol.protocol_versions USING btree (name, version)`
- `CREATE UNIQUE INDEX protocol_versions_pkey ON data_protocol.protocol_versions USING btree (id)`

## `data_protocol.recording_provenance`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `recording_id` | `uuid` | NO |  | Recording reference; FK inside Data & Protocol, external in Recognition. |
| `operator_id` | `uuid` | NO |  | Cloud operator reference; external to non-identity services, API-authorized. |
| `source_kind` | `text` | NO |  | Synthetic fixture, dataset or device origin. |
| `source_name` | `text` | NO |  | Origin dataset/device family. |
| `source_version` | `text` | NO |  | Origin version; not overwritten by a later import. |
| `source_participant_key` | `text` | NO |  | Participant identifier within the declared source. |
| `original_signal_key` | `text` | NO |  | Stable identity within source namespace; ingestion validates equivalence. |
| `original_sha256` | `text` | NO |  | Original artifact checksum attestation. |
| `original_start_sample` | `bigint` | NO |  | Inclusive original-coordinate start. |
| `original_end_sample` | `bigint` | NO |  | Exclusive original-coordinate end. |
| `channel_map` | `jsonb` | NO |  | Ordered source-channel mapping; ingestion validates transformation/contract. |
| `units` | `text` | NO |  | Declared source units, explicitly unspecified when unknown. |
| `identity_method_version` | `text` | NO |  | Version of source-identity resolution method. |
| `created_at` | `timestamp with time zone` | NO | CURRENT_TIMESTAMP | Database creation timestamp. |

### Keys and constraints

- `recording_provenance_channel_map_check`: `CHECK (((jsonb_typeof(channel_map) = 'array'::text) AND (jsonb_array_length(channel_map) > 0)))`
- `recording_provenance_check`: `CHECK ((original_end_sample > original_start_sample))`
- `recording_provenance_identity_method_version_check`: `CHECK ((length(btrim(identity_method_version)) > 0))`
- `recording_provenance_original_sha256_check`: `CHECK ((original_sha256 ~ '^[0-9a-f]{64}$'::text))`
- `recording_provenance_original_signal_key_check`: `CHECK ((length(btrim(original_signal_key)) > 0))`
- `recording_provenance_original_start_sample_check`: `CHECK ((original_start_sample >= 0))`
- `recording_provenance_pkey`: `PRIMARY KEY (recording_id)`
- `recording_provenance_recording_id_fkey`: `FOREIGN KEY (recording_id) REFERENCES data_protocol.recordings(id) ON DELETE RESTRICT`
- `recording_provenance_source_kind_check`: `CHECK ((source_kind = ANY (ARRAY['synthetic'::text, 'dataset'::text, 'device'::text])))`
- `recording_provenance_source_name_check`: `CHECK ((length(btrim(source_name)) > 0))`
- `recording_provenance_source_participant_key_check`: `CHECK ((length(btrim(source_participant_key)) > 0))`
- `recording_provenance_source_version_check`: `CHECK ((length(btrim(source_version)) > 0))`
- `recording_provenance_units_check`: `CHECK ((length(btrim(units)) > 0))`

### Indexes

- `CREATE INDEX recording_provenance_operator ON data_protocol.recording_provenance USING btree (operator_id)`
- `CREATE UNIQUE INDEX recording_provenance_pkey ON data_protocol.recording_provenance USING btree (recording_id)`
- `CREATE INDEX recording_source_identity ON data_protocol.recording_provenance USING btree (source_name, source_version, original_signal_key)`

## `data_protocol.recordings`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO |  | Stable UUID primary identifier. |
| `participant_id` | `uuid` | NO |  | Research participant reference. |
| `sample_rate_hz` | `numeric` | NO |  | Signal sampling frequency in hertz. |
| `sample_count` | `integer` | NO |  | Number of samples in the recording. |
| `artifact_sha256` | `character varying(64)` | NO |  | Signal artifact checksum. |

### Keys and constraints

- `recordings_artifact_sha256_check`: `CHECK (((artifact_sha256)::text ~ '^[0-9a-f]{64}$'::text))`
- `recordings_participant_id_fkey`: `FOREIGN KEY (participant_id) REFERENCES data_protocol.participants(id) ON DELETE RESTRICT`
- `recordings_pkey`: `PRIMARY KEY (id)`
- `recordings_sample_count_check`: `CHECK (((sample_count >= 1) AND (sample_count <= 10000)))`
- `recordings_sample_rate_hz_check`: `CHECK (((sample_rate_hz > (0)::numeric) AND (sample_rate_hz <= (100000)::numeric)))`

### Indexes

- `CREATE UNIQUE INDEX recordings_pkey ON data_protocol.recordings USING btree (id)`

## `data_protocol.research_manifests`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO |  | Stable UUID primary identifier. |
| `protocol_id` | `uuid` | NO |  | Protocol version FK. |
| `name` | `character varying(120)` | NO |  | Readable label. |
| `version` | `integer` | NO |  | Positive immutable version number within its name. |
| `state` | `text` | NO | 'draft'::text | Lifecycle/publication state constrained by CHECKs and triggers. |
| `checksum` | `character varying(64)` | YES |  | Frozen manifest/model checksum. |
| `frozen_at` | `timestamp with time zone` | YES |  | Manifest freeze timestamp. |

### Keys and constraints

- `research_manifests_check`: `CHECK ((((state = 'draft'::text) AND (checksum IS NULL) AND (frozen_at IS NULL)) OR ((state = 'frozen'::text) AND (checksum IS NOT NULL) AND ((checksum)::text ~ '^[0-9a-f]{64}$'::text) AND (frozen_at IS NOT NULL))))`
- `research_manifests_name_version_key`: `UNIQUE (name, version)`
- `research_manifests_pkey`: `PRIMARY KEY (id)`
- `research_manifests_protocol_id_fkey`: `FOREIGN KEY (protocol_id) REFERENCES data_protocol.protocol_versions(id) ON DELETE RESTRICT`
- `research_manifests_state_check`: `CHECK ((state = ANY (ARRAY['draft'::text, 'frozen'::text])))`
- `research_manifests_version_check`: `CHECK ((version > 0))`

### Indexes

- `CREATE UNIQUE INDEX research_manifests_name_version_key ON data_protocol.research_manifests USING btree (name, version)`
- `CREATE UNIQUE INDEX research_manifests_pkey ON data_protocol.research_manifests USING btree (id)`

## `data_protocol.synthetic_splits`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO |  | Stable UUID primary identifier. |
| `source_recording_id` | `uuid` | NO |  | Source recording FK for legacy synthetic split. |
| `test_recording_id` | `uuid` | NO |  | Test recording FK for legacy synthetic split. |
| `checksum` | `character varying(64)` | NO |  | Frozen manifest/model checksum. |

### Keys and constraints

- `synthetic_splits_check`: `CHECK ((source_recording_id <> test_recording_id))`
- `synthetic_splits_checksum_check`: `CHECK (((checksum)::text ~ '^[0-9a-f]{64}$'::text))`
- `synthetic_splits_pkey`: `PRIMARY KEY (id)`
- `synthetic_splits_source_recording_id_fkey`: `FOREIGN KEY (source_recording_id) REFERENCES data_protocol.recordings(id) ON DELETE RESTRICT`
- `synthetic_splits_test_recording_id_fkey`: `FOREIGN KEY (test_recording_id) REFERENCES data_protocol.recordings(id) ON DELETE RESTRICT`

### Indexes

- `CREATE UNIQUE INDEX synthetic_splits_pkey ON data_protocol.synthetic_splits USING btree (id)`

## `identity.access_sessions`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO | gen_random_uuid() | Stable UUID primary identifier. |
| `operator_id` | `uuid` | NO |  | Cloud operator reference; external to non-identity services, API-authorized. |
| `client_id` | `uuid` | YES |  | Registered client identity; external outside identity service. |
| `token_sha256` | `text` | NO |  | Digest of high-entropy token; raw token is not stored. |
| `scope` | `text` | NO |  | Web/desktop/worker access scope. |
| `issued_at` | `timestamp with time zone` | NO | CURRENT_TIMESTAMP | Access-session issue time. |
| `expires_at` | `timestamp with time zone` | NO |  | Access-session expiry time. |
| `revoked_at` | `timestamp with time zone` | YES |  | Revocation time, immutable after revocation. |

### Keys and constraints

- `access_sessions_check`: `CHECK ((expires_at > issued_at))`
- `access_sessions_check1`: `CHECK (((revoked_at IS NULL) OR (revoked_at >= issued_at)))`
- `access_sessions_check2`: `CHECK ((((scope = 'web'::text) AND (client_id IS NULL)) OR ((scope <> 'web'::text) AND (client_id IS NOT NULL))))`
- `access_sessions_client_id_operator_id_fkey`: `FOREIGN KEY (client_id, operator_id) REFERENCES identity.clients(id, operator_id) ON DELETE RESTRICT`
- `access_sessions_operator_id_fkey`: `FOREIGN KEY (operator_id) REFERENCES identity.operators(id) ON DELETE RESTRICT`
- `access_sessions_pkey`: `PRIMARY KEY (id)`
- `access_sessions_scope_check`: `CHECK ((scope = ANY (ARRAY['web'::text, 'desktop'::text, 'training_worker'::text])))`
- `access_sessions_token_sha256_check`: `CHECK ((token_sha256 ~ '^[0-9a-f]{64}$'::text))`
- `access_sessions_token_sha256_key`: `UNIQUE (token_sha256)`

### Indexes

- `CREATE INDEX access_sessions_operator ON identity.access_sessions USING btree (operator_id)`
- `CREATE UNIQUE INDEX access_sessions_pkey ON identity.access_sessions USING btree (id)`
- `CREATE UNIQUE INDEX access_sessions_token_sha256_key ON identity.access_sessions USING btree (token_sha256)`

## `identity.clients`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO | gen_random_uuid() | Stable UUID primary identifier. |
| `operator_id` | `uuid` | NO |  | Cloud operator reference; external to non-identity services, API-authorized. |
| `kind` | `text` | NO |  | Entity/client/operation category, constrained to supported values. |
| `name` | `text` | NO |  | Readable label. |
| `platform` | `text` | NO |  | Registered client OS/architecture identity. |
| `state` | `text` | NO | 'active'::text | Lifecycle/publication state constrained by CHECKs and triggers. |
| `created_at` | `timestamp with time zone` | NO | CURRENT_TIMESTAMP | Database creation timestamp. |

### Keys and constraints

- `clients_id_operator_id_key`: `UNIQUE (id, operator_id)`
- `clients_kind_check`: `CHECK ((kind = ANY (ARRAY['desktop'::text, 'training_worker'::text])))`
- `clients_name_check`: `CHECK (((length(btrim(name)) >= 1) AND (length(btrim(name)) <= 120)))`
- `clients_operator_id_fkey`: `FOREIGN KEY (operator_id) REFERENCES identity.operators(id) ON DELETE RESTRICT`
- `clients_pkey`: `PRIMARY KEY (id)`
- `clients_platform_check`: `CHECK (((length(btrim(platform)) >= 1) AND (length(btrim(platform)) <= 120)))`
- `clients_state_check`: `CHECK ((state = ANY (ARRAY['active'::text, 'revoked'::text])))`

### Indexes

- `CREATE UNIQUE INDEX clients_id_operator_id_key ON identity.clients USING btree (id, operator_id)`
- `CREATE INDEX clients_operator ON identity.clients USING btree (operator_id)`
- `CREATE UNIQUE INDEX clients_pkey ON identity.clients USING btree (id)`

## `identity.operators`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO | gen_random_uuid() | Stable UUID primary identifier. |
| `email` | `text` | NO |  | Normalized unique account email. |
| `display_name` | `text` | NO |  | Operator-facing account label. |
| `password_hash` | `text` | NO |  | Encoded Argon2id password hash; never a plaintext password. |
| `role` | `text` | NO | 'operator'::text | Application access role; separate from PostgreSQL service roles. |
| `state` | `text` | NO | 'active'::text | Lifecycle/publication state constrained by CHECKs and triggers. |
| `created_at` | `timestamp with time zone` | NO | CURRENT_TIMESTAMP | Database creation timestamp. |
| `updated_at` | `timestamp with time zone` | NO | CURRENT_TIMESTAMP | Last account update timestamp maintained by trigger. |

### Keys and constraints

- `operators_display_name_check`: `CHECK (((length(btrim(display_name)) >= 1) AND (length(btrim(display_name)) <= 120)))`
- `operators_email_check`: `CHECK (((email = lower(btrim(email))) AND (length(email) <= 320) AND (email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'::text)))`
- `operators_email_key`: `UNIQUE (email)`
- `operators_password_hash_check`: `CHECK (((password_hash ~~ '$argon2id$v=19$%'::text) AND ((length(password_hash) >= 40) AND (length(password_hash) <= 1024))))`
- `operators_pkey`: `PRIMARY KEY (id)`
- `operators_role_check`: `CHECK ((role = ANY (ARRAY['operator'::text, 'reviewer'::text, 'administrator'::text])))`
- `operators_state_check`: `CHECK ((state = ANY (ARRAY['active'::text, 'disabled'::text])))`

### Indexes

- `CREATE UNIQUE INDEX operators_email_key ON identity.operators USING btree (email)`
- `CREATE UNIQUE INDEX operators_pkey ON identity.operators USING btree (id)`

## `ml_experiments.artifacts`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO | gen_random_uuid() | Stable UUID primary identifier. |
| `operator_id` | `uuid` | NO |  | Cloud operator reference; external to non-identity services, API-authorized. |
| `storage_key` | `text` | NO |  | Unique controlled storage identifier, not a public URL. |
| `sha256` | `text` | NO |  | Expected artifact SHA-256 digest. |
| `size_bytes` | `bigint` | NO |  | Artifact size in bytes. |
| `media_type` | `text` | NO |  | Artifact content type. |
| `state` | `text` | NO | 'staged'::text | Lifecycle/publication state constrained by CHECKs and triggers. |
| `created_at` | `timestamp with time zone` | NO | CURRENT_TIMESTAMP | Database creation timestamp. |
| `verified_at` | `timestamp with time zone` | YES |  | Trusted service byte-verification attestation time; PostgreSQL cannot inspect the file. |

### Keys and constraints

- `artifacts_check`: `CHECK ((((state = 'staged'::text) AND (verified_at IS NULL)) OR ((state = 'verified'::text) AND (verified_at IS NOT NULL))))`
- `artifacts_media_type_check`: `CHECK ((length(btrim(media_type)) > 0))`
- `artifacts_pkey`: `PRIMARY KEY (id)`
- `artifacts_sha256_check`: `CHECK ((sha256 ~ '^[0-9a-f]{64}$'::text))`
- `artifacts_size_bytes_check`: `CHECK ((size_bytes > 0))`
- `artifacts_state_check`: `CHECK ((state = ANY (ARRAY['staged'::text, 'verified'::text])))`
- `artifacts_storage_key_check`: `CHECK ((length(btrim(storage_key)) > 0))`
- `artifacts_storage_key_key`: `UNIQUE (storage_key)`

### Indexes

- `CREATE UNIQUE INDEX artifacts_pkey ON ml_experiments.artifacts USING btree (id)`
- `CREATE UNIQUE INDEX artifacts_storage_key_key ON ml_experiments.artifacts USING btree (storage_key)`

## `ml_experiments.confusion_counts`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `evaluation_id` | `uuid` | NO |  | Evaluation owning this confusion cell. |
| `model_id` | `uuid` | NO |  | Registered model reference. |
| `actual_class` | `text` | NO |  | Ground-truth class FK into the model mapping. |
| `predicted_class` | `text` | NO |  | Predicted class FK into the model mapping. |
| `count` | `bigint` | NO |  | Nonnegative window count for this class pair. |

### Keys and constraints

- `confusion_counts_count_check`: `CHECK ((count >= 0))`
- `confusion_counts_evaluation_id_model_id_fkey`: `FOREIGN KEY (evaluation_id, model_id) REFERENCES ml_experiments.evaluations(id, model_id) ON DELETE RESTRICT`
- `confusion_counts_model_id_actual_class_fkey`: `FOREIGN KEY (model_id, actual_class) REFERENCES ml_experiments.model_classes(model_id, code) ON DELETE RESTRICT`
- `confusion_counts_model_id_predicted_class_fkey`: `FOREIGN KEY (model_id, predicted_class) REFERENCES ml_experiments.model_classes(model_id, code) ON DELETE RESTRICT`
- `confusion_counts_pkey`: `PRIMARY KEY (evaluation_id, actual_class, predicted_class)`

### Indexes

- `CREATE UNIQUE INDEX confusion_counts_pkey ON ml_experiments.confusion_counts USING btree (evaluation_id, actual_class, predicted_class)`

## `ml_experiments.evaluations`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO | gen_random_uuid() | Stable UUID primary identifier. |
| `run_id` | `uuid` | NO |  | Producing/evaluation run reference. |
| `model_id` | `uuid` | NO |  | Registered model reference. |
| `accuracy` | `double precision` | NO |  | Fraction correct; checked against full confusion counts at evaluation completion. |
| `macro_f1` | `double precision` | NO |  | Mean per-class F1 over the complete model class set; checked arithmetically. |
| `rest_false_activation_rate` | `double precision` | YES |  | Rest windows predicted non-rest / all rest windows; NULL if no rest windows. |
| `rest_missing_reason` | `text` | YES |  | Explicit reason for an unavailable rest metric. |

### Keys and constraints

- `evaluations_accuracy_check`: `CHECK (((accuracy >= (0)::double precision) AND (accuracy <= (1)::double precision)))`
- `evaluations_check`: `CHECK ((((rest_false_activation_rate IS NOT NULL) AND (rest_missing_reason IS NULL)) OR ((rest_false_activation_rate IS NULL) AND (rest_missing_reason IS NOT NULL) AND (length(btrim(rest_missing_reason)) > 0))))`
- `evaluations_id_model_id_key`: `UNIQUE (id, model_id)`
- `evaluations_macro_f1_check`: `CHECK (((macro_f1 >= (0)::double precision) AND (macro_f1 <= (1)::double precision)))`
- `evaluations_model_id_fkey`: `FOREIGN KEY (model_id) REFERENCES ml_experiments.model_versions(id) ON DELETE RESTRICT`
- `evaluations_pkey`: `PRIMARY KEY (id)`
- `evaluations_rest_false_activation_rate_check`: `CHECK (((rest_false_activation_rate >= (0)::double precision) AND (rest_false_activation_rate <= (1)::double precision)))`
- `evaluations_run_id_fkey`: `FOREIGN KEY (run_id) REFERENCES ml_experiments.experiment_runs(id) ON DELETE RESTRICT`
- `evaluations_run_id_key`: `UNIQUE (run_id)`

### Indexes

- `CREATE UNIQUE INDEX evaluations_id_model_id_key ON ml_experiments.evaluations USING btree (id, model_id)`
- `CREATE UNIQUE INDEX evaluations_pkey ON ml_experiments.evaluations USING btree (id)`
- `CREATE UNIQUE INDEX evaluations_run_id_key ON ml_experiments.evaluations USING btree (run_id)`

## `ml_experiments.experiment_runs`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO | gen_random_uuid() | Stable UUID primary identifier. |
| `operator_id` | `uuid` | NO |  | Cloud operator reference; external to non-identity services, API-authorized. |
| `submission_key` | `text` | NO |  | Operator-scoped stable submission/idempotency key. |
| `retry_of_id` | `uuid` | YES |  | Previous failed/interrupted run; retries create new IDs. |
| `kind` | `text` | NO |  | Entity/client/operation category, constrained to supported values. |
| `family` | `text` | NO |  | LDA, SVM or MLP family. |
| `condition` | `text` | NO |  | Source-only, personalised or target-only learning condition. |
| `execution_location` | `text` | NO |  | Local workstation or desktop; general source training is workstation-only. |
| `manifest_id` | `uuid` | NO |  | Frozen research manifest ID; external Data & Protocol reference in ML. |
| `manifest_sha256` | `text` | NO |  | Frozen manifest checksum used by this run. |
| `target_participant_id` | `uuid` | YES |  | External target participant identity. |
| `calibration_subset_id` | `uuid` | YES |  | External frozen calibration selection; required for calibrated conditions. |
| `parent_model_id` | `uuid` | YES |  | Published compatible source model used for personalisation. |
| `evaluated_model_id` | `uuid` | YES |  | Published model selected by an evaluation run. |
| `feature_contract` | `jsonb` | NO |  | Versioned signal/feature contract JSON object. |
| `input_snapshot` | `jsonb` | NO |  | Immutable input membership/provenance snapshot JSON. |
| `parameters` | `jsonb` | NO |  | Versioned algorithm-specific parameters JSON. |
| `seed` | `bigint` | NO |  | Recorded random seed. |
| `software_version` | `text` | NO |  | Recorded implementation/environment version. |
| `status` | `text` | NO | 'queued'::text | Run/session state constrained by CHECKs/transitions. |
| `worker_client_id` | `uuid` | YES |  | External identity of the worker/desktop executing the attempt. |
| `lease_sha256` | `text` | YES |  | Fencing digest for the worker lease, excluded from reviewer views. |
| `created_at` | `timestamp with time zone` | NO | CURRENT_TIMESTAMP | Database creation timestamp. |
| `started_at` | `timestamp with time zone` | YES |  | Operation start timestamp. |
| `heartbeat_at` | `timestamp with time zone` | YES |  | Latest worker heartbeat timestamp. |
| `lease_expires_at` | `timestamp with time zone` | YES |  | Worker lease expiry timestamp. |
| `completed_at` | `timestamp with time zone` | YES |  | Terminal experiment timestamp. |
| `error` | `text` | YES |  | Failure/interruption reason. |

### Keys and constraints

- `experiment_runs_check`: `CHECK ((((condition = 'source_only'::text) AND (calibration_subset_id IS NULL)) OR ((condition <> 'source_only'::text) AND (calibration_subset_id IS NOT NULL) AND (target_participant_id IS NOT NULL))))`
- `experiment_runs_check1`: `CHECK ((((kind = 'source_train'::text) AND (condition = 'source_only'::text) AND (execution_location = 'local_workstation'::text)) OR ((kind = 'personalise'::text) AND (condition = 'personalised'::text)) OR ((kind = 'target_train'::text) AND (condition = 'target_only'::text)) OR (kind = 'evaluate'::text)))`
- `experiment_runs_check2`: `CHECK ((((kind = 'personalise'::text) AND (parent_model_id IS NOT NULL)) OR ((kind <> 'personalise'::text) AND (parent_model_id IS NULL))))`
- `experiment_runs_check3`: `CHECK ((((kind = 'evaluate'::text) AND (evaluated_model_id IS NOT NULL) AND (target_participant_id IS NOT NULL)) OR ((kind <> 'evaluate'::text) AND (evaluated_model_id IS NULL))))`
- `experiment_runs_check4`: `CHECK ((((status = 'queued'::text) AND (started_at IS NULL) AND (heartbeat_at IS NULL) AND (lease_expires_at IS NULL) AND (worker_client_id IS NULL) AND (lease_sha256 IS NULL) AND (completed_at IS NULL) AND (error IS NULL)) OR ((status <> 'queued'::text) AND (worker_client_id IS NOT NULL) AND (lease_sha256 IS NOT NULL) AND (started_at IS NOT NULL) AND (heartbeat_at IS NOT NULL) AND (lease_expires_at IS NOT NULL) AND (heartbeat_at >= started_at) AND (lease_expires_at > heartbeat_at) AND (((status = 'running'::text) AND (completed_at IS NULL) AND (error IS NULL)) OR ((status = 'succeeded'::text) AND (completed_at IS NOT NULL) AND (completed_at >= started_at) AND (error IS NULL)) OR ((status = ANY (ARRAY['failed'::text, 'interrupted'::text])) AND (completed_at IS NOT NULL) AND (completed_at >= started_at) AND (error IS NOT NULL) AND (length(btrim(error)) > 0))))))`
- `experiment_runs_condition_check`: `CHECK ((condition = ANY (ARRAY['source_only'::text, 'personalised'::text, 'target_only'::text])))`
- `experiment_runs_evaluated_model_id_fkey`: `FOREIGN KEY (evaluated_model_id) REFERENCES ml_experiments.model_versions(id) ON DELETE RESTRICT`
- `experiment_runs_execution_location_check`: `CHECK ((execution_location = ANY (ARRAY['local_workstation'::text, 'desktop'::text])))`
- `experiment_runs_family_check`: `CHECK ((family = ANY (ARRAY['lda'::text, 'svm'::text, 'mlp'::text])))`
- `experiment_runs_feature_contract_check`: `CHECK (((jsonb_typeof(feature_contract) = 'object'::text) AND (feature_contract ? 'version'::text) AND (jsonb_typeof((feature_contract -> 'version'::text)) = 'string'::text) AND (length(btrim((feature_contract ->> 'version'::text))) > 0)))`
- `experiment_runs_input_snapshot_check`: `CHECK ((jsonb_typeof(input_snapshot) = 'object'::text))`
- `experiment_runs_kind_check`: `CHECK ((kind = ANY (ARRAY['source_train'::text, 'personalise'::text, 'target_train'::text, 'evaluate'::text])))`
- `experiment_runs_lease_sha256_check`: `CHECK ((lease_sha256 ~ '^[0-9a-f]{64}$'::text))`
- `experiment_runs_manifest_sha256_check`: `CHECK ((manifest_sha256 ~ '^[0-9a-f]{64}$'::text))`
- `experiment_runs_operator_id_submission_key_key`: `UNIQUE (operator_id, submission_key)`
- `experiment_runs_parameters_check`: `CHECK ((jsonb_typeof(parameters) = 'object'::text))`
- `experiment_runs_parent_model_id_fkey`: `FOREIGN KEY (parent_model_id) REFERENCES ml_experiments.model_versions(id) ON DELETE RESTRICT`
- `experiment_runs_pkey`: `PRIMARY KEY (id)`
- `experiment_runs_retry_of_id_fkey`: `FOREIGN KEY (retry_of_id) REFERENCES ml_experiments.experiment_runs(id) ON DELETE RESTRICT`
- `experiment_runs_software_version_check`: `CHECK ((length(btrim(software_version)) > 0))`
- `experiment_runs_status_check`: `CHECK ((status = ANY (ARRAY['queued'::text, 'running'::text, 'succeeded'::text, 'failed'::text, 'interrupted'::text])))`
- `experiment_runs_submission_key_check`: `CHECK (((length(btrim(submission_key)) >= 1) AND (length(btrim(submission_key)) <= 120)))`
- `validate_run_output`: `TRIGGER DEFERRABLE INITIALLY DEFERRED`

### Indexes

- `CREATE INDEX experiment_runs_history ON ml_experiments.experiment_runs USING btree (operator_id, created_at DESC)`
- `CREATE UNIQUE INDEX experiment_runs_operator_id_submission_key_key ON ml_experiments.experiment_runs USING btree (operator_id, submission_key)`
- `CREATE UNIQUE INDEX experiment_runs_pkey ON ml_experiments.experiment_runs USING btree (id)`
- `CREATE INDEX experiment_runs_queue ON ml_experiments.experiment_runs USING btree (operator_id, execution_location, created_at) WHERE (status = 'queued'::text)`
- `CREATE INDEX experiment_runs_stale ON ml_experiments.experiment_runs USING btree (lease_expires_at) WHERE (status = 'running'::text)`

## `ml_experiments.model_classes`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `model_id` | `uuid` | NO |  | Registered model reference. |
| `code` | `text` | NO |  | Canonical gesture code, including rest. |
| `position` | `integer` | NO |  | Class order within a model. |

### Keys and constraints

- `model_classes_code_check`: `CHECK ((code ~ '^[A-Za-z0-9_-]{1,100}$'::text))`
- `model_classes_model_id_fkey`: `FOREIGN KEY (model_id) REFERENCES ml_experiments.model_versions(id) ON DELETE RESTRICT`
- `model_classes_model_id_position_key`: `UNIQUE (model_id, "position")`
- `model_classes_pkey`: `PRIMARY KEY (model_id, code)`
- `model_classes_position_check`: `CHECK (("position" >= 0))`

### Indexes

- `CREATE UNIQUE INDEX model_classes_model_id_position_key ON ml_experiments.model_classes USING btree (model_id, "position")`
- `CREATE UNIQUE INDEX model_classes_pkey ON ml_experiments.model_classes USING btree (model_id, code)`

## `ml_experiments.model_package_items`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `model_id` | `uuid` | NO |  | Registered model reference. |
| `purpose` | `text` | NO |  | Configuration/source-statistics/source-pool/replay-pool package role. |
| `artifact_id` | `uuid` | NO |  | Verified artifact registry reference. |

### Keys and constraints

- `model_package_items_artifact_id_fkey`: `FOREIGN KEY (artifact_id) REFERENCES ml_experiments.artifacts(id) ON DELETE RESTRICT`
- `model_package_items_model_id_fkey`: `FOREIGN KEY (model_id) REFERENCES ml_experiments.model_versions(id) ON DELETE RESTRICT`
- `model_package_items_pkey`: `PRIMARY KEY (model_id, purpose)`
- `model_package_items_purpose_check`: `CHECK ((purpose = ANY (ARRAY['source_statistics'::text, 'source_pool'::text, 'replay_pool'::text, 'configuration'::text])))`

### Indexes

- `CREATE INDEX model_package_artifact ON ml_experiments.model_package_items USING btree (artifact_id)`
- `CREATE UNIQUE INDEX model_package_items_pkey ON ml_experiments.model_package_items USING btree (model_id, purpose)`

## `ml_experiments.model_versions`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO | gen_random_uuid() | Stable UUID primary identifier. |
| `run_id` | `uuid` | NO |  | Producing/evaluation run reference. |
| `artifact_id` | `uuid` | NO |  | Verified artifact registry reference. |
| `name` | `text` | NO |  | Readable label. |
| `adaptation_method` | `text` | NO | 'none'::text | Advertised adaptation algorithm and required package material. |
| `state` | `text` | NO | 'draft'::text | Lifecycle/publication state constrained by CHECKs and triggers. |
| `created_at` | `timestamp with time zone` | NO | CURRENT_TIMESTAMP | Database creation timestamp. |
| `published_at` | `timestamp with time zone` | YES |  | Publication timestamp. |

### Keys and constraints

- `model_versions_adaptation_method_check`: `CHECK ((adaptation_method = ANY (ARRAY['none'::text, 'lda_statistics'::text, 'svm_weighted'::text, 'mlp_replay'::text])))`
- `model_versions_artifact_id_fkey`: `FOREIGN KEY (artifact_id) REFERENCES ml_experiments.artifacts(id) ON DELETE RESTRICT`
- `model_versions_check`: `CHECK ((((state = 'draft'::text) AND (published_at IS NULL)) OR ((state = 'published'::text) AND (published_at IS NOT NULL))))`
- `model_versions_name_check`: `CHECK (((length(btrim(name)) >= 1) AND (length(btrim(name)) <= 160)))`
- `model_versions_pkey`: `PRIMARY KEY (id)`
- `model_versions_run_id_fkey`: `FOREIGN KEY (run_id) REFERENCES ml_experiments.experiment_runs(id) ON DELETE RESTRICT`
- `model_versions_run_id_key`: `UNIQUE (run_id)`
- `model_versions_state_check`: `CHECK ((state = ANY (ARRAY['draft'::text, 'published'::text])))`

### Indexes

- `CREATE UNIQUE INDEX model_versions_pkey ON ml_experiments.model_versions USING btree (id)`
- `CREATE UNIQUE INDEX model_versions_run_id_key ON ml_experiments.model_versions USING btree (run_id)`

## `ml_experiments.outbox_events`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO |  | Stable UUID primary identifier. |
| `run_id` | `uuid` | NO |  | Producing/evaluation run reference. |
| `event_type` | `character varying(100)` | NO |  | Publication event type. |
| `payload` | `jsonb` | NO |  | Versioned domain-event payload. |
| `created_at` | `timestamp with time zone` | NO | CURRENT_TIMESTAMP | Database creation timestamp. |
| `published_at` | `timestamp with time zone` | YES |  | Publication timestamp. |

### Keys and constraints

- `outbox_events_event_type_check`: `CHECK (((event_type)::text = 'ModelPublished'::text))`
- `outbox_events_pkey`: `PRIMARY KEY (id)`
- `outbox_events_run_id_fkey`: `FOREIGN KEY (run_id) REFERENCES ml_experiments.source_lda_runs(id) ON DELETE RESTRICT`
- `outbox_events_run_id_key`: `UNIQUE (run_id)`

### Indexes

- `CREATE UNIQUE INDEX outbox_events_pkey ON ml_experiments.outbox_events USING btree (id)`
- `CREATE UNIQUE INDEX outbox_events_run_id_key ON ml_experiments.outbox_events USING btree (run_id)`
- `CREATE INDEX outbox_unpublished ON ml_experiments.outbox_events USING btree (created_at) WHERE (published_at IS NULL)`

## `ml_experiments.signal_summary_jobs`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO |  | Stable UUID primary identifier. |
| `split_id` | `uuid` | NO |  | External legacy synthetic split reference. |
| `status` | `character varying(20)` | NO |  | Run/session state constrained by CHECKs/transitions. |
| `split_checksum` | `character varying(64)` | YES |  | Service-specific persisted value; see the existing dictionary and migration contract. |
| `result` | `jsonb` | YES |  | Legacy replay/summary output JSON. |
| `error` | `character varying(100)` | YES |  | Failure/interruption reason. |

### Keys and constraints

- `signal_summary_jobs_check`: `CHECK (((((status)::text = 'running'::text) AND (result IS NULL) AND (error IS NULL) AND (split_checksum IS NULL)) OR (((status)::text = 'succeeded'::text) AND (result IS NOT NULL) AND (error IS NULL) AND ((split_checksum)::text ~ '^[0-9a-f]{64}$'::text)) OR (((status)::text = 'failed'::text) AND (result IS NULL) AND (error IS NOT NULL) AND (split_checksum IS NULL))))`
- `signal_summary_jobs_pkey`: `PRIMARY KEY (id)`
- `signal_summary_jobs_status_check`: `CHECK (((status)::text = ANY ((ARRAY['running'::character varying, 'succeeded'::character varying, 'failed'::character varying])::text[])))`

### Indexes

- `CREATE UNIQUE INDEX signal_summary_jobs_pkey ON ml_experiments.signal_summary_jobs USING btree (id)`

## `ml_experiments.source_lda_runs`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO |  | Stable UUID primary identifier. |
| `manifest_id` | `uuid` | NO |  | Frozen research manifest ID; external Data & Protocol reference in ML. |
| `target_participant_id` | `uuid` | NO |  | External target participant identity. |
| `status` | `character varying(20)` | NO |  | Run/session state constrained by CHECKs/transitions. |
| `manifest_checksum` | `character varying(64)` | YES |  | Service-specific persisted value; see the existing dictionary and migration contract. |
| `snapshot` | `jsonb` | YES |  | Legacy frozen input snapshot. |
| `model` | `jsonb` | YES |  | Legacy LDA model JSON. |
| `metrics` | `jsonb` | YES |  | Legacy computed metric JSON. |
| `error` | `text` | YES |  | Failure/interruption reason. |
| `created_at` | `timestamp with time zone` | NO | CURRENT_TIMESTAMP | Database creation timestamp. |
| `completed_at` | `timestamp with time zone` | YES |  | Terminal experiment timestamp. |
| `model_checksum` | `character varying(64)` | YES |  | Legacy model JSON checksum. |
| `started_at` | `timestamp with time zone` | YES |  | Operation start timestamp. |
| `heartbeat_at` | `timestamp with time zone` | YES |  | Latest worker heartbeat timestamp. |
| `idempotency_key` | `character varying(100)` | YES |  | Legacy submission deduplication key. |
| `correlation_id` | `character varying(64)` | NO | 'legacy'::character varying | Request/job tracing identifier. |
| `trace_context` | `jsonb` | NO | '{}'::jsonb | Stored OpenTelemetry trace context. |

### Keys and constraints

- `source_lda_runs_idempotency_key_key`: `UNIQUE (idempotency_key)`
- `source_lda_runs_pkey`: `PRIMARY KEY (id)`
- `source_lda_runs_state_v2`: `CHECK (((((status)::text = 'queued'::text) AND (started_at IS NULL) AND (heartbeat_at IS NULL) AND (completed_at IS NULL) AND (manifest_checksum IS NULL) AND (snapshot IS NULL) AND (model IS NULL) AND (metrics IS NULL) AND (error IS NULL)) OR (((status)::text = 'running'::text) AND (started_at IS NOT NULL) AND (heartbeat_at IS NOT NULL) AND (completed_at IS NULL) AND (manifest_checksum IS NULL) AND (snapshot IS NULL) AND (model IS NULL) AND (metrics IS NULL) AND (error IS NULL)) OR (((status)::text = 'succeeded'::text) AND (completed_at IS NOT NULL) AND (manifest_checksum IS NOT NULL) AND ((manifest_checksum)::text ~ '^[0-9a-f]{64}$'::text) AND (snapshot IS NOT NULL) AND (model IS NOT NULL) AND (metrics IS NOT NULL) AND (error IS NULL)) OR (((status)::text = ANY ((ARRAY['failed'::character varying, 'interrupted'::character varying])::text[])) AND (completed_at IS NOT NULL) AND (snapshot IS NULL) AND (model IS NULL) AND (metrics IS NULL) AND (error IS NOT NULL))))`
- `source_lda_runs_status_v2`: `CHECK (((status)::text = ANY ((ARRAY['queued'::character varying, 'running'::character varying, 'succeeded'::character varying, 'failed'::character varying, 'interrupted'::character varying])::text[])))`
- `source_lda_runs_trace_context_check`: `CHECK ((jsonb_typeof(trace_context) = 'object'::text))`

### Indexes

- `CREATE INDEX source_lda_runs_heartbeat ON ml_experiments.source_lda_runs USING btree (heartbeat_at) WHERE ((status)::text = 'running'::text)`
- `CREATE UNIQUE INDEX source_lda_runs_idempotency_key_key ON ml_experiments.source_lda_runs USING btree (idempotency_key)`
- `CREATE UNIQUE INDEX source_lda_runs_pkey ON ml_experiments.source_lda_runs USING btree (id)`
- `CREATE INDEX source_lda_runs_queue ON ml_experiments.source_lda_runs USING btree (created_at) WHERE ((status)::text = 'queued'::text)`

## `recognition.desktop_sessions`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO | gen_random_uuid() | Stable UUID primary identifier. |
| `operator_id` | `uuid` | NO |  | Cloud operator reference; external to non-identity services, API-authorized. |
| `client_id` | `uuid` | NO |  | Registered client identity; external outside identity service. |
| `local_session_id` | `uuid` | NO |  | Stable desktop session identity for deduplication. |
| `model_version_id` | `uuid` | NO |  | External ML model version reference. |
| `model_sha256` | `text` | NO |  | Checksum of the model actually used. |
| `feature_version` | `text` | NO |  | Signal/feature specification identifier. |
| `mode` | `text` | NO |  | Live or recorded replay. |
| `recording_id` | `uuid` | YES |  | Recording reference; FK inside Data & Protocol, external in Recognition. |
| `status` | `text` | NO |  | Run/session state constrained by CHECKs/transitions. |
| `started_at` | `timestamp with time zone` | NO |  | Operation start timestamp. |
| `ended_at` | `timestamp with time zone` | NO |  | Terminal local session timestamp. |
| `termination_reason` | `text` | NO |  | Reported stop/failure/interruption cause. |
| `neutral_confirmed` | `boolean` | NO |  | Actual neutral-transition evidence; false is retained for incident review. |
| `prediction_count` | `bigint` | NO |  | Number of reported predictions. |
| `processing_p95_ms` | `double precision` | YES |  | Measured processing-only p95 in milliseconds, if available. |
| `display_p95_ms` | `double precision` | YES |  | Measured display/end-to-end p95 in milliseconds, if available. |
| `timing_scope` | `text` | NO |  | Explicit timing measurement boundary. |
| `payload_sha256` | `text` | NO |  | Publication payload digest, verified/canonicalized by trusted API. |
| `received_at` | `timestamp with time zone` | NO | CURRENT_TIMESTAMP | Cloud receipt time. |

### Keys and constraints

- `desktop_sessions_check`: `CHECK ((ended_at >= started_at))`
- `desktop_sessions_check1`: `CHECK (((mode <> 'replay'::text) OR (recording_id IS NOT NULL)))`
- `desktop_sessions_display_p95_ms_check`: `CHECK (((display_p95_ms >= (0)::double precision) AND (display_p95_ms < 'Infinity'::double precision)))`
- `desktop_sessions_feature_version_check`: `CHECK ((length(btrim(feature_version)) > 0))`
- `desktop_sessions_mode_check`: `CHECK ((mode = ANY (ARRAY['live'::text, 'replay'::text])))`
- `desktop_sessions_model_sha256_check`: `CHECK ((model_sha256 ~ '^[0-9a-f]{64}$'::text))`
- `desktop_sessions_operator_id_client_id_local_session_id_key`: `UNIQUE (operator_id, client_id, local_session_id)`
- `desktop_sessions_payload_sha256_check`: `CHECK ((payload_sha256 ~ '^[0-9a-f]{64}$'::text))`
- `desktop_sessions_pkey`: `PRIMARY KEY (id)`
- `desktop_sessions_prediction_count_check`: `CHECK ((prediction_count >= 0))`
- `desktop_sessions_processing_p95_ms_check`: `CHECK (((processing_p95_ms >= (0)::double precision) AND (processing_p95_ms < 'Infinity'::double precision)))`
- `desktop_sessions_status_check`: `CHECK ((status = ANY (ARRAY['completed'::text, 'stopped'::text, 'interrupted'::text, 'failed'::text])))`
- `desktop_sessions_termination_reason_check`: `CHECK ((length(btrim(termination_reason)) > 0))`
- `desktop_sessions_timing_scope_check`: `CHECK ((length(btrim(timing_scope)) > 0))`

### Indexes

- `CREATE INDEX desktop_sessions_model ON recognition.desktop_sessions USING btree (model_version_id)`
- `CREATE UNIQUE INDEX desktop_sessions_operator_id_client_id_local_session_id_key ON recognition.desktop_sessions USING btree (operator_id, client_id, local_session_id)`
- `CREATE INDEX desktop_sessions_operator_time ON recognition.desktop_sessions USING btree (operator_id, started_at DESC)`
- `CREATE UNIQUE INDEX desktop_sessions_pkey ON recognition.desktop_sessions USING btree (id)`

## `recognition.model_events`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `event_id` | `uuid` | NO |  | Service-specific persisted value; see the existing dictionary and migration contract. |
| `model_run_id` | `uuid` | NO |  | External legacy source-LDA run reference. |
| `manifest_id` | `uuid` | NO |  | Frozen research manifest ID; external Data & Protocol reference in ML. |
| `correlation_id` | `character varying(64)` | NO |  | Request/job tracing identifier. |
| `received_at` | `timestamp with time zone` | NO | CURRENT_TIMESTAMP | Cloud receipt time. |

### Keys and constraints

- `model_events_pkey`: `PRIMARY KEY (event_id)`

### Indexes

- `CREATE INDEX model_events_by_model ON recognition.model_events USING btree (model_run_id)`
- `CREATE UNIQUE INDEX model_events_pkey ON recognition.model_events USING btree (event_id)`

## `recognition.replay_sessions`

| Column | PostgreSQL type | Nullable | Default | Meaning |
| --- | --- | --- | --- | --- |
| `id` | `uuid` | NO |  | Stable UUID primary identifier. |
| `model_run_id` | `uuid` | NO |  | External legacy source-LDA run reference. |
| `recording_id` | `uuid` | NO |  | Recording reference; FK inside Data & Protocol, external in Recognition. |
| `status` | `character varying(20)` | NO |  | Run/session state constrained by CHECKs/transitions. |
| `model_checksum` | `character varying(64)` | YES |  | Legacy model JSON checksum. |
| `result` | `jsonb` | YES |  | Legacy replay/summary output JSON. |
| `error` | `character varying(200)` | YES |  | Failure/interruption reason. |

### Keys and constraints

- `replay_sessions_check`: `CHECK (((((status)::text = 'running'::text) AND (model_checksum IS NULL) AND (result IS NULL) AND (error IS NULL)) OR (((status)::text = 'succeeded'::text) AND (model_checksum IS NOT NULL) AND ((model_checksum)::text ~ '^[0-9a-f]{64}$'::text) AND (result IS NOT NULL) AND (error IS NULL)) OR (((status)::text = 'failed'::text) AND (result IS NOT NULL) AND (error IS NOT NULL))))`
- `replay_sessions_pkey`: `PRIMARY KEY (id)`
- `replay_sessions_status_check`: `CHECK (((status)::text = ANY ((ARRAY['running'::character varying, 'succeeded'::character varying, 'failed'::character varying])::text[])))`

### Indexes

- `CREATE UNIQUE INDEX replay_sessions_pkey ON recognition.replay_sessions USING btree (id)`

## Views and trigger enforcement

- `data_protocol.calibration_durations`
- `identity.operator_directory`
- `identity.valid_session_ids`
- `ml_experiments.published_models`
- `ml_experiments.reviewer_results`

Triggers enforce immutable publication, class/package membership, run leases, atomic successful output and confusion-matrix metric consistency. See the migration SQL for executable definitions; SQL CHECK text alone does not show trigger behaviour.
