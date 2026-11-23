-- Run as schema owner with CREATEROLE, after service migrations.
-- LOGIN roles and their secrets are provisioned separately per environment.
DO $$
DECLARE item record;
BEGIN
    FOR item IN SELECT * FROM (VALUES
        ('myocontrol_identity', 'identity'),
        ('myocontrol_data', 'data_protocol'),
        ('myocontrol_ml', 'ml_experiments'),
        ('myocontrol_recognition', 'recognition')
    ) AS roles(role_name, schema_name) LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = item.role_name) THEN
            EXECUTE format('CREATE ROLE %I NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', item.role_name);
        END IF;
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = item.role_name AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolcanlogin)) THEN
            RAISE EXCEPTION 'Existing role % has unexpected privileges', item.role_name;
        END IF;
        IF EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = item.schema_name) THEN
            EXECUTE format('REVOKE ALL ON SCHEMA %I FROM PUBLIC', item.schema_name);
            EXECUTE format('REVOKE ALL ON ALL TABLES IN SCHEMA %I FROM PUBLIC', item.schema_name);
            EXECUTE format('REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA %I FROM PUBLIC', item.schema_name);
            EXECUTE format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA %I TO %I', item.schema_name, item.role_name);
            EXECUTE format('GRANT USAGE ON SCHEMA %I TO %I', item.schema_name, item.role_name);
            EXECUTE format('REVOKE CREATE ON SCHEMA %I FROM %I', item.schema_name, item.role_name);
            EXECUTE format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA %I TO %I', item.schema_name, item.role_name);
            EXECUTE format('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA %I TO %I', item.schema_name, item.role_name);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', item.schema_name, item.role_name);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT USAGE, SELECT ON SEQUENCES TO %I', item.schema_name, item.role_name);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC', item.schema_name);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA %I GRANT EXECUTE ON FUNCTIONS TO %I', item.schema_name, item.role_name);
        END IF;
    END LOOP;
END $$;

-- Reviewers see research evidence, never password/token/lease hashes or write access.
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'myocontrol_reviewer') THEN
        CREATE ROLE myocontrol_reviewer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'myocontrol_reviewer'
               AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolcanlogin)) THEN
        RAISE EXCEPTION 'Unexpected reviewer role privileges';
    END IF;
END $$;
REVOKE ALL ON SCHEMA identity FROM myocontrol_reviewer;
REVOKE ALL ON ALL TABLES IN SCHEMA identity FROM myocontrol_reviewer;
GRANT USAGE ON SCHEMA ml_experiments TO myocontrol_reviewer;
GRANT SELECT ON ml_experiments.published_models, ml_experiments.reviewer_results TO myocontrol_reviewer;
