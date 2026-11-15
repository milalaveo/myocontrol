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
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.guard_selected_segment();
