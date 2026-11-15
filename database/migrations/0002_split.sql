-- Canonical identity is assigned by an importer using a documented source-specific rule.
CREATE TABLE myoprosthesis.canonical_signals (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    identity_scheme text NOT NULL CHECK (length(trim(identity_scheme)) > 0),
    identity_value text NOT NULL CHECK (length(trim(identity_value)) > 0),
    participant_id bigint NOT NULL REFERENCES myoprosthesis.participants(id) ON DELETE RESTRICT,
    sample_count bigint NOT NULL CHECK (sample_count > 0),
    UNIQUE (identity_scheme, identity_value),
    UNIQUE (id, participant_id)
);

ALTER TABLE myoprosthesis.recordings
    ADD COLUMN canonical_signal_id bigint REFERENCES myoprosthesis.canonical_signals(id) ON DELETE RESTRICT;

CREATE TABLE myoprosthesis.source_recording_keys (
    dataset_version_id bigint NOT NULL REFERENCES myoprosthesis.dataset_versions(id) ON DELETE RESTRICT,
    external_key text NOT NULL CHECK (length(trim(external_key)) > 0),
    recording_id bigint NOT NULL UNIQUE REFERENCES myoprosthesis.recordings(id) ON DELETE RESTRICT,
    PRIMARY KEY (dataset_version_id, external_key)
);

CREATE FUNCTION myoprosthesis.validate_source_recording_key() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM myoprosthesis.recordings r
        JOIN myoprosthesis.recording_sessions s ON s.id = r.session_id
        WHERE r.id = NEW.recording_id AND s.dataset_version_id = NEW.dataset_version_id
          AND s.mode = 'import'
    ) THEN
        RAISE EXCEPTION 'Source key does not match an imported recording and dataset version';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER validate_source_recording_key BEFORE INSERT OR UPDATE ON myoprosthesis.source_recording_keys
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.validate_source_recording_key();

CREATE TABLE myoprosthesis.split_manifests (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (length(trim(name)) > 0),
    version integer NOT NULL CHECK (version > 0),
    state text NOT NULL DEFAULT 'draft' CHECK (state IN ('draft', 'frozen')),
    checksum char(64),
    frozen_at timestamptz,
    UNIQUE (name, version),
    CHECK ((state = 'draft' AND checksum IS NULL AND frozen_at IS NULL) OR
           (state = 'frozen' AND checksum ~ '^[0-9a-f]{64}$' AND frozen_at IS NOT NULL))
);

CREATE TABLE myoprosthesis.split_participants (
    manifest_id bigint NOT NULL REFERENCES myoprosthesis.split_manifests(id) ON DELETE RESTRICT,
    participant_id bigint NOT NULL REFERENCES myoprosthesis.participants(id) ON DELETE RESTRICT,
    category text NOT NULL CHECK (category IN ('source', 'development', 'target')),
    PRIMARY KEY (manifest_id, participant_id),
    UNIQUE (manifest_id, participant_id, category)
);

CREATE TABLE myoprosthesis.split_units (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    manifest_id bigint NOT NULL,
    participant_id bigint NOT NULL,
    category text NOT NULL,
    signal_id bigint NOT NULL,
    start_sample bigint NOT NULL CHECK (start_sample >= 0),
    end_sample bigint NOT NULL CHECK (end_sample > start_sample),
    role text NOT NULL CHECK (role IN ('source_train', 'development_validation', 'target_calibration', 'target_test')),
    FOREIGN KEY (manifest_id, participant_id, category) REFERENCES myoprosthesis.split_participants(manifest_id, participant_id, category) ON DELETE RESTRICT,
    FOREIGN KEY (signal_id, participant_id) REFERENCES myoprosthesis.canonical_signals(id, participant_id) ON DELETE RESTRICT,
    CHECK ((category = 'source' AND role = 'source_train') OR
           (category = 'development' AND role = 'development_validation') OR
           (category = 'target' AND role IN ('target_calibration', 'target_test'))),
    UNIQUE (manifest_id, signal_id, start_sample, end_sample, role)
);

