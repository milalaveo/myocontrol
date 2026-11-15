# Simulated Myoelectric Prosthesis

A research prototype for recognising hand gestures from surface electromyography (sEMG), studying calibration with limited labelled data, and controlling a simulated hand.

## Project structure

- `backend/` — Python application, artifact storage and tests.
- `database/` — PostgreSQL schema, migrations, roles and database documentation.
- `frontend/` — operator interface.
- `experiments/` — experiment protocols and configurations.
- `data/` — local data and artifact storage guidance.

## Current status

The repository contains an initial PostgreSQL schema, local artifact storage and a synthetic persistence workflow. The workflow generates four-channel samples and exercises the database and model publication path; it does not train a classifier or measure recognition performance. Setup instructions are available in the [backend](backend/README.md) and [database](database/README.md) directories.

The following work remains **TBD**:

- Import and validation of real recordings, including Ninapro DB2.
- Signal processing, feature extraction, model training and evaluation.
- API, operator interface, simulated hand and BITalino integration.
- Final experimental protocol, deployment configuration and data retention policy.

Participant data, restricted datasets, credentials and generated artifacts must remain outside version control.
