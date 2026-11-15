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
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.validate_model_calibration_input();
