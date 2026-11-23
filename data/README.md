# Local data

## Accepted storage boundary

Under [ADR-001](../docs/ARCHITECTURE_DECISIONS.md), central published models/results and permitted research artifacts reside in cloud storage; workstation data and Electron packages/recordings are local working copies or pending records. Preserve IDs, checksums and provenance when transferring via APIs. Raw-data upload is governed by source/participant permissions and retention policy; it is not automatic for every live session. These ignored directories remain local development/research storage, not the cloud publication mechanism.

Use this directory for local datasets, intermediate files, model artifacts and exports. The corresponding data directories are excluded from version control. Keep participant data, restricted datasets and credentials out of the repository. Label synthetic fixtures clearly and keep automated-test fixtures with the tests.

**TBD:** long-term storage, backup, retention and deletion policies.
