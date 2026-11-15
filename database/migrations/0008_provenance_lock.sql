CREATE FUNCTION myoprosthesis.lock_signal_provenance_dependencies() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    PERFORM 1 FROM myoprosthesis.canonical_signals WHERE id = NEW.signal_id FOR UPDATE;
    PERFORM 1 FROM myoprosthesis.artifacts WHERE id = NEW.artifact_id FOR UPDATE;
    RETURN NEW;
END $$;
CREATE TRIGGER lock_signal_provenance_dependencies BEFORE INSERT ON myoprosthesis.signal_provenance
FOR EACH ROW EXECUTE FUNCTION myoprosthesis.lock_signal_provenance_dependencies();
