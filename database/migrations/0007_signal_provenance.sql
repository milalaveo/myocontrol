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
GROUP BY samples.subset_id, samples.gesture_id;
