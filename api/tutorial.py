"""Executable cloud-access and synthetic-research tutorials using only Python's standard library."""

import argparse
import base64
import getpass
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid


class Client:
    def __init__(self, base, authorization=None):
        self.base = base.rstrip("/")
        self.authorization = authorization

    def call(self, method, path, body=None, expected=200, headers=None):
        request_headers = dict(headers or {})
        if self.authorization:
            request_headers["Authorization"] = self.authorization
        data = None if body is None else json.dumps(body).encode()
        if data is not None:
            request_headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base + path, data=data, headers=request_headers, method=method
        )
        try:
            response = urllib.request.urlopen(request, timeout=35)
        except urllib.error.HTTPError as error:
            if error.code == expected:
                return None
            raise RuntimeError(f"{method} {path}: HTTP {error.code}, expected {expected}") from None
        with response:
            if response.status != expected:
                raise RuntimeError(f"{method} {path}: HTTP {response.status}, expected {expected}")
            payload = response.read()
            return json.loads(payload) if payload else None

    def bytes(self, path):
        request = urllib.request.Request(
            self.base + path, headers={"Authorization": self.authorization}
        )
        with urllib.request.urlopen(request, timeout=35) as response:
            return response.read(), response.headers.get("X-Artifact-SHA256")


def cloud(args):
    client = Client(args.base)
    password = getpass.getpass("Operator password: ")
    access = client.call("POST", "/auth/v1/sessions", {"email": args.email, "password": password})
    del password
    client.authorization = "Bearer " + access["access_token"]
    client_id = None
    try:
        me = client.call("GET", "/auth/v1/me")
        print("Signed in; scope=" + me["scope"])
        for collection in ("runs", "models", "results"):
            page = client.call("GET", f"/cloud/v1/{collection}?limit=25&offset=0")
            print(f"{collection}: {len(page['items'])} item(s), next_offset={page['next_offset']}")
        issued = client.call(
            "POST",
            "/auth/v1/clients",
            {"kind": "training_worker", "name": "Tutorial workstation", "platform": "tutorial"},
            expected=201,
        )
        client_id = issued["client_id"]
        worker = Client(args.base, "Bearer " + issued["access_token"])
        assert worker.call("GET", "/auth/v1/me")["scope"] == "training_worker"
        client.call("GET", "/auth/v1/clients")
        client.call("DELETE", "/auth/v1/clients/" + client_id, expected=204)
        client_id = None
        worker.call("GET", "/auth/v1/me", expected=401)
        print("Client token scope and immediate revocation verified; no token was printed.")
    finally:
        if client_id:
            client.call("DELETE", "/auth/v1/clients/" + client_id, expected=204)
        client.call("DELETE", "/auth/v1/sessions/current", expected=204)
    client.call("GET", "/auth/v1/me", expected=401)
    print("Logout verified: revoked web token receives HTTP 401.")


