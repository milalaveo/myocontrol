"""Import five development-only excerpts from official Ninapro DB2 subject 1.

This is an ingestion pilot, not a research dataset importer or a train/test split.
Original 12-channel data remain in the archive; provenance is stored in a local receipt.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import zipfile

import httpx
import numpy as np
from scipy.io import loadmat


SOURCE_URL = "https://ninapro.hevs.ch/files/DB2_Preproc/DB2_s1.zip"
MEMBER = "DB2_s1/S1_E1_A1.mat"
SAMPLE_RATE = 2000
EXCERPT_SAMPLES = 2000
# One-based ring channels, chosen only to exercise ingestion, not for performance.
CHANNELS = [1, 3, 5, 7]
GESTURES = {0: "rest", 5: "finger_spread", 6: "fist", 13: "wrist_flexion", 14: "wrist_extension"}


def sha256_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, default=Path("data/raw/ninapro-db2/DB2_s1.zip"))
    parser.add_argument("--receipt", type=Path, default=Path("data/interim/ninapro-db2/pilot-s1-e1.json"))
    parser.add_argument("--url", default="http://127.0.0.1:8000/data")
    args = parser.parse_args()
    credentials = {}
    if Path(".env").exists():
        for line in Path(".env").read_text(encoding="utf-8-sig").splitlines():
            key, separator, value = line.partition("=")
            if separator and key in {"GATEWAY_USERNAME", "GATEWAY_PASSWORD"}:
                credentials[key] = value.strip().strip("\"'")
    for key in ("GATEWAY_USERNAME", "GATEWAY_PASSWORD"):
        if os.getenv(key):
            credentials[key] = os.environ[key]
        if not credentials.get(key):
            raise ValueError(f"{key} is required")
    digest = sha256_file(args.archive)
    with zipfile.ZipFile(args.archive) as archive:
        with archive.open(MEMBER) as stream:
            member_digest = hashlib.file_digest(stream, "sha256").hexdigest()
        with archive.open(MEMBER) as stream:
            data = loadmat(stream, variable_names=["emg", "restimulus", "rerepetition", "subject", "exercise"])
    emg = data["emg"]
    labels, repetitions = data["restimulus"].ravel(), data["rerepetition"].ravel()
    if emg.ndim != 2 or emg.shape[1] != 12 or len(labels) != len(emg) or len(repetitions) != len(emg):
        raise ValueError("Unexpected DB2 array dimensions")
    if int(data["subject"].item()) != 1 or int(data["exercise"].item()) != 1:
        raise ValueError("Expected subject 1, exercise 1")
    if not np.isfinite(emg).all():
        raise ValueError("Non-finite EMG values")
    print(f"Validated E1: {len(emg)} samples, 12 channels; repetition values {np.unique(repetitions).tolist()}")
    receipt = {"format": "ninapro-db2-ingestion-pilot-v1", "purpose": "development_only",
               "source_url": SOURCE_URL, "archive_sha256": digest, "member": MEMBER,
               "member_sha256": member_digest, "source_sample_count": len(emg),
               "sample_rate_hz": SAMPLE_RATE, "sample_rate_source": "https://ninapro.hevs.ch/instructions/DB2.html",
               "channels_one_based": CHANNELS, "preprocessing": "none; unchanged float32 values converted to JSON numbers",
               "label_field": "restimulus", "repetition_field": "rerepetition", "excerpts": []}
    if args.receipt.exists():
        receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
        if receipt["archive_sha256"] != digest or receipt["channels_one_based"] != CHANNELS:
            raise ValueError("Receipt does not match source archive/channel configuration")

    def save():
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.receipt.with_suffix(".tmp")
        temporary.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
        temporary.replace(args.receipt)

    with httpx.Client(base_url=args.url.rstrip("/") + "/", timeout=45, trust_env=False,
                      auth=(credentials["GATEWAY_USERNAME"], credentials["GATEWAY_PASSWORD"])) as client:
        def post(path, payload):
            response = client.post(path, json=payload)
            response.raise_for_status()
            return response.json()

        if "participant_id" not in receipt:
            receipt["participant_id"] = post("v1/participants", {"pseudonym": "ninapro-db2-s01-pilot-" + digest[:12]})["id"]
            save()
        boundaries = np.r_[0, np.flatnonzero((labels[1:] != labels[:-1]) | (repetitions[1:] != repetitions[:-1])) + 1, len(labels)]
        for label, gesture in GESTURES.items():
            existing = next((e for e in receipt["excerpts"] if e["source_label"] == label), None)
            if existing:
                response = client.get(f"v1/recordings/{existing['recording_id']}")
                response.raise_for_status()
                if response.json()["artifact_sha256"] != existing["artifact_sha256"]:
                    raise ValueError("Previously imported recording changed")
                print(f"Already imported: {gesture}, recording {existing['recording_id']}")
                continue
            intervals = [(int(a), int(b)) for a, b in zip(boundaries[:-1], boundaries[1:])
                         if labels[a] == label and b - a >= EXCERPT_SAMPLES]
            if not intervals:
                raise ValueError(f"No full one-second homogeneous interval for label {label}")
            a, b = intervals[0]
            start = a + (b - a - EXCERPT_SAMPLES) // 2
            end = start + EXCERPT_SAMPLES
            recording = post("v1/recordings", {"participant_id": receipt["participant_id"], "sample_rate_hz": SAMPLE_RATE,
                                              "samples": emg[start:end, np.array(CHANNELS) - 1].tolist()})
            segment = post("v1/segments", {"recording_id": recording["id"], "gesture_code": gesture,
                                          "repetition_key": f"E1-label{label}-rep{int(repetitions[start])}-start{start}",
                                          "start_sample": 0, "end_sample": EXCERPT_SAMPLES})
            receipt["excerpts"].append({"source_label": label, "gesture": gesture, "source_repetition": int(repetitions[start]),
                                        "source_interval_zero_based_half_open": [start, end], "recording_id": recording["id"],
                                        "segment_id": segment["id"], "artifact_sha256": recording["artifact_sha256"]})
            save()
            check = client.get(f"v1/recordings/{recording['id']}/signal")
            check.raise_for_status()
            if not np.array_equal(np.asarray(check.json()["samples"]), emg[start:end, np.array(CHANNELS) - 1]):
                raise ValueError("Imported signal differs from source excerpt")
            print(f"Imported and verified {gesture}: samples [{start}, {end}), recording {recording['id']}")
    print(f"Receipt: {args.receipt}. No training or test manifest created.")


if __name__ == "__main__":
    main()
