-- Persistence boundary for cloud operator access. No user is a PostgreSQL login.
CREATE SCHEMA identity;

CREATE TABLE identity.operators (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL UNIQUE CHECK (email = lower(btrim(email)) AND length(email) <= 320
        AND email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'),
    display_name text NOT NULL CHECK (length(btrim(display_name)) BETWEEN 1 AND 120),
    password_hash text NOT NULL CHECK (password_hash LIKE '$argon2id$v=19$%' AND length(password_hash) BETWEEN 40 AND 1024),
    role text NOT NULL DEFAULT 'operator' CHECK (role IN ('operator', 'reviewer', 'administrator')),
    state text NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'disabled')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE FUNCTION identity.touch_operator() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Disable operator accounts instead of deleting research identity'; END IF;
    IF (NEW.id, NEW.created_at) IS DISTINCT FROM (OLD.id, OLD.created_at) THEN RAISE EXCEPTION 'Operator identity is immutable'; END IF;
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END $$;
CREATE TRIGGER touch_operator BEFORE UPDATE OR DELETE ON identity.operators
FOR EACH ROW EXECUTE FUNCTION identity.touch_operator();

CREATE TABLE identity.clients (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id uuid NOT NULL REFERENCES identity.operators(id) ON DELETE RESTRICT,
    kind text NOT NULL CHECK (kind IN ('desktop', 'training_worker')),
    name text NOT NULL CHECK (length(btrim(name)) BETWEEN 1 AND 120),
    platform text NOT NULL CHECK (length(btrim(platform)) BETWEEN 1 AND 120),
    state text NOT NULL DEFAULT 'active' CHECK (state IN ('active', 'revoked')),
    created_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (id, operator_id)
);
CREATE TABLE identity.access_sessions (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    operator_id uuid NOT NULL REFERENCES identity.operators(id) ON DELETE RESTRICT,
    client_id uuid,
    token_sha256 text NOT NULL UNIQUE CHECK (token_sha256 ~ '^[0-9a-f]{64}$'),
    scope text NOT NULL CHECK (scope IN ('web', 'desktop', 'training_worker')),
    issued_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at timestamptz NOT NULL,
    revoked_at timestamptz,
    FOREIGN KEY (client_id, operator_id) REFERENCES identity.clients(id, operator_id) ON DELETE RESTRICT,
    CHECK (expires_at > issued_at),
    CHECK (revoked_at IS NULL OR revoked_at >= issued_at),
    CHECK ((scope = 'web' AND client_id IS NULL) OR (scope <> 'web' AND client_id IS NOT NULL))
);
CREATE FUNCTION identity.guard_client() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Revoke clients instead of deleting identity'; END IF;
    IF (NEW.id, NEW.operator_id, NEW.kind, NEW.platform, NEW.created_at) IS DISTINCT FROM
       (OLD.id, OLD.operator_id, OLD.kind, OLD.platform, OLD.created_at) THEN
        RAISE EXCEPTION 'Client owner, kind and platform are immutable';
    END IF;
    IF OLD.state = 'revoked' AND NEW.state <> 'revoked' THEN RAISE EXCEPTION 'Register a new client instead of restoring a revoked one'; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_client BEFORE UPDATE OR DELETE ON identity.clients
FOR EACH ROW EXECUTE FUNCTION identity.guard_client();
CREATE INDEX access_sessions_operator ON identity.access_sessions(operator_id);
CREATE INDEX clients_operator ON identity.clients(operator_id);
CREATE FUNCTION identity.guard_access_session() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'INSERT' AND NEW.client_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM identity.clients WHERE id = NEW.client_id AND operator_id = NEW.operator_id
          AND kind = NEW.scope AND state = 'active'
    ) THEN RAISE EXCEPTION 'Session client kind/owner/state does not match scope'; END IF;
    IF TG_OP = 'UPDATE' AND (NEW.id, NEW.operator_id, NEW.client_id, NEW.token_sha256, NEW.scope, NEW.issued_at, NEW.expires_at)
        IS DISTINCT FROM (OLD.id, OLD.operator_id, OLD.client_id, OLD.token_sha256, OLD.scope, OLD.issued_at, OLD.expires_at) THEN
        RAISE EXCEPTION 'Rotate sessions by issuing a new token';
    END IF;
    IF TG_OP = 'UPDATE' AND OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS DISTINCT FROM OLD.revoked_at THEN
        RAISE EXCEPTION 'Revoked sessions cannot be restored';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER guard_access_session BEFORE INSERT OR UPDATE OR DELETE ON identity.access_sessions
FOR EACH ROW EXECUTE FUNCTION identity.guard_access_session();

-- Intentionally excludes token/password hashes. Authentication uses service-owned tables.
CREATE VIEW identity.operator_directory AS
SELECT id, display_name, role, state, created_at FROM identity.operators;
CREATE VIEW identity.valid_session_ids AS
SELECT s.id, s.operator_id, s.client_id, s.scope, s.expires_at
FROM identity.access_sessions s JOIN identity.operators o ON o.id = s.operator_id
LEFT JOIN identity.clients c ON c.id = s.client_id
WHERE o.state = 'active' AND s.revoked_at IS NULL AND s.expires_at > CURRENT_TIMESTAMP
  AND (s.client_id IS NULL OR (c.state = 'active' AND c.kind = s.scope));

COMMENT ON SCHEMA identity IS 'Cloud identity persistence; HTTP authentication and offline grants require application implementation.';
COMMENT ON COLUMN identity.operators.password_hash IS 'Encoded Argon2id hash; service must validate algorithm parameters and never accept this value from an untrusted client.';
COMMENT ON COLUMN identity.access_sessions.token_sha256 IS 'Digest of a high-entropy opaque token. Never store raw bearer/refresh tokens.';
