CREATE FUNCTION data_protocol.validate_protocol_gestures() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM unnest(NEW.gesture_codes) code WHERE code IS NULL OR code !~ '^[A-Za-z0-9_-]{1,100}$') OR
       cardinality(NEW.gesture_codes) <> (SELECT count(DISTINCT code) FROM unnest(NEW.gesture_codes) code) THEN
        RAISE EXCEPTION 'Protocol gestures must be unique nonempty identifiers' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER validate_protocol_gestures BEFORE INSERT OR UPDATE ON data_protocol.protocol_versions
FOR EACH ROW EXECUTE FUNCTION data_protocol.validate_protocol_gestures();

CREATE TABLE data_protocol.calibration_subsets (
    id uuid PRIMARY KEY,
    manifest_id uuid NOT NULL,
    participant_id uuid NOT NULL,
    category text NOT NULL DEFAULT 'target' CHECK (category = 'target'),
    selection_version text NOT NULL CHECK (length(trim(selection_version)) > 0),
    budget_per_gesture integer NOT NULL CHECK (budget_per_gesture > 0),
    state text NOT NULL DEFAULT 'draft' CHECK (state IN ('draft', 'frozen')),
    FOREIGN KEY (manifest_id, participant_id, category) REFERENCES data_protocol.manifest_participants(manifest_id, participant_id, category) ON DELETE RESTRICT,
    UNIQUE (manifest_id, participant_id, selection_version, budget_per_gesture)
);

CREATE TABLE data_protocol.calibration_items (
    subset_id uuid NOT NULL REFERENCES data_protocol.calibration_subsets(id) ON DELETE RESTRICT,
    unit_id uuid NOT NULL REFERENCES data_protocol.manifest_units(id) ON DELETE RESTRICT,
    PRIMARY KEY (subset_id, unit_id)
);

CREATE FUNCTION data_protocol.guard_calibration_item() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE subset_key uuid; subset_row data_protocol.calibration_subsets%ROWTYPE;
BEGIN
    FOR subset_key IN SELECT DISTINCT x FROM unnest(ARRAY[
        CASE WHEN TG_OP <> 'INSERT' THEN OLD.subset_id END,
        CASE WHEN TG_OP <> 'DELETE' THEN NEW.subset_id END
    ]) x WHERE x IS NOT NULL ORDER BY x LOOP
        SELECT * INTO subset_row FROM data_protocol.calibration_subsets WHERE id = subset_key FOR UPDATE;
        IF subset_row.state IS DISTINCT FROM 'draft' THEN RAISE EXCEPTION 'Calibration subset is not editable'; END IF;
    END LOOP;
    IF TG_OP <> 'DELETE' AND NOT EXISTS (
        SELECT 1 FROM data_protocol.calibration_subsets c
        JOIN data_protocol.research_manifests m ON m.id = c.manifest_id
        JOIN data_protocol.manifest_units u ON u.manifest_id = c.manifest_id AND u.participant_id = c.participant_id
        WHERE c.id = NEW.subset_id AND u.id = NEW.unit_id AND u.role = 'target_calibration' AND m.state = 'frozen'
    ) THEN RAISE EXCEPTION 'Unit is not in the frozen target calibration split' USING ERRCODE = '23514'; END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_calibration_item BEFORE INSERT OR UPDATE OR DELETE ON data_protocol.calibration_items
FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_calibration_item();

