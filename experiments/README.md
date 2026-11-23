# Experiments and Reproducible Local Training

The [accepted architecture](../docs/ARCHITECTURE_DECISIONS.md) executes **general LDA/SVM/MLP training and batch research evaluation on a powerful local workstation**. Cloud APIs coordinate jobs and store published models/results. Electron executes interactive calibration/adaptation and live recognition locally.

## Research protocol

Version splits, calibration budgets, feature/channel/class mappings, source pools, adaptation methods and evaluation rules before final testing. Compare source-only, personalised and target-only under matching conditions. Keep final tests out of fit, adaptation and preprocessing fit. Generated results and restricted recordings remain outside Git.

## Workstation delivery contract

- Provide a reproducible CLI/container or equivalent tool, pinned environment, data preparation and example invocation usable outside the author's computer.
- Obtain permitted immutable input snapshots/artifacts from cloud APIs. Verify hashes and contract/runtime versions before fitting.
- Claim jobs with identity/attempt and report heartbeat/progress. Offline workers are shown unavailable; queued work does not silently execute in the cloud.
- Publish model packages, actual metrics, input membership, seed, software/configuration versions and checksums. Incomplete uploads are not published as complete.
- Reruns have explicit attempt/run identities; failed retries do not overwrite immutable results.

## Adaptation package contract

Desktop personalisation must receive required source statistics (LDA), fixed weighted source feature/label pools (SVM), or weights plus fixed source replay pools (MLP). Define distribution permission, bounds, preprocessing, membership and checksums. Benchmark adaptation duration and peak memory per supported desktop method. Comparable target-only controls use the same calibration subset and frozen test.

## Status

The current development worker implements synthetic source-only LDA and accesses its service database locally. Authenticated remote-worker APIs/tooling, full SVM/MLP/personalised/target-only paths and adaptation packages are not complete. Final model parameters, budget plan and statistical reporting rules remain to be fixed in the protocol.
