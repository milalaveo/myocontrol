CREATE TABLE recognition.desktop_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id uuid NOT NULL,
    client_id uuid NOT NULL,
    local_session_id uuid NOT NULL,
    model_version_id uuid NOT NULL,
    model_sha256 text NOT NULL CHECK (model_sha256 ~ '^[0-9a-f]{64}$'),
    feature_version text NOT NULL CHECK (length(btrim(feature_version)) > 0),
    mode text NOT NULL CHECK (mode IN ('live', 'replay')),
    recording_id uuid,
    status text NOT NULL CHECK (status IN ('completed', 'stopped', 'interrupted', 'failed')),
    started_at timestamptz NOT NULL,
    ended_at timestamptz NOT NULL,
    termination_reason text NOT NULL CHECK (length(btrim(termination_reason)) > 0),
    neutral_confirmed boolean NOT NULL,
    prediction_count bigint NOT NULL CHECK (prediction_count >= 0),
    processing_p95_ms double precision CHECK (processing_p95_ms >= 0 AND processing_p95_ms < 'Infinity'::float8),
    display_p95_ms double precision CHECK (display_p95_ms >= 0 AND display_p95_ms < 'Infinity'::float8),
    timing_scope text NOT NULL CHECK (length(btrim(timing_scope)) > 0),
    payload_sha256 text NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    received_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (operator_id, client_id, local_session_id),
    CHECK (ended_at >= started_at),
    CHECK (mode <> 'replay' OR recording_id IS NOT NULL)
);
CREATE INDEX desktop_sessions_operator_time ON recognition.desktop_sessions(operator_id, started_at DESC);
CREATE INDEX desktop_sessions_model ON recognition.desktop_sessions(model_version_id);
CREATE FUNCTION recognition.guard_desktop_session() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Published desktop session reports are immutable';
END $$;
CREATE TRIGGER immutable_desktop_session BEFORE UPDATE OR DELETE ON recognition.desktop_sessions
FOR EACH ROW EXECUTE FUNCTION recognition.guard_desktop_session();
COMMENT ON TABLE recognition.desktop_sessions IS 'Terminal synchronized summaries only; local active sessions do not require cloud availability. Model, identity and recording references are validated through owning APIs.';
COMMENT ON COLUMN recognition.desktop_sessions.neutral_confirmed IS 'Recorded evidence, not an invented guarantee. False records an unconfirmed/failed neutral transition for incident review; runtime acceptance still requires neutral behaviour.';
