BEGIN;

CREATE TABLE alembic_version (
    version_num VARCHAR(32) NOT NULL,
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 0001_sources

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
);;

INSERT INTO alembic_version (version_num) VALUES ('0001_sources') RETURNING alembic_version.version_num;

-- Running upgrade 0001_sources -> 0002_split

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
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_used_signal();;

UPDATE alembic_version SET version_num='0002_split' WHERE alembic_version.version_num = '0001_sources';

-- Running upgrade 0002_split -> 0003_calibration

CREATE TABLE myoprosthesis.gestures (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code text NOT NULL UNIQUE CHECK (length(trim(code)) > 0),
    description text NOT NULL
);

CREATE TABLE myoprosthesis.labelled_segments (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    signal_id bigint NOT NULL REFERENCES myoprosthesis.canonical_signals(id) ON DELETE RESTRICT,
    gesture_id bigint NOT NULL REFERENCES myoprosthesis.gestures(id) ON DELETE RESTRICT,
    repetition_key text NOT NULL CHECK (length(trim(repetition_key)) > 0),
    start_sample bigint NOT NULL CHECK (start_sample >= 0),
    end_sample bigint NOT NULL CHECK (end_sample > start_sample),
    UNIQUE (signal_id, repetition_key)
);

CREATE FUNCTION myoprosthesis.validate_segment() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE n bigint;
BEGIN
    SELECT sample_count INTO n FROM myoprosthesis.canonical_signals WHERE id = NEW.signal_id FOR UPDATE;
    IF NEW.end_sample > n THEN RAISE EXCEPTION 'Segment exceeds signal bounds'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER validate_segment BEFORE INSERT OR UPDATE ON myoprosthesis.labelled_segments
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.validate_segment();

CREATE OR REPLACE FUNCTION myoprosthesis.guard_used_signal() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM myoprosthesis.split_units WHERE signal_id = OLD.id) OR
       EXISTS (SELECT 1 FROM myoprosthesis.labelled_segments WHERE signal_id = OLD.id) THEN
        RAISE EXCEPTION 'A signal referenced by a split or segment cannot be modified';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;

CREATE TABLE myoprosthesis.calibration_subsets (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    manifest_id bigint NOT NULL,
    participant_id bigint NOT NULL,
    category text NOT NULL DEFAULT 'target' CHECK (category = 'target'),
    budget_per_gesture integer NOT NULL CHECK (budget_per_gesture > 0),
    selection_version text NOT NULL CHECK (length(trim(selection_version)) > 0),
    parent_id bigint REFERENCES myoprosthesis.calibration_subsets(id) ON DELETE RESTRICT,
    state text NOT NULL DEFAULT 'draft' CHECK (state IN ('draft', 'frozen')),
    FOREIGN KEY (manifest_id, participant_id, category) REFERENCES myoprosthesis.split_participants(manifest_id, participant_id, category) ON DELETE RESTRICT,
    CHECK (parent_id IS NULL OR parent_id <> id),
    UNIQUE (manifest_id, participant_id, selection_version, budget_per_gesture)
);

CREATE TABLE myoprosthesis.calibration_items (
    subset_id bigint NOT NULL REFERENCES myoprosthesis.calibration_subsets(id) ON DELETE RESTRICT,
    segment_id bigint NOT NULL REFERENCES myoprosthesis.labelled_segments(id) ON DELETE RESTRICT,
    PRIMARY KEY (subset_id, segment_id)
);

CREATE FUNCTION myoprosthesis.guard_calibration_item() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE subset_key bigint; subset_row myoprosthesis.calibration_subsets%ROWTYPE;
BEGIN
    FOR subset_key IN SELECT DISTINCT x FROM unnest(ARRAY[
        CASE WHEN TG_OP <> 'INSERT' THEN OLD.subset_id END,
        CASE WHEN TG_OP <> 'DELETE' THEN NEW.subset_id END
    ]) x WHERE x IS NOT NULL ORDER BY x LOOP
        SELECT * INTO subset_row FROM myoprosthesis.calibration_subsets WHERE id = subset_key FOR UPDATE;
        IF subset_row.state IS DISTINCT FROM 'draft' THEN RAISE EXCEPTION 'Calibration subset is not editable'; END IF;
    END LOOP;
    IF TG_OP <> 'DELETE' THEN
        SELECT * INTO subset_row FROM myoprosthesis.calibration_subsets WHERE id = NEW.subset_id;
        IF NOT EXISTS (
            SELECT 1 FROM myoprosthesis.labelled_segments s
            JOIN myoprosthesis.split_units u ON u.signal_id = s.signal_id
            JOIN myoprosthesis.split_manifests m ON m.id = u.manifest_id
            WHERE s.id = NEW.segment_id AND u.manifest_id = subset_row.manifest_id
              AND u.participant_id = subset_row.participant_id AND u.role = 'target_calibration'
              AND s.start_sample >= u.start_sample AND s.end_sample <= u.end_sample AND m.state = 'frozen'
        ) THEN RAISE EXCEPTION 'Segment is not in the frozen target calibration split'; END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_calibration_item BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.calibration_items
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_calibration_item();

CREATE FUNCTION myoprosthesis.guard_calibration_subset() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent myoprosthesis.calibration_subsets%ROWTYPE;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'draft' THEN RAISE EXCEPTION 'New subsets must be drafts'; END IF;
        RETURN NEW;
    END IF;
    IF OLD.state = 'frozen' THEN RAISE EXCEPTION 'Frozen calibration subsets are immutable'; END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    IF EXISTS (SELECT 1 FROM myoprosthesis.calibration_items WHERE subset_id = OLD.id) AND
       (NEW.manifest_id, NEW.participant_id, NEW.selection_version) IS DISTINCT FROM
       (OLD.manifest_id, OLD.participant_id, OLD.selection_version) THEN
        RAISE EXCEPTION 'Cannot change subset identity while it contains items';
    END IF;
    IF NEW.state = 'frozen' THEN
        IF NOT EXISTS (SELECT 1 FROM myoprosthesis.calibration_items WHERE subset_id = OLD.id) THEN
            RAISE EXCEPTION 'Cannot freeze an empty subset';
        END IF;
        IF NEW.parent_id IS NOT NULL THEN
            SELECT * INTO parent FROM myoprosthesis.calibration_subsets WHERE id = NEW.parent_id FOR UPDATE;
            IF parent.state IS DISTINCT FROM 'frozen' OR parent.manifest_id <> NEW.manifest_id OR
               parent.participant_id <> NEW.participant_id OR parent.selection_version <> NEW.selection_version OR
               parent.budget_per_gesture >= NEW.budget_per_gesture THEN
                RAISE EXCEPTION 'Invalid calibration parent';
            END IF;
            IF EXISTS (SELECT segment_id FROM myoprosthesis.calibration_items WHERE subset_id = parent.id
                       EXCEPT SELECT segment_id FROM myoprosthesis.calibration_items WHERE subset_id = OLD.id) THEN
                RAISE EXCEPTION 'Calibration budgets are not nested';
            END IF;
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_calibration_subset BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.calibration_subsets
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_calibration_subset();

CREATE FUNCTION myoprosthesis.guard_selected_segment() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM myoprosthesis.calibration_items WHERE segment_id = OLD.id) THEN
        RAISE EXCEPTION 'A selected segment cannot be modified';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_selected_segment BEFORE UPDATE OR DELETE ON myoprosthesis.labelled_segments
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_selected_segment();;

UPDATE alembic_version SET version_num='0003_calibration' WHERE alembic_version.version_num = '0002_split';

-- Running upgrade 0003_calibration -> 0004_integrity

