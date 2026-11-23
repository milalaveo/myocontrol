-- Identity UUIDs are external service references validated by authenticated APIs.
CREATE TABLE data_protocol.recording_provenance (
    recording_id uuid PRIMARY KEY REFERENCES data_protocol.recordings(id) ON DELETE RESTRICT,
    operator_id uuid NOT NULL,
    source_kind text NOT NULL CHECK (source_kind IN ('synthetic', 'dataset', 'device')),
    source_name text NOT NULL CHECK (length(btrim(source_name)) > 0),
    source_version text NOT NULL CHECK (length(btrim(source_version)) > 0),
    source_participant_key text NOT NULL CHECK (length(btrim(source_participant_key)) > 0),
    original_signal_key text NOT NULL CHECK (length(btrim(original_signal_key)) > 0),
    original_sha256 text NOT NULL CHECK (original_sha256 ~ '^[0-9a-f]{64}$'),
    original_start_sample bigint NOT NULL CHECK (original_start_sample >= 0),
    original_end_sample bigint NOT NULL,
    channel_map jsonb NOT NULL CHECK (jsonb_typeof(channel_map) = 'array' AND jsonb_array_length(channel_map) > 0),
    units text NOT NULL CHECK (length(btrim(units)) > 0),
    identity_method_version text NOT NULL CHECK (length(btrim(identity_method_version)) > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (original_end_sample > original_start_sample)
);
CREATE INDEX recording_source_identity ON data_protocol.recording_provenance(source_name, source_version, original_signal_key);
CREATE INDEX recording_provenance_operator ON data_protocol.recording_provenance(operator_id);

CREATE TABLE data_protocol.client_publications (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id uuid NOT NULL,
    client_id uuid NOT NULL,
    local_recording_id uuid NOT NULL,
    recording_id uuid NOT NULL UNIQUE REFERENCES data_protocol.recordings(id) ON DELETE RESTRICT,
    payload_sha256 text NOT NULL CHECK (payload_sha256 ~ '^[0-9a-f]{64}$'),
    received_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (operator_id, client_id, local_recording_id)
);
CREATE FUNCTION data_protocol.guard_publication_metadata() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'Published source identity and receipts are immutable'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER immutable_recording_provenance BEFORE UPDATE OR DELETE ON data_protocol.recording_provenance
FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_publication_metadata();
CREATE TRIGGER immutable_client_publication BEFORE UPDATE OR DELETE ON data_protocol.client_publications
FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_publication_metadata();

-- Same local identity + changed payload is a conflict, not a silent overwrite.
CREATE FUNCTION data_protocol.register_client_recording(p_operator uuid, p_client uuid, p_local uuid, p_recording uuid, p_hash text)
RETURNS uuid LANGUAGE plpgsql AS $$
DECLARE receipt data_protocol.client_publications%ROWTYPE;
BEGIN
    INSERT INTO data_protocol.client_publications(operator_id, client_id, local_recording_id, recording_id, payload_sha256)
    VALUES (p_operator, p_client, p_local, p_recording, p_hash)
    ON CONFLICT (operator_id, client_id, local_recording_id) DO NOTHING;
    SELECT * INTO STRICT receipt FROM data_protocol.client_publications
    WHERE operator_id = p_operator AND client_id = p_client AND local_recording_id = p_local;
    IF (receipt.recording_id, receipt.payload_sha256) IS DISTINCT FROM (p_recording, p_hash) THEN
        RAISE EXCEPTION 'Client recording identity conflicts with an existing publication';
    END IF;
    RETURN receipt.id;
END $$;
COMMENT ON TABLE data_protocol.recording_provenance IS 'New publication metadata; legacy synthetic recordings are not retroactively asserted research-ready. Byte/identity and transformation validation belongs to ingestion.';