CREATE FUNCTION myoprosthesis.guard_manifest_membership() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE manifest_key bigint; manifest_state text;
BEGIN
    FOR manifest_key IN SELECT DISTINCT x FROM unnest(ARRAY[
        CASE WHEN TG_OP <> 'INSERT' THEN OLD.manifest_id END,
        CASE WHEN TG_OP <> 'DELETE' THEN NEW.manifest_id END
    ]) AS x WHERE x IS NOT NULL ORDER BY x LOOP
        SELECT state INTO manifest_state FROM myoprosthesis.split_manifests WHERE id = manifest_key FOR UPDATE;
        IF manifest_state IS DISTINCT FROM 'draft' THEN
            RAISE EXCEPTION 'Manifest % is not an editable draft', manifest_key;
        END IF;
    END LOOP;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_split_participants BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.split_participants
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_manifest_membership();
CREATE TRIGGER guard_split_units BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.split_units
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_manifest_membership();

CREATE FUNCTION myoprosthesis.split_conflicts(p_manifest_id bigint)
RETURNS TABLE (unit_id bigint, conflicting_unit_id bigint, reason text) LANGUAGE sql STABLE AS $$
    SELECT a.id, b.id, 'overlapping roles'::text
    FROM myoprosthesis.split_units a JOIN myoprosthesis.split_units b
      ON a.manifest_id = b.manifest_id AND a.id < b.id AND a.signal_id = b.signal_id
     AND a.role <> b.role AND int8range(a.start_sample, a.end_sample, '[)') && int8range(b.start_sample, b.end_sample, '[)')
    WHERE a.manifest_id = p_manifest_id
    UNION ALL
    SELECT u.id, NULL::bigint, 'outside signal bounds'::text
    FROM myoprosthesis.split_units u JOIN myoprosthesis.canonical_signals s ON s.id = u.signal_id
    WHERE u.manifest_id = p_manifest_id AND u.end_sample > s.sample_count;
$$;

CREATE FUNCTION myoprosthesis.guard_manifest_row() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_payload text;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'draft' THEN RAISE EXCEPTION 'New manifests must be drafts'; END IF;
        RETURN NEW;
    END IF;
    IF OLD.state = 'frozen' THEN RAISE EXCEPTION 'Frozen manifests are immutable'; END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    IF NEW.state = 'frozen' THEN
        IF NOT EXISTS (SELECT 1 FROM myoprosthesis.split_units WHERE manifest_id = OLD.id) OR
           EXISTS (SELECT 1 FROM myoprosthesis.split_conflicts(OLD.id)) THEN
            RAISE EXCEPTION 'Manifest % is empty or contains conflicting units', OLD.id;
        END IF;
        SELECT jsonb_build_object(
            'format', 1, 'manifest_id', OLD.id,
            'participants', COALESCE((SELECT jsonb_agg(jsonb_build_array(participant_id, category) ORDER BY participant_id)
                FROM myoprosthesis.split_participants WHERE manifest_id = OLD.id), '[]'::jsonb),
            'units', COALESCE((SELECT jsonb_agg(jsonb_build_array(id, participant_id, category, signal_id, start_sample, end_sample, role)
                ORDER BY id) FROM myoprosthesis.split_units WHERE manifest_id = OLD.id), '[]'::jsonb)
        )::text INTO v_payload;
        NEW.checksum := encode(sha256(convert_to(v_payload, 'UTF8')), 'hex');
        NEW.frozen_at := clock_timestamp();
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_manifest BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.split_manifests
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_manifest_row();

CREATE PROCEDURE myoprosthesis.freeze_manifest(p_manifest_id bigint) LANGUAGE plpgsql AS $$
DECLARE v_state text;
BEGIN
    SELECT state INTO v_state FROM myoprosthesis.split_manifests WHERE id = p_manifest_id FOR UPDATE;
    IF v_state IS DISTINCT FROM 'draft' THEN RAISE EXCEPTION 'Manifest % is not a draft', p_manifest_id; END IF;
    IF NOT EXISTS (SELECT 1 FROM myoprosthesis.split_units WHERE manifest_id = p_manifest_id) THEN
        RAISE EXCEPTION 'Manifest % has no units', p_manifest_id;
    END IF;
    IF EXISTS (SELECT 1 FROM myoprosthesis.split_conflicts(p_manifest_id)) THEN
        RAISE EXCEPTION 'Manifest % contains conflicting units', p_manifest_id;
    END IF;
    UPDATE myoprosthesis.split_manifests SET state = 'frozen' WHERE id = p_manifest_id;
END $$;

CREATE FUNCTION myoprosthesis.guard_used_signal() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM myoprosthesis.split_units WHERE signal_id = OLD.id) THEN
        RAISE EXCEPTION 'A signal referenced by a split cannot be modified';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_used_signal BEFORE UPDATE OR DELETE ON myoprosthesis.canonical_signals
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_used_signal();