-- Serialize segment selection with edits to that segment.
CREATE OR REPLACE FUNCTION myoprosthesis.guard_calibration_item() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE subset_key bigint; subset_row myoprosthesis.calibration_subsets%ROWTYPE;
BEGIN
    FOR subset_key IN SELECT DISTINCT x FROM unnest(ARRAY[
        CASE WHEN TG_OP <> 'INSERT' THEN OLD.subset_id END,
        CASE WHEN TG_OP <> 'DELETE' THEN NEW.subset_id END
    ]) x WHERE x IS NOT NULL ORDER BY x LOOP
        SELECT * INTO subset_row FROM myoprosthesis.calibration_subsets WHERE id = subset_key FOR UPDATE;
        IF subset_row.state IS DISTINCT FROM 'draft' THEN RAISE EXCEPTION 'Calibration subset is not editable'; END IF;
    END LOOP;
    IF TG_OP <> 'DELETE' THEN
        -- A concurrent segment update must either finish first or observe this selection.
        PERFORM 1 FROM myoprosthesis.labelled_segments WHERE id = NEW.segment_id FOR UPDATE;
        SELECT * INTO subset_row FROM myoprosthesis.calibration_subsets WHERE id = NEW.subset_id;
        IF NOT EXISTS (
            SELECT 1 FROM myoprosthesis.labelled_segments s
            JOIN myoprosthesis.split_units u ON u.signal_id = s.signal_id
            JOIN myoprosthesis.split_manifests m ON m.id = u.manifest_id
            WHERE s.id = NEW.segment_id AND u.manifest_id = subset_row.manifest_id
              AND u.participant_id = subset_row.participant_id AND u.role = 'target_calibration'
              AND s.start_sample >= u.start_sample AND s.end_sample <= u.end_sample AND m.state = 'frozen'
        ) THEN RAISE EXCEPTION 'Segment is not in the frozen target calibration split'; END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;

-- All frozen budgets in the same selection series must be nested, even without a parent.
CREATE OR REPLACE FUNCTION myoprosthesis.guard_calibration_subset() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE parent myoprosthesis.calibration_subsets%ROWTYPE; other myoprosthesis.calibration_subsets%ROWTYPE;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'draft' THEN RAISE EXCEPTION 'New subsets must be drafts'; END IF;
        RETURN NEW;
    END IF;
    IF OLD.state = 'frozen' THEN RAISE EXCEPTION 'Frozen calibration subsets are immutable'; END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    IF EXISTS (SELECT 1 FROM myoprosthesis.calibration_items WHERE subset_id = OLD.id) AND
       (NEW.manifest_id, NEW.participant_id, NEW.selection_version) IS DISTINCT FROM
       (OLD.manifest_id, OLD.participant_id, OLD.selection_version) THEN
        RAISE EXCEPTION 'Cannot change subset identity while it contains items';
    END IF;
    IF NEW.state = 'frozen' THEN
        -- Serialize publication of all budgets for the participant and manifest.
        PERFORM 1 FROM myoprosthesis.split_participants
        WHERE manifest_id = NEW.manifest_id AND participant_id = NEW.participant_id FOR UPDATE;
        IF NOT EXISTS (SELECT 1 FROM myoprosthesis.calibration_items WHERE subset_id = OLD.id) THEN
            RAISE EXCEPTION 'Cannot freeze an empty subset';
        END IF;
        IF NEW.parent_id IS NOT NULL THEN
            SELECT * INTO parent FROM myoprosthesis.calibration_subsets WHERE id = NEW.parent_id;
            IF parent.state IS DISTINCT FROM 'frozen' OR parent.manifest_id <> NEW.manifest_id OR
               parent.participant_id <> NEW.participant_id OR parent.selection_version <> NEW.selection_version OR
               parent.budget_per_gesture >= NEW.budget_per_gesture THEN
                RAISE EXCEPTION 'Invalid calibration parent';
            END IF;
        END IF;
        FOR other IN SELECT * FROM myoprosthesis.calibration_subsets
            WHERE manifest_id = NEW.manifest_id AND participant_id = NEW.participant_id
              AND selection_version = NEW.selection_version AND state = 'frozen' AND id <> OLD.id LOOP
            IF other.budget_per_gesture < NEW.budget_per_gesture AND EXISTS (
                SELECT segment_id FROM myoprosthesis.calibration_items WHERE subset_id = other.id
                EXCEPT SELECT segment_id FROM myoprosthesis.calibration_items WHERE subset_id = OLD.id
            ) THEN RAISE EXCEPTION 'Calibration budgets are not nested'; END IF;
            IF other.budget_per_gesture > NEW.budget_per_gesture AND EXISTS (
                SELECT segment_id FROM myoprosthesis.calibration_items WHERE subset_id = OLD.id
                EXCEPT SELECT segment_id FROM myoprosthesis.calibration_items WHERE subset_id = other.id
            ) THEN RAISE EXCEPTION 'Calibration budgets are not nested'; END IF;
        END LOOP;
    END IF;
    RETURN NEW;
END $$;

-- Signal edits and new split membership share the same signal row lock.
CREATE FUNCTION myoprosthesis.lock_unit_signal() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM myoprosthesis.canonical_signals WHERE id = NEW.signal_id FOR UPDATE;
    RETURN NEW;
END $$;
CREATE TRIGGER lock_unit_signal BEFORE INSERT OR UPDATE ON myoprosthesis.split_units
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.lock_unit_signal();;

UPDATE alembic_version SET version_num='0004_integrity' WHERE alembic_version.version_num = '0003_calibration';

-- Running upgrade 0004_integrity -> 0005_runs

-- This is the initial run and result schema. Publication and compatibility rules
-- must be completed before this schema is used for research.
CREATE TABLE myoprosthesis.feature_configs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (length(trim(name)) > 0),
    version integer NOT NULL CHECK (version > 0),
    schema_version text NOT NULL CHECK (length(trim(schema_version)) > 0),
    parameters jsonb NOT NULL CHECK (jsonb_typeof(parameters) = 'object'),
    UNIQUE (name, version)
);

CREATE TABLE myoprosthesis.runs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    kind text NOT NULL CHECK (kind IN ('train', 'adapt', 'evaluate')),
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'succeeded', 'failed', 'interrupted')),
    manifest_id bigint NOT NULL REFERENCES myoprosthesis.split_manifests(id) ON DELETE RESTRICT,
    feature_config_id bigint NOT NULL REFERENCES myoprosthesis.feature_configs(id) ON DELETE RESTRICT,
    seed bigint NOT NULL,
    parameter_schema_version text NOT NULL CHECK (length(trim(parameter_schema_version)) > 0),
    parameters jsonb NOT NULL CHECK (jsonb_typeof(parameters) = 'object'),
    software_version text NOT NULL CHECK (length(trim(software_version)) > 0),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at timestamptz,
    finished_at timestamptz,
    failure_reason text,
    CHECK (started_at IS NULL OR started_at >= created_at),
    CHECK (finished_at IS NULL OR (started_at IS NOT NULL AND finished_at >= started_at)),
    CHECK ((status = 'queued' AND started_at IS NULL AND finished_at IS NULL) OR
           (status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL) OR
           (status IN ('succeeded', 'failed', 'interrupted') AND started_at IS NOT NULL AND finished_at IS NOT NULL)),
    CHECK (status NOT IN ('failed', 'interrupted') OR (failure_reason IS NOT NULL AND length(trim(failure_reason)) > 0))
);

CREATE FUNCTION myoprosthesis.guard_run_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'queued' THEN RAISE EXCEPTION 'New runs must be queued'; END IF;
        IF NOT EXISTS (SELECT 1 FROM myoprosthesis.split_manifests WHERE id = NEW.manifest_id AND state = 'frozen') THEN
            RAISE EXCEPTION 'Run requires a frozen manifest';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.status IN ('succeeded', 'failed', 'interrupted') THEN RAISE EXCEPTION 'Terminal runs are immutable'; END IF;
    IF (NEW.kind, NEW.manifest_id, NEW.feature_config_id, NEW.seed, NEW.parameter_schema_version, NEW.parameters, NEW.software_version, NEW.created_at)
       IS DISTINCT FROM (OLD.kind, OLD.manifest_id, OLD.feature_config_id, OLD.seed, OLD.parameter_schema_version, OLD.parameters, OLD.software_version, OLD.created_at) THEN
        RAISE EXCEPTION 'Run configuration is immutable';
    END IF;
    IF NOT ((OLD.status = 'queued' AND NEW.status = 'running') OR
            (OLD.status = 'running' AND NEW.status IN ('succeeded', 'failed', 'interrupted'))) THEN
        RAISE EXCEPTION 'Invalid run transition: % to %', OLD.status, NEW.status;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_run_transition BEFORE INSERT OR UPDATE ON myoprosthesis.runs
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_run_transition();

