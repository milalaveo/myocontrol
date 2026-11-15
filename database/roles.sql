-- Execute as the schema owner with CREATEROLE. These are NOLOGIN group roles;
-- create environment-specific login roles separately and grant only what is needed.
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_read') THEN
        CREATE ROLE app_read NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_write') THEN
        CREATE ROLE app_write NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'app_reviewer') THEN
        CREATE ROLE app_reviewer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
END $$;
GRANT USAGE ON SCHEMA myoprosthesis TO app_read, app_write, app_reviewer;
REVOKE CREATE ON SCHEMA myoprosthesis FROM PUBLIC, app_read, app_write, app_reviewer;
GRANT SELECT ON ALL TABLES IN SCHEMA myoprosthesis TO app_read, app_write;
GRANT INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA myoprosthesis TO app_write;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA myoprosthesis TO app_write;
ALTER DEFAULT PRIVILEGES IN SCHEMA myoprosthesis GRANT SELECT ON TABLES TO app_read, app_write;
ALTER DEFAULT PRIVILEGES IN SCHEMA myoprosthesis GRANT INSERT, UPDATE, DELETE ON TABLES TO app_write;
ALTER DEFAULT PRIVILEGES IN SCHEMA myoprosthesis GRANT USAGE, SELECT ON SEQUENCES TO app_write;
GRANT SELECT ON myoprosthesis.completed_evaluations TO app_reviewer;
GRANT SELECT ON myoprosthesis.reviewer_metrics TO app_reviewer;
