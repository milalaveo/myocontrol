"""Synthetic documentation examples. None of these credentials or IDs are live."""


def uid(number):
    return f"00000000-0000-4000-8000-{number:012d}"


HASH = "a" * 64
TIME = "2026-11-24T10:00:00Z"
TOKEN = "example-only-not-a-valid-session-token-0000000000"
PARTICIPANT = {"id": uid(1), "pseudonym": "tutorial_source"}
SIGNAL = {"participant_id": uid(1), "sample_rate_hz": 1000, "samples": [[1, 2, 3, 4], [2, 3, 4, 5]]}
RECORDING = {
    "id": uid(2),
    "participant_id": uid(1),
    "sample_rate_hz": 1000,
    "sample_count": 2,
    "artifact_sha256": HASH,
}
PROTOCOL = {
    "id": uid(3),
    "name": "tutorial_protocol",
    "version": 1,
    "gesture_codes": ["rest", "fist"],
}
MANIFEST = {
    "id": uid(4),
    "name": "tutorial_manifest",
    "version": 1,
    "protocol_id": uid(3),
    "state": "draft",
    "checksum": None,
}
SEGMENT = {
    "id": uid(5),
    "recording_id": uid(2),
    "gesture_code": "rest",
    "repetition_key": "one",
    "start_sample": 0,
    "end_sample": 2,
}
ASSIGNMENT = {"manifest_id": uid(4), "participant_id": uid(1), "category": "source"}
UNIT = {**ASSIGNMENT, "id": uid(6), "segment_id": uid(5), "role": "source_train"}
CALIBRATION = {
    "id": uid(7),
    "manifest_id": uid(4),
    "participant_id": uid(8),
    "selection_version": "tutorial-v1",
    "budget_per_gesture": 1,
    "state": "draft",
}
FEATURES = {
    "version": "time-domain-4ch-v1",
    "channels": 4,
    "order": "channel-major",
    "features": ["mav", "rms", "waveform_length", "zero_crossings", "slope_sign_changes"],
    "window_ms": 200,
    "step_ms": 100,
    "zc_threshold": 0,
    "ssc_threshold": 0,
    "filter": "none",
    "sample_rate_hz": 1000,
    "fit_roles": ["source_train"],
}
MODEL = {
    "family": "lda",
    "solver": "lsqr",
    "shrinkage": "auto",
    "classes": ["fist", "rest"],
    "coefficients": [[0.1] * 20],
    "intercepts": [0.0],
    "feature_config": FEATURES,
    "sklearn_version": "1.6.1",
}
METRICS = {
    "accuracy": 1.0,
    "macro_f1": 1.0,
    "rest_false_activation_rate": 0.0,
    "rest_false_activation_missing_reason": None,
    "class_order": ["rest", "fist"],
    "confusion_matrix": [[3, 0], [0, 3]],
    "training_windows": 6,
    "test_windows": 6,
}
RUN = {
    "id": uid(9),
    "kind": "source_train",
    "family": "lda",
    "condition": "source_only",
    "execution_location": "local_workstation",
    "manifest_id": uid(4),
    "manifest_sha256": HASH,
    "target_participant_id": None,
    "calibration_subset_id": None,
    "parent_model_id": None,
    "evaluated_model_id": None,
    "feature_contract": {"version": "time-domain-4ch-v1", "channels": 4},
    "parameters": {},
    "seed": 1,
    "software_version": "tutorial-v1",
    "status": "queued",
    "created_at": TIME,
    "started_at": None,
    "heartbeat_at": None,
    "lease_expires_at": None,
    "completed_at": None,
    "error": None,
}
PUBLISHED = {
    "id": uid(10),
    "name": "Source LDA",
    "run_id": uid(9),
    "operator_id": uid(11),
    "family": "lda",
    "condition": "source_only",
    "parent_model_id": None,
    "calibration_subset_id": None,
    "manifest_id": uid(4),
    "manifest_sha256": HASH,
    "feature_contract": RUN["feature_contract"],
    "adaptation_method": "none",
    "sha256": HASH,
    "size_bytes": 1024,
    "published_at": TIME,
}
EVALUATION = {
    "id": uid(12),
    "model_id": uid(10),
    "run_id": uid(13),
    "family": "lda",
    "condition": "source_only",
    "manifest_id": uid(4),
    "manifest_sha256": HASH,
    "target_participant_id": uid(8),
    "calibration_subset_id": None,
    "feature_contract": RUN["feature_contract"],
    "seed": 1,
    "software_version": "tutorial-v1",
    "accuracy": 0.8,
    "macro_f1": 0.8,
    "rest_false_activation_rate": 0.2,
    "rest_missing_reason": None,
}
CONFUSION = [
    {"actual_class": a, "predicted_class": p, "count": 4 if a == p else 1}
    for a in ["rest", "fist"]
    for p in ["rest", "fist"]
]
OPERATOR = {"id": uid(11), "display_name": "Tutorial operator", "role": "operator"}
CLIENT = {
    "id": uid(14),
    "kind": "training_worker",
    "name": "Local workstation",
    "platform": "linux-x86_64",
    "state": "active",
    "created_at": TIME,
}

