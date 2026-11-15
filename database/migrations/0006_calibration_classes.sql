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
GROUP BY ci.subset_id, s.gesture_id, s.signal_id;
