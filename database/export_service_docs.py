"""Export the physical dictionary from a migrated review DB, without row data."""
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
if (ROOT/'.deps').exists():sys.path.insert(0,str(ROOT/'.deps'))
import psycopg

MEANINGS={
 'id':'Stable UUID primary identifier.', 'operator_id':'Cloud operator reference; external to non-identity services, API-authorized.',
 'email':'Normalized unique account email.', 'display_name':'Operator-facing account label.',
 'password_hash':'Encoded Argon2id password hash; never a plaintext password.',
 'role':'Application access role; separate from PostgreSQL service roles.',
 'state':'Lifecycle/publication state constrained by CHECKs and triggers.',
 'created_at':'Database creation timestamp.', 'updated_at':'Last account update timestamp maintained by trigger.',
 'kind':'Entity/client/operation category, constrained to supported values.', 'name':'Readable label.',
 'platform':'Registered client OS/architecture identity.', 'client_id':'Registered client identity; external outside identity service.',
 'token_sha256':'Digest of high-entropy token; raw token is not stored.', 'scope':'Web/desktop/worker access scope.',
 'issued_at':'Access-session issue time.', 'expires_at':'Access-session expiry time.', 'revoked_at':'Revocation time, immutable after revocation.',
 'channel_count':'Actual stored sample width (1-6), default four; no implicit channel padding.',
 'recording_id':'Recording reference; FK inside Data & Protocol, external in Recognition.',
 'source_kind':'Synthetic fixture, dataset or device origin.', 'source_name':'Origin dataset/device family.',
 'source_version':'Origin version; not overwritten by a later import.', 'source_participant_key':'Participant identifier within the declared source.',
 'original_signal_key':'Stable identity within source namespace; ingestion validates equivalence.',
 'original_sha256':'Original artifact checksum attestation.', 'original_start_sample':'Inclusive original-coordinate start.',
 'original_end_sample':'Exclusive original-coordinate end.', 'channel_map':'Ordered source-channel mapping; ingestion validates transformation/contract.',
 'units':'Declared source units, explicitly unspecified when unknown.', 'identity_method_version':'Version of source-identity resolution method.',
 'local_recording_id':'Stable desktop recording UUID for idempotent publication.',
 'payload_sha256':'Publication payload digest, verified/canonicalized by trusted API.',
 'received_at':'Cloud receipt time.', 'storage_key':'Unique controlled storage identifier, not a public URL.',
 'sha256':'Expected artifact SHA-256 digest.', 'size_bytes':'Artifact size in bytes.', 'media_type':'Artifact content type.',
 'verified_at':'Trusted service byte-verification attestation time; PostgreSQL cannot inspect the file.',
 'submission_key':'Operator-scoped stable submission/idempotency key.', 'retry_of_id':'Previous failed/interrupted run; retries create new IDs.',
 'family':'LDA, SVM or MLP family.', 'condition':'Source-only, personalised or target-only learning condition.',
 'execution_location':'Local workstation or desktop; general source training is workstation-only.',
 'manifest_id':'Frozen research manifest ID; external Data & Protocol reference in ML.',
 'manifest_sha256':'Frozen manifest checksum used by this run.', 'target_participant_id':'External target participant identity.',
 'calibration_subset_id':'External frozen calibration selection; required for calibrated conditions.',
 'parent_model_id':'Published compatible source model used for personalisation.',
 'evaluated_model_id':'Published model selected by an evaluation run.',
 'feature_contract':'Versioned signal/feature contract JSON object.', 'input_snapshot':'Immutable input membership/provenance snapshot JSON.',
 'parameters':'Versioned algorithm-specific parameters JSON.', 'seed':'Recorded random seed.',
 'software_version':'Recorded implementation/environment version.', 'status':'Run/session state constrained by CHECKs/transitions.',
 'worker_client_id':'External identity of the worker/desktop executing the attempt.',
 'lease_sha256':'Fencing digest for the worker lease, excluded from reviewer views.',
 'started_at':'Operation start timestamp.', 'heartbeat_at':'Latest worker heartbeat timestamp.',
 'lease_expires_at':'Worker lease expiry timestamp.', 'completed_at':'Terminal experiment timestamp.',
 'error':'Failure/interruption reason.', 'run_id':'Producing/evaluation run reference.',
 'artifact_id':'Verified artifact registry reference.', 'adaptation_method':'Advertised adaptation algorithm and required package material.',
 'published_at':'Immutable model publication time.', 'model_id':'Registered model reference.',
 'code':'Canonical gesture code, including rest.', 'position':'Class order within a model.',
 'purpose':'Configuration/source-statistics/source-pool/replay-pool package role.',
 'accuracy':'Fraction correct; checked against full confusion counts at evaluation completion.',
 'macro_f1':'Mean per-class F1 over the complete model class set; checked arithmetically.',
 'rest_false_activation_rate':'Rest windows predicted non-rest / all rest windows; NULL if no rest windows.',
 'rest_missing_reason':'Explicit reason for an unavailable rest metric.', 'evaluation_id':'Evaluation owning this confusion cell.',
 'actual_class':'Ground-truth class FK into the model mapping.', 'predicted_class':'Predicted class FK into the model mapping.',
 'count':'Nonnegative window count for this class pair.', 'local_session_id':'Stable desktop session identity for deduplication.',
 'model_version_id':'External ML model version reference.', 'model_sha256':'Checksum of the model actually used.',
 'feature_version':'Signal/feature specification identifier.', 'mode':'Live or recorded replay.',
 'ended_at':'Terminal local session timestamp.', 'termination_reason':'Reported stop/failure/interruption cause.',
 'neutral_confirmed':'Actual neutral-transition evidence; false is retained for incident review.',
 'prediction_count':'Number of reported predictions.', 'processing_p95_ms':'Measured processing-only p95 in milliseconds, if available.',
 'display_p95_ms':'Measured display/end-to-end p95 in milliseconds, if available.',
 'timing_scope':'Explicit timing measurement boundary.',
 'pseudonym':'Pseudonymous research participant code, not an application account.',
 'sample_rate_hz':'Signal sampling frequency in hertz.', 'sample_count':'Number of samples in the recording.',
 'artifact_sha256':'Signal artifact checksum.', 'gesture_codes':'Protocol class set including rest.',
 'version':'Positive immutable version number within its name.', 'protocol_id':'Protocol version FK.',
 'checksum':'Frozen manifest/model checksum.', 'frozen_at':'Manifest freeze timestamp.',
 'participant_id':'Research participant reference.', 'category':'Source/development/target participant allocation.',
 'segment_id':'Selected labelled segment FK.', 'gesture_code':'Canonical segment gesture.',
 'repetition_key':'Repeat identity within a recording.', 'start_sample':'Inclusive local signal coordinate.',
 'end_sample':'Exclusive local signal coordinate.', 'subset_id':'Calibration subset FK.', 'unit_id':'Eligible manifest unit FK.',
 'selection_version':'Nested calibration series identifier.', 'budget_per_gesture':'Required distinct repeat count per class.',
 'source_recording_id':'Source recording FK for legacy synthetic split.', 'test_recording_id':'Test recording FK for legacy synthetic split.',
 'split_id':'External legacy synthetic split reference.', 'model':'Legacy LDA model JSON.', 'metrics':'Legacy computed metric JSON.',
 'snapshot':'Legacy frozen input snapshot.', 'model_checksum':'Legacy model JSON checksum.',
 'idempotency_key':'Legacy submission deduplication key.', 'correlation_id':'Request/job tracing identifier.',
 'trace_context':'Stored OpenTelemetry trace context.', 'event_type':'Publication event type.',
 'payload':'Versioned domain-event payload.', 'published_at':'Publication timestamp.',
 'last_error':'Last event-delivery error.', 'attempts':'Delivery attempt count.', 'next_attempt_at':'Next retry time.',
 'model_run_id':'External legacy source-LDA run reference.', 'result':'Legacy replay/summary output JSON.',
}

