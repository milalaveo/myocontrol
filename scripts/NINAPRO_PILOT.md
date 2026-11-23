# Ninapro DB2 ingestion pilot

## Accepted execution and publication context

[ADR-001](../docs/ARCHITECTURE_DECISIONS.md) keeps general training/batch experiments on a powerful local workstation, publishes approved metadata/models/results through cloud APIs, and reserves local live/calibration for Electron. This script remains an ingestion pilot; it is not a production importer, a research training package, a cloud deployment or an Electron recording path. Its local receipt does not replace database-backed publication/provenance.

`import_ninapro_pilot.py` imports one second each of rest and Exercise B movements 5, 6, 13 and 14 from subject 1, exercise E1. It uses refined `restimulus` and `rerepetition` arrays and keeps excerpts inside contiguous intervals with unchanged label and repetition. No split, calibration selection or training job is created.

Download subject 1 from the [official DB2 page](https://ninapro.hevs.ch/instructions/DB2.html) and place `DB2_s1.zip` in `data/raw/ninapro-db2/`. Consult the dataset's terms and cite the associated publication when reporting results. The archive retains all twelve original channels and exercises. The current pilot does not redistribute source data.

With NumPy, SciPy and HTTPX installed, start the local application and run from the repository root:

```powershell
python scripts/import_ninapro_pilot.py
```

Credentials come from `GATEWAY_USERNAME` and `GATEWAY_PASSWORD` in the environment or the ignored local `.env`. The default gateway route is `http://127.0.0.1:8000/data`; override with `--url`. The script downloads nothing by itself. It validates dimensions, participant/exercise identity and finite values, and verifies each newly uploaded excerpt by reading it through the API.

The exploratory four-channel projection uses one-based ring channels `[1, 3, 5, 7]` at the documented 2000 Hz without filtering, resampling or normalization. This is an ingestion check, not an anatomically matched or statistically selected MuscleBIT configuration.

Source URL, archive/member hashes, original sample coordinates, channel order, labels/repetitions and resulting API IDs are saved to `data/interim/ninapro-db2/pilot-s1-e1.json`. Both this receipt and raw data are ignored by Git. Keep the receipt with the database backup: source provenance is not yet persisted in service database columns. Completed excerpts are skipped on repeat runs using this receipt, after checking their stored artifact checksum. There is no server-side import idempotency: a failure between an API write and receipt update can leave an untracked row. Do not delete the receipt and blindly re-run.

**TBD before research import:** transactional database-backed source identity and provenance, full-recording/file ingestion, server-side idempotency and recovery, versioned channel/gesture contracts and leakage detection using original source coordinates. Excerpts in this pilot have local coordinates starting at zero; the local receipt alone is insufficient for enforcing cross-import split integrity. Subject 1 is development data and must not later be treated as an untouched final target.