MODELS = {
    "HealthResponse": {"status": "live"},
    "Login": {"email": "operator@example.test", "password": "not-a-real-password"},
    "SessionResponse": {
        "access_token": TOKEN,
        "token_type": "bearer",
        "expires_at": "2026-11-24T18:00:00Z",
        "operator": OPERATOR,
    },
    "CurrentOperatorResponse": {
        "operator_id": uid(11),
        "display_name": "Tutorial operator",
        "role": "operator",
        "scope": "web",
        "client_id": None,
        "expires_at": "2026-11-24T18:00:00Z",
    },
    "ClientCreate": {k: CLIENT[k] for k in ["kind", "name", "platform"]},
    "ClientResponse": CLIENT,
    "ClientTokenResponse": {
        "client_id": uid(14),
        "access_token": TOKEN,
        "token_type": "bearer",
        "expires_at": "2026-12-24T10:00:00Z",
        "scope": "training_worker",
    },
    "ParticipantCreate": {"pseudonym": "tutorial_source"},
    "ParticipantResponse": PARTICIPANT,
    "RecordingCreate": SIGNAL,
    "RecordingResponse": RECORDING,
    "SyntheticSplitCreate": {"source_recording_id": uid(2), "test_recording_id": uid(15)},
    "SyntheticSplitResponse": {
        "id": uid(16),
        "source_recording_id": uid(2),
        "test_recording_id": uid(15),
        "checksum": HASH,
    },
    "ProtocolCreate": {k: PROTOCOL[k] for k in ["name", "version", "gesture_codes"]},
    "ProtocolResponse": PROTOCOL,
    "SegmentCreate": {k: v for k, v in SEGMENT.items() if k != "id"},
    "SegmentResponse": SEGMENT,
    "ManifestCreate": {k: MANIFEST[k] for k in ["protocol_id", "name", "version"]},
    "ManifestResponse": MANIFEST,
    "ParticipantAssignment": {k: ASSIGNMENT[k] for k in ["participant_id", "category"]},
    "ParticipantAssignmentResponse": ASSIGNMENT,
    "UnitCreate": {k: UNIT[k] for k in ["participant_id", "category", "segment_id", "role"]},
    "UnitResponse": UNIT,
    "SnapshotResponse": {
        **MANIFEST,
        "state": "frozen",
        "checksum": HASH,
        "protocol_name": PROTOCOL["name"],
        "protocol_version": 1,
        "gesture_codes": ["rest", "fist"],
        "units": [
            {
                **{k: v for k, v in UNIT.items() if k != "manifest_id"},
                **{k: v for k, v in SEGMENT.items() if k != "id"},
                "sample_rate_hz": 1000,
                "sample_count": 2,
                "artifact_sha256": HASH,
            }
        ],
    },
    "CalibrationCreate": {
        k: CALIBRATION[k]
        for k in ["manifest_id", "participant_id", "selection_version", "budget_per_gesture"]
    },
    "CalibrationResponse": CALIBRATION,
    "CalibrationItemCreate": {"unit_id": uid(6)},
    "CalibrationItemResponse": {"subset_id": uid(7), "unit_id": uid(6)},
    "CalibrationDetailResponse": {
        **CALIBRATION,
        "unit_ids": [uid(6)],
        "durations": [{"gesture_code": "rest", "unique_seconds": 0.2}],
    },
    "JobCreate": {"split_id": uid(16)},
    "JobResponse": {
        "id": uid(17),
        "split_id": uid(16),
        "status": "succeeded",
        "split_checksum": HASH,
        "result": {
            "kind": "synthetic_signal_summary",
            "sample_count": 2,
            "channel_means": [1.5, 2.5, 3.5, 4.5],
        },
        "error": None,
    },
    "ExperimentCreate": {"manifest_id": uid(4), "target_participant_id": uid(8)},
    "ExperimentResponse": {
        "id": uid(18),
        "manifest_id": uid(4),
        "target_participant_id": uid(8),
        "status": "queued",
        "manifest_checksum": None,
        "model": None,
        "model_checksum": None,
        "metrics": None,
        "error": None,
    },
    "LdaModel": MODEL,
    "RegistryRun": RUN,
    "PublishedModel": PUBLISHED,
    "EvaluationResult": EVALUATION,
    "EvaluationDetail": {**EVALUATION, "confusion_counts": CONFUSION},
    "RunPage": {"items": [RUN], "next_offset": None},
    "ModelPage": {"items": [PUBLISHED], "next_offset": None},
    "ResultPage": {"items": [EVALUATION], "next_offset": None},
    "ReplayCreate": {"model_run_id": uid(18), "recording_id": uid(2)},
    "ReplayResponse": {
        "id": uid(19),
        "model_run_id": uid(18),
        "recording_id": uid(2),
        "status": "succeeded",
        "model_checksum": HASH,
        "result": {
            "feature_version": "time-domain-4ch-v1",
            "predictions": [{"start_sample": 0, "gesture": "rest", "command": "neutral"}],
            "prediction_count": 1,
            "processing_p95_ms": 0.05,
            "timing_scope": "feature extraction and prediction only; excludes input buffering and rendering",
        },
        "error": None,
    },
    "AvailableModel": {"model_run_id": uid(18), "manifest_id": uid(4), "received_at": TIME},
}
