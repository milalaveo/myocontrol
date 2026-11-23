# MyoControl — Architecture Overview

**Status:** accepted deployment/delivery decisions; implementation incomplete.<br>
**Updated:** 23 November 2026

[ADR-001](ARCHITECTURE_DECISIONS.md) is authoritative for placement and delivery. See the [deployment diagram](DEPLOYMENT_ARCHITECTURE.md), [PNG](DEPLOYMENT_ARCHITECTURE.png) and [service implementation](../architecture/README.md).

## Accepted boundaries

| Boundary | Owns |
| --- | --- |
| Cloud | Operator identities/authorization, research metadata/protocols, models/artifacts, experiment results, job coordination and adaptive research web UI. |
| Powerful local workstation | General LDA/SVM/MLP training and batch evaluations through reproducible compute tooling, with API-based publication. |
| Electron client | Local React UI, bundled Python/PLUX SDK, acquisition, calibration/adaptation, live recognition, virtual hand, replay and recoverable local data. |

Cloud does not execute general training. The local training workstation is not required during a prepared client session. Model adaptation belongs to Electron. Mac mini hosting remains an infrastructure option rather than an architectural requirement.

## Domain ownership

- Data & Protocol owns participants, canonical source metadata, recordings/segments, class sets, protocols, frozen manifests and calibration membership. Local collections are validated when published centrally.
- ML Experiments owns job/configuration metadata, immutable input snapshots, model versions, adaptation packages and evaluations. Computation runs on the authorized workstation or in desktop adaptation, according to operation type.
- Recognition executes locally in Electron, with ordered inference, compatibility checks, neutral handling and timing. Synchronized summaries may be centrally persisted.
- Operator access is cloud-managed and separate from participant identities. Offline authorization/cache behaviour is explicitly specified.
- Client code can reuse React/Carbon components; cloud responsive research workflows and Electron local-control navigation remain distinct surfaces.

## Research invariants

- Assign roles before windowing; block leakage before fitting.
- Keep test membership fixed across comparable conditions and calibration budgets nested.
- Version preprocessing, channel/feature order, class mapping and adaptation materials; test cross-runtime compatibility.
- Retain LDA/SVM/MLP and source-only/personalised/target-only conditions. Test data never enter fit or adaptation.
- Distinguish synthetic, DB2, MuscleBIT and live engineering evidence.
- Pause/stop and input/processing failure produce neutral with a visible cause; explicit restart follows failure.

## Implementation and submission

Current SQL/API documents describe existing behaviour, not completed target features. Operator/session persistence and model/package/run/evaluation registries now have migrations and acceptance tests. Application package generation/transfer, remote job/result APIs, Electron and synchronization still require implementation. Existing Compose commands remain development commands.

Submission includes clean-machine desktop installation, permitted prepared replay, measured calibration/live behaviour and separately reproducible training tooling. Platform support is a tested OS/CPU/SDK matrix, not a guarantee supplied by Electron.
