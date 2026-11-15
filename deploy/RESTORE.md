# Backup and restore

Run `python deploy/backup.py` from the repository root while the `myocontrol` Compose project is running. It writes a custom-format PostgreSQL dump, copies signal files and records SHA-256 checksums under the Git-ignored `data/backups/` directory. Database and container names can be changed through command-line options; use `python deploy/backup.py --help` for details.

The database snapshot is taken before the signal copy. This relies on the service publishing immutable signal files before committing database references and on no external process modifying or deleting those files during backup. A backup may contain additional unreferenced files. Temporary files and RabbitMQ, Redis, Loki, Prometheus, Grafana and Jaeger state are not included. Model outbox events in PostgreSQL are included, but broker messages already marked published are not; broker recovery and event reconciliation are TBD. The backup contains potentially sensitive data and must be protected and retained according to the approved data policy.

## Restore rehearsal

Restore into a new, disposable database and a separate artifact directory, not over a running environment. Verify `database_sha256` and each signal hash from `backup-manifest.json` before importing. Use `pg_restore --no-owner --no-acl` with a designated administrator, then apply role grants and compare the restored row counts and artifact references. Configure the restored Data & Protocol service to use the copied `signals` directory. The application roles and passwords must be provisioned separately.

A local rehearsal restored one synthetic backup into a separate PostgreSQL database and compared counts for recordings, LDA runs and replay sessions. The backup command also verified the copied signal file hashes. This does not yet demonstrate a complete restored application or broker recovery.

**TBD:** an automated restore command, broker/outbox reconciliation, encrypted off-host backups, retention and deletion policy, and a complete disaster-recovery drill. Do not treat a successful dump as proof of complete recovery.
