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
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.lock_unit_signal();
