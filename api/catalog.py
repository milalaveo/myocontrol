"""Operation semantics and application errors added to generated type schemas."""

DATA = {
    "POST /v1/participants": (
        "Create a pseudonymous research participant",
        "Operator accounts and research participants are different identities.",
        {409: "Pseudonym already exists"},
    ),
    "GET /v1/participants": (
        "List participants",
        "Offset pagination; limit 1–100 (default 50).",
        {},
    ),
    "GET /v1/participants/{participant_id}": (
        "Read a participant",
        "Returns its pseudonym, not operator credentials.",
        {404: "Participant not found"},
    ),
    "POST /v1/recordings": (
        "Store a four-channel recording",
        "1–10,000 finite four-value samples. SHA-256 identifies the stored JSON artifact; this engineering upload does not establish measured-data provenance.",
        {404: "Participant not found"},
    ),
    "GET /v1/recordings": (
        "List recordings",
        "Optional participant filter with limit/offset pagination.",
        {},
    ),
    "GET /v1/recordings/{recording_id}": (
        "Read recording metadata",
        "Returns metadata and the stored artifact digest.",
        {404: "Recording not found"},
    ),
    "GET /v1/recordings/{recording_id}/signal": (
        "Read a recording signal",
        "Returns original stored samples; no display downsampling is applied.",
        {404: "Recording not found", 503: "Signal artifact missing or invalid"},
    ),
    "POST /v1/synthetic-splits": (
        "Create an immutable synthetic split",
        "Distinct full-recording source/test inputs. This is an engineering check, not a complete research leakage policy.",
        {404: "Recording not found", 409: "Source and test recordings overlap"},
    ),
    "GET /v1/synthetic-splits/{split_id}": (
        "Read a synthetic split",
        "Returns the immutable recording IDs and checksum.",
        {404: "Split not found"},
    ),
    "POST /v1/protocols": (
        "Create a protocol version",
        "Gesture codes are unique and must include rest.",
        {
            404: "Referenced record not found",
            409: "Operation conflicts with split constraints",
        },
    ),
    "POST /v1/segments": (
        "Create a labelled segment",
        "Sample coordinates are half-open [start_sample, end_sample); recording and bounds are checked transactionally.",
        {
            404: "Referenced record not found",
            409: "Operation conflicts with split constraints",
        },
    ),
    "POST /v1/research-manifests": (
        "Create a draft research manifest",
        "A manifest references one protocol version. Membership can be edited only while draft.",
        {
            404: "Referenced record not found",
            409: "Operation conflicts with split constraints",
        },
    ),
    "POST /v1/research-manifests/{manifest_id}/participants": (
        "Assign a participant to a manifest",
        "Source, development and target membership must obey the database split constraints.",
        {
            404: "Referenced record not found",
            409: "Operation conflicts with split constraints",
        },
    ),
    "POST /v1/research-manifests/{manifest_id}/units": (
        "Add a labelled unit to a manifest",
        "A unit binds a segment, participant category and fit/evaluation role. Test data must not be used for fitting.",
        {
            404: "Referenced record not found",
            409: "Operation conflicts with split constraints",
        },
    ),
    "POST /v1/research-manifests/{manifest_id}/freeze": (
        "Freeze a research manifest",
        "Validates membership, computes the checksum and makes its research inputs immutable.",
        {
            404: "Draft manifest not found",
            409: "Operation conflicts with split constraints",
        },
    ),
    "GET /v1/research-manifests/{manifest_id}": (
        "Read a research manifest",
        "Returns draft or frozen metadata; draft checksum is null.",
        {404: "Manifest not found"},
    ),
    "GET /v1/research-manifests/{manifest_id}/snapshot": (
        "Read frozen experiment inputs",
        "Returns protocol and ordered labelled units with recording digests. It does not contain signal arrays; fetch the referenced recording signals separately.",
        {404: "Frozen manifest not found"},
    ),
    "POST /v1/calibration-subsets": (
        "Create a calibration subset",
        "Declares a target participant, selection version and per-gesture budget against a manifest. No model adaptation is executed here.",
        {
            404: "Referenced record not found",
            409: "Operation conflicts with split constraints",
        },
    ),
    "POST /v1/calibration-subsets/{subset_id}/items": (
        "Add a calibration unit",
        "Only compatible target-calibration membership can be selected; target-test units cannot enter calibration.",
        {
            404: "Referenced record not found",
            409: "Operation conflicts with split constraints",
        },
    ),
    "POST /v1/calibration-subsets/{subset_id}/freeze": (
        "Freeze calibration membership",
        "Validates the per-gesture selection and makes it immutable; this endpoint does not fit classifier weights.",
        {
            404: "Draft calibration subset not found",
            409: "Operation conflicts with split constraints",
        },
    ),
    "GET /v1/calibration-subsets/{subset_id}": (
        "Read calibration membership and duration",
        "Returns selected unit IDs and unique seconds by gesture. Null or missing observations must not be interpreted as zero error.",
        {404: "Calibration subset not found"},
    ),
}

