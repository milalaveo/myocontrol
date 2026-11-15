-- Initial provenance entities. Apply through Alembic, not manually, in managed environments.
CREATE SCHEMA myoprosthesis;

CREATE TABLE myoprosthesis.datasets (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL UNIQUE CHECK (length(trim(name)) > 0)
);

CREATE TABLE myoprosthesis.dataset_versions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dataset_id bigint NOT NULL REFERENCES myoprosthesis.datasets(id) ON DELETE RESTRICT,
    version text NOT NULL CHECK (length(trim(version)) > 0),
    usage_notes text,
    UNIQUE (dataset_id, version)
);

CREATE TABLE myoprosthesis.participants (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pseudonym text NOT NULL UNIQUE CHECK (length(trim(pseudonym)) > 0)
);

CREATE TABLE myoprosthesis.participant_source_ids (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    participant_id bigint NOT NULL REFERENCES myoprosthesis.participants(id) ON DELETE RESTRICT,
    dataset_version_id bigint NOT NULL REFERENCES myoprosthesis.dataset_versions(id) ON DELETE RESTRICT,
    source_id text NOT NULL CHECK (length(trim(source_id)) > 0),
    UNIQUE (dataset_version_id, source_id),
    UNIQUE (dataset_version_id, participant_id)
);

CREATE TABLE myoprosthesis.artifacts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    storage_namespace text NOT NULL CHECK (length(trim(storage_namespace)) > 0),
    storage_key text NOT NULL CHECK (length(trim(storage_key)) > 0),
    media_type text NOT NULL CHECK (length(trim(media_type)) > 0),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    sha256 char(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (storage_namespace, storage_key)
);

CREATE TABLE myoprosthesis.recording_sessions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    participant_id bigint NOT NULL REFERENCES myoprosthesis.participants(id) ON DELETE RESTRICT,
    dataset_version_id bigint REFERENCES myoprosthesis.dataset_versions(id) ON DELETE RESTRICT,
    mode text NOT NULL CHECK (mode IN ('import', 'live')),
    status text NOT NULL CHECK (status IN ('recording', 'completed', 'interrupted', 'failed')),
    started_at timestamptz NOT NULL,
    ended_at timestamptz,
    stop_reason text,
    CHECK ((mode = 'import' AND dataset_version_id IS NOT NULL) OR mode = 'live'),
    CHECK (ended_at IS NULL OR ended_at >= started_at),
    CHECK ((status = 'recording' AND ended_at IS NULL) OR (status <> 'recording' AND ended_at IS NOT NULL)),
    CHECK (status NOT IN ('interrupted', 'failed') OR (stop_reason IS NOT NULL AND length(trim(stop_reason)) > 0)),
    UNIQUE (id, participant_id)
);

CREATE TABLE myoprosthesis.recordings (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id bigint NOT NULL REFERENCES myoprosthesis.recording_sessions(id) ON DELETE RESTRICT,
    artifact_id bigint NOT NULL REFERENCES myoprosthesis.artifacts(id) ON DELETE RESTRICT,
    source_external_key text,
    sample_rate_hz numeric NOT NULL CHECK (sample_rate_hz > 0),
    sample_count bigint NOT NULL CHECK (sample_count > 0),
    UNIQUE (session_id, source_external_key)
);

CREATE TABLE myoprosthesis.recording_channels (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    recording_id bigint NOT NULL REFERENCES myoprosthesis.recordings(id) ON DELETE RESTRICT,
    position integer NOT NULL CHECK (position >= 0),
    source_channel_id text NOT NULL CHECK (length(trim(source_channel_id)) > 0),
    electrode_description text,
    UNIQUE (recording_id, position),
    UNIQUE (recording_id, source_channel_id)
);
