"""Create a local PostgreSQL and signal-artifact backup without stopping services."""

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import re
import subprocess
import uuid


def digest_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description="Back up the local Myocontrol database and signal files.")
    parser.add_argument("--destination", type=Path, default=Path("data/backups"))
    parser.add_argument("--database-container", default="myocontrol-database-1")
    parser.add_argument("--data-container", default="myocontrol-data-protocol-1")
    parser.add_argument("--database-user", default="thesis_admin")
    parser.add_argument("--database-name", default="thesis")
    args = parser.parse_args()
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = args.destination / f"{timestamp}-{uuid.uuid4().hex[:8]}"
    destination.mkdir(parents=True, exist_ok=False)
    dump = destination / "database.dump"
    with dump.open("xb") as stream:
        subprocess.run(["docker", "exec", args.database_container, "pg_dump", "-U", args.database_user,
                        "-d", args.database_name, "--format=custom", "--no-owner", "--no-acl"],
                       stdout=stream, check=True)
    signals = destination / "signals"
    subprocess.run(["docker", "cp", f"{args.data_container}:/signal-data", str(signals)], check=True)
    artifacts = []
    for path in sorted(signals.iterdir()):
        if path.is_file() and not path.is_symlink() and re.fullmatch(r"[0-9a-f]{64}", path.name):
            digest = digest_file(path)
            if digest != path.name:
                raise RuntimeError(f"Signal checksum mismatch: {path.name}")
            artifacts.append({"file": f"signals/{path.name}", "sha256": digest, "size_bytes": path.stat().st_size})
    report = {"format": 1, "created_at": timestamp, "database_file": dump.name,
              "database_sha256": digest_file(dump), "signal_artifacts": artifacts,
              "note": "Database snapshot followed by an immutable signal copy; RabbitMQ and observability data are not included."}
    (destination / "backup-manifest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Backup created: {destination}")
    print(f"Verified signal files: {len(artifacts)}")


if __name__ == "__main__":
    main()