def esc(value):return str(value or '').replace('|','&#124;').replace('\n',' ')

def main():
 dsn=os.environ.get('TEST_DATABASE_URL')
 if not dsn:raise SystemExit('Set TEST_DATABASE_URL to a migrated review database')
 schemas=('identity','data_protocol','ml_experiments','recognition')
 with psycopg.connect(dsn) as c:
  c.read_only=True
  version=c.execute('SHOW server_version').fetchone()[0]
  tables=c.execute("SELECT table_schema,table_name FROM information_schema.tables WHERE table_schema=ANY(%s) AND table_type='BASE TABLE' ORDER BY 1,2",(list(schemas),)).fetchall()
  lines=['# Service Database — Generated Physical Dictionary','',
    'Generated from the migrated service schemas. No account/recording/result row data is exported.',
    f'Validated source server: PostgreSQL {version}. Target CI uses PostgreSQL 18.',
    '',f'**Business tables:** {len(tables)}. `public.service_schema_migrations` is bookkeeping and is listed separately in the main dictionary.',
    '', 'Semantic overview: [logical model](SERVICE_MODEL.md). Review workflow: [teacher README](README_TEACHER.md).',
    '', 'External operator/client/manifest/participant UUIDs in other service domains intentionally have no cross-schema FK. The owning API validates them; database roles are not per-operator HTTP authorization.',
    '', 'JSON contracts require API/runtime schema validation in addition to the structural database checks shown below.']
  for schema,table in tables:
   lines+=['',f'## `{schema}.{table}`','', '| Column | PostgreSQL type | Nullable | Default | Meaning |','| --- | --- | --- | --- | --- |']
   cols=c.execute("""SELECT a.attname,format_type(a.atttypid,a.atttypmod),NOT a.attnotnull,pg_get_expr(d.adbin,d.adrelid)
     FROM pg_attribute a JOIN pg_class t ON t.oid=a.attrelid JOIN pg_namespace n ON n.oid=t.relnamespace
     LEFT JOIN pg_attrdef d ON d.adrelid=t.oid AND d.adnum=a.attnum
     WHERE n.nspname=%s AND t.relname=%s AND a.attnum>0 AND NOT a.attisdropped ORDER BY a.attnum""",(schema,table)).fetchall()
   for name,typ,nullable,default in cols:
    meaning=MEANINGS.get(name,'Service-specific persisted value; see the existing dictionary and migration contract.')
    lines.append(f'| `{name}` | `{typ}` | {"YES" if nullable else "NO"} | {esc(default)} | {meaning} |')
   constraints=c.execute("""SELECT conname,pg_get_constraintdef(x.oid) FROM pg_constraint x
     JOIN pg_class t ON t.oid=x.conrelid JOIN pg_namespace n ON n.oid=t.relnamespace
     WHERE n.nspname=%s AND t.relname=%s ORDER BY conname""",(schema,table)).fetchall()
   lines+=['','### Keys and constraints','']
   for name,definition in constraints:lines.append(f'- `{name}`: `{esc(definition)}`')
   indexes=c.execute('SELECT indexdef FROM pg_indexes WHERE schemaname=%s AND tablename=%s ORDER BY indexname',(schema,table)).fetchall()
   lines+=['','### Indexes','']+[f'- `{esc(x[0])}`' for x in indexes]
  lines+=['','## Views and trigger enforcement','']
  for schema,name in c.execute('SELECT schemaname,viewname FROM pg_views WHERE schemaname=ANY(%s) ORDER BY 1,2',(list(schemas),)):
   lines.append(f'- `{schema}.{name}`')
  lines+=['','Triggers enforce immutable publication, class/package membership, run leases, atomic successful output and confusion-matrix metric consistency. See the migration SQL for executable definitions; SQL CHECK text alone does not show trigger behaviour.','']
  (ROOT/'database/SERVICE_DATA_DICTIONARY.md').write_text('\n'.join(lines),encoding='utf-8')
  print(f'Exported {len(tables)} tables and all their columns/constraints/indexes')

if __name__=='__main__':main()
