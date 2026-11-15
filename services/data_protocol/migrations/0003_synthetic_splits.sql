-- A limited full-recording source/test split for the synthetic vertical slice.
-- This does not replace the research split protocol in the legacy schema.
CREATE TABLE data_protocol.synthetic_splits (
    id uuid PRIMARY KEY,
    source_recording_id uuid NOT NULL REFERENCES data_protocol.recordings(id) ON DELETE RESTRICT,
    test_recording_id uuid NOT NULL REFERENCES data_protocol.recordings(id) ON DELETE RESTRICT,
    checksum varchar(64) NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
    CHECK (source_recording_id <> test_recording_id)
);

CREATE FUNCTION data_protocol.validate_synthetic_split() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE source_row data_protocol.recordings%ROWTYPE; test_row data_protocol.recordings%ROWTYPE;
BEGIN
    PERFORM id FROM data_protocol.recordings WHERE id IN (NEW.source_recording_id, NEW.test_recording_id) ORDER BY id FOR UPDATE;
    SELECT * INTO source_row FROM data_protocol.recordings WHERE id = NEW.source_recording_id;
    SELECT * INTO test_row FROM data_protocol.recordings WHERE id = NEW.test_recording_id;
    IF source_row.id IS NULL OR test_row.id IS NULL THEN RAISE EXCEPTION 'Recording not found' USING ERRCODE = '23503'; END IF;
    IF source_row.participant_id = test_row.participant_id OR source_row.artifact_sha256 = test_row.artifact_sha256 THEN
        RAISE EXCEPTION 'Source and test recordings overlap' USING ERRCODE = '23514';
    END IF;
    NEW.checksum := encode(sha256(convert_to(jsonb_build_array(
        'synthetic-split-v1', NEW.id, source_row.id, source_row.participant_id, source_row.artifact_sha256,
        source_row.sample_rate_hz, source_row.sample_count, test_row.id, test_row.participant_id,
        test_row.artifact_sha256, test_row.sample_rate_hz, test_row.sample_count)::text, 'UTF8')), 'hex');
    RETURN NEW;
END $$;
CREATE TRIGGER validate_synthetic_split BEFORE INSERT ON data_protocol.synthetic_splits
FOR EACH ROW EXECUTE FUNCTION data_protocol.validate_synthetic_split();

CREATE FUNCTION data_protocol.guard_synthetic_split() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Frozen synthetic splits cannot be changed';
END $$;
CREATE TRIGGER guard_synthetic_split BEFORE UPDATE OR DELETE ON data_protocol.synthetic_splits
FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_synthetic_split();

CREATE FUNCTION data_protocol.guard_split_recording() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM data_protocol.synthetic_splits WHERE source_recording_id = OLD.id OR test_recording_id = OLD.id) THEN
        RAISE EXCEPTION 'Recording is referenced by a frozen split';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_split_recording BEFORE UPDATE OR DELETE ON data_protocol.recordings
FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_split_recording();