CREATE TABLE myoprosthesis.model_versions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id bigint NOT NULL UNIQUE REFERENCES myoprosthesis.runs(id) ON DELETE RESTRICT,
    family text NOT NULL CHECK (family IN ('lda', 'svm', 'mlp')),
    condition text NOT NULL CHECK (condition IN ('source_only', 'personalised', 'target_only')),
    artifact_id bigint NOT NULL REFERENCES myoprosthesis.artifacts(id) ON DELETE RESTRICT,
    parent_model_id bigint REFERENCES myoprosthesis.model_versions(id) ON DELETE RESTRICT,
    calibration_subset_id bigint REFERENCES myoprosthesis.calibration_subsets(id) ON DELETE RESTRICT,
    CHECK ((condition = 'source_only' AND parent_model_id IS NULL AND calibration_subset_id IS NULL) OR
           (condition = 'personalised' AND parent_model_id IS NOT NULL AND calibration_subset_id IS NOT NULL) OR
           (condition = 'target_only' AND parent_model_id IS NULL AND calibration_subset_id IS NOT NULL))
);

CREATE TABLE myoprosthesis.evaluations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id bigint NOT NULL UNIQUE REFERENCES myoprosthesis.runs(id) ON DELETE RESTRICT,
    model_id bigint NOT NULL REFERENCES myoprosthesis.model_versions(id) ON DELETE RESTRICT,
    participant_id bigint NOT NULL REFERENCES myoprosthesis.participants(id) ON DELETE RESTRICT
);

CREATE TABLE myoprosthesis.evaluation_metrics (
    evaluation_id bigint NOT NULL REFERENCES myoprosthesis.evaluations(id) ON DELETE RESTRICT,
    metric text NOT NULL CHECK (metric IN ('macro_f1', 'accuracy', 'rest_false_activation_rate')),
    value numeric CHECK (value BETWEEN 0 AND 1),
    missing_reason text,
    numerator bigint CHECK (numerator >= 0),
    denominator bigint CHECK (denominator > 0),
    PRIMARY KEY (evaluation_id, metric),
    CHECK ((value IS NOT NULL AND missing_reason IS NULL) OR
           (value IS NULL AND missing_reason IS NOT NULL AND length(trim(missing_reason)) > 0)),
    CHECK ((numerator IS NULL AND denominator IS NULL) OR
           (numerator IS NOT NULL AND denominator IS NOT NULL AND numerator <= denominator))
);

CREATE TABLE myoprosthesis.confusion_counts (
    evaluation_id bigint NOT NULL REFERENCES myoprosthesis.evaluations(id) ON DELETE RESTRICT,
    actual_gesture_id bigint NOT NULL REFERENCES myoprosthesis.gestures(id) ON DELETE RESTRICT,
    predicted_gesture_id bigint NOT NULL REFERENCES myoprosthesis.gestures(id) ON DELETE RESTRICT,
    count bigint NOT NULL CHECK (count >= 0),
    PRIMARY KEY (evaluation_id, actual_gesture_id, predicted_gesture_id)
);;

UPDATE alembic_version SET version_num='0005_runs' WHERE alembic_version.version_num = '0004_integrity';

-- Running upgrade 0005_runs -> 0006_calibration_classes

CREATE TABLE myoprosthesis.gesture_sets (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (length(trim(name)) > 0),
    version integer NOT NULL CHECK (version > 0),
    UNIQUE (name, version)
);
CREATE TABLE myoprosthesis.gesture_set_members (
    gesture_set_id bigint NOT NULL REFERENCES myoprosthesis.gesture_sets(id) ON DELETE RESTRICT,
    gesture_id bigint NOT NULL REFERENCES myoprosthesis.gestures(id) ON DELETE RESTRICT,
    is_rest boolean NOT NULL DEFAULT false,
    PRIMARY KEY (gesture_set_id, gesture_id)
);
CREATE UNIQUE INDEX one_rest_per_gesture_set ON myoprosthesis.gesture_set_members(gesture_set_id) WHERE is_rest;

ALTER TABLE myoprosthesis.calibration_subsets ADD COLUMN gesture_set_id bigint REFERENCES myoprosthesis.gesture_sets(id) ON DELETE RESTRICT;

CREATE FUNCTION myoprosthesis.validate_calibration_classes() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.state = 'frozen' THEN RETURN NEW; END IF;
    IF EXISTS (SELECT 1 FROM myoprosthesis.calibration_items WHERE subset_id = OLD.id)
       AND NEW.gesture_set_id IS DISTINCT FROM OLD.gesture_set_id THEN
        RAISE EXCEPTION 'Cannot change gesture set while subset has items';
    END IF;
    IF NEW.state = 'frozen' THEN
        IF NEW.gesture_set_id IS NULL THEN RAISE EXCEPTION 'A gesture set is required'; END IF;
        -- Lock the set so membership edits and publication cannot race.
        PERFORM 1 FROM myoprosthesis.gesture_sets WHERE id = NEW.gesture_set_id FOR UPDATE;
        IF NOT EXISTS (SELECT 1 FROM myoprosthesis.gesture_set_members WHERE gesture_set_id = NEW.gesture_set_id AND is_rest) THEN
            RAISE EXCEPTION 'Gesture set must include rest';
        END IF;
        IF EXISTS (
            SELECT 1 FROM myoprosthesis.gesture_set_members gm
            LEFT JOIN myoprosthesis.labelled_segments s ON s.gesture_id = gm.gesture_id
            LEFT JOIN myoprosthesis.calibration_items ci ON ci.segment_id = s.id AND ci.subset_id = OLD.id
            WHERE gm.gesture_set_id = NEW.gesture_set_id
            GROUP BY gm.gesture_id HAVING count(ci.segment_id) <> NEW.budget_per_gesture
        ) THEN RAISE EXCEPTION 'Calibration budget does not match required gesture counts'; END IF;
        IF EXISTS (
            SELECT 1 FROM myoprosthesis.calibration_items ci
            JOIN myoprosthesis.labelled_segments s ON s.id = ci.segment_id
            WHERE ci.subset_id = OLD.id AND NOT EXISTS (
                SELECT 1 FROM myoprosthesis.gesture_set_members gm
                WHERE gm.gesture_set_id = NEW.gesture_set_id AND gm.gesture_id = s.gesture_id)
        ) THEN RAISE EXCEPTION 'Calibration contains a gesture outside the set'; END IF;
        IF EXISTS (SELECT 1 FROM myoprosthesis.calibration_subsets other
                   WHERE other.manifest_id = NEW.manifest_id AND other.participant_id = NEW.participant_id
                     AND other.selection_version = NEW.selection_version AND other.state = 'frozen'
                     AND other.gesture_set_id IS DISTINCT FROM NEW.gesture_set_id) THEN
            RAISE EXCEPTION 'Budgets in a selection series must use the same gesture set';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER validate_calibration_classes BEFORE UPDATE ON myoprosthesis.calibration_subsets
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.validate_calibration_classes();

