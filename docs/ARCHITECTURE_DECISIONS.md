# MyoControl — Accepted Architecture Decisions

**Status:** accepted decisions; implementation incomplete.<br>
**Decision date:** 23 November 2026<br>
**Decision owner:** project author

## ADR-001 — Cloud research portal and packaged local control

This decision supersedes earlier proposals about physical deployment, client delivery and responsive UI scope. Research goals, LDA/SVM/MLP, source-only/personalised/target-only comparisons, leakage rules and final-test isolation remain unchanged. The two-/four-channel research configuration remains a separate open decision.

### Placement and delivery

| Boundary | Responsibility | Exclusions |
| --- | --- | --- |
| Cloud platform | Operator accounts/authorization, research metadata/protocols, models and artifacts, experiment results, research-job coordination and adaptive web interface. | General model fitting, device acquisition, interactive calibration/adaptation and per-window live prediction. |
| Powerful local training workstation | General LDA/SVM/MLP training, batch experiments/evaluation from versioned inputs, publication of models/metrics/provenance through cloud APIs. | A mandatory dependency of a prepared live client session; direct cloud database access. |
| Electron desktop application | Packaged local UI, Python runtime and PLUX SDK; acquisition, guided calibration, local adaptation, live recognition, virtual hand, replay, local persistence and synchronization. | Manually installed Python, manually started local workers, Docker on the user's laptop or a required browser tab. |

Cloud provider and resource sizing remain operational choices. The previously discussed Mac mini is an infrastructure option, not a required node or a confirmed cloud deployment. General training remains on a powerful local workstation.

### Interfaces

- The adaptive browser portal handles operator access, data/protocol/model management, job submission/status, results/comparison and export. Job submission coordinates local computation; an unavailable worker leaves a job waiting or unavailable, not executing in the cloud.
- Electron embeds a local React build and automatically manages the bundled Python process. Local commands/events use a restricted process/IPC interface; exact transport remains an implementation choice. Remote content cannot access arbitrary local processes or files.
- The 1440/768/390 px responsive requirement applies to the cloud portal. Electron supports usable laptop/desktop window sizes; mobile live/calibration or browser-based remote sensor control is not required.
- The external compute worker claims permitted work through authenticated cloud APIs, sends heartbeat/progress and uploads results. Desktop users and external workers receive no direct PostgreSQL credentials.
- Cloud storage is authoritative for operator identities and published model/result versions. Local drafts, recordings, packages and pending transfers are explicitly distinct from centrally published records.

### Calibration and model packages

Calibration includes labelled target-data collection and local model adaptation. Ordinary live predictions are not ground-truth training labels. Successful adaptation creates a new personal model with parent ID, exact subset, parameters and integrity information; failure preserves the source model.

Each package includes the model, signal/feature/class mapping, runtime versions and method-specific adaptation material:

- LDA mixing requires source statistics appropriate to the chosen estimator.
- Weighted SVM retraining requires the fixed source feature/label pool and weights.
- MLP source-replay adaptation requires model weights and the fixed replay feature/label pool.

Pools must be bounded, versioned and permissible to distribute. Record membership/checksums and preprocessing. Package size, adaptation time and peak memory are tested separately for every supported desktop method. Comparable target-only controls use identical calibration/test memberships. Research batch controls execute on the workstation; any interactive desktop fitting executes locally.

### Research and runtime invariants

- Assign data roles before windowing; test data do not enter training, adaptation, preprocessing fit or method selection.
- Freeze test membership across comparable methods/budgets and enforce nested calibration selections.
- Use one versioned signal/feature specification across training, adaptation and inference, verified with cross-runtime reference vectors.
- Preserve seeds, software/configuration versions, source pools, frozen inputs and checksums. Keep synthetic, DB2, MuscleBIT and live engineering results separate.
- Per-window live control stays local. Cloud loss cannot interrupt a prepared live session. Pause/stop and acquisition/input/processing failure produce neutral and a visible reason; restart after failure is explicit.
- Model replacement occurs between sessions; recording, adaptation and live execution have explicit lifecycle states.

### Offline and synchronization boundary

A prepared authorized desktop can acquire, calibrate, adapt and run live/replay without a server round trip. First account access, uncached package retrieval and new cloud research operations require connectivity. Offline authorization duration, expiry and revocation behaviour need an explicit policy; offline use is not unlimited cloud-account access.

Transfers use stable identities, checksums, idempotency and incomplete-transfer recovery. Retry cannot duplicate a model or overwrite immutable results. Local pending results remain labelled pending until server validation/publication. Raw-data upload follows the approved data policy; central storage does not imply automatic upload of every recording.

### Packaging and submission

- Deliver separate tested installers for supported OS/CPU targets, bundling UI, Python/dependencies, native SDK and permitted demo assets. Native SDK/Bluetooth compatibility must be tested per target; Electron alone does not guarantee it.
- One application launch manages local process startup, health, error reporting and shutdown. Users do not configure Python, Docker or a worker manually.
- Deliver general training as separately reproducible CLI/container tooling, environment definitions, data-preparation instructions, configurations and an example run. Training must work outside the author's private workstation.
- Deploy and document cloud services separately. The installer does not establish completed cloud authorization or synchronization.

### Required acceptance evidence

1. Clean-machine desktop installation and supplied replay without Python/Docker setup.
2. Real SDK acquisition with continuity checks and repeated startup/shutdown.
3. Local calibration/adaptation with measured duration and memory for advertised methods.
4. Live latency, neutral response, failure and explicit recovery checks.
5. Prepared session during cloud loss, then successful duplicate-free synchronization.
6. Cloud job executed on another provisioned local workstation; verified publication and reproducible training.
7. Operator authorization across cloud, desktop and worker; account identity remains separate from participant identity.
8. Adaptive web checks at desktop/tablet/mobile sizes and Electron checks at supported window sizes.

### Consequences and open details

Accepted complexity includes installer maintenance, two UI surfaces, native SDK testing, local persistence, synchronization and remote-worker contracts. Provider, identity/session mechanism, offline policy, local transport, native build matrix, package format, data retention and source-pool distribution remain to be specified. Placement of general training, local adaptation and live execution is settled.

Current code contains single-host development Compose, service APIs, synthetic source-only LDA and offline replay. Electron, local adaptation, direct SDK integration, remote-worker APIs and synchronization are not yet implemented. SQL migrations now model operators/clients/sessions, generic jobs/models/adaptation packages/evaluations, recording receipts/provenance and desktop reports. These are persistence capabilities, not a completed authentication/synchronization API. See [database acceptance](../database/README_TEACHER.md).

## Related documents

- [Deployment architecture](DEPLOYMENT_ARCHITECTURE.md)
- [Design PRD](DESIGN_PRD.md)
- [Project requirements](PROJECT_REQUIREMENTS.md)
- [Database requirements](DATABASE_REQUIREMENTS.md)
- [Service architecture](../architecture/README.md)
