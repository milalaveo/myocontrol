# Backend

The backend contains the local artifact store, a source-only model publication path and a synthetic persistence workflow. Application code is in `src/myoprosthesis`; tests are in `tests`.

## Synthetic workflow

Install `database/requirements.txt` in a Python virtual environment. In PowerShell, set `PYTHONPATH` to the absolute path of `backend/src` and set `TEST_DATABASE_URL` to a psycopg connection URL for a disposable PostgreSQL database with the migrations applied. From the project root, run:

```powershell
python -m myoprosthesis.experiments.synthetic_workflow --store data/artifacts/rehearsal
python -m unittest discover -s backend/tests -p 'test_*.py' -v
```

The workflow creates synthetic database records and returns their IDs. Its signals are generated four-channel CSV samples; the model is a placeholder and the metrics are recorded as unavailable. Run it only against a disposable database.

## Artifact storage

The local store uses SHA-256 content-addressed keys. It writes a staging file, flushes it and publishes it through a hard link on the same filesystem. Existing files are checked before reuse. The storage root must be controlled by the service and consistently mapped to the `local` database namespace.

Model publication verifies the file and saves its metadata and the completed run state in one database transaction. A failure after the file is written can leave an unreferenced object. Reconciliation lists old unreferenced objects and staging files without deleting them. File data is flushed, but directory durability after a power loss depends on the platform.

**TBD:** API and job worker; signal processing and model training; automatic reconciliation and recovery; backup and retention policies; and deployment-specific storage configuration.