CREATE FUNCTION myoprosthesis.guard_gesture_set_members() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE set_key bigint;
BEGIN
    FOR set_key IN SELECT DISTINCT x FROM unnest(ARRAY[
        CASE WHEN TG_OP <> 'INSERT' THEN OLD.gesture_set_id END,
        CASE WHEN TG_OP <> 'DELETE' THEN NEW.gesture_set_id END
    ]) x WHERE x IS NOT NULL ORDER BY x LOOP
        PERFORM 1 FROM myoprosthesis.gesture_sets WHERE id = set_key FOR UPDATE;
        IF EXISTS (SELECT 1 FROM myoprosthesis.calibration_subsets WHERE gesture_set_id = set_key AND state = 'frozen') THEN
            RAISE EXCEPTION 'Gesture set used by a frozen subset is immutable';
        END IF;
    END LOOP;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_gesture_set_members BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.gesture_set_members
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_gesture_set_members();

CREATE VIEW myoprosthesis.calibration_samples AS
SELECT ci.subset_id, s.gesture_id, s.signal_id,
       count(DISTINCT s.id) AS repetitions,
       range_agg(int8range(s.start_sample, s.end_sample, '[)')) AS sample_intervals
FROM myoprosthesis.calibration_items ci
JOIN myoprosthesis.labelled_segments s ON s.id = ci.segment_id
GROUP BY ci.subset_id, s.gesture_id, s.signal_id;;

UPDATE alembic_version SET version_num='0006_calibration_classes' WHERE alembic_version.version_num = '0005_runs';

-- Running upgrade 0006_calibration_classes -> 0007_signal_provenance

-- Versioned importer contracts determine how identity_value and the signal digest
-- are derived. A container checksum alone is not a canonical signal identity.
CREATE TABLE myoprosthesis.signal_provenance (
    signal_id bigint PRIMARY KEY REFERENCES myoprosthesis.canonical_signals(id) ON DELETE RESTRICT,
    artifact_id bigint NOT NULL REFERENCES myoprosthesis.artifacts(id) ON DELETE RESTRICT,
    sample_rate_hz numeric NOT NULL CHECK (sample_rate_hz > 0 AND sample_rate_hz < 'Infinity'::numeric),
    identity_method_version text NOT NULL CHECK (length(trim(identity_method_version)) > 0)
);

CREATE FUNCTION myoprosthesis.immutable_signal_provenance() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Signal provenance is immutable; create a new signal version';
END $$;
CREATE TRIGGER immutable_signal_provenance BEFORE UPDATE OR DELETE ON myoprosthesis.signal_provenance
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.immutable_signal_provenance();

CREATE OR REPLACE FUNCTION myoprosthesis.guard_used_signal() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM myoprosthesis.split_units WHERE signal_id = OLD.id) OR
       EXISTS (SELECT 1 FROM myoprosthesis.labelled_segments WHERE signal_id = OLD.id) OR
       EXISTS (SELECT 1 FROM myoprosthesis.signal_provenance WHERE signal_id = OLD.id) THEN
        RAISE EXCEPTION 'A referenced signal cannot be modified';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;

CREATE FUNCTION myoprosthesis.guard_provenance_artifact() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM myoprosthesis.signal_provenance WHERE artifact_id = OLD.id) THEN
        RAISE EXCEPTION 'An artifact referenced by signal provenance is immutable';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_provenance_artifact BEFORE UPDATE OR DELETE ON myoprosthesis.artifacts
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_provenance_artifact();

CREATE FUNCTION myoprosthesis.validate_provenance_on_freeze() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE payload text;
BEGIN
    IF NEW.state = 'frozen' AND OLD.state = 'draft' THEN
        IF EXISTS (SELECT 1 FROM myoprosthesis.split_units u
                   LEFT JOIN myoprosthesis.signal_provenance p ON p.signal_id = u.signal_id
                   WHERE u.manifest_id = OLD.id AND p.signal_id IS NULL) THEN
            RAISE EXCEPTION 'Every split signal requires immutable provenance';
        END IF;
        SELECT jsonb_build_object(
            'format', 2, 'manifest_id', OLD.id, 'name', NEW.name, 'version', NEW.version,
            'participants', COALESCE((SELECT jsonb_agg(jsonb_build_array(participant_id, category) ORDER BY participant_id)
                FROM myoprosthesis.split_participants WHERE manifest_id = OLD.id), '[]'::jsonb),
            'units', COALESCE((SELECT jsonb_agg(jsonb_build_array(u.id, u.participant_id, u.category, u.signal_id,
                         s.identity_scheme, s.identity_value, s.sample_count, p.sample_rate_hz,
                         p.identity_method_version, a.storage_namespace, a.storage_key, a.size_bytes, a.sha256,
                         u.start_sample, u.end_sample, u.role) ORDER BY u.id)
                FROM myoprosthesis.split_units u JOIN myoprosthesis.canonical_signals s ON s.id = u.signal_id
                JOIN myoprosthesis.signal_provenance p ON p.signal_id = s.id
                JOIN myoprosthesis.artifacts a ON a.id = p.artifact_id WHERE u.manifest_id = OLD.id), '[]'::jsonb)
        )::text INTO payload;
        NEW.checksum := encode(sha256(convert_to(payload, 'UTF8')), 'hex');
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER z_validate_provenance_on_freeze BEFORE UPDATE ON myoprosthesis.split_manifests
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.validate_provenance_on_freeze();

CREATE VIEW myoprosthesis.calibration_durations AS
SELECT samples.subset_id, samples.gesture_id,
       sum((upper(interval) - lower(interval))::numeric / p.sample_rate_hz) AS unique_seconds
FROM myoprosthesis.calibration_samples samples
JOIN myoprosthesis.signal_provenance p ON p.signal_id = samples.signal_id
CROSS JOIN LATERAL unnest(samples.sample_intervals) AS interval
GROUP BY samples.subset_id, samples.gesture_id;;

UPDATE alembic_version SET version_num='0007_signal_provenance' WHERE alembic_version.version_num = '0006_calibration_classes';

-- Running upgrade 0007_signal_provenance -> 0008_provenance_lock

CREATE FUNCTION myoprosthesis.lock_signal_provenance_dependencies() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM myoprosthesis.canonical_signals WHERE id = NEW.signal_id FOR UPDATE;
    PERFORM 1 FROM myoprosthesis.artifacts WHERE id = NEW.artifact_id FOR UPDATE;
    RETURN NEW;
END $$;
CREATE TRIGGER lock_signal_provenance_dependencies BEFORE INSERT ON myoprosthesis.signal_provenance
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.lock_signal_provenance_dependencies();;

UPDATE alembic_version SET version_num='0008_provenance_lock' WHERE alembic_version.version_num = '0007_signal_provenance';

-- Running upgrade 0008_provenance_lock -> 0009_publication

-- A verification record is an application attestation, not a filesystem check.
CREATE TABLE myoprosthesis.artifact_verifications (
    artifact_id bigint PRIMARY KEY REFERENCES myoprosthesis.artifacts(id) ON DELETE RESTRICT,
    verified_sha256 char(64) NOT NULL CHECK (verified_sha256 ~ '^[0-9a-f]{64}$'),
    verified_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE FUNCTION myoprosthesis.validate_artifact_verification() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM myoprosthesis.artifacts WHERE id = NEW.artifact_id AND sha256 = NEW.verified_sha256 FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Artifact checksum does not match'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER validate_artifact_verification BEFORE INSERT OR UPDATE ON myoprosthesis.artifact_verifications
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.validate_artifact_verification();

CREATE TABLE myoprosthesis.run_inputs (
    run_id bigint NOT NULL REFERENCES myoprosthesis.runs(id) ON DELETE RESTRICT,
    split_unit_id bigint NOT NULL REFERENCES myoprosthesis.split_units(id) ON DELETE RESTRICT,
    PRIMARY KEY (run_id, split_unit_id)
);
CREATE FUNCTION myoprosthesis.guard_run_input() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r myoprosthesis.runs%ROWTYPE; u myoprosthesis.split_units%ROWTYPE;
BEGIN
    IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'Run inputs are immutable'; END IF;
    SELECT * INTO r FROM myoprosthesis.runs WHERE id = NEW.run_id FOR UPDATE;
    SELECT * INTO u FROM myoprosthesis.split_units WHERE id = NEW.split_unit_id;
    IF r.status IS DISTINCT FROM 'queued' OR u.manifest_id IS DISTINCT FROM r.manifest_id OR
       NOT ((r.kind = 'train' AND u.role = 'source_train') OR
            (r.kind = 'adapt' AND u.role IN ('source_train', 'target_calibration')) OR
            (r.kind = 'evaluate' AND u.role = 'target_test')) THEN
        RAISE EXCEPTION 'Run input role or manifest is incompatible';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_run_input BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.run_inputs
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_run_input();

CREATE FUNCTION myoprosthesis.guard_published_artifact() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM myoprosthesis.artifact_verifications WHERE artifact_id = OLD.id) THEN
        RAISE EXCEPTION 'Verified artifact metadata is immutable';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_verified_artifact BEFORE UPDATE OR DELETE ON myoprosthesis.artifacts
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_published_artifact();

