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
WHERE r.status = 'succeeded';