ML = {
    "POST /v1/synthetic-signal-summary-jobs": (
        "Compute a synthetic signal summary",
        "Development integration check, completed synchronously. HTTP 201 persists either a succeeded or failed job; inspect status/error.",
        {},
    ),
    "GET /v1/synthetic-signal-summary-jobs/{job_id}": (
        "Read a signal-summary job",
        "Job failure is represented by status/error in the response, not a successful scientific result.",
        {404: "Job not found"},
    ),
    "POST /v1/source-lda-experiments": (
        "Queue a development source-only LDA experiment",
        "HTTP 202 means accepted, not trained. The separate single-host development worker consumes this legacy queue. Optional Idempotency-Key reuses an identical submission; a changed input is a conflict. This is not the remote workstation API.",
        {
            409: "Idempotency key belongs to a different request",
            422: "Invalid idempotency key",
        },
    ),
    "GET /v1/source-lda-experiments/{run_id}": (
        "Read an LDA experiment",
        "Poll queued/running until succeeded, failed or interrupted. Models/metrics remain null until successful processing. Synthetic scores do not measure real EMG quality.",
        {404: "Experiment not found"},
    ),
    "GET /v1/source-lda-experiments/{run_id}/model": (
        "Download a published LDA artifact",
        "Exact stored JSON bytes. Verify SHA-256 against model_checksum from the run (or X-Artifact-SHA256); do not reserialize before hashing. Coefficients in documentation examples are illustrative.",
        {404: "Published model not found"},
    ),
    "GET /v1/registry/{collection}": (
        "List an operator-owned registry collection",
        "Internal gateway-only API; collection is runs, models or results. Response is RunPage, ModelPage or ResultPage respectively. Queued metadata do not execute training.",
        {
            401: "Trusted gateway context required",
            404: "Collection not found",
            503: "Cloud registry is not configured",
        },
    ),
    "GET /v1/registry/{collection}/{item_id}": (
        "Read an operator-owned registry record",
        "Internal gateway-only API; run/model/result detail matches the selected collection. Foreign records return 404. Result detail includes actual/predicted confusion counts.",
        {
            401: "Trusted gateway context required",
            404: "Registry item not found",
            503: "Cloud registry is not configured",
        },
    ),
}

RECOGNITION = {
    "POST /v1/replay-sessions": (
        "Compute a development recording replay",
        "Synchronous legacy replay, not live SDK acquisition. HTTP 201 persists either succeeded predictions or a failed session with neutral command; inspect status/error. Processing p95 excludes buffering and rendering.",
        {},
    ),
    "GET /v1/replay-sessions/{session_id}": (
        "Read a replay session",
        "Returns persisted predictions or the explicit neutral failure result.",
        {404: "Replay session not found"},
    ),
    "GET /v1/available-models/{model_run_id}": (
        "Read model-event receipt",
        "Confirms that Recognition consumed ModelPublished. It is not an artifact download or model-quality approval.",
        {404: "Model event not received"},
    ),
}