CREATE FUNCTION myoprosthesis.guard_verification_change() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Artifact verification records are immutable';
END $$;
CREATE TRIGGER guard_verification_change BEFORE UPDATE OR DELETE ON myoprosthesis.artifact_verifications
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_verification_change();

CREATE FUNCTION myoprosthesis.validate_run_publication() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE model myoprosthesis.model_versions%ROWTYPE; evaluation myoprosthesis.evaluations%ROWTYPE;
BEGIN
    IF NEW.status <> 'succeeded' OR OLD.status = 'succeeded' THEN RETURN NEW; END IF;
    IF NOT EXISTS (SELECT 1 FROM myoprosthesis.run_inputs WHERE run_id = NEW.id) THEN
        RAISE EXCEPTION 'Successful run requires explicit input units';
    END IF;
    IF NEW.kind IN ('train', 'adapt') THEN
        SELECT * INTO model FROM myoprosthesis.model_versions WHERE run_id = NEW.id;
        IF NOT FOUND OR NOT EXISTS (SELECT 1 FROM myoprosthesis.artifact_verifications WHERE artifact_id = model.artifact_id) THEN
            RAISE EXCEPTION 'Successful model run requires a verified artifact';
        END IF;
        IF (NEW.kind = 'adapt') <> (model.condition = 'personalised') THEN
            RAISE EXCEPTION 'Model condition does not match run kind';
        END IF;
        IF model.calibration_subset_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM myoprosthesis.calibration_subsets c
            WHERE c.id = model.calibration_subset_id AND c.manifest_id = NEW.manifest_id AND c.state = 'frozen'
        ) THEN RAISE EXCEPTION 'Model requires a compatible frozen calibration subset'; END IF;
        IF model.parent_model_id IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM myoprosthesis.model_versions parent JOIN myoprosthesis.runs parent_run ON parent.run_id = parent_run.id
            WHERE parent.id = model.parent_model_id AND parent.condition = 'source_only' AND parent.family = model.family
              AND parent_run.status = 'succeeded' AND parent_run.manifest_id = NEW.manifest_id
              AND parent_run.feature_config_id = NEW.feature_config_id
        ) THEN RAISE EXCEPTION 'Incompatible parent model'; END IF;
    ELSE
        SELECT * INTO evaluation FROM myoprosthesis.evaluations WHERE run_id = NEW.id;
        IF NOT FOUND OR NOT EXISTS (
            SELECT 1 FROM myoprosthesis.model_versions m JOIN myoprosthesis.runs model_run ON model_run.id = m.run_id
            WHERE m.id = evaluation.model_id AND model_run.status = 'succeeded'
              AND model_run.manifest_id = NEW.manifest_id AND model_run.feature_config_id = NEW.feature_config_id
        ) THEN RAISE EXCEPTION 'Evaluation requires a compatible completed model'; END IF;
        IF EXISTS (SELECT 1 FROM myoprosthesis.run_inputs i JOIN myoprosthesis.split_units u ON u.id = i.split_unit_id
                   WHERE i.run_id = NEW.id AND u.participant_id <> evaluation.participant_id) OR
           EXISTS (SELECT id FROM myoprosthesis.split_units WHERE manifest_id = NEW.manifest_id
                   AND participant_id = evaluation.participant_id AND role = 'target_test'
                   EXCEPT SELECT split_unit_id FROM myoprosthesis.run_inputs WHERE run_id = NEW.id) THEN
            RAISE EXCEPTION 'Evaluation must use the complete frozen target test';
        END IF;
        IF (SELECT count(*) FROM myoprosthesis.evaluation_metrics WHERE evaluation_id = evaluation.id) <> 3 THEN
            RAISE EXCEPTION 'Evaluation requires all metrics, including explicit missing reasons';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER z_validate_run_publication BEFORE UPDATE ON myoprosthesis.runs
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.validate_run_publication();

CREATE VIEW myoprosthesis.completed_evaluations AS
SELECT e.id AS evaluation_id, e.participant_id, e.model_id, r.manifest_id, r.feature_config_id,
       r.id AS run_id, r.software_version, r.seed
FROM myoprosthesis.evaluations e JOIN myoprosthesis.runs r ON r.id = e.run_id
WHERE r.status = 'succeeded';;

UPDATE alembic_version SET version_num='0009_publication' WHERE alembic_version.version_num = '0008_provenance_lock';

-- Running upgrade 0009_publication -> 0010_result_integrity

CREATE OR REPLACE FUNCTION myoprosthesis.guard_run_input() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r myoprosthesis.runs%ROWTYPE; u myoprosthesis.split_units%ROWTYPE;
BEGIN
    IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'Run inputs are immutable'; END IF;
    SELECT * INTO r FROM myoprosthesis.runs WHERE id = NEW.run_id FOR UPDATE;
    SELECT * INTO u FROM myoprosthesis.split_units WHERE id = NEW.split_unit_id;
    IF r.status IS DISTINCT FROM 'queued' OR u.manifest_id IS DISTINCT FROM r.manifest_id OR
       NOT ((r.kind IN ('train', 'adapt') AND u.role IN ('source_train', 'target_calibration')) OR
            (r.kind = 'evaluate' AND u.role = 'target_test')) THEN
        RAISE EXCEPTION 'Run input role or manifest is incompatible';
    END IF;
    RETURN NEW;
END $$;

CREATE FUNCTION myoprosthesis.guard_result_row() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r_id bigint; r_state text;
BEGIN
    IF TG_TABLE_NAME IN ('model_versions', 'evaluations') THEN
        IF TG_OP = 'INSERT' THEN r_id := NEW.run_id; ELSE r_id := OLD.run_id; END IF;
        IF TG_OP = 'UPDATE' AND NEW.run_id <> OLD.run_id THEN RAISE EXCEPTION 'Result run cannot be changed'; END IF;
    ELSE
        IF TG_OP = 'INSERT' THEN
            SELECT run_id INTO r_id FROM myoprosthesis.evaluations WHERE id = NEW.evaluation_id;
        ELSE
            SELECT run_id INTO r_id FROM myoprosthesis.evaluations WHERE id = OLD.evaluation_id;
            IF TG_OP = 'UPDATE' AND NEW.evaluation_id <> OLD.evaluation_id THEN RAISE EXCEPTION 'Evaluation cannot be changed'; END IF;
        END IF;
    END IF;
    SELECT status INTO r_state FROM myoprosthesis.runs WHERE id = r_id FOR UPDATE;
    IF r_state IS DISTINCT FROM 'running' THEN RAISE EXCEPTION 'Results may only change while the run is running'; END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_model_result BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.model_versions
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_result_row();
CREATE TRIGGER guard_evaluation_result BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.evaluations
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_result_row();
CREATE TRIGGER guard_metric_result BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.evaluation_metrics
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_result_row();
CREATE TRIGGER guard_confusion_result BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.confusion_counts
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_result_row();