CREATE FUNCTION data_protocol.guard_calibration_subset() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE classes text[]; other data_protocol.calibration_subsets%ROWTYPE;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'draft' THEN RAISE EXCEPTION 'New subsets must be drafts'; END IF;
        IF NOT EXISTS (SELECT 1 FROM data_protocol.research_manifests WHERE id = NEW.manifest_id AND state = 'frozen') THEN
            RAISE EXCEPTION 'Calibration requires a frozen manifest';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.state = 'frozen' THEN RAISE EXCEPTION 'Frozen calibration subsets are immutable'; END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    IF (NEW.manifest_id, NEW.participant_id, NEW.category, NEW.selection_version, NEW.budget_per_gesture) IS DISTINCT FROM
       (OLD.manifest_id, OLD.participant_id, OLD.category, OLD.selection_version, OLD.budget_per_gesture) THEN
        RAISE EXCEPTION 'Calibration subset identity is immutable';
    END IF;
    IF NEW.state = 'frozen' THEN
        -- Serialize all budget freezes within the same target/manifest.
        PERFORM 1 FROM data_protocol.manifest_participants WHERE manifest_id = OLD.manifest_id AND participant_id = OLD.participant_id FOR UPDATE;
        SELECT p.gesture_codes INTO classes FROM data_protocol.research_manifests m
            JOIN data_protocol.protocol_versions p ON p.id = m.protocol_id WHERE m.id = OLD.manifest_id;
        IF EXISTS (
            SELECT code FROM unnest(classes) code
            LEFT JOIN (SELECT s.gesture_code, count(DISTINCT (r.artifact_sha256, s.repetition_key)) AS n
                       FROM data_protocol.calibration_items i JOIN data_protocol.manifest_units u ON u.id = i.unit_id
                       JOIN data_protocol.labelled_segments s ON s.id = u.segment_id
                       JOIN data_protocol.recordings r ON r.id = s.recording_id
                       WHERE i.subset_id = OLD.id GROUP BY s.gesture_code) counts ON counts.gesture_code = code
            WHERE COALESCE(counts.n, 0) <> OLD.budget_per_gesture
        ) THEN RAISE EXCEPTION 'Calibration budget does not match required gesture counts'; END IF;
        FOR other IN SELECT * FROM data_protocol.calibration_subsets
            WHERE manifest_id = OLD.manifest_id AND participant_id = OLD.participant_id
              AND selection_version = OLD.selection_version AND state = 'frozen' AND id <> OLD.id LOOP
            IF other.budget_per_gesture < OLD.budget_per_gesture AND EXISTS (
                SELECT unit_id FROM data_protocol.calibration_items WHERE subset_id = other.id
                EXCEPT SELECT unit_id FROM data_protocol.calibration_items WHERE subset_id = OLD.id
            ) THEN RAISE EXCEPTION 'Calibration budgets are not nested'; END IF;
            IF other.budget_per_gesture > OLD.budget_per_gesture AND EXISTS (
                SELECT unit_id FROM data_protocol.calibration_items WHERE subset_id = OLD.id
                EXCEPT SELECT unit_id FROM data_protocol.calibration_items WHERE subset_id = other.id
            ) THEN RAISE EXCEPTION 'Calibration budgets are not nested'; END IF;
        END LOOP;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_calibration_subset BEFORE INSERT OR UPDATE OR DELETE ON data_protocol.calibration_subsets
FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_calibration_subset();

CREATE VIEW data_protocol.calibration_durations AS
WITH intervals AS (
    SELECT i.subset_id, s.gesture_code, r.artifact_sha256, r.sample_rate_hz,
           count(DISTINCT s.repetition_key) AS repetitions,
           range_agg(int8range(s.start_sample, s.end_sample, '[)')) AS sample_intervals
    FROM data_protocol.calibration_items i JOIN data_protocol.manifest_units u ON u.id = i.unit_id
    JOIN data_protocol.labelled_segments s ON s.id = u.segment_id JOIN data_protocol.recordings r ON r.id = s.recording_id
    GROUP BY i.subset_id, s.gesture_code, r.artifact_sha256, r.sample_rate_hz
)
SELECT intervals.subset_id, intervals.gesture_code,
       sum((upper(samples) - lower(samples))::numeric / intervals.sample_rate_hz) AS unique_seconds
FROM intervals CROSS JOIN LATERAL unnest(intervals.sample_intervals) samples
GROUP BY intervals.subset_id, intervals.gesture_code;
