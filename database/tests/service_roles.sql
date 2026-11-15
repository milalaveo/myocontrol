BEGIN;
SET LOCAL ROLE myocontrol_data;
SELECT count(*) FROM data_protocol.participants;
DO $$ BEGIN
    BEGIN
        PERFORM count(*) FROM ml_experiments.source_lda_runs;
        RAISE EXCEPTION 'Data service read ML data';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
    BEGIN
        CREATE TABLE data_protocol.role_test(id integer);
        RAISE EXCEPTION 'Data service performed DDL';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
RESET ROLE;
SET LOCAL ROLE myocontrol_ml;
SELECT count(*) FROM ml_experiments.source_lda_runs;
DO $$ BEGIN
    BEGIN
        PERFORM count(*) FROM data_protocol.participants;
        RAISE EXCEPTION 'ML service read data service tables';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
RESET ROLE;
SET LOCAL ROLE myocontrol_recognition;
SELECT count(*) FROM recognition.replay_sessions;
DO $$ BEGIN
    BEGIN
        PERFORM count(*) FROM ml_experiments.source_lda_runs;
        RAISE EXCEPTION 'Recognition service read ML tables';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
ROLLBACK;