CREATE FUNCTION myoprosthesis.guard_model_input_roles() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE model myoprosthesis.model_versions%ROWTYPE;
BEGIN
    IF NEW.status = 'succeeded' AND NEW.kind IN ('train', 'adapt') THEN
        SELECT * INTO model FROM myoprosthesis.model_versions WHERE run_id = NEW.id;
        IF model.condition = 'source_only' AND EXISTS (
            SELECT 1 FROM myoprosthesis.run_inputs i JOIN myoprosthesis.split_units u ON u.id = i.split_unit_id
            WHERE i.run_id = NEW.id AND u.role <> 'source_train'
        ) THEN RAISE EXCEPTION 'Source-only model cannot use target data'; END IF;
        IF model.condition = 'target_only' AND EXISTS (
            SELECT 1 FROM myoprosthesis.run_inputs i JOIN myoprosthesis.split_units u ON u.id = i.split_unit_id
            JOIN myoprosthesis.calibration_subsets c ON c.id = model.calibration_subset_id
            WHERE i.run_id = NEW.id AND (u.role <> 'target_calibration' OR u.participant_id <> c.participant_id)
        ) THEN RAISE EXCEPTION 'Target-only model has incompatible inputs'; END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER zz_guard_model_input_roles BEFORE UPDATE ON myoprosthesis.runs
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_model_input_roles();

CREATE FUNCTION myoprosthesis.guard_used_feature_config() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM myoprosthesis.runs WHERE feature_config_id = OLD.id) THEN
        RAISE EXCEPTION 'A feature configuration referenced by a run is immutable';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_used_feature_config BEFORE UPDATE OR DELETE ON myoprosthesis.feature_configs
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_used_feature_config();;

UPDATE alembic_version SET version_num='0010_result_integrity' WHERE alembic_version.version_num = '0009_publication';

-- Running upgrade 0010_result_integrity -> 0011_protocol_calibration

CREATE TABLE myoprosthesis.protocol_versions (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name text NOT NULL CHECK (length(trim(name)) > 0),
    version integer NOT NULL CHECK (version > 0),
    gesture_set_id bigint NOT NULL REFERENCES myoprosthesis.gesture_sets(id) ON DELETE RESTRICT,
    schema_version text NOT NULL CHECK (length(trim(schema_version)) > 0),
    configuration jsonb NOT NULL CHECK (jsonb_typeof(configuration) = 'object'),
    UNIQUE (name, version)
);
ALTER TABLE myoprosthesis.split_manifests ADD COLUMN protocol_id bigint REFERENCES myoprosthesis.protocol_versions(id) ON DELETE RESTRICT;

CREATE FUNCTION myoprosthesis.guard_referenced_protocol() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM myoprosthesis.split_manifests WHERE protocol_id = OLD.id) THEN
        RAISE EXCEPTION 'Referenced protocol is immutable';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_referenced_protocol BEFORE UPDATE OR DELETE ON myoprosthesis.protocol_versions
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_referenced_protocol();

CREATE FUNCTION myoprosthesis.require_manifest_protocol() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE protocol myoprosthesis.protocol_versions%ROWTYPE; payload text;
BEGIN
    IF NEW.state = 'frozen' AND OLD.state = 'draft' THEN
        SELECT * INTO protocol FROM myoprosthesis.protocol_versions WHERE id = NEW.protocol_id FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'A versioned protocol is required to freeze a split'; END IF;
        IF NOT EXISTS (SELECT 1 FROM myoprosthesis.gesture_set_members WHERE gesture_set_id = protocol.gesture_set_id AND is_rest) THEN
            RAISE EXCEPTION 'Protocol gesture set must contain rest';
        END IF;
        payload := jsonb_build_object('format', 3, 'split_v2_checksum', NEW.checksum,
            'protocol_id', protocol.id, 'name', protocol.name, 'version', protocol.version,
            'schema_version', protocol.schema_version, 'configuration', protocol.configuration,
            'gestures', (SELECT jsonb_agg(jsonb_build_array(gm.gesture_id, gm.is_rest, g.code) ORDER BY gm.gesture_id)
                         FROM myoprosthesis.gesture_set_members gm JOIN myoprosthesis.gestures g ON g.id = gm.gesture_id
                         WHERE gm.gesture_set_id = protocol.gesture_set_id))::text;
        NEW.checksum := encode(sha256(convert_to(payload, 'UTF8')), 'hex');
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER zz_require_manifest_protocol BEFORE UPDATE ON myoprosthesis.split_manifests
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.require_manifest_protocol();

CREATE FUNCTION myoprosthesis.guard_protocol_gesture_set() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE set_id bigint;
BEGIN
    FOR set_id IN SELECT DISTINCT x FROM unnest(ARRAY[
        CASE WHEN TG_OP <> 'INSERT' THEN OLD.gesture_set_id END,
        CASE WHEN TG_OP <> 'DELETE' THEN NEW.gesture_set_id END
    ]) x WHERE x IS NOT NULL ORDER BY x LOOP
        PERFORM 1 FROM myoprosthesis.gesture_sets WHERE id = set_id FOR UPDATE;
        IF EXISTS (SELECT 1 FROM myoprosthesis.protocol_versions p JOIN myoprosthesis.split_manifests m ON m.protocol_id = p.id
                   WHERE p.gesture_set_id = set_id AND m.state = 'frozen') THEN
            RAISE EXCEPTION 'Gesture set is used by a frozen protocol';
        END IF;
    END LOOP;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_protocol_gesture_set BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.gesture_set_members
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_protocol_gesture_set();

CREATE FUNCTION myoprosthesis.guard_protocol_gesture() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM myoprosthesis.gesture_set_members gm JOIN myoprosthesis.protocol_versions p ON p.gesture_set_id = gm.gesture_set_id
               JOIN myoprosthesis.split_manifests m ON m.protocol_id = p.id WHERE gm.gesture_id = OLD.id AND m.state = 'frozen') THEN
        RAISE EXCEPTION 'Gesture is referenced by a frozen protocol';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_protocol_gesture BEFORE UPDATE OR DELETE ON myoprosthesis.gestures
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_protocol_gesture();

CREATE TABLE myoprosthesis.run_calibration_items (
    run_id bigint NOT NULL REFERENCES myoprosthesis.runs(id) ON DELETE RESTRICT,
    segment_id bigint NOT NULL REFERENCES myoprosthesis.labelled_segments(id) ON DELETE RESTRICT,
    PRIMARY KEY (run_id, segment_id)
);
CREATE FUNCTION myoprosthesis.guard_run_calibration_item() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r myoprosthesis.runs%ROWTYPE;
BEGIN
    IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'Run calibration items are immutable'; END IF;
    SELECT * INTO r FROM myoprosthesis.runs WHERE id = NEW.run_id FOR UPDATE;
    IF r.status IS DISTINCT FROM 'queued' OR r.kind NOT IN ('train', 'adapt') THEN
        RAISE EXCEPTION 'Calibration items require a queued model run';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_run_calibration_item BEFORE INSERT OR UPDATE OR DELETE ON myoprosthesis.run_calibration_items
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_run_calibration_item();

