-- Participant categories and data roles are assigned before windowing.
CREATE TABLE data_protocol.protocol_versions (
    id uuid PRIMARY KEY,
    name varchar(120) NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    gesture_codes text[] NOT NULL CHECK (cardinality(gesture_codes) > 0 AND 'rest' = ANY(gesture_codes)),
    UNIQUE (name, version)
);

CREATE TABLE data_protocol.labelled_segments (
    id uuid PRIMARY KEY,
    recording_id uuid NOT NULL REFERENCES data_protocol.recordings(id) ON DELETE RESTRICT,
    gesture_code text NOT NULL CHECK (gesture_code ~ '^[A-Za-z0-9_-]{1,100}$'),
    repetition_key text NOT NULL CHECK (length(trim(repetition_key)) > 0),
    start_sample bigint NOT NULL CHECK (start_sample >= 0),
    end_sample bigint NOT NULL CHECK (end_sample > start_sample),
    UNIQUE (recording_id, repetition_key)
);

CREATE TABLE data_protocol.research_manifests (
    id uuid PRIMARY KEY,
    protocol_id uuid NOT NULL REFERENCES data_protocol.protocol_versions(id) ON DELETE RESTRICT,
    name varchar(120) NOT NULL,
    version integer NOT NULL CHECK (version > 0),
    state text NOT NULL DEFAULT 'draft' CHECK (state IN ('draft', 'frozen')),
    checksum varchar(64),
    frozen_at timestamptz,
    CHECK ((state = 'draft' AND checksum IS NULL AND frozen_at IS NULL) OR
           (state = 'frozen' AND checksum IS NOT NULL AND checksum ~ '^[0-9a-f]{64}$' AND frozen_at IS NOT NULL)),
    UNIQUE (name, version)
);

CREATE TABLE data_protocol.manifest_participants (
    manifest_id uuid NOT NULL REFERENCES data_protocol.research_manifests(id) ON DELETE RESTRICT,
    participant_id uuid NOT NULL REFERENCES data_protocol.participants(id) ON DELETE RESTRICT,
    category text NOT NULL CHECK (category IN ('source', 'development', 'target')),
    PRIMARY KEY (manifest_id, participant_id),
    UNIQUE (manifest_id, participant_id, category)
);

CREATE TABLE data_protocol.manifest_units (
    id uuid PRIMARY KEY,
    manifest_id uuid NOT NULL,
    participant_id uuid NOT NULL,
    category text NOT NULL,
    segment_id uuid NOT NULL REFERENCES data_protocol.labelled_segments(id) ON DELETE RESTRICT,
    role text NOT NULL CHECK (role IN ('source_train', 'development_validation', 'target_calibration', 'target_test')),
    FOREIGN KEY (manifest_id, participant_id, category) REFERENCES data_protocol.manifest_participants(manifest_id, participant_id, category) ON DELETE RESTRICT,
    CHECK ((category = 'source' AND role = 'source_train') OR
           (category = 'development' AND role = 'development_validation') OR
           (category = 'target' AND role IN ('target_calibration', 'target_test'))),
    UNIQUE (manifest_id, segment_id, role)
);

CREATE FUNCTION data_protocol.validate_segment() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE n integer;
BEGIN
    SELECT sample_count INTO n FROM data_protocol.recordings WHERE id = NEW.recording_id FOR UPDATE;
    IF n IS NULL THEN RAISE EXCEPTION 'Recording not found' USING ERRCODE = '23503'; END IF;
    IF NEW.end_sample > n THEN RAISE EXCEPTION 'Segment exceeds recording bounds' USING ERRCODE = '23514'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER validate_segment BEFORE INSERT OR UPDATE ON data_protocol.labelled_segments
FOR EACH ROW EXECUTE FUNCTION data_protocol.validate_segment();

CREATE FUNCTION data_protocol.guard_manifest_membership() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE manifest_key uuid; manifest_state text; segment_participant uuid;
BEGIN
    FOR manifest_key IN SELECT DISTINCT x FROM unnest(ARRAY[
        CASE WHEN TG_OP <> 'INSERT' THEN OLD.manifest_id END,
        CASE WHEN TG_OP <> 'DELETE' THEN NEW.manifest_id END
    ]) x WHERE x IS NOT NULL ORDER BY x LOOP
        SELECT state INTO manifest_state FROM data_protocol.research_manifests WHERE id = manifest_key FOR UPDATE;
        IF manifest_state IS DISTINCT FROM 'draft' THEN RAISE EXCEPTION 'Manifest is not an editable draft'; END IF;
    END LOOP;
    IF TG_TABLE_NAME = 'manifest_units' AND TG_OP <> 'DELETE' THEN
        PERFORM 1 FROM data_protocol.labelled_segments WHERE id = NEW.segment_id FOR UPDATE;
        SELECT r.participant_id INTO segment_participant FROM data_protocol.labelled_segments s
        JOIN data_protocol.recordings r ON r.id = s.recording_id WHERE s.id = NEW.segment_id FOR UPDATE OF r;
        IF segment_participant IS DISTINCT FROM NEW.participant_id THEN
            RAISE EXCEPTION 'Segment belongs to another participant or does not exist' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_manifest_participants BEFORE INSERT OR UPDATE OR DELETE ON data_protocol.manifest_participants
FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_manifest_membership();
CREATE TRIGGER guard_manifest_units BEFORE INSERT OR UPDATE OR DELETE ON data_protocol.manifest_units
FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_manifest_membership();

CREATE FUNCTION data_protocol.research_split_conflicts(p_manifest uuid)
RETURNS TABLE (unit_id uuid, conflicting_unit_id uuid, reason text) LANGUAGE sql STABLE AS $$
    SELECT a.id, b.id, 'overlapping roles'::text
    FROM data_protocol.manifest_units a
    JOIN data_protocol.labelled_segments sa ON sa.id = a.segment_id
    JOIN data_protocol.recordings ra ON ra.id = sa.recording_id
    JOIN data_protocol.manifest_units b ON b.manifest_id = a.manifest_id AND a.id < b.id AND a.role <> b.role
    JOIN data_protocol.labelled_segments sb ON sb.id = b.segment_id
    JOIN data_protocol.recordings rb ON rb.id = sb.recording_id
    WHERE a.manifest_id = p_manifest AND ra.artifact_sha256 = rb.artifact_sha256
      AND int8range(sa.start_sample, sa.end_sample, '[)') && int8range(sb.start_sample, sb.end_sample, '[)');
$$;

CREATE FUNCTION data_protocol.guard_research_manifest() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE protocol data_protocol.protocol_versions%ROWTYPE; payload text;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'draft' THEN RAISE EXCEPTION 'New manifest must be a draft'; END IF;
        RETURN NEW;
    END IF;
    IF OLD.state = 'frozen' THEN RAISE EXCEPTION 'Frozen manifests cannot be modified'; END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    IF NEW.state = 'frozen' THEN
        SELECT * INTO protocol FROM data_protocol.protocol_versions WHERE id = NEW.protocol_id FOR UPDATE;
        IF NOT EXISTS (SELECT 1 FROM data_protocol.manifest_units WHERE manifest_id = OLD.id AND role = 'source_train') OR
           NOT EXISTS (SELECT 1 FROM data_protocol.manifest_units WHERE manifest_id = OLD.id AND role = 'target_test') THEN
            RAISE EXCEPTION 'Source training and target test units are required';
        END IF;
        IF EXISTS (SELECT 1 FROM data_protocol.research_split_conflicts(OLD.id)) THEN
            RAISE EXCEPTION 'Manifest contains overlapping roles';
        END IF;
        IF EXISTS (SELECT 1 FROM data_protocol.manifest_units u JOIN data_protocol.labelled_segments s ON s.id = u.segment_id
                   WHERE u.manifest_id = OLD.id AND NOT (s.gesture_code = ANY(protocol.gesture_codes))) THEN
            RAISE EXCEPTION 'Manifest contains a gesture outside the protocol';
        END IF;
        SELECT jsonb_build_object('format', 1, 'manifest_id', OLD.id, 'name', NEW.name, 'version', NEW.version,
            'protocol', jsonb_build_array(protocol.id, protocol.name, protocol.version, protocol.gesture_codes),
            'participants', (SELECT jsonb_agg(jsonb_build_array(participant_id, category) ORDER BY participant_id)
                             FROM data_protocol.manifest_participants WHERE manifest_id = OLD.id),
            'units', (SELECT jsonb_agg(jsonb_build_array(u.id, u.participant_id, u.category, u.role, s.id,
                     s.gesture_code, s.repetition_key, s.start_sample, s.end_sample, r.id, r.artifact_sha256,
                     r.sample_rate_hz, r.sample_count) ORDER BY u.id)
                      FROM data_protocol.manifest_units u JOIN data_protocol.labelled_segments s ON s.id = u.segment_id
                      JOIN data_protocol.recordings r ON r.id = s.recording_id WHERE u.manifest_id = OLD.id))::text INTO payload;
        NEW.checksum := encode(sha256(convert_to(payload, 'UTF8')), 'hex');
        NEW.frozen_at := clock_timestamp();
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_research_manifest BEFORE INSERT OR UPDATE OR DELETE ON data_protocol.research_manifests
FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_research_manifest();

CREATE FUNCTION data_protocol.guard_research_dependencies() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'protocol_versions' AND EXISTS (SELECT 1 FROM data_protocol.research_manifests WHERE protocol_id = OLD.id) THEN
        RAISE EXCEPTION 'Protocol referenced by a manifest cannot be modified';
    ELSIF TG_TABLE_NAME = 'labelled_segments' AND EXISTS (SELECT 1 FROM data_protocol.manifest_units WHERE segment_id = OLD.id) THEN
        RAISE EXCEPTION 'Segment referenced by a manifest cannot be modified';
    ELSIF TG_TABLE_NAME = 'recordings' AND EXISTS (
        SELECT 1 FROM data_protocol.manifest_units u JOIN data_protocol.labelled_segments s ON s.id = u.segment_id WHERE s.recording_id = OLD.id
    ) THEN RAISE EXCEPTION 'Recording referenced by a manifest cannot be modified';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_research_protocol BEFORE UPDATE OR DELETE ON data_protocol.protocol_versions
FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_research_dependencies();
CREATE TRIGGER guard_research_segment BEFORE UPDATE OR DELETE ON data_protocol.labelled_segments
FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_research_dependencies();
CREATE TRIGGER guard_research_recording BEFORE UPDATE OR DELETE ON data_protocol.recordings
FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_research_dependencies();
