# Local runtime

Python 3.12 child process owned by Electron. Acquisition, two- and four-channel feature extraction/LDA inference, labelled calibration capture, durable SQLite recording chunks, bounded replay and an operator-bound cloud upload outbox live here. See [desktop usage and limitations](../desktop/README.md).

Default acquisition: **A1–A4**, 1000 Hz, ten seconds. The signal contract preserves actual channel widths and ordered source mappings. No padding or silent channel transformation is applied.

Packages:

- `acquisition/`: BITalino SDK adapter, timeout and sequence checks.
- `processing/`, `recognition/`: versioned feature contract, safe JSON LDA parser and incremental windows.
- `calibration/`: labelled repetition summary and local target-only personal LDA training; source-model adaptation remains unimplemented.
- `storage/`: SQLite WAL chunks, interrupted-session recovery, streaming JSON export and durable outbox.
- `sync/`: authenticated publication, capped exponential retry, explicit auth/conflict/rejection states.

`python -m myocontrol_runtime --data-dir PATH` uses private JSON-lines stdio. Electron main restricts the renderer's callable commands and owns file dialogs. This protocol is not a remote API and must not be exposed as a network service. EOF or shutdown stops acquisition and synchronization. A forced process termination preserves committed chunks, which are marked interrupted at the next startup.

Only `fixtures/synthetic-demo.json` is bundled: deterministic synthetic waveforms without participant data or model weights. Hardware adapter tests inject a simulated SDK and do not establish real Bluetooth compatibility.

## LDA channel contracts

The runtime accepts `time-domain-2ch-v1` (`channels: 2`, 10 features) and the existing `time-domain-4ch-v1` (`channels: 4`, 20 features). Both retain the same five features per channel in channel-major order, 200 ms windows and 100 ms steps, with no filtering. A1/A2 use `channel_map: [0, 1]`. Live inference also requires declared units matching acquisition (`ADC counts`) and matching sample rate. The shared reference electrode is not a measured channel.

Import a model actually trained for the selected channels and preprocessing. Relabelling a four-channel model, truncating its coefficients, padding signals or duplicating channels does not produce a validated two-channel model. This change adds runtime compatibility only; it neither trains a model nor establishes prediction accuracy. Evaluate on held-out recordings before treating predictions as reliable.


Experimental DB2 transfer uses `time-domain-2ch-dc-common-rms-v1`, explicitly distinct from the raw-amplitude contracts. Each 200 ms window is centered per channel and divided by one common RMS across both channels (floor `1e-12`, otherwise zero features for a constant window). It preserves relative channel energy but loses absolute energy, including a useful rest cue. Both training and runtime call the same extractor. The model declares raw accepted input units separately from `window-normalized` feature units and is marked experimental. DB2 Delsys channel 9/10 to BITalino A1/A2 is an unvalidated anatomical approximation, not a sensor calibration or a promise of accuracy.

## Personal calibration training

`train_personal_model(recording_ids)` fits a target-only LDA from explicitly selected completed BITalino calibration recordings for one participant/configuration. The supported initial classes are `rest`, `fist`, `finger_spread`; select 5–20 repetitions per class, preferably 10, 6 seconds each, at 1000 Hz with 2 or 4 measured channels. Research, failed/stopped, duplicate, mixed-configuration, constant-channel, integrity-failed and >1% clipped recordings are rejected. Each recording must last 4–30 seconds. Labels describe the held pose for the entire repetition; one second is removed at each edge.

The latest ceil(20%) whole repetitions per class are held out before feature extraction/fitting, with no refit on test recordings. The exported `time-domain-2ch-dc-v1` or `time-domain-4ch-dc-v1` contract subtracts each window's per-channel mean while retaining amplitude. Training-only standardization is folded into the exported weights. The NumPy LDA uses equal priors, balanced training windows, seed 7 and fixed 0.1 pooled-covariance shrinkage toward a scaled identity; it is not the DB2 auto-shrinkage estimator. No SciPy/scikit-learn runtime dependency is added.

A successful command archives the model and full split/recording-digest report under the runtime profile's `models/` directory and selects a validated persistent copy. Failure retains the previous selected model. The UI shows window accuracy, balanced accuracy, rest false activations and a confusion matrix. These are correlated windows from a small repetition holdout, not new-session performance or proof of scientific/clinical validity. Source-statistics mixing and general model adaptation remain separate unimplemented methods.
