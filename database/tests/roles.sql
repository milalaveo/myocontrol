BEGIN;
SET LOCAL ROLE app_read;
SELECT count(*) FROM myoprosthesis.gestures;
DO $$ BEGIN
    BEGIN
        INSERT INTO myoprosthesis.gestures(code, description) VALUES ('denied-read', 'test');
        RAISE EXCEPTION 'Read role wrote data';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
RESET ROLE;
SET LOCAL ROLE app_write;
INSERT INTO myoprosthesis.gestures(code, description) VALUES ('role-write-test', 'test');
DO $$ BEGIN
    BEGIN
        CREATE TABLE myoprosthesis.role_write_test(id integer);
        RAISE EXCEPTION 'Write role created a table';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
RESET ROLE;
SET LOCAL ROLE app_reviewer;
SELECT count(*) FROM myoprosthesis.completed_evaluations;
SELECT count(*) FROM myoprosthesis.reviewer_metrics;
DO $$ BEGIN
    BEGIN
        PERFORM count(*) FROM myoprosthesis.artifacts;
        RAISE EXCEPTION 'Reviewer read artifact metadata';
    EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END $$;
ROLLBACK;