CREATE FUNCTION myoprosthesis.validate_model_calibration_input() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE model myoprosthesis.model_versions%ROWTYPE; protocol_set bigint; subset_set bigint;
BEGIN
    IF NEW.status <> 'succeeded' OR NEW.kind NOT IN ('train', 'adapt') THEN RETURN NEW; END IF;
    SELECT * INTO model FROM myoprosthesis.model_versions WHERE run_id = NEW.id;
    SELECT p.gesture_set_id INTO protocol_set FROM myoprosthesis.split_manifests m
        JOIN myoprosthesis.protocol_versions p ON p.id = m.protocol_id WHERE m.id = NEW.manifest_id;
    IF protocol_set IS NULL THEN RAISE EXCEPTION 'Run must use a versioned protocol'; END IF;
    IF model.calibration_subset_id IS NULL THEN
        IF EXISTS (SELECT 1 FROM myoprosthesis.run_calibration_items WHERE run_id = NEW.id) THEN
            RAISE EXCEPTION 'Source-only run cannot use calibration items';
        END IF;
    ELSE
        SELECT gesture_set_id INTO subset_set FROM myoprosthesis.calibration_subsets WHERE id = model.calibration_subset_id;
        IF subset_set IS DISTINCT FROM protocol_set THEN RAISE EXCEPTION 'Calibration gesture set does not match protocol'; END IF;
        IF EXISTS (SELECT segment_id FROM myoprosthesis.calibration_items WHERE subset_id = model.calibration_subset_id
                   EXCEPT SELECT segment_id FROM myoprosthesis.run_calibration_items WHERE run_id = NEW.id) OR
           EXISTS (SELECT segment_id FROM myoprosthesis.run_calibration_items WHERE run_id = NEW.id
                   EXCEPT SELECT segment_id FROM myoprosthesis.calibration_items WHERE subset_id = model.calibration_subset_id) THEN
            RAISE EXCEPTION 'Run calibration items differ from the frozen subset';
        END IF;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER zzz_validate_model_calibration_input BEFORE UPDATE ON myoprosthesis.runs
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.validate_model_calibration_input();;

UPDATE alembic_version SET version_num='0011_protocol_calibration' WHERE alembic_version.version_num = '0010_result_integrity';

-- Running upgrade 0011_protocol_calibration -> 0012_protocol_integrity

CREATE OR REPLACE FUNCTION myoprosthesis.require_manifest_protocol() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE protocol myoprosthesis.protocol_versions%ROWTYPE; payload text;
BEGIN
    IF NEW.state = 'frozen' AND OLD.state = 'draft' THEN
        SELECT * INTO protocol FROM myoprosthesis.protocol_versions WHERE id = NEW.protocol_id FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'A versioned protocol is required to freeze a split'; END IF;
        PERFORM 1 FROM myoprosthesis.gesture_sets WHERE id = protocol.gesture_set_id FOR UPDATE;
        IF NOT EXISTS (SELECT 1 FROM myoprosthesis.gesture_set_members WHERE gesture_set_id = protocol.gesture_set_id AND is_rest) THEN
            RAISE EXCEPTION 'Protocol gesture set must contain rest';
        END IF;
        payload := jsonb_build_object('format', 3, 'split_v2_checksum', NEW.checksum,
            'protocol_id', protocol.id, 'name', protocol.name, 'version', protocol.version,
            'schema_version', protocol.schema_version, 'configuration', protocol.configuration,
            'gestures', (SELECT jsonb_agg(jsonb_build_array(gm.gesture_id, gm.is_rest, g.code) ORDER BY gm.gesture_id)
                         FROM myoprosthesis.gesture_set_members gm JOIN myoprosthesis.gestures g ON g.id = gm.gesture_id
                         WHERE gm.gesture_set_id = protocol.gesture_set_id))::text;
        NEW.checksum := encode(sha256(convert_to(payload, 'UTF8')), 'hex');
    END IF;
    RETURN NEW;
END $$;

CREATE FUNCTION myoprosthesis.require_run_protocol() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM myoprosthesis.split_manifests WHERE id = NEW.manifest_id AND protocol_id IS NOT NULL) THEN
        RAISE EXCEPTION 'Run requires a versioned protocol';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER require_run_protocol BEFORE INSERT ON myoprosthesis.runs
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.require_run_protocol();

CREATE VIEW myoprosthesis.published_models AS
SELECT m.id, m.run_id, m.family, m.condition, m.artifact_id, m.parent_model_id, m.calibration_subset_id,
       r.manifest_id, r.feature_config_id
FROM myoprosthesis.model_versions m JOIN myoprosthesis.runs r ON r.id = m.run_id
WHERE r.status = 'succeeded';;

UPDATE alembic_version SET version_num='0012_protocol_integrity' WHERE alembic_version.version_num = '0011_protocol_calibration';

-- Running upgrade 0012_protocol_integrity -> 0013_evaluation_integrity

CREATE FUNCTION myoprosthesis.validate_condition_inputs() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE model myoprosthesis.model_versions%ROWTYPE; target_id bigint;
BEGIN
    IF NEW.status <> 'succeeded' OR NEW.kind NOT IN ('train', 'adapt') THEN RETURN NEW; END IF;
    SELECT * INTO model FROM myoprosthesis.model_versions WHERE run_id = NEW.id;
    IF model.calibration_subset_id IS NOT NULL THEN
        SELECT participant_id INTO target_id FROM myoprosthesis.calibration_subsets WHERE id = model.calibration_subset_id;
        IF NOT EXISTS (SELECT 1 FROM myoprosthesis.run_inputs i JOIN myoprosthesis.split_units u ON u.id = i.split_unit_id
                       WHERE i.run_id = NEW.id AND u.role = 'target_calibration' AND u.participant_id = target_id) OR
           EXISTS (SELECT 1 FROM myoprosthesis.run_inputs i JOIN myoprosthesis.split_units u ON u.id = i.split_unit_id
                   WHERE i.run_id = NEW.id AND u.role = 'target_calibration' AND u.participant_id <> target_id) THEN
            RAISE EXCEPTION 'Calibration inputs must belong to the subset participant';
        END IF;
        IF EXISTS (
            SELECT 1 FROM myoprosthesis.run_calibration_items ci JOIN myoprosthesis.labelled_segments s ON s.id = ci.segment_id
            WHERE ci.run_id = NEW.id AND NOT EXISTS (
                SELECT 1 FROM myoprosthesis.run_inputs i JOIN myoprosthesis.split_units u ON u.id = i.split_unit_id
                WHERE i.run_id = NEW.id AND u.signal_id = s.signal_id AND u.role = 'target_calibration'
                  AND s.start_sample >= u.start_sample AND s.end_sample <= u.end_sample)
        ) THEN RAISE EXCEPTION 'Calibration segment is not covered by declared run inputs'; END IF;
    END IF;
    IF model.condition = 'personalised' AND NOT EXISTS (
        SELECT 1 FROM myoprosthesis.run_inputs i JOIN myoprosthesis.split_units u ON u.id = i.split_unit_id
        WHERE i.run_id = NEW.id AND u.role = 'source_train'
    ) THEN RAISE EXCEPTION 'Personalised run requires source inputs'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER zzzz_validate_condition_inputs BEFORE UPDATE ON myoprosthesis.runs
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.validate_condition_inputs();

CREATE FUNCTION myoprosthesis.validate_evaluation_class_set() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE ev myoprosthesis.evaluations%ROWTYPE; set_id bigint; expected bigint; actual bigint; subset_participant bigint;
BEGIN
    IF NEW.status <> 'succeeded' OR NEW.kind <> 'evaluate' THEN RETURN NEW; END IF;
    SELECT * INTO ev FROM myoprosthesis.evaluations WHERE run_id = NEW.id;
    SELECT p.gesture_set_id INTO set_id FROM myoprosthesis.split_manifests m
      JOIN myoprosthesis.protocol_versions p ON p.id = m.protocol_id WHERE m.id = NEW.manifest_id;
    SELECT count(*) INTO expected FROM myoprosthesis.gesture_set_members WHERE gesture_set_id = set_id;
    IF expected = 0 THEN RAISE EXCEPTION 'Evaluation requires a fixed gesture set'; END IF;
    SELECT count(*) INTO actual FROM myoprosthesis.confusion_counts WHERE evaluation_id = ev.id;
    IF actual <> expected * expected OR EXISTS (
        SELECT 1 FROM myoprosthesis.confusion_counts c WHERE c.evaluation_id = ev.id AND
        (NOT EXISTS (SELECT 1 FROM myoprosthesis.gesture_set_members gm WHERE gm.gesture_set_id = set_id AND gm.gesture_id = c.actual_gesture_id)
         OR NOT EXISTS (SELECT 1 FROM myoprosthesis.gesture_set_members gm WHERE gm.gesture_set_id = set_id AND gm.gesture_id = c.predicted_gesture_id))
    ) THEN RAISE EXCEPTION 'Confusion matrix must contain every gesture pair in the protocol'; END IF;
    SELECT c.participant_id INTO subset_participant FROM myoprosthesis.model_versions model
      JOIN myoprosthesis.calibration_subsets c ON c.id = model.calibration_subset_id WHERE model.id = ev.model_id;
    IF subset_participant IS NOT NULL AND subset_participant <> ev.participant_id THEN
        RAISE EXCEPTION 'Model calibration participant does not match evaluation target';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER zzzz_validate_evaluation_class_set BEFORE UPDATE ON myoprosthesis.runs
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.validate_evaluation_class_set();;

