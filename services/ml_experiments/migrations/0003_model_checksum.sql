ALTER TABLE ml_experiments.source_lda_runs ADD COLUMN model_checksum varchar(64);

CREATE FUNCTION ml_experiments.set_model_checksum() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status = 'succeeded' THEN
        NEW.model_checksum := encode(sha256(convert_to(NEW.model::text, 'UTF8')), 'hex');
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER z_set_model_checksum BEFORE UPDATE ON ml_experiments.source_lda_runs
FOR EACH ROW EXECUTE FUNCTION ml_experiments.set_model_checksum();
