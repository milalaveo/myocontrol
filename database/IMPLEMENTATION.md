# Database implementation status

## Accepted target versus existing schema

The accepted [ADR-001](../docs/ARCHITECTURE_DECISIONS.md) now has additive persistence migrations: `identity/0001`, `data_protocol/0006`, `ml_experiments/0007` and `recognition/0003`. They add operator/client/session records, publication provenance/receipts, a generic run/model/package/evaluation registry and desktop reports. See the [teacher guide](README_TEACHER.md), [current logical diagrams](SERVICE_MODEL.md) and [generated service dictionary](SERVICE_DATA_DICTIONARY.md). HTTP identity, authenticated worker APIs and actual Electron synchronization remain application work; schema support does not establish a completed runtime.

This document describes the original `myoprosthesis` backend and its limits. Statements about missing APIs or workers below refer to that implementation. The current service schemas, migration setup and relationships are described in the [database overview](README.md), [data dictionary](DATA_DICTIONARY.md) and [logical model](LOGICAL_MODEL.md). The database remains a research prototype; synthetic checks do not validate final research results or participant-data handling.

## Additive service database acceptance — 23 November 2026

- Four new migrations extend, rather than rewrite, the 13 previously applied service migrations; the migrator now records 17 checksummed revisions.
- Identity, original-source recording metadata/client receipts, general model/adaptation-package registry, worker leases, mathematically checked evaluations and terminal desktop reports are implemented in SQL.
- Verified locally on an isolated PostgreSQL 16.3: clean migration, repeat migration, upgrade preserving existing participant/queued LDA rows, generated-DDL restoration, 18 acceptance tests (including concurrent claims), and existing Data/ML/Recognition test suites.
- CI now includes the same migrations/upgrade/acceptance/DDL checks on PostgreSQL 18. A CI configuration change is not a claim that the remote job has already passed.
- [Teacher review procedure](README_TEACHER.md) gives a standalone PostgreSQL 18 setup and safe test commands. No application database was migrated during these local checks.

The historical backend limitations below remain labelled as such. New registry metrics have arithmetic checks; byte authenticity, actual fit inputs, real-data identity resolution and cross-service authorization remain application responsibilities.

## Deployment and access

Migrations are ordered by Alembic revision and executed by the schema owner. `roles.sql` creates NOLOGIN group roles for reading, writing and restricted reviewer access and must be run by the actual object owner with permission to create roles. Environment-specific login roles and secrets are managed separately. The default privilege statements apply only to objects subsequently created by the role executing them; run and test grants for each migration owner. The read and write roles have broad operational metadata access; the reviewer role has access only to explicitly granted views, which contain pseudonymous participant IDs and are not automatically suitable for public release. Database file access is separately controlled by the storage service.

The repeatable reference seed is separate from migrations. Reapplying it does not replace existing labels. Synthetic tests never establish recognition performance. Before any actual deployment, define a backup and restore policy, participant deletion procedure, secure credentials, and role-specific access to sensitive metadata and recordings.

## Split checksum

New manifests require a protocol version and signal provenance. The format 3 checksum is SHA-256 over UTF-8 PostgreSQL `jsonb` text of the protocol ID, name, version, schema version, parameters, ordered gesture IDs/codes/rest markers and the format 2 split checksum. The latter contains the ordered participants and units, canonical identities, sample rates, identity-method versions, artifact storage identifiers, sizes and SHA-256 values. Source artifact bytes are not verified by the database. PostgreSQL's JSON serialization and identity values are part of this format: independent implementations must match it precisely. Existing manifests frozen before these migrations retain older checksums and must not be used as final evidence; create new versions.

`signal_provenance` binds one canonical signal to one artifact and sampling rate. This does not resolve duplicates automatically: the importer must use a documented source-specific identity method, validate bytes and metadata, and map transformed or repeated imports to the same original signal. If equivalence or participant identity is unknown, the limitation must be explicit. Protocol JSON and algorithm JSON still need published schemas and validation owners.

## Calibration

Each new frozen subset requires a gesture set containing rest, exactly the requested number of distinct labelled repetitions per required gesture, eligible calibration membership, and nesting with frozen budgets in the same series. `calibration_durations` unions half-open sample intervals separately per gesture and signal and divides by the signal sampling rate. It is not a substitute for validating correct labels or source timing. The application must ensure the same gesture vocabulary is used consistently during the experiment.

## Runs and publication

Runs have guarded status transitions and explicit split inputs. Model publication checks a recorded checksum attestation, compatible parent and subset, and exact selected calibration segment IDs. Evaluation publication checks the completed model, participant, manifest, feature configuration, full target test and metric presence. Terminal run results are protected from ordinary updates. `published_models` and `completed_evaluations` are selection views.

An artifact verification is an attestation inserted by a trusted service: PostgreSQL cannot prove the file exists or that its bytes were hashed. The initial local storage adapter verifies file bytes before recording verification and publishes a source-only model and successful run in one database transaction. It can list potential orphan objects and abandoned staging files, but does not delete them or run reconciliation automatically. The database has a stale-heartbeat interruption procedure, but no worker invokes it automatically. No job worker or trusted API is implemented yet. SQL run-input records alone cannot prove which arrays were actually passed to model fit. A complete confusion matrix for the protocol gesture set is required, but mathematical consistency of its counts and reported metrics, comparison uncertainty and end-to-end compatibility remain to be enforced and tested.

## Verification and remaining work

Numbered SQL tests correspond to their migration revisions; Python concurrency tests require `TEST_DATABASE_URL` and leave synthetic rows in the disposable test database. Tests performed so far cover individual constraints, two split freeze/mutation orderings, one segment edit/selection ordering, publication and basic role permissions. They are not a complete acceptance suite.

The PostgreSQL CI job has successfully exercised migrations, constraints, concurrency checks, API tests, schema isolation and generated DDL on a clean database. The baseline dictionary described 46 business tables. The additive migrations bring coverage to 59 across the 31-table historical schema and 28-table current service schemas. The generated service dictionary includes all current service columns/constraints/indexes. Migration bookkeeping is documented separately. The separate Compose smoke job still requires investigation.

Still required for final research/production use: DB2 import identity and provenance validation; further protocol and gesture concurrency audits; complete calibrated input enforcement against actual model arrays; complete result and comparison compatibility; mathematical metric checks; further role hardening; artifact reconciliation; representative query plans; and participant-data retention procedures. These limitations must be distinguished from the narrower database submission checklist.

The preceding paragraph describes the historical schema/research validation backlog. In the new service registry, complete confusion-count arithmetic and required package/class checks are implemented and tested. It still cannot prove correct ground-truth labels, actual fit arrays, file bytes, cross-service authorization or final statistical comparison rules; those require application/research evidence.
