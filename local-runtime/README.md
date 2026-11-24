# Local runtime

Python 3.12 child process owned by Electron. Acquisition, four-channel feature extraction/LDA inference, labelled calibration capture, durable SQLite recording chunks, bounded replay and an operator-bound cloud upload outbox live here. See [desktop usage and limitations](../desktop/README.md).

Default acquisition: **A1–A4**, 1000 Hz, ten seconds. The signal contract preserves actual channel widths and ordered source mappings. No padding or silent channel transformation is applied.

Packages:

- `acquisition/`: BITalino SDK adapter, timeout and sequence checks.
- `processing/`, `recognition/`: versioned feature contract, safe JSON LDA parser and incremental windows.
- `calibration/`: collected labelled repetition summary; no model adaptation implementation.
- `storage/`: SQLite WAL chunks, interrupted-session recovery, streaming JSON export and durable outbox.
- `sync/`: authenticated publication, capped exponential retry, explicit auth/conflict/rejection states.

`python -m myocontrol_runtime --data-dir PATH` uses private JSON-lines stdio. Electron main restricts the renderer's callable commands and owns file dialogs. This protocol is not a remote API and must not be exposed as a network service. EOF or shutdown stops acquisition and synchronization. A forced process termination preserves committed chunks, which are marked interrupted at the next startup.

Only `fixtures/synthetic-demo.json` is bundled: deterministic synthetic waveforms without participant data or model weights. Hardware adapter tests inject a simulated SDK and do not establish real Bluetooth compatibility.
