# Tutorial: integrate the development research pipeline

## Goal and boundary

Create synthetic labelled recordings, freeze a source/target manifest, submit an idempotent LDA job, verify its artifact bytes and replay a target recording. This is an engineering integration exercise, **not** a real-EMG experiment or a claim about recognition quality.

Complete [Getting Started](../GETTING_STARTED.md). The development `experiment-worker` must be running in the same local Compose environment. Use the separate development Basic credentials, not an operator bearer token. No external workstation/cloud job API is implied by this tutorial.

Run the complete example from the repository root:

```powershell
python api/tutorial.py synthetic --env-file .env
```

`--env-file` reads only the development credentials for use; nothing is printed or sent to a third-party service. Alternatively omit it and enter credentials when prompted. Each run creates uniquely named synthetic research records in the selected database; use a disposable development/review database for repeated assessment runs.

The [executable source](../tutorial.py) implements the HTTP steps below with Python's standard library. Replace all placeholder IDs with the actual preceding responses. OpenAPI includes a full schema and an example for every operation.

## 1. Create separate source and target participants

Send these using Basic authentication:

```http
POST /data/v1/participants
Content-Type: application/json

{"pseudonym":"tutorial_source_UNIQUE_SUFFIX"}
```

Expected **201**: `{"id":"SOURCE_PARTICIPANT_ID","pseudonym":"tutorial_source_UNIQUE_SUFFIX"}`.

Repeat for `tutorial_target_UNIQUE_SUFFIX`, retaining the distinct target ID. Duplicate pseudonyms return **409**. Participant IDs are independent of operator IDs.

## 2. Create the protocol and draft manifest

`POST /data/v1/protocols`:

```json
{"name":"tutorial_UNIQUE_SUFFIX","version":1,"gesture_codes":["rest","fist"]}
```

Expected **201** includes `id`, `name`, `version`, `gesture_codes`. Retain `PROTOCOL_ID`.

`POST /data/v1/research-manifests`:

```json
{"protocol_id":"PROTOCOL_ID","name":"tutorial_UNIQUE_SUFFIX","version":1}
```

Expected **201** includes `id`, `protocol_id`, `state:"draft"`, `checksum:null`. Retain `MANIFEST_ID`.

## 3. Assign participant roles before creating windows

For `POST /data/v1/research-manifests/{MANIFEST_ID}/participants`, submit:

```json
{"participant_id":"SOURCE_PARTICIPANT_ID","category":"source"}
```

Repeat with the target ID and `category:"target"`. Each returns **201** with the manifest ID and assignment. Invalid/overlapping membership is rejected; do not combine source and target identities.

## 4. Create four synthetic labelled recordings and units

The executable tutorial generates 400 four-channel samples at 1000 Hz for each row:

| Participant | Gesture | Signal base | Unit role |
| --- | --- | --- | --- |
| Source | rest | 1.0 | source_train |
| Source | fist | 10.0 | source_train |
| Target | rest | 1.1 | target_test |
| Target | fist | 10.1 | target_test |

For sample `i` and channel `c`, the value is `base + (i % 7) * 0.01 + c * 0.02`. This creates explicit, distinct synthetic arrays with a reproducible shape; it is not an EMG simulator or a dataset substitute.

For each row:

1. `POST /data/v1/recordings` with `{participant_id,sample_rate_hz:1000,samples:[...]}`. Expected **201** with recording ID, `sample_count:400` and artifact SHA-256.
2. `POST /data/v1/segments` with `{recording_id,gesture_code,repetition_key:"one",start_sample:0,end_sample:400}`. Expected **201** with segment ID. Sample bounds are half-open.
3. `POST /data/v1/research-manifests/{MANIFEST_ID}/units` with `{participant_id,category,segment_id,role}` from the table. Expected **201** with unit ID and membership.

The tutorial fits only `source_train`. Target-test samples are reserved for evaluation. Calibration/subset endpoints exist for membership management but no adaptation is executed by this tutorial.

## 5. Freeze and verify the snapshot

Send `POST /data/v1/research-manifests/{MANIFEST_ID}/freeze` with no body. Expected **200**, `state:"frozen"` and non-null checksum.

Read:

```http
GET /data/v1/research-manifests/{MANIFEST_ID}
GET /data/v1/research-manifests/{MANIFEST_ID}/snapshot
```

Expected **200**. The snapshot contains the same checksum, protocol information and four ordered units with recording IDs/digests. Published inputs are immutable; create another manifest version to change them.

## 6. Submit once, repeat safely and poll

Send `POST /experiments/v1/source-lda-experiments` with `Idempotency-Key: tutorial-UNIQUE_SUFFIX`:

```json
{"manifest_id":"MANIFEST_ID","target_participant_id":"TARGET_PARTICIPANT_ID"}
```

Expected **202**, a `Location` header and an experiment response containing `id`, `status:"queued"`, and null model/metrics while work is pending. Repeat the exact request/key: it must return the same job ID. Reusing the key with different inputs returns **409**.

Poll `GET /experiments/v1/source-lda-experiments/{RUN_ID}` while status is `queued` or `running`. The executable tutorial waits up to 90 seconds. On success expect `status:"succeeded"`, the manifest checksum, model checksum, model and metrics. On `failed` or `interrupted`, inspect `error`; do not report the job as successful just because HTTP GET returned 200.

If it stays queued, check `docker compose logs experiment-worker`. Do not submit duplicates to repair a worker configuration issue.

## 7. Verify exact model artifact bytes

`GET /experiments/v1/source-lda-experiments/{RUN_ID}/model` returns **200** JSON with `X-Artifact-SHA256`. Compute SHA-256 on the **raw response bytes** and compare it with both that header and `model_checksum` from the run. Do not parse and reserialize before hashing.

The tutorial asserts all three digests match. This verifies transport/storage consistency, not authenticity or scientific quality.

## 8. Compute and read a replay

Send `POST /recognition/v1/replay-sessions`:

```json
{"model_run_id":"RUN_ID","recording_id":"TARGET_FIST_RECORDING_ID"}
```

Expected **201** with `status:"succeeded"`, checksum and a result containing window predictions, `prediction_count`, `processing_p95_ms` and `timing_scope`. Read it back using `GET /recognition/v1/replay-sessions/{SESSION_ID}`; expected **200** with the same persisted session.

On dependency/incompatible-input failure, the created session has `status:"failed"`, an `error` and a neutral command. Processing p95 measures feature extraction/prediction only. This recorded replay does not validate live acquisition latency.

Expected executable output:

```text
Created and froze a four-unit synthetic research manifest.
LDA succeeded; artifact SHA-256 verified; replay predictions=3.
Synthetic engineering evidence only. These legacy runs do not populate the cloud generic registry.
```

The synthetic records remain for inspection. They belong to the private development workflow, not the operator-owned generic cloud registry. See [API boundaries and errors](../ERRORS.md) for retry, authorization and missing-data conventions.