UPDATE alembic_version SET version_num='0013_evaluation_integrity' WHERE alembic_version.version_num = '0012_protocol_integrity';

-- Running upgrade 0013_evaluation_integrity -> 0014_recovery

ALTER TABLE myoprosthesis.runs ADD COLUMN heartbeat_at timestamptz;

CREATE OR REPLACE FUNCTION myoprosthesis.guard_run_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'queued' OR NEW.heartbeat_at IS NOT NULL THEN RAISE EXCEPTION 'New runs must be queued'; END IF;
        IF NOT EXISTS (SELECT 1 FROM myoprosthesis.split_manifests WHERE id = NEW.manifest_id AND state = 'frozen') THEN
            RAISE EXCEPTION 'Run requires a frozen manifest';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.status IN ('succeeded', 'failed', 'interrupted') THEN RAISE EXCEPTION 'Terminal runs are immutable'; END IF;
    IF (NEW.kind, NEW.manifest_id, NEW.feature_config_id, NEW.seed, NEW.parameter_schema_version, NEW.parameters, NEW.software_version, NEW.created_at)
       IS DISTINCT FROM (OLD.kind, OLD.manifest_id, OLD.feature_config_id, OLD.seed, OLD.parameter_schema_version, OLD.parameters, OLD.software_version, OLD.created_at) THEN
        RAISE EXCEPTION 'Run configuration is immutable';
    END IF;
    IF OLD.status = 'running' AND NEW.status = 'running' THEN
        IF (NEW.started_at, NEW.finished_at, NEW.failure_reason) IS DISTINCT FROM (OLD.started_at, OLD.finished_at, OLD.failure_reason)
           OR NEW.heartbeat_at IS NULL OR NEW.heartbeat_at < OLD.started_at
           OR (OLD.heartbeat_at IS NOT NULL AND NEW.heartbeat_at < OLD.heartbeat_at) THEN
            RAISE EXCEPTION 'Invalid heartbeat update';
        END IF;
        RETURN NEW;
    END IF;
    IF NOT ((OLD.status = 'queued' AND NEW.status = 'running') OR
            (OLD.status = 'running' AND NEW.status IN ('succeeded', 'failed', 'interrupted'))) THEN
        RAISE EXCEPTION 'Invalid run transition: % to %', OLD.status, NEW.status;
    END IF;
    IF NEW.heartbeat_at IS NOT NULL AND (NEW.started_at IS NULL OR NEW.heartbeat_at < NEW.started_at) THEN
        RAISE EXCEPTION 'Heartbeat precedes run start';
    END IF;
    RETURN NEW;
END $$;

CREATE PROCEDURE myoprosthesis.interrupt_stale_runs(p_cutoff timestamptz) LANGUAGE plpgsql AS $$
BEGIN
    IF p_cutoff IS NULL OR p_cutoff > clock_timestamp() THEN RAISE EXCEPTION 'Cutoff must be in the past'; END IF;
    UPDATE myoprosthesis.runs SET status = 'interrupted', finished_at = clock_timestamp(), failure_reason = 'Worker heartbeat expired'
    WHERE status = 'running' AND COALESCE(heartbeat_at, started_at) < p_cutoff;
END $$;

CREATE TABLE myoprosthesis.run_idempotency_keys (
    operation text NOT NULL CHECK (length(trim(operation)) > 0),
    idempotency_key text NOT NULL CHECK (length(trim(idempotency_key)) > 0),
    run_id bigint NOT NULL UNIQUE REFERENCES myoprosthesis.runs(id) ON DELETE RESTRICT,
    PRIMARY KEY (operation, idempotency_key)
);
CREATE FUNCTION myoprosthesis.immutable_run_idempotency_key() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'Idempotency keys are immutable';
END $$;
CREATE TRIGGER immutable_run_idempotency_key BEFORE UPDATE OR DELETE ON myoprosthesis.run_idempotency_keys
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.immutable_run_idempotency_key();;

UPDATE alembic_version SET version_num='0014_recovery' WHERE alembic_version.version_num = '0013_evaluation_integrity';

-- Running upgrade 0014_recovery -> 0015_reviewer_view

CREATE VIEW myoprosthesis.reviewer_metrics AS
SELECT e.evaluation_id, e.participant_id, e.model_id, e.manifest_id, e.feature_config_id,
       m.metric, m.value, m.missing_reason
FROM myoprosthesis.completed_evaluations e
JOIN myoprosthesis.evaluation_metrics m ON m.evaluation_id = e.evaluation_id;;

UPDATE alembic_version SET version_num='0015_reviewer_view' WHERE alembic_version.version_num = '0014_recovery';

-- Running upgrade 0015_reviewer_view -> 0016_snapshot_locks

-- Freeze and gesture edits must serialize on the same gesture rows.
CREATE OR REPLACE FUNCTION myoprosthesis.require_manifest_protocol() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE protocol myoprosthesis.protocol_versions%ROWTYPE; payload text;
BEGIN
    IF NEW.state = 'frozen' AND OLD.state = 'draft' THEN
        SELECT * INTO protocol FROM myoprosthesis.protocol_versions WHERE id = NEW.protocol_id FOR UPDATE;
        IF NOT FOUND THEN RAISE EXCEPTION 'A versioned protocol is required to freeze a split'; END IF;
        PERFORM 1 FROM myoprosthesis.gesture_sets WHERE id = protocol.gesture_set_id FOR UPDATE;
        PERFORM g.id FROM myoprosthesis.gestures g
          JOIN myoprosthesis.gesture_set_members gm ON gm.gesture_id = g.id
          WHERE gm.gesture_set_id = protocol.gesture_set_id ORDER BY g.id FOR UPDATE OF g;
        IF NOT EXISTS (SELECT 1 FROM myoprosthesis.gesture_set_members WHERE gesture_set_id = protocol.gesture_set_id AND is_rest) THEN
            RAISE EXCEPTION 'Protocol gesture set must contain rest';
        END IF;
        payload := jsonb_build_object('format', 3, 'split_v2_checksum', NEW.checksum,
            'protocol_id', protocol.id, 'name', protocol.name, 'version', protocol.version,
            'schema_version', protocol.schema_version, 'configuration', protocol.configuration,
            'gestures', (SELECT jsonb_agg(jsonb_build_array(gm.gesture_id, gm.is_rest, g.code) ORDER BY gm.gesture_id)
                         FROM myoprosthesis.gesture_set_members gm JOIN myoprosthesis.gestures g ON g.id = gm.gesture_id
                         WHERE gm.gesture_set_id = protocol.gesture_set_id))::text;
        NEW.checksum := encode(sha256(convert_to(payload, 'UTF8')), 'hex');
    END IF;
    RETURN NEW;
END $$;

CREATE FUNCTION myoprosthesis.lock_run_feature_config() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM myoprosthesis.feature_configs WHERE id = NEW.feature_config_id FOR UPDATE;
    RETURN NEW;
END $$;
CREATE TRIGGER lock_run_feature_config BEFORE INSERT ON myoprosthesis.runs
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.lock_run_feature_config();;

UPDATE alembic_version SET version_num='0016_snapshot_locks' WHERE alembic_version.version_num = '0015_reviewer_view';

COMMIT;
