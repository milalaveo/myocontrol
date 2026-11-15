# Logical data dictionary

Status: proposed entities and attributes, not a physical schema. Every entity has a primary key; relationships below indicate intended foreign keys. Physical types, nullability, defaults, delete policies, validation ownership and examples will be specified for every column alongside DDL. `id` denotes a surrogate identifier unless otherwise stated. Times are timezone-aware; signal offsets are integer sample coordinates. Derived quantities are not stored without a documented reason and consistency rule.

## Sources and recordings

| Entity | Purpose and principal attributes | Relationships and rules |
| --- | --- | --- |
| `datasets` | Source identity and descriptive metadata. | One dataset has many immutable dataset versions. |
| `dataset_versions` | Dataset, version identifier, usage and provenance metadata. | Unique version per dataset; preserve historical imports. Device-origin sessions may not have a dataset version. |
| `participants` | Pseudonymous participant code and minimal research metadata. | Code is unique; direct identifiers and consent are external. |
| `participant_source_ids` | Source-specific participant identifier and version. | Links participant and dataset version; source identifier is unique within its defined scope. Unknown cross-source identity remains unknown. |
| `artifacts` | Storage key, media/schema type, byte size, checksum algorithm and digest, availability/publication state. | Stable keys are unique within storage namespace; nonnegative size and validated digest. Actual file access and verification require storage checks. |
| `recording_sessions` | Participant, acquisition mode, source/device configuration, status, timestamps and interruption reason. | References participant and, when applicable, dataset version; status and timestamp combinations are validated. |
| `recordings` | Session, artifact, source external key, canonical signal identity, sample rate, sample count and provenance. | Sample rate is positive and sample count nonnegative; external key is unique within source version where applicable. Canonical signal identity survives duplicate import. |
| `recording_channels` | Recording, channel position, source channel identifier and available electrode metadata. | Unique position within recording; ordered channels describe the actual source. |
| `labelled_segments` | Recording, canonical gesture, source label, repetition identity and start/end sample offsets. | `0 <= start < end <= sample_count`; labels and repetition mapping retain source provenance. |

## Gestures and signal configuration

| Entity | Purpose and principal attributes | Relationships and rules |
| --- | --- | --- |
| `gestures` | Canonical gesture identifier and description, including rest. | Stable identity independent of source labels. |
| `gesture_set_versions` | Versioned gesture vocabulary and status. | Published membership is immutable. |
| `gesture_set_members` | Membership and display/order information. | Unique gesture and order within a set version; required sets include rest. |
| `gesture_mappings` | Versioned mapping from source context and source label to canonical gesture, optionally to a simulation action. | Source mapping scope and uniqueness are explicit; published mappings are immutable. Simulation actions may be separated into their own versioned mapping if needed. |
| `feature_configs` | Versioned preprocessing, window length/step, channel and feature order, thresholds and fit policy. | Published configuration immutable; algorithm-specific JSON parameters require a versioned schema and application validation. |
| `protocol_versions` | Versioned experiment protocol, class set, selection and comparison rules. | Identifies frozen decisions and exploratory changes; links relevant gesture and feature versions. |

## Splits and calibration

| Entity | Purpose and principal attributes | Relationships and rules |
| --- | --- | --- |
| `split_manifests` | Protocol, version, draft/frozen state, canonical checksum and timestamps. | Frozen only after serialized validation; frozen contents and checksum dependencies are immutable. |
| `split_participants` | Manifest, participant and category: source, development or target. | Unique `(manifest, participant)`; membership is guarded on every write. |
| `split_units` | Manifest, participant, recording or segment, resolved canonical signal interval and assigned role. | Role must match category; unit and participant must match. Cross-role overlap is rejected, including duplicate imports. Derived coordinates require explicit consistency checks. |
| `calibration_subsets` | Frozen manifest, target participant, selection version, requested budget and optional parent subset. | Parent and child belong to the same manifest and participant; child extends parent. A source-only condition has zero calibration and does not require a subset. |
| `calibration_items` | Subset, eligible calibration unit and repetition/segment identity. | Unique selected repetition within subset; participant and manifest match; test units excluded. Required classes and nested membership are validated before use. |

## Runs, models and evaluation

| Entity | Purpose and principal attributes | Relationships and rules |
| --- | --- | --- |
| `runs` | Type, state, operation-scoped idempotency key, protocol, manifest, feature configuration, seed, versioned algorithm parameters, software versions and lifecycle timestamps. | Allowed state transitions use expected prior state; intentional reruns have distinct IDs. Training input membership and role provenance must be recorded explicitly. |
| `run_inputs` | Explicit references to input manifests, units, subsets or artifacts and their role in a run. | Exact physical representation must preserve referential integrity and distinguish input types; no unvalidated polymorphic foreign key. |
| `model_versions` | Producing run, model family, condition, feature configuration, artifact, optional parent model and calibration subset. | Published model requires a verified artifact and successful producing run. Personalised and target-only conditions require their appropriate parent/subset references. |
| `evaluations` | Evaluation run, model, target participant, protocol, frozen manifest and exact test selection. | Test selection must match target and manifest; evaluations of incompatible test sets are not comparable. |
| `evaluation_metrics` | Evaluation, metric type, value or missing reason, optional numerator and denominator. | Unique metric type per evaluation; bounded metrics in `[0,1]`; absence is explicit, not silently zero. |
| `confusion_counts` | Evaluation, actual gesture, predicted gesture and count. | Unique gesture pair per evaluation; counts nonnegative and gestures belong to the evaluation class set. |
| `recognition_sessions` | Published model, live/replay mode, input configuration or replay source, status, timestamps, stop reason and timing summary. | Replay source is required for replay; timing summary includes prediction count. Session safety is also enforced by the application. |

## Normalization and unresolved details

Entities separate source identity, participant identity, recording identity and artifact storage; many-to-many relationships use explicit membership tables. Configurations and versions are shared by reference rather than copied into each result. The intended design is 3NF; functional dependencies and justified denormalizations must be verified against the final physical schema. Versioned JSON is limited to algorithm-specific parameters, with its schema, example and validation owner documented per field.

This logical dictionary deliberately does not invent final physical columns or claim that proposed checks are already enforced. The final dictionary must enumerate every table and column, SQL type, unit, nullability, default, PK/FK, allowed values, source, quality checks and delete policy, and match the migrations exactly.