GATEWAY = {
    "POST /auth/v1/sessions": (
        "Sign in an operator",
        "Returns an opaque web bearer session valid for eight hours. Accounts are created with the administrative CLI, not public registration. Incorrect, unknown and disabled accounts receive the same error.",
        {401: "Invalid email or password", 503: "Operator access is not configured"},
    ),
    "GET /auth/v1/me": (
        "Read the authenticated operator",
        "Validates session expiry/revocation, operator state and client state on every request.",
        {401: "Session expired or revoked", 503: "Operator access unavailable"},
    ),
    "DELETE /auth/v1/sessions/current": (
        "Revoke the current session",
        "HTTP 204 has no body. A second request with the revoked token receives 401.",
        {401: "Session expired or revoked", 503: "Operator access unavailable"},
    ),
    "POST /auth/v1/clients": (
        "Register a local client and issue its scoped token",
        "Requires a web session and operator/administrator role. Kind is desktop or training_worker. Token expires after thirty days and is returned only once. This provisions access; remote job execution/synchronization is not implemented.",
        {
            401: "Session expired or revoked",
            403: "Reviewer access is read-only",
            422: "Name and platform must not be blank",
            503: "Operator access unavailable",
        },
    ),
    "GET /auth/v1/clients": (
        "List your registered clients",
        "Requires a web session; credential digests and raw tokens are excluded.",
        {
            401: "Session expired or revoked",
            403: "Web session required",
            503: "Operator access unavailable",
        },
    ),
    "DELETE /auth/v1/clients/{client_id}": (
        "Revoke your registered client",
        "Requires a web session. Revocation immediately invalidates that client's sessions and is irreversible; a foreign client returns 404.",
        {
            401: "Session expired or revoked",
            403: "Web session required",
            404: "Client not found",
            503: "Operator access unavailable",
        },
    ),
    "GET /cloud/v1/{collection}": (
        "List your cloud registry",
        "Bearer-authenticated owner-filtered collection: runs, models or results. limit 1–100, offset >= 0. Empty collections return items=[] and next_offset=null. Legacy synthetic LDA runs are not automatically backfilled.",
        {
            401: "Session expired or revoked",
            404: "Collection not found",
            502: "Registry unavailable",
            503: "Cloud registry is not configured",
            504: "Registry request timed out",
        },
    ),
    "GET /cloud/v1/{collection}/{item_id}": (
        "Read your cloud registry record",
        "Bearer-authenticated detail. No lease digests, raw storage paths or foreign records are exposed. Result details include confusion counts.",
        {
            401: "Session expired or revoked",
            404: "Registry item not found",
            502: "Registry unavailable",
            503: "Cloud registry is not configured",
            504: "Registry request timed out",
        },
    ),
}

DATA.update(
    {
        "POST /v1/client-recordings": (
            "Publish a desktop recording part",
            "Private gateway-only operation. Canonical payload hash and operator/local UUID make retries idempotent, including after desktop client rotation. Parts contain at most 10,000 samples; channel widths are preserved. Source checksum is a client attestation, not independent proof of measurement.",
            {
                401: "Trusted desktop gateway context required",
                403: "Desktop client context required for publication",
                409: "Local recording identity conflicts with a previous publication",
            },
        ),
        "GET /v1/client-recordings": (
            "List an operator's desktop recording parts",
            "Private gateway-only operation. Ownership is selected exclusively from the trusted gateway context. Paginated by receipt time and UUID.",
            {401: "Trusted desktop gateway context required"},
        ),
        "GET /v1/client-recordings/{recording_id}/signal": (
            "Download owned samples",
            "Private gateway-only operation. Returns the exact stored samples and ordered channel mapping after verifying the artifact digest.",
            {
                401: "Trusted desktop gateway context required",
                404: "Recording not found",
                503: "Signal artifact missing or invalid",
            },
        ),
    }
)
DATA["GET /v1/recordings/{recording_id}/signal"][2][
    409
] = "Legacy signal endpoint requires four channels; use the owned cloud signal endpoint"
for method, suffix, summary in (
    ("POST", "", "Publish a local recording part"),
    ("GET", "", "List your published recording parts"),
    ("GET", "/{recording_id}/signal", "Download your published signal"),
):
    errors = {
        401: "Session expired or revoked",
        502: "Recording service unavailable",
        503: "Desktop publication is not configured",
        504: "Recording service timed out",
    }
    if method == "POST":
        errors.update(
            {
                403: "Desktop client session required for recording publication",
                409: "Local recording identity conflicts with a previous publication",
                413: "Request body is too large",
            }
        )
    if suffix:
        errors[404] = "Recording not found"
    GATEWAY[method + " /cloud/v1/recordings" + suffix] = (
        summary,
        "Bearer-authenticated desktop synchronization. The gateway derives operator and client identity from the access session and replaces incoming identity headers. Publishing requires a desktop session and a non-reviewer operator. Samples retain their actual channel count and original half-open coordinates; same identity with different content returns 409.",
        errors,
    )

CATALOG = {"data": DATA, "ml": ML, "recognition": RECOGNITION, "gateway": GATEWAY}