def synthetic(args):
    if args.env_file:
        values = {}
        for line in Path(args.env_file).read_text(encoding="utf-8-sig").splitlines():
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                values[key] = value.strip().strip("\"'")
        username, password = values["GATEWAY_USERNAME"], values["GATEWAY_PASSWORD"]
    else:
        username = (
            args.username
            or os.environ.get("GATEWAY_USERNAME")
            or input("Development gateway username: ")
        )
        password = os.environ.get("GATEWAY_PASSWORD") or getpass.getpass(
            "Development gateway password: "
        )
    authorization = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
    client = Client(args.base, authorization)
    unique = uuid.uuid4().hex[:12]
    source = client.call(
        "POST", "/data/v1/participants", {"pseudonym": "tutorial_source_" + unique}, expected=201
    )
    target = client.call(
        "POST", "/data/v1/participants", {"pseudonym": "tutorial_target_" + unique}, expected=201
    )
    protocol = client.call(
        "POST",
        "/data/v1/protocols",
        {"name": "tutorial_" + unique, "version": 1, "gesture_codes": ["rest", "fist"]},
        expected=201,
    )
    manifest = client.call(
        "POST",
        "/data/v1/research-manifests",
        {"protocol_id": protocol["id"], "name": "tutorial_" + unique, "version": 1},
        expected=201,
    )
    path = "/data/v1/research-manifests/" + manifest["id"]
    for participant, category in ((source, "source"), (target, "target")):
        client.call(
            "POST",
            path + "/participants",
            {"participant_id": participant["id"], "category": category},
            expected=201,
        )
    target_recording = None
    for participant, category, gesture, base in (
        (source, "source", "rest", 1),
        (source, "source", "fist", 10),
        (target, "target", "rest", 1.1),
        (target, "target", "fist", 10.1),
    ):
        samples = [
            [base + (i % 7) * 0.01 + channel * 0.02 for channel in range(4)] for i in range(400)
        ]
        recording = client.call(
            "POST",
            "/data/v1/recordings",
            {"participant_id": participant["id"], "sample_rate_hz": 1000, "samples": samples},
            expected=201,
        )
        segment = client.call(
            "POST",
            "/data/v1/segments",
            {
                "recording_id": recording["id"],
                "gesture_code": gesture,
                "repetition_key": "one",
                "start_sample": 0,
                "end_sample": 400,
            },
            expected=201,
        )
        client.call(
            "POST",
            path + "/units",
            {
                "participant_id": participant["id"],
                "category": category,
                "segment_id": segment["id"],
                "role": "source_train" if category == "source" else "target_test",
            },
            expected=201,
        )
        if category == "target":
            target_recording = recording["id"]
    frozen = client.call("POST", path + "/freeze")
    client.call("GET", path)
    snapshot = client.call("GET", path + "/snapshot")
    assert snapshot["checksum"] == frozen["checksum"] and len(snapshot["units"]) == 4
    print("Created and froze a four-unit synthetic research manifest.")
    body = {"manifest_id": manifest["id"], "target_participant_id": target["id"]}
    headers = {"Idempotency-Key": "tutorial-" + unique}
    run = client.call(
        "POST", "/experiments/v1/source-lda-experiments", body, expected=202, headers=headers
    )
    repeated = client.call(
        "POST", "/experiments/v1/source-lda-experiments", body, expected=202, headers=headers
    )
    assert repeated["id"] == run["id"]
    run_path = "/experiments/v1/source-lda-experiments/" + run["id"]
    deadline = time.monotonic() + 90
    while run["status"] in {"queued", "running"} and time.monotonic() < deadline:
        time.sleep(0.5)
        run = client.call("GET", run_path)
    if run["status"] != "succeeded":
        raise RuntimeError(
            "LDA did not succeed; inspect its status/error and the development experiment-worker logs."
        )
    artifact, header_digest = client.bytes(run_path + "/model")
    assert hashlib.sha256(artifact).hexdigest() == run["model_checksum"] == header_digest
    replay = client.call(
        "POST",
        "/recognition/v1/replay-sessions",
        {"model_run_id": run["id"], "recording_id": target_recording},
        expected=201,
    )
    assert replay["status"] == "succeeded"
    assert (
        client.call("GET", "/recognition/v1/replay-sessions/" + replay["id"])["id"] == replay["id"]
    )
    print(
        f"LDA succeeded; artifact SHA-256 verified; replay predictions={replay['result']['prediction_count']}."
    )
    print(
        "Synthetic engineering evidence only. These legacy runs do not populate the cloud generic registry."
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    commands = parser.add_subparsers(dest="command", required=True)
    access = commands.add_parser("cloud")
    access.add_argument("--email", required=True)
    research = commands.add_parser("synthetic")
    research.add_argument("--username")
    research.add_argument(
        "--env-file", help="Read local development Basic credentials from an ignored env file"
    )
    args = parser.parse_args()
    try:
        (cloud if args.command == "cloud" else synthetic)(args)
    except (RuntimeError, urllib.error.URLError, KeyError, AssertionError) as error:
        raise SystemExit(f"Tutorial failed: {error}") from None


if __name__ == "__main__":
    main()
