--
-- PostgreSQL database dump
--

-- Dumped from database version 16.3
-- Dumped by pg_dump version 16.3

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: data_protocol; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA data_protocol;


--
-- Name: identity; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA identity;


--
-- Name: SCHEMA identity; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA identity IS 'Cloud identity persistence; HTTP authentication and offline grants require application implementation.';


--
-- Name: ml_experiments; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA ml_experiments;


--
-- Name: recognition; Type: SCHEMA; Schema: -; Owner: -
--

CREATE SCHEMA recognition;


--
-- Name: guard_calibration_item(); Type: FUNCTION; Schema: data_protocol; Owner: -
--

CREATE FUNCTION data_protocol.guard_calibration_item() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE subset_key uuid; subset_row data_protocol.calibration_subsets%ROWTYPE;
BEGIN
    FOR subset_key IN SELECT DISTINCT x FROM unnest(ARRAY[
        CASE WHEN TG_OP <> 'INSERT' THEN OLD.subset_id END,
        CASE WHEN TG_OP <> 'DELETE' THEN NEW.subset_id END
    ]) x WHERE x IS NOT NULL ORDER BY x LOOP
        SELECT * INTO subset_row FROM data_protocol.calibration_subsets WHERE id = subset_key FOR UPDATE;
        IF subset_row.state IS DISTINCT FROM 'draft' THEN RAISE EXCEPTION 'Calibration subset is not editable'; END IF;
    END LOOP;
    IF TG_OP <> 'DELETE' AND NOT EXISTS (
        SELECT 1 FROM data_protocol.calibration_subsets c
        JOIN data_protocol.research_manifests m ON m.id = c.manifest_id
        JOIN data_protocol.manifest_units u ON u.manifest_id = c.manifest_id AND u.participant_id = c.participant_id
        WHERE c.id = NEW.subset_id AND u.id = NEW.unit_id AND u.role = 'target_calibration' AND m.state = 'frozen'
    ) THEN RAISE EXCEPTION 'Unit is not in the frozen target calibration split' USING ERRCODE = '23514'; END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;


--
-- Name: guard_calibration_subset(); Type: FUNCTION; Schema: data_protocol; Owner: -
--

CREATE FUNCTION data_protocol.guard_calibration_subset() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE classes text[]; other data_protocol.calibration_subsets%ROWTYPE;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'draft' THEN RAISE EXCEPTION 'New subsets must be drafts'; END IF;
        IF NOT EXISTS (SELECT 1 FROM data_protocol.research_manifests WHERE id = NEW.manifest_id AND state = 'frozen') THEN
            RAISE EXCEPTION 'Calibration requires a frozen manifest';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.state = 'frozen' THEN RAISE EXCEPTION 'Frozen calibration subsets are immutable'; END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    IF (NEW.manifest_id, NEW.participant_id, NEW.category, NEW.selection_version, NEW.budget_per_gesture) IS DISTINCT FROM
       (OLD.manifest_id, OLD.participant_id, OLD.category, OLD.selection_version, OLD.budget_per_gesture) THEN
        RAISE EXCEPTION 'Calibration subset identity is immutable';
    END IF;
    IF NEW.state = 'frozen' THEN
        -- Serialize all budget freezes within the same target/manifest.
        PERFORM 1 FROM data_protocol.manifest_participants WHERE manifest_id = OLD.manifest_id AND participant_id = OLD.participant_id FOR UPDATE;
        SELECT p.gesture_codes INTO classes FROM data_protocol.research_manifests m
            JOIN data_protocol.protocol_versions p ON p.id = m.protocol_id WHERE m.id = OLD.manifest_id;
        IF EXISTS (
            SELECT code FROM unnest(classes) code
            LEFT JOIN (SELECT s.gesture_code, count(DISTINCT (r.artifact_sha256, s.repetition_key)) AS n
                       FROM data_protocol.calibration_items i JOIN data_protocol.manifest_units u ON u.id = i.unit_id
                       JOIN data_protocol.labelled_segments s ON s.id = u.segment_id
                       JOIN data_protocol.recordings r ON r.id = s.recording_id
                       WHERE i.subset_id = OLD.id GROUP BY s.gesture_code) counts ON counts.gesture_code = code
            WHERE COALESCE(counts.n, 0) <> OLD.budget_per_gesture
        ) THEN RAISE EXCEPTION 'Calibration budget does not match required gesture counts'; END IF;
        FOR other IN SELECT * FROM data_protocol.calibration_subsets
            WHERE manifest_id = OLD.manifest_id AND participant_id = OLD.participant_id
              AND selection_version = OLD.selection_version AND state = 'frozen' AND id <> OLD.id LOOP
            IF other.budget_per_gesture < OLD.budget_per_gesture AND EXISTS (
                SELECT unit_id FROM data_protocol.calibration_items WHERE subset_id = other.id
                EXCEPT SELECT unit_id FROM data_protocol.calibration_items WHERE subset_id = OLD.id
            ) THEN RAISE EXCEPTION 'Calibration budgets are not nested'; END IF;
            IF other.budget_per_gesture > OLD.budget_per_gesture AND EXISTS (
                SELECT unit_id FROM data_protocol.calibration_items WHERE subset_id = OLD.id
                EXCEPT SELECT unit_id FROM data_protocol.calibration_items WHERE subset_id = other.id
            ) THEN RAISE EXCEPTION 'Calibration budgets are not nested'; END IF;
        END LOOP;
    END IF;
    RETURN NEW;
END $$;


--
-- Name: guard_manifest_membership(); Type: FUNCTION; Schema: data_protocol; Owner: -
--

CREATE FUNCTION data_protocol.guard_manifest_membership() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE manifest_key uuid; manifest_state text; segment_participant uuid;
BEGIN
    FOR manifest_key IN SELECT DISTINCT x FROM unnest(ARRAY[
        CASE WHEN TG_OP <> 'INSERT' THEN OLD.manifest_id END,
        CASE WHEN TG_OP <> 'DELETE' THEN NEW.manifest_id END
    ]) x WHERE x IS NOT NULL ORDER BY x LOOP
        SELECT state INTO manifest_state FROM data_protocol.research_manifests WHERE id = manifest_key FOR UPDATE;
        IF manifest_state IS DISTINCT FROM 'draft' THEN RAISE EXCEPTION 'Manifest is not an editable draft'; END IF;
    END LOOP;
    IF TG_TABLE_NAME = 'manifest_units' AND TG_OP <> 'DELETE' THEN
        PERFORM 1 FROM data_protocol.labelled_segments WHERE id = NEW.segment_id FOR UPDATE;
        SELECT r.participant_id INTO segment_participant FROM data_protocol.labelled_segments s
        JOIN data_protocol.recordings r ON r.id = s.recording_id WHERE s.id = NEW.segment_id FOR UPDATE OF r;
        IF segment_participant IS DISTINCT FROM NEW.participant_id THEN
            RAISE EXCEPTION 'Segment belongs to another participant or does not exist' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;


--
-- Name: guard_publication_metadata(); Type: FUNCTION; Schema: data_protocol; Owner: -
--

CREATE FUNCTION data_protocol.guard_publication_metadata() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP <> 'INSERT' THEN RAISE EXCEPTION 'Published source identity and receipts are immutable'; END IF;
    RETURN NEW;
END $$;


--
-- Name: guard_research_dependencies(); Type: FUNCTION; Schema: data_protocol; Owner: -
--

CREATE FUNCTION data_protocol.guard_research_dependencies() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_TABLE_NAME = 'protocol_versions' AND EXISTS (SELECT 1 FROM data_protocol.research_manifests WHERE protocol_id = OLD.id) THEN
        RAISE EXCEPTION 'Protocol referenced by a manifest cannot be modified';
    ELSIF TG_TABLE_NAME = 'labelled_segments' AND EXISTS (SELECT 1 FROM data_protocol.manifest_units WHERE segment_id = OLD.id) THEN
        RAISE EXCEPTION 'Segment referenced by a manifest cannot be modified';
    ELSIF TG_TABLE_NAME = 'recordings' AND EXISTS (
        SELECT 1 FROM data_protocol.manifest_units u JOIN data_protocol.labelled_segments s ON s.id = u.segment_id WHERE s.recording_id = OLD.id
    ) THEN RAISE EXCEPTION 'Recording referenced by a manifest cannot be modified';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;


--
-- Name: guard_research_manifest(); Type: FUNCTION; Schema: data_protocol; Owner: -
--

CREATE FUNCTION data_protocol.guard_research_manifest() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE protocol data_protocol.protocol_versions%ROWTYPE; payload text;
BEGIN
    IF TG_OP = 'INSERT' THEN
        IF NEW.state <> 'draft' THEN RAISE EXCEPTION 'New manifest must be a draft'; END IF;
        RETURN NEW;
    END IF;
    IF OLD.state = 'frozen' THEN RAISE EXCEPTION 'Frozen manifests cannot be modified'; END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    IF NEW.state = 'frozen' THEN
        SELECT * INTO protocol FROM data_protocol.protocol_versions WHERE id = NEW.protocol_id FOR UPDATE;
        IF NOT EXISTS (SELECT 1 FROM data_protocol.manifest_units WHERE manifest_id = OLD.id AND role = 'source_train') OR
           NOT EXISTS (SELECT 1 FROM data_protocol.manifest_units WHERE manifest_id = OLD.id AND role = 'target_test') THEN
            RAISE EXCEPTION 'Source training and target test units are required';
        END IF;
        IF EXISTS (SELECT 1 FROM data_protocol.research_split_conflicts(OLD.id)) THEN
            RAISE EXCEPTION 'Manifest contains overlapping roles';
        END IF;
        IF EXISTS (SELECT 1 FROM data_protocol.manifest_units u JOIN data_protocol.labelled_segments s ON s.id = u.segment_id
                   WHERE u.manifest_id = OLD.id AND NOT (s.gesture_code = ANY(protocol.gesture_codes))) THEN
            RAISE EXCEPTION 'Manifest contains a gesture outside the protocol';
        END IF;
        SELECT jsonb_build_object('format', 1, 'manifest_id', OLD.id, 'name', NEW.name, 'version', NEW.version,
            'protocol', jsonb_build_array(protocol.id, protocol.name, protocol.version, protocol.gesture_codes),
            'participants', (SELECT jsonb_agg(jsonb_build_array(participant_id, category) ORDER BY participant_id)
                             FROM data_protocol.manifest_participants WHERE manifest_id = OLD.id),
            'units', (SELECT jsonb_agg(jsonb_build_array(u.id, u.participant_id, u.category, u.role, s.id,
                     s.gesture_code, s.repetition_key, s.start_sample, s.end_sample, r.id, r.artifact_sha256,
                     r.sample_rate_hz, r.sample_count) ORDER BY u.id)
                      FROM data_protocol.manifest_units u JOIN data_protocol.labelled_segments s ON s.id = u.segment_id
                      JOIN data_protocol.recordings r ON r.id = s.recording_id WHERE u.manifest_id = OLD.id))::text INTO payload;
        NEW.checksum := encode(sha256(convert_to(payload, 'UTF8')), 'hex');
        NEW.frozen_at := clock_timestamp();
    END IF;
    RETURN NEW;
END $$;


--
-- Name: guard_split_recording(); Type: FUNCTION; Schema: data_protocol; Owner: -
--

CREATE FUNCTION data_protocol.guard_split_recording() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF EXISTS (SELECT 1 FROM data_protocol.synthetic_splits WHERE source_recording_id = OLD.id OR test_recording_id = OLD.id) THEN
        RAISE EXCEPTION 'Recording is referenced by a frozen split';
    END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;


--
-- Name: guard_synthetic_split(); Type: FUNCTION; Schema: data_protocol; Owner: -
--

CREATE FUNCTION data_protocol.guard_synthetic_split() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION 'Frozen synthetic splits cannot be changed';
END $$;


--
-- Name: register_client_recording(uuid, uuid, uuid, uuid, text); Type: FUNCTION; Schema: data_protocol; Owner: -
--

CREATE FUNCTION data_protocol.register_client_recording(p_operator uuid, p_client uuid, p_local uuid, p_recording uuid, p_hash text) RETURNS uuid
    LANGUAGE plpgsql
    AS $$
DECLARE receipt data_protocol.client_publications%ROWTYPE;
BEGIN
    INSERT INTO data_protocol.client_publications(operator_id, client_id, local_recording_id, recording_id, payload_sha256)
    VALUES (p_operator, p_client, p_local, p_recording, p_hash)
    ON CONFLICT (operator_id, client_id, local_recording_id) DO NOTHING;
    SELECT * INTO STRICT receipt FROM data_protocol.client_publications
    WHERE operator_id = p_operator AND client_id = p_client AND local_recording_id = p_local;
    IF (receipt.recording_id, receipt.payload_sha256) IS DISTINCT FROM (p_recording, p_hash) THEN
        RAISE EXCEPTION 'Client recording identity conflicts with an existing publication';
    END IF;
    RETURN receipt.id;
END $$;


--
-- Name: research_split_conflicts(uuid); Type: FUNCTION; Schema: data_protocol; Owner: -
--

CREATE FUNCTION data_protocol.research_split_conflicts(p_manifest uuid) RETURNS TABLE(unit_id uuid, conflicting_unit_id uuid, reason text)
    LANGUAGE sql STABLE
    AS $$
    SELECT a.id, b.id, 'overlapping roles'::text
    FROM data_protocol.manifest_units a
    JOIN data_protocol.labelled_segments sa ON sa.id = a.segment_id
    JOIN data_protocol.recordings ra ON ra.id = sa.recording_id
    JOIN data_protocol.manifest_units b ON b.manifest_id = a.manifest_id AND a.id < b.id AND a.role <> b.role
    JOIN data_protocol.labelled_segments sb ON sb.id = b.segment_id
    JOIN data_protocol.recordings rb ON rb.id = sb.recording_id
    WHERE a.manifest_id = p_manifest AND ra.artifact_sha256 = rb.artifact_sha256
      AND int8range(sa.start_sample, sa.end_sample, '[)') && int8range(sb.start_sample, sb.end_sample, '[)');
$$;


--
-- Name: validate_protocol_gestures(); Type: FUNCTION; Schema: data_protocol; Owner: -
--

CREATE FUNCTION data_protocol.validate_protocol_gestures() RETURNS trigger
    LANGUAGE plpgsql
    AS $_$
BEGIN
    IF EXISTS (SELECT 1 FROM unnest(NEW.gesture_codes) code WHERE code IS NULL OR code !~ '^[A-Za-z0-9_-]{1,100}$') OR
       cardinality(NEW.gesture_codes) <> (SELECT count(DISTINCT code) FROM unnest(NEW.gesture_codes) code) THEN
        RAISE EXCEPTION 'Protocol gestures must be unique nonempty identifiers' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $_$;


--
-- Name: validate_segment(); Type: FUNCTION; Schema: data_protocol; Owner: -
--

CREATE FUNCTION data_protocol.validate_segment() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE n integer;
BEGIN
    SELECT sample_count INTO n FROM data_protocol.recordings WHERE id = NEW.recording_id FOR UPDATE;
    IF n IS NULL THEN RAISE EXCEPTION 'Recording not found' USING ERRCODE = '23503'; END IF;
    IF NEW.end_sample > n THEN RAISE EXCEPTION 'Segment exceeds recording bounds' USING ERRCODE = '23514'; END IF;
    RETURN NEW;
END $$;


--
-- Name: validate_synthetic_split(); Type: FUNCTION; Schema: data_protocol; Owner: -
--

CREATE FUNCTION data_protocol.validate_synthetic_split() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE source_row data_protocol.recordings%ROWTYPE; test_row data_protocol.recordings%ROWTYPE;
BEGIN
    PERFORM id FROM data_protocol.recordings WHERE id IN (NEW.source_recording_id, NEW.test_recording_id) ORDER BY id FOR UPDATE;
    SELECT * INTO source_row FROM data_protocol.recordings WHERE id = NEW.source_recording_id;
    SELECT * INTO test_row FROM data_protocol.recordings WHERE id = NEW.test_recording_id;
    IF source_row.id IS NULL OR test_row.id IS NULL THEN RAISE EXCEPTION 'Recording not found' USING ERRCODE = '23503'; END IF;
    IF source_row.participant_id = test_row.participant_id OR source_row.artifact_sha256 = test_row.artifact_sha256 THEN
        RAISE EXCEPTION 'Source and test recordings overlap' USING ERRCODE = '23514';
    END IF;
    NEW.checksum := encode(sha256(convert_to(jsonb_build_array(
        'synthetic-split-v1', NEW.id, source_row.id, source_row.participant_id, source_row.artifact_sha256,
        source_row.sample_rate_hz, source_row.sample_count, test_row.id, test_row.participant_id,
        test_row.artifact_sha256, test_row.sample_rate_hz, test_row.sample_count)::text, 'UTF8')), 'hex');
    RETURN NEW;
END $$;


--
-- Name: guard_access_session(); Type: FUNCTION; Schema: identity; Owner: -
--

CREATE FUNCTION identity.guard_access_session() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
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


--
-- Name: guard_client(); Type: FUNCTION; Schema: identity; Owner: -
--

CREATE FUNCTION identity.guard_client() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Revoke clients instead of deleting identity'; END IF;
    IF (NEW.id, NEW.operator_id, NEW.kind, NEW.platform, NEW.created_at) IS DISTINCT FROM
       (OLD.id, OLD.operator_id, OLD.kind, OLD.platform, OLD.created_at) THEN
        RAISE EXCEPTION 'Client owner, kind and platform are immutable';
    END IF;
    IF OLD.state = 'revoked' AND NEW.state <> 'revoked' THEN RAISE EXCEPTION 'Register a new client instead of restoring a revoked one'; END IF;
    RETURN NEW;
END $$;


--
-- Name: touch_operator(); Type: FUNCTION; Schema: identity; Owner: -
--

CREATE FUNCTION identity.touch_operator() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Disable operator accounts instead of deleting research identity'; END IF;
    IF (NEW.id, NEW.created_at) IS DISTINCT FROM (OLD.id, OLD.created_at) THEN RAISE EXCEPTION 'Operator identity is immutable'; END IF;
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END $$;


--
-- Name: claim_experiment(uuid, uuid, text, text, integer); Type: FUNCTION; Schema: ml_experiments; Owner: -
--

CREATE FUNCTION ml_experiments.claim_experiment(p_operator uuid, p_worker uuid, p_lease_sha256 text, p_location text, p_seconds integer DEFAULT 120) RETURNS uuid
    LANGUAGE plpgsql
    AS $_$
DECLARE k uuid; t timestamptz := clock_timestamp();
BEGIN
    IF p_seconds NOT BETWEEN 10 AND 3600 OR p_location NOT IN ('local_workstation','desktop') OR p_lease_sha256 !~ '^[0-9a-f]{64}$' THEN
        RAISE EXCEPTION 'Invalid lease configuration';
    END IF;
    SELECT id INTO k FROM ml_experiments.experiment_runs
    WHERE operator_id = p_operator AND execution_location = p_location AND status = 'queued'
    ORDER BY created_at, id FOR UPDATE SKIP LOCKED LIMIT 1;
    IF k IS NULL THEN RETURN NULL; END IF;
    UPDATE ml_experiments.experiment_runs SET status = 'running', worker_client_id = p_worker,
        lease_sha256 = p_lease_sha256, started_at = t, heartbeat_at = t, lease_expires_at = t+make_interval(secs=>p_seconds)
    WHERE id = k;
    RETURN k;
END $_$;


--
-- Name: finish_experiment(uuid, uuid, text, text, text); Type: FUNCTION; Schema: ml_experiments; Owner: -
--

CREATE FUNCTION ml_experiments.finish_experiment(p_run uuid, p_worker uuid, p_hash text, p_status text, p_error text DEFAULT NULL::text) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF p_status NOT IN ('succeeded','failed') THEN RAISE EXCEPTION 'Invalid completion status'; END IF;
    UPDATE ml_experiments.experiment_runs SET status = p_status, completed_at = clock_timestamp(), error = p_error
    WHERE id = p_run AND status = 'running' AND worker_client_id = p_worker AND lease_sha256 = p_hash AND lease_expires_at > clock_timestamp();
    IF NOT FOUND THEN RAISE EXCEPTION 'Unknown, stale or unauthorized worker lease'; END IF;
END $$;


--
-- Name: guard_evaluation_members(); Type: FUNCTION; Schema: ml_experiments; Owner: -
--

CREATE FUNCTION ml_experiments.guard_evaluation_members() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE run_key uuid; eval_key uuid; run_state text;
BEGIN
    IF TG_TABLE_NAME = 'evaluations' THEN
        run_key := CASE WHEN TG_OP = 'DELETE' THEN OLD.run_id ELSE NEW.run_id END;
        IF TG_OP = 'UPDATE' AND (NEW.id, NEW.run_id, NEW.model_id) IS DISTINCT FROM (OLD.id, OLD.run_id, OLD.model_id) THEN
            RAISE EXCEPTION 'Evaluation identity is immutable';
        END IF;
    ELSE
        IF TG_OP = 'UPDATE' AND (NEW.evaluation_id, NEW.model_id) IS DISTINCT FROM (OLD.evaluation_id, OLD.model_id) THEN
            RAISE EXCEPTION 'Confusion cell identity cannot move';
        END IF;
        eval_key := CASE WHEN TG_OP = 'DELETE' THEN OLD.evaluation_id ELSE NEW.evaluation_id END;
        SELECT run_id INTO run_key FROM ml_experiments.evaluations WHERE id = eval_key;
    END IF;
    SELECT status INTO run_state FROM ml_experiments.experiment_runs WHERE id = run_key FOR UPDATE;
    IF run_state IS DISTINCT FROM 'running' THEN RAISE EXCEPTION 'Evaluation inputs are editable only during their run'; END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;


--
-- Name: guard_experiment_run(); Type: FUNCTION; Schema: ml_experiments; Owner: -
--

CREATE FUNCTION ml_experiments.guard_experiment_run() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE parent_run ml_experiments.experiment_runs%ROWTYPE;
BEGIN
    IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'Run history cannot be deleted'; END IF;
    IF TG_OP = 'INSERT' THEN
        IF NEW.status <> 'queued' THEN RAISE EXCEPTION 'Submit queued runs before claiming'; END IF;
        IF NEW.parent_model_id IS NOT NULL THEN
            SELECT r.* INTO parent_run FROM ml_experiments.model_versions m JOIN ml_experiments.experiment_runs r ON r.id = m.run_id
            WHERE m.id = NEW.parent_model_id AND m.state = 'published';
            IF NOT FOUND OR (parent_run.operator_id, parent_run.family, parent_run.condition, parent_run.manifest_id, parent_run.manifest_sha256, parent_run.feature_contract)
                IS DISTINCT FROM (NEW.operator_id, NEW.family, 'source_only'::text, NEW.manifest_id, NEW.manifest_sha256, NEW.feature_contract) THEN
                RAISE EXCEPTION 'Incompatible source parent';
            END IF;
        END IF;
        IF NEW.retry_of_id IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ml_experiments.experiment_runs
            WHERE id = NEW.retry_of_id AND operator_id = NEW.operator_id AND status IN ('failed', 'interrupted')) THEN
            RAISE EXCEPTION 'Retry must reference a failed/interrupted run of the same operator';
        END IF;
        RETURN NEW;
    END IF;
    IF OLD.status IN ('succeeded', 'failed', 'interrupted') THEN RAISE EXCEPTION 'Terminal runs are immutable'; END IF;
    IF (to_jsonb(NEW) - ARRAY['status','worker_client_id','lease_sha256','started_at','heartbeat_at','lease_expires_at','completed_at','error'])
        IS DISTINCT FROM (to_jsonb(OLD) - ARRAY['status','worker_client_id','lease_sha256','started_at','heartbeat_at','lease_expires_at','completed_at','error']) THEN
        RAISE EXCEPTION 'Run inputs are immutable';
    END IF;
    IF OLD.status = 'queued' THEN
        IF NEW.status <> 'running' THEN RAISE EXCEPTION 'A queued run must be claimed'; END IF;
    ELSE
        IF (NEW.worker_client_id, NEW.lease_sha256, NEW.started_at) IS DISTINCT FROM (OLD.worker_client_id, OLD.lease_sha256, OLD.started_at) THEN
            RAISE EXCEPTION 'Lease identity is immutable; retries require a new run';
        END IF;
        IF NEW.status NOT IN ('running', 'succeeded', 'failed', 'interrupted') THEN RAISE EXCEPTION 'Invalid run transition'; END IF;
        IF NEW.status <> 'interrupted' AND OLD.lease_expires_at <= clock_timestamp() THEN RAISE EXCEPTION 'Worker lease expired'; END IF;
        IF NEW.heartbeat_at < OLD.heartbeat_at OR NEW.lease_expires_at < OLD.lease_expires_at THEN RAISE EXCEPTION 'Heartbeat cannot move backwards'; END IF;
    END IF;
    RETURN NEW;
END $$;


--
-- Name: guard_model_members(); Type: FUNCTION; Schema: ml_experiments; Owner: -
--

CREATE FUNCTION ml_experiments.guard_model_members() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE k uuid; state_value text;
BEGIN
    FOR k IN SELECT DISTINCT x FROM unnest(ARRAY[
        CASE WHEN TG_OP <> 'INSERT' THEN OLD.model_id END,
        CASE WHEN TG_OP <> 'DELETE' THEN NEW.model_id END]) x WHERE x IS NOT NULL ORDER BY x LOOP
        SELECT state INTO state_value FROM ml_experiments.model_versions WHERE id = k FOR UPDATE;
        IF state_value IS DISTINCT FROM 'draft' THEN RAISE EXCEPTION 'Published package/class membership is immutable'; END IF;
    END LOOP;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    RETURN NEW;
END $$;


--
-- Name: guard_model_version(); Type: FUNCTION; Schema: ml_experiments; Owner: -
--

CREATE FUNCTION ml_experiments.guard_model_version() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE r ml_experiments.experiment_runs%ROWTYPE; a ml_experiments.artifacts%ROWTYPE; required_purpose text;
BEGIN
    IF TG_OP <> 'INSERT' THEN
        IF OLD.state = 'published' THEN RAISE EXCEPTION 'Published models are immutable'; END IF;
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        IF (NEW.id, NEW.run_id, NEW.created_at) IS DISTINCT FROM (OLD.id, OLD.run_id, OLD.created_at) THEN
            RAISE EXCEPTION 'Model identity is immutable';
        END IF;
    ELSIF NEW.state <> 'draft' THEN RAISE EXCEPTION 'Create a draft package before publishing';
    END IF;
    SELECT * INTO STRICT r FROM ml_experiments.experiment_runs WHERE id = NEW.run_id;
    IF r.kind = 'evaluate' THEN RAISE EXCEPTION 'An evaluation cannot produce a model'; END IF;
    IF NEW.state = 'published' THEN
        IF r.status <> 'succeeded' THEN RAISE EXCEPTION 'Model publication requires a successful run'; END IF;
        SELECT * INTO STRICT a FROM ml_experiments.artifacts WHERE id = NEW.artifact_id;
        IF a.state <> 'verified' OR a.operator_id <> r.operator_id THEN RAISE EXCEPTION 'Model artifact is unverified or belongs to another operator'; END IF;
        IF (SELECT count(*) FROM ml_experiments.model_classes WHERE model_id = NEW.id) < 2 OR NOT EXISTS (
            SELECT 1 FROM ml_experiments.model_classes WHERE model_id = NEW.id AND code = 'rest'
        ) THEN RAISE EXCEPTION 'Model class mapping requires at least two classes including rest'; END IF;
        IF EXISTS (SELECT 1 FROM ml_experiments.model_package_items i JOIN ml_experiments.artifacts x ON x.id = i.artifact_id
                   WHERE i.model_id = NEW.id AND (x.state <> 'verified' OR x.operator_id <> r.operator_id)) THEN
            RAISE EXCEPTION 'Package contains unverified or foreign artifacts';
        END IF;
        required_purpose := CASE NEW.adaptation_method WHEN 'lda_statistics' THEN 'source_statistics'
            WHEN 'svm_weighted' THEN 'source_pool' WHEN 'mlp_replay' THEN 'replay_pool' END;
        IF NEW.adaptation_method <> 'none' AND NEW.adaptation_method <> (CASE r.family
            WHEN 'lda' THEN 'lda_statistics' WHEN 'svm' THEN 'svm_weighted' WHEN 'mlp' THEN 'mlp_replay' END) THEN
            RAISE EXCEPTION 'Adaptation method does not match model family';
        END IF;
        IF required_purpose IS NOT NULL AND NOT EXISTS (SELECT 1 FROM ml_experiments.model_package_items
            WHERE model_id = NEW.id AND purpose = required_purpose) THEN RAISE EXCEPTION 'Required adaptation material is missing'; END IF;
        IF r.parent_model_id IS NOT NULL AND EXISTS (
            (SELECT code FROM ml_experiments.model_classes WHERE model_id = r.parent_model_id
             EXCEPT SELECT code FROM ml_experiments.model_classes WHERE model_id = NEW.id)
            UNION ALL
            (SELECT code FROM ml_experiments.model_classes WHERE model_id = NEW.id
             EXCEPT SELECT code FROM ml_experiments.model_classes WHERE model_id = r.parent_model_id)
        ) THEN RAISE EXCEPTION 'Personal model class mapping differs from parent'; END IF;
    END IF;
    RETURN NEW;
END $$;


--
-- Name: guard_registry_artifact(); Type: FUNCTION; Schema: ml_experiments; Owner: -
--

CREATE FUNCTION ml_experiments.guard_registry_artifact() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF OLD.state = 'verified' THEN RAISE EXCEPTION 'Verified artifact metadata is immutable'; END IF;
    IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
    IF (NEW.id, NEW.operator_id, NEW.created_at) IS DISTINCT FROM (OLD.id, OLD.operator_id, OLD.created_at) THEN
        RAISE EXCEPTION 'Artifact identity is immutable';
    END IF;
    RETURN NEW;
END $$;


--
-- Name: guard_source_lda_run(); Type: FUNCTION; Schema: ml_experiments; Owner: -
--

CREATE FUNCTION ml_experiments.guard_source_lda_run() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF TG_OP = 'DELETE' OR OLD.status IN ('succeeded', 'failed', 'interrupted') THEN
        RAISE EXCEPTION 'Completed experiment runs are immutable';
    END IF;
    IF (NEW.id, NEW.manifest_id, NEW.target_participant_id, NEW.created_at, NEW.idempotency_key, NEW.correlation_id) IS DISTINCT FROM
       (OLD.id, OLD.manifest_id, OLD.target_participant_id, OLD.created_at, OLD.idempotency_key, OLD.correlation_id) THEN
        RAISE EXCEPTION 'Experiment identity is immutable';
    END IF;
    IF NOT ((OLD.status = 'queued' AND NEW.status = 'running') OR
            (OLD.status = 'running' AND NEW.status IN ('running', 'succeeded', 'failed', 'interrupted'))) THEN
        RAISE EXCEPTION 'Invalid experiment run transition';
    END IF;
    IF OLD.status = 'running' AND NEW.status = 'running' AND
       ((NEW.started_at, NEW.completed_at, NEW.model, NEW.metrics, NEW.snapshot, NEW.error, NEW.manifest_checksum, NEW.model_checksum)
        IS DISTINCT FROM (OLD.started_at, OLD.completed_at, OLD.model, OLD.metrics, OLD.snapshot, OLD.error, OLD.manifest_checksum, OLD.model_checksum) OR
        NEW.heartbeat_at IS NULL OR NEW.heartbeat_at < OLD.heartbeat_at) THEN
        RAISE EXCEPTION 'Invalid experiment heartbeat';
    END IF;
    RETURN NEW;
END $$;


--
-- Name: guard_trace_context(); Type: FUNCTION; Schema: ml_experiments; Owner: -
--

CREATE FUNCTION ml_experiments.guard_trace_context() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.trace_context IS DISTINCT FROM OLD.trace_context THEN
        RAISE EXCEPTION 'Experiment trace context is immutable';
    END IF;
    RETURN NEW;
END $$;


--
-- Name: heartbeat_experiment(uuid, uuid, text, integer); Type: FUNCTION; Schema: ml_experiments; Owner: -
--

CREATE FUNCTION ml_experiments.heartbeat_experiment(p_run uuid, p_worker uuid, p_hash text, p_seconds integer DEFAULT 120) RETURNS void
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF p_seconds NOT BETWEEN 10 AND 3600 THEN RAISE EXCEPTION 'Invalid lease duration'; END IF;
    UPDATE ml_experiments.experiment_runs SET heartbeat_at = clock_timestamp(),
        lease_expires_at = greatest(lease_expires_at, clock_timestamp()+make_interval(secs=>p_seconds))
    WHERE id = p_run AND status = 'running' AND worker_client_id = p_worker AND lease_sha256 = p_hash AND lease_expires_at > clock_timestamp();
    IF NOT FOUND THEN RAISE EXCEPTION 'Unknown, stale or unauthorized worker lease'; END IF;
END $$;


--
-- Name: interrupt_expired_experiments(); Type: FUNCTION; Schema: ml_experiments; Owner: -
--

CREATE FUNCTION ml_experiments.interrupt_expired_experiments() RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE n bigint;
BEGIN
    UPDATE ml_experiments.experiment_runs SET status = 'interrupted', completed_at = clock_timestamp(), error = 'Worker lease expired'
    WHERE status = 'running' AND lease_expires_at <= clock_timestamp();
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END $$;


--
-- Name: set_model_checksum(); Type: FUNCTION; Schema: ml_experiments; Owner: -
--

CREATE FUNCTION ml_experiments.set_model_checksum() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    IF NEW.status = 'succeeded' THEN
        NEW.model_checksum := encode(sha256(convert_to(NEW.model::text, 'UTF8')), 'hex');
    END IF;
    RETURN NEW;
END $$;


--
-- Name: validate_run_output(); Type: FUNCTION; Schema: ml_experiments; Owner: -
--

CREATE FUNCTION ml_experiments.validate_run_output() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
DECLARE r ml_experiments.experiment_runs%ROWTYPE; e ml_experiments.evaluations%ROWTYPE;
    mr ml_experiments.experiment_runs%ROWTYPE; n bigint; total numeric; diagonal numeric;
    rest_total numeric; rest_false numeric; calculated_f1 numeric;
BEGIN
    SELECT * INTO STRICT r FROM ml_experiments.experiment_runs WHERE id = NEW.id;
    IF r.status <> 'succeeded' THEN RETURN NULL; END IF;
    IF r.kind <> 'evaluate' THEN
        IF NOT EXISTS (SELECT 1 FROM ml_experiments.model_versions WHERE run_id = r.id AND state = 'published') THEN
            RAISE EXCEPTION 'Successful fitting run requires a published model';
        END IF;
        RETURN NULL;
    END IF;
    SELECT * INTO e FROM ml_experiments.evaluations WHERE run_id = r.id AND model_id = r.evaluated_model_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Successful evaluation requires matching metrics'; END IF;
    SELECT x.* INTO mr FROM ml_experiments.model_versions m JOIN ml_experiments.experiment_runs x ON x.id = m.run_id
    WHERE m.id = e.model_id AND m.state = 'published';
    IF NOT FOUND OR (mr.operator_id, mr.family, mr.condition, mr.manifest_id, mr.manifest_sha256, mr.feature_contract, mr.calibration_subset_id)
        IS DISTINCT FROM (r.operator_id, r.family, r.condition, r.manifest_id, r.manifest_sha256, r.feature_contract, r.calibration_subset_id) THEN
        RAISE EXCEPTION 'Evaluation model and frozen conditions are incompatible';
    END IF;
    IF mr.target_participant_id IS NOT NULL AND mr.target_participant_id <> r.target_participant_id THEN RAISE EXCEPTION 'Model target mismatch'; END IF;
    SELECT count(*) INTO n FROM ml_experiments.model_classes WHERE model_id = e.model_id;
    IF (SELECT count(*) FROM ml_experiments.confusion_counts WHERE evaluation_id = e.id) <> n*n THEN
        RAISE EXCEPTION 'Confusion matrix must contain every class pair including zeros';
    END IF;
    SELECT sum(count), sum(count) FILTER (WHERE actual_class = predicted_class),
        coalesce(sum(count) FILTER (WHERE actual_class = 'rest'),0),
        coalesce(sum(count) FILTER (WHERE actual_class = 'rest' AND predicted_class <> 'rest'),0)
    INTO total, diagonal, rest_total, rest_false FROM ml_experiments.confusion_counts WHERE evaluation_id = e.id;
    IF total <= 0 THEN RAISE EXCEPTION 'Evaluation requires test windows'; END IF;
    SELECT avg(CASE WHEN actual_n + predicted_n = 0 THEN 0 ELSE 2*true_n/(actual_n+predicted_n) END)
    INTO calculated_f1 FROM (
        SELECT c.code,
            coalesce(sum(x.count) FILTER (WHERE x.actual_class = c.code),0)::numeric actual_n,
            coalesce(sum(x.count) FILTER (WHERE x.predicted_class = c.code),0)::numeric predicted_n,
            coalesce(sum(x.count) FILTER (WHERE x.actual_class = c.code AND x.predicted_class = c.code),0)::numeric true_n
        FROM ml_experiments.model_classes c CROSS JOIN ml_experiments.confusion_counts x
        WHERE c.model_id = e.model_id AND x.evaluation_id = e.id GROUP BY c.code
    ) counts;
    IF abs(e.accuracy - coalesce(diagonal,0)/total) > 1e-9 OR abs(e.macro_f1-calculated_f1) > 1e-9 THEN
        RAISE EXCEPTION 'Metrics disagree with confusion counts';
    END IF;
    IF (rest_total = 0 AND e.rest_false_activation_rate IS NOT NULL) OR
       (rest_total > 0 AND (e.rest_false_activation_rate IS NULL OR abs(e.rest_false_activation_rate-rest_false/rest_total) > 1e-9)) THEN
        RAISE EXCEPTION 'Rest false-activation metric is inconsistent';
    END IF;
    RETURN NULL;
END $$;


--
-- Name: guard_desktop_session(); Type: FUNCTION; Schema: recognition; Owner: -
--

CREATE FUNCTION recognition.guard_desktop_session() RETURNS trigger
    LANGUAGE plpgsql
    AS $$
BEGIN
    RAISE EXCEPTION 'Published desktop session reports are immutable';
END $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: calibration_items; Type: TABLE; Schema: data_protocol; Owner: -
--

CREATE TABLE data_protocol.calibration_items (
    subset_id uuid NOT NULL,
    unit_id uuid NOT NULL
);


--
-- Name: labelled_segments; Type: TABLE; Schema: data_protocol; Owner: -
--

CREATE TABLE data_protocol.labelled_segments (
    id uuid NOT NULL,
    recording_id uuid NOT NULL,
    gesture_code text NOT NULL,
    repetition_key text NOT NULL,
    start_sample bigint NOT NULL,
    end_sample bigint NOT NULL,
    CONSTRAINT labelled_segments_check CHECK ((end_sample > start_sample)),
    CONSTRAINT labelled_segments_gesture_code_check CHECK ((gesture_code ~ '^[A-Za-z0-9_-]{1,100}$'::text)),
    CONSTRAINT labelled_segments_repetition_key_check CHECK ((length(TRIM(BOTH FROM repetition_key)) > 0)),
    CONSTRAINT labelled_segments_start_sample_check CHECK ((start_sample >= 0))
);


--
-- Name: manifest_units; Type: TABLE; Schema: data_protocol; Owner: -
--

CREATE TABLE data_protocol.manifest_units (
    id uuid NOT NULL,
    manifest_id uuid NOT NULL,
    participant_id uuid NOT NULL,
    category text NOT NULL,
    segment_id uuid NOT NULL,
    role text NOT NULL,
    CONSTRAINT manifest_units_check CHECK ((((category = 'source'::text) AND (role = 'source_train'::text)) OR ((category = 'development'::text) AND (role = 'development_validation'::text)) OR ((category = 'target'::text) AND (role = ANY (ARRAY['target_calibration'::text, 'target_test'::text]))))),
    CONSTRAINT manifest_units_role_check CHECK ((role = ANY (ARRAY['source_train'::text, 'development_validation'::text, 'target_calibration'::text, 'target_test'::text])))
);


--
-- Name: recordings; Type: TABLE; Schema: data_protocol; Owner: -
--

CREATE TABLE data_protocol.recordings (
    id uuid NOT NULL,
    participant_id uuid NOT NULL,
    sample_rate_hz numeric NOT NULL,
    sample_count integer NOT NULL,
    artifact_sha256 character varying(64) NOT NULL,
    CONSTRAINT recordings_artifact_sha256_check CHECK (((artifact_sha256)::text ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT recordings_sample_count_check CHECK (((sample_count >= 1) AND (sample_count <= 10000))),
    CONSTRAINT recordings_sample_rate_hz_check CHECK (((sample_rate_hz > (0)::numeric) AND (sample_rate_hz <= (100000)::numeric)))
);


--
-- Name: calibration_durations; Type: VIEW; Schema: data_protocol; Owner: -
--

CREATE VIEW data_protocol.calibration_durations AS
 WITH intervals AS (
         SELECT i.subset_id,
            s.gesture_code,
            r.artifact_sha256,
            r.sample_rate_hz,
            count(DISTINCT s.repetition_key) AS repetitions,
            range_agg(int8range(s.start_sample, s.end_sample, '[)'::text)) AS sample_intervals
           FROM (((data_protocol.calibration_items i
             JOIN data_protocol.manifest_units u ON ((u.id = i.unit_id)))
             JOIN data_protocol.labelled_segments s ON ((s.id = u.segment_id)))
             JOIN data_protocol.recordings r ON ((r.id = s.recording_id)))
          GROUP BY i.subset_id, s.gesture_code, r.artifact_sha256, r.sample_rate_hz
        )
 SELECT intervals.subset_id,
    intervals.gesture_code,
    sum((((upper(samples.samples) - lower(samples.samples)))::numeric / intervals.sample_rate_hz)) AS unique_seconds
   FROM (intervals
     CROSS JOIN LATERAL unnest(intervals.sample_intervals) samples(samples))
  GROUP BY intervals.subset_id, intervals.gesture_code;


--
-- Name: calibration_subsets; Type: TABLE; Schema: data_protocol; Owner: -
--

CREATE TABLE data_protocol.calibration_subsets (
    id uuid NOT NULL,
    manifest_id uuid NOT NULL,
    participant_id uuid NOT NULL,
    category text DEFAULT 'target'::text NOT NULL,
    selection_version text NOT NULL,
    budget_per_gesture integer NOT NULL,
    state text DEFAULT 'draft'::text NOT NULL,
    CONSTRAINT calibration_subsets_budget_per_gesture_check CHECK ((budget_per_gesture > 0)),
    CONSTRAINT calibration_subsets_category_check CHECK ((category = 'target'::text)),
    CONSTRAINT calibration_subsets_selection_version_check CHECK ((length(TRIM(BOTH FROM selection_version)) > 0)),
    CONSTRAINT calibration_subsets_state_check CHECK ((state = ANY (ARRAY['draft'::text, 'frozen'::text])))
);


--
-- Name: client_publications; Type: TABLE; Schema: data_protocol; Owner: -
--

CREATE TABLE data_protocol.client_publications (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    operator_id uuid NOT NULL,
    client_id uuid NOT NULL,
    local_recording_id uuid NOT NULL,
    recording_id uuid NOT NULL,
    payload_sha256 text NOT NULL,
    received_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT client_publications_payload_sha256_check CHECK ((payload_sha256 ~ '^[0-9a-f]{64}$'::text))
);


--
-- Name: manifest_participants; Type: TABLE; Schema: data_protocol; Owner: -
--

CREATE TABLE data_protocol.manifest_participants (
    manifest_id uuid NOT NULL,
    participant_id uuid NOT NULL,
    category text NOT NULL,
    CONSTRAINT manifest_participants_category_check CHECK ((category = ANY (ARRAY['source'::text, 'development'::text, 'target'::text])))
);


--
-- Name: participants; Type: TABLE; Schema: data_protocol; Owner: -
--

CREATE TABLE data_protocol.participants (
    id uuid NOT NULL,
    pseudonym character varying(100) NOT NULL,
    CONSTRAINT participants_pseudonym_format CHECK (((pseudonym)::text ~ '^[A-Za-z0-9_-]{1,100}$'::text))
);


--
-- Name: protocol_versions; Type: TABLE; Schema: data_protocol; Owner: -
--

CREATE TABLE data_protocol.protocol_versions (
    id uuid NOT NULL,
    name character varying(120) NOT NULL,
    version integer NOT NULL,
    gesture_codes text[] NOT NULL,
    CONSTRAINT protocol_versions_gesture_codes_check CHECK (((cardinality(gesture_codes) > 0) AND ('rest'::text = ANY (gesture_codes)))),
    CONSTRAINT protocol_versions_version_check CHECK ((version > 0))
);


--
-- Name: recording_provenance; Type: TABLE; Schema: data_protocol; Owner: -
--

CREATE TABLE data_protocol.recording_provenance (
    recording_id uuid NOT NULL,
    operator_id uuid NOT NULL,
    source_kind text NOT NULL,
    source_name text NOT NULL,
    source_version text NOT NULL,
    source_participant_key text NOT NULL,
    original_signal_key text NOT NULL,
    original_sha256 text NOT NULL,
    original_start_sample bigint NOT NULL,
    original_end_sample bigint NOT NULL,
    channel_map jsonb NOT NULL,
    units text NOT NULL,
    identity_method_version text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT recording_provenance_channel_map_check CHECK (((jsonb_typeof(channel_map) = 'array'::text) AND (jsonb_array_length(channel_map) > 0))),
    CONSTRAINT recording_provenance_check CHECK ((original_end_sample > original_start_sample)),
    CONSTRAINT recording_provenance_identity_method_version_check CHECK ((length(btrim(identity_method_version)) > 0)),
    CONSTRAINT recording_provenance_original_sha256_check CHECK ((original_sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT recording_provenance_original_signal_key_check CHECK ((length(btrim(original_signal_key)) > 0)),
    CONSTRAINT recording_provenance_original_start_sample_check CHECK ((original_start_sample >= 0)),
    CONSTRAINT recording_provenance_source_kind_check CHECK ((source_kind = ANY (ARRAY['synthetic'::text, 'dataset'::text, 'device'::text]))),
    CONSTRAINT recording_provenance_source_name_check CHECK ((length(btrim(source_name)) > 0)),
    CONSTRAINT recording_provenance_source_participant_key_check CHECK ((length(btrim(source_participant_key)) > 0)),
    CONSTRAINT recording_provenance_source_version_check CHECK ((length(btrim(source_version)) > 0)),
    CONSTRAINT recording_provenance_units_check CHECK ((length(btrim(units)) > 0))
);


--
-- Name: TABLE recording_provenance; Type: COMMENT; Schema: data_protocol; Owner: -
--

COMMENT ON TABLE data_protocol.recording_provenance IS 'New publication metadata; legacy synthetic recordings are not retroactively asserted research-ready. Byte/identity and transformation validation belongs to ingestion.';


--
-- Name: research_manifests; Type: TABLE; Schema: data_protocol; Owner: -
--

CREATE TABLE data_protocol.research_manifests (
    id uuid NOT NULL,
    protocol_id uuid NOT NULL,
    name character varying(120) NOT NULL,
    version integer NOT NULL,
    state text DEFAULT 'draft'::text NOT NULL,
    checksum character varying(64),
    frozen_at timestamp with time zone,
    CONSTRAINT research_manifests_check CHECK ((((state = 'draft'::text) AND (checksum IS NULL) AND (frozen_at IS NULL)) OR ((state = 'frozen'::text) AND (checksum IS NOT NULL) AND ((checksum)::text ~ '^[0-9a-f]{64}$'::text) AND (frozen_at IS NOT NULL)))),
    CONSTRAINT research_manifests_state_check CHECK ((state = ANY (ARRAY['draft'::text, 'frozen'::text]))),
    CONSTRAINT research_manifests_version_check CHECK ((version > 0))
);


--
-- Name: synthetic_splits; Type: TABLE; Schema: data_protocol; Owner: -
--

CREATE TABLE data_protocol.synthetic_splits (
    id uuid NOT NULL,
    source_recording_id uuid NOT NULL,
    test_recording_id uuid NOT NULL,
    checksum character varying(64) NOT NULL,
    CONSTRAINT synthetic_splits_check CHECK ((source_recording_id <> test_recording_id)),
    CONSTRAINT synthetic_splits_checksum_check CHECK (((checksum)::text ~ '^[0-9a-f]{64}$'::text))
);


--
-- Name: access_sessions; Type: TABLE; Schema: identity; Owner: -
--

CREATE TABLE identity.access_sessions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    operator_id uuid NOT NULL,
    client_id uuid,
    token_sha256 text NOT NULL,
    scope text NOT NULL,
    issued_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    revoked_at timestamp with time zone,
    CONSTRAINT access_sessions_check CHECK ((expires_at > issued_at)),
    CONSTRAINT access_sessions_check1 CHECK (((revoked_at IS NULL) OR (revoked_at >= issued_at))),
    CONSTRAINT access_sessions_check2 CHECK ((((scope = 'web'::text) AND (client_id IS NULL)) OR ((scope <> 'web'::text) AND (client_id IS NOT NULL)))),
    CONSTRAINT access_sessions_scope_check CHECK ((scope = ANY (ARRAY['web'::text, 'desktop'::text, 'training_worker'::text]))),
    CONSTRAINT access_sessions_token_sha256_check CHECK ((token_sha256 ~ '^[0-9a-f]{64}$'::text))
);


--
-- Name: COLUMN access_sessions.token_sha256; Type: COMMENT; Schema: identity; Owner: -
--

COMMENT ON COLUMN identity.access_sessions.token_sha256 IS 'Digest of a high-entropy opaque token. Never store raw bearer/refresh tokens.';


--
-- Name: clients; Type: TABLE; Schema: identity; Owner: -
--

CREATE TABLE identity.clients (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    operator_id uuid NOT NULL,
    kind text NOT NULL,
    name text NOT NULL,
    platform text NOT NULL,
    state text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT clients_kind_check CHECK ((kind = ANY (ARRAY['desktop'::text, 'training_worker'::text]))),
    CONSTRAINT clients_name_check CHECK (((length(btrim(name)) >= 1) AND (length(btrim(name)) <= 120))),
    CONSTRAINT clients_platform_check CHECK (((length(btrim(platform)) >= 1) AND (length(btrim(platform)) <= 120))),
    CONSTRAINT clients_state_check CHECK ((state = ANY (ARRAY['active'::text, 'revoked'::text])))
);


--
-- Name: operators; Type: TABLE; Schema: identity; Owner: -
--

CREATE TABLE identity.operators (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    email text NOT NULL,
    display_name text NOT NULL,
    password_hash text NOT NULL,
    role text DEFAULT 'operator'::text NOT NULL,
    state text DEFAULT 'active'::text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT operators_display_name_check CHECK (((length(btrim(display_name)) >= 1) AND (length(btrim(display_name)) <= 120))),
    CONSTRAINT operators_email_check CHECK (((email = lower(btrim(email))) AND (length(email) <= 320) AND (email ~ '^[^[:space:]@]+@[^[:space:]@]+\.[^[:space:]@]+$'::text))),
    CONSTRAINT operators_password_hash_check CHECK (((password_hash ~~ '$argon2id$v=19$%'::text) AND ((length(password_hash) >= 40) AND (length(password_hash) <= 1024)))),
    CONSTRAINT operators_role_check CHECK ((role = ANY (ARRAY['operator'::text, 'reviewer'::text, 'administrator'::text]))),
    CONSTRAINT operators_state_check CHECK ((state = ANY (ARRAY['active'::text, 'disabled'::text])))
);


--
-- Name: COLUMN operators.password_hash; Type: COMMENT; Schema: identity; Owner: -
--

COMMENT ON COLUMN identity.operators.password_hash IS 'Encoded Argon2id hash; service must validate algorithm parameters and never accept this value from an untrusted client.';


--
-- Name: operator_directory; Type: VIEW; Schema: identity; Owner: -
--

CREATE VIEW identity.operator_directory AS
 SELECT id,
    display_name,
    role,
    state,
    created_at
   FROM identity.operators;


--
-- Name: valid_session_ids; Type: VIEW; Schema: identity; Owner: -
--

CREATE VIEW identity.valid_session_ids AS
 SELECT s.id,
    s.operator_id,
    s.client_id,
    s.scope,
    s.expires_at
   FROM ((identity.access_sessions s
     JOIN identity.operators o ON ((o.id = s.operator_id)))
     LEFT JOIN identity.clients c ON ((c.id = s.client_id)))
  WHERE ((o.state = 'active'::text) AND (s.revoked_at IS NULL) AND (s.expires_at > CURRENT_TIMESTAMP) AND ((s.client_id IS NULL) OR ((c.state = 'active'::text) AND (c.kind = s.scope))));


--
-- Name: artifacts; Type: TABLE; Schema: ml_experiments; Owner: -
--

CREATE TABLE ml_experiments.artifacts (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    operator_id uuid NOT NULL,
    storage_key text NOT NULL,
    sha256 text NOT NULL,
    size_bytes bigint NOT NULL,
    media_type text NOT NULL,
    state text DEFAULT 'staged'::text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    verified_at timestamp with time zone,
    CONSTRAINT artifacts_check CHECK ((((state = 'staged'::text) AND (verified_at IS NULL)) OR ((state = 'verified'::text) AND (verified_at IS NOT NULL)))),
    CONSTRAINT artifacts_media_type_check CHECK ((length(btrim(media_type)) > 0)),
    CONSTRAINT artifacts_sha256_check CHECK ((sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT artifacts_size_bytes_check CHECK ((size_bytes > 0)),
    CONSTRAINT artifacts_state_check CHECK ((state = ANY (ARRAY['staged'::text, 'verified'::text]))),
    CONSTRAINT artifacts_storage_key_check CHECK ((length(btrim(storage_key)) > 0))
);


--
-- Name: COLUMN artifacts.verified_at; Type: COMMENT; Schema: ml_experiments; Owner: -
--

COMMENT ON COLUMN ml_experiments.artifacts.verified_at IS 'Trusted storage verification attestation, not proof of bytes by PostgreSQL.';


--
-- Name: confusion_counts; Type: TABLE; Schema: ml_experiments; Owner: -
--

CREATE TABLE ml_experiments.confusion_counts (
    evaluation_id uuid NOT NULL,
    model_id uuid NOT NULL,
    actual_class text NOT NULL,
    predicted_class text NOT NULL,
    count bigint NOT NULL,
    CONSTRAINT confusion_counts_count_check CHECK ((count >= 0))
);


--
-- Name: evaluations; Type: TABLE; Schema: ml_experiments; Owner: -
--

CREATE TABLE ml_experiments.evaluations (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    run_id uuid NOT NULL,
    model_id uuid NOT NULL,
    accuracy double precision NOT NULL,
    macro_f1 double precision NOT NULL,
    rest_false_activation_rate double precision,
    rest_missing_reason text,
    CONSTRAINT evaluations_accuracy_check CHECK (((accuracy >= (0)::double precision) AND (accuracy <= (1)::double precision))),
    CONSTRAINT evaluations_check CHECK ((((rest_false_activation_rate IS NOT NULL) AND (rest_missing_reason IS NULL)) OR ((rest_false_activation_rate IS NULL) AND (rest_missing_reason IS NOT NULL) AND (length(btrim(rest_missing_reason)) > 0)))),
    CONSTRAINT evaluations_macro_f1_check CHECK (((macro_f1 >= (0)::double precision) AND (macro_f1 <= (1)::double precision))),
    CONSTRAINT evaluations_rest_false_activation_rate_check CHECK (((rest_false_activation_rate >= (0)::double precision) AND (rest_false_activation_rate <= (1)::double precision)))
);


--
-- Name: experiment_runs; Type: TABLE; Schema: ml_experiments; Owner: -
--

CREATE TABLE ml_experiments.experiment_runs (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    operator_id uuid NOT NULL,
    submission_key text NOT NULL,
    retry_of_id uuid,
    kind text NOT NULL,
    family text NOT NULL,
    condition text NOT NULL,
    execution_location text NOT NULL,
    manifest_id uuid NOT NULL,
    manifest_sha256 text NOT NULL,
    target_participant_id uuid,
    calibration_subset_id uuid,
    parent_model_id uuid,
    evaluated_model_id uuid,
    feature_contract jsonb NOT NULL,
    input_snapshot jsonb NOT NULL,
    parameters jsonb NOT NULL,
    seed bigint NOT NULL,
    software_version text NOT NULL,
    status text DEFAULT 'queued'::text NOT NULL,
    worker_client_id uuid,
    lease_sha256 text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    started_at timestamp with time zone,
    heartbeat_at timestamp with time zone,
    lease_expires_at timestamp with time zone,
    completed_at timestamp with time zone,
    error text,
    CONSTRAINT experiment_runs_check CHECK ((((condition = 'source_only'::text) AND (calibration_subset_id IS NULL)) OR ((condition <> 'source_only'::text) AND (calibration_subset_id IS NOT NULL) AND (target_participant_id IS NOT NULL)))),
    CONSTRAINT experiment_runs_check1 CHECK ((((kind = 'source_train'::text) AND (condition = 'source_only'::text) AND (execution_location = 'local_workstation'::text)) OR ((kind = 'personalise'::text) AND (condition = 'personalised'::text)) OR ((kind = 'target_train'::text) AND (condition = 'target_only'::text)) OR (kind = 'evaluate'::text))),
    CONSTRAINT experiment_runs_check2 CHECK ((((kind = 'personalise'::text) AND (parent_model_id IS NOT NULL)) OR ((kind <> 'personalise'::text) AND (parent_model_id IS NULL)))),
    CONSTRAINT experiment_runs_check3 CHECK ((((kind = 'evaluate'::text) AND (evaluated_model_id IS NOT NULL) AND (target_participant_id IS NOT NULL)) OR ((kind <> 'evaluate'::text) AND (evaluated_model_id IS NULL)))),
    CONSTRAINT experiment_runs_check4 CHECK ((((status = 'queued'::text) AND (started_at IS NULL) AND (heartbeat_at IS NULL) AND (lease_expires_at IS NULL) AND (worker_client_id IS NULL) AND (lease_sha256 IS NULL) AND (completed_at IS NULL) AND (error IS NULL)) OR ((status <> 'queued'::text) AND (worker_client_id IS NOT NULL) AND (lease_sha256 IS NOT NULL) AND (started_at IS NOT NULL) AND (heartbeat_at IS NOT NULL) AND (lease_expires_at IS NOT NULL) AND (heartbeat_at >= started_at) AND (lease_expires_at > heartbeat_at) AND (((status = 'running'::text) AND (completed_at IS NULL) AND (error IS NULL)) OR ((status = 'succeeded'::text) AND (completed_at IS NOT NULL) AND (completed_at >= started_at) AND (error IS NULL)) OR ((status = ANY (ARRAY['failed'::text, 'interrupted'::text])) AND (completed_at IS NOT NULL) AND (completed_at >= started_at) AND (error IS NOT NULL) AND (length(btrim(error)) > 0)))))),
    CONSTRAINT experiment_runs_condition_check CHECK ((condition = ANY (ARRAY['source_only'::text, 'personalised'::text, 'target_only'::text]))),
    CONSTRAINT experiment_runs_execution_location_check CHECK ((execution_location = ANY (ARRAY['local_workstation'::text, 'desktop'::text]))),
    CONSTRAINT experiment_runs_family_check CHECK ((family = ANY (ARRAY['lda'::text, 'svm'::text, 'mlp'::text]))),
    CONSTRAINT experiment_runs_feature_contract_check CHECK (((jsonb_typeof(feature_contract) = 'object'::text) AND (feature_contract ? 'version'::text) AND (jsonb_typeof((feature_contract -> 'version'::text)) = 'string'::text) AND (length(btrim((feature_contract ->> 'version'::text))) > 0))),
    CONSTRAINT experiment_runs_input_snapshot_check CHECK ((jsonb_typeof(input_snapshot) = 'object'::text)),
    CONSTRAINT experiment_runs_kind_check CHECK ((kind = ANY (ARRAY['source_train'::text, 'personalise'::text, 'target_train'::text, 'evaluate'::text]))),
    CONSTRAINT experiment_runs_lease_sha256_check CHECK ((lease_sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT experiment_runs_manifest_sha256_check CHECK ((manifest_sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT experiment_runs_parameters_check CHECK ((jsonb_typeof(parameters) = 'object'::text)),
    CONSTRAINT experiment_runs_software_version_check CHECK ((length(btrim(software_version)) > 0)),
    CONSTRAINT experiment_runs_status_check CHECK ((status = ANY (ARRAY['queued'::text, 'running'::text, 'succeeded'::text, 'failed'::text, 'interrupted'::text]))),
    CONSTRAINT experiment_runs_submission_key_check CHECK (((length(btrim(submission_key)) >= 1) AND (length(btrim(submission_key)) <= 120)))
);


--
-- Name: COLUMN experiment_runs.operator_id; Type: COMMENT; Schema: ml_experiments; Owner: -
--

COMMENT ON COLUMN ml_experiments.experiment_runs.operator_id IS 'External identity reference. API validates active operator, client ownership and authorization before calling service-owned functions.';


--
-- Name: model_classes; Type: TABLE; Schema: ml_experiments; Owner: -
--

CREATE TABLE ml_experiments.model_classes (
    model_id uuid NOT NULL,
    code text NOT NULL,
    "position" integer NOT NULL,
    CONSTRAINT model_classes_code_check CHECK ((code ~ '^[A-Za-z0-9_-]{1,100}$'::text)),
    CONSTRAINT model_classes_position_check CHECK (("position" >= 0))
);


--
-- Name: model_package_items; Type: TABLE; Schema: ml_experiments; Owner: -
--

CREATE TABLE ml_experiments.model_package_items (
    model_id uuid NOT NULL,
    purpose text NOT NULL,
    artifact_id uuid NOT NULL,
    CONSTRAINT model_package_items_purpose_check CHECK ((purpose = ANY (ARRAY['source_statistics'::text, 'source_pool'::text, 'replay_pool'::text, 'configuration'::text])))
);


--
-- Name: model_versions; Type: TABLE; Schema: ml_experiments; Owner: -
--

CREATE TABLE ml_experiments.model_versions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    run_id uuid NOT NULL,
    artifact_id uuid NOT NULL,
    name text NOT NULL,
    adaptation_method text DEFAULT 'none'::text NOT NULL,
    state text DEFAULT 'draft'::text NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    published_at timestamp with time zone,
    CONSTRAINT model_versions_adaptation_method_check CHECK ((adaptation_method = ANY (ARRAY['none'::text, 'lda_statistics'::text, 'svm_weighted'::text, 'mlp_replay'::text]))),
    CONSTRAINT model_versions_check CHECK ((((state = 'draft'::text) AND (published_at IS NULL)) OR ((state = 'published'::text) AND (published_at IS NOT NULL)))),
    CONSTRAINT model_versions_name_check CHECK (((length(btrim(name)) >= 1) AND (length(btrim(name)) <= 160))),
    CONSTRAINT model_versions_state_check CHECK ((state = ANY (ARRAY['draft'::text, 'published'::text])))
);


--
-- Name: outbox_events; Type: TABLE; Schema: ml_experiments; Owner: -
--

CREATE TABLE ml_experiments.outbox_events (
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    event_type character varying(100) NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    published_at timestamp with time zone,
    CONSTRAINT outbox_events_event_type_check CHECK (((event_type)::text = 'ModelPublished'::text))
);


--
-- Name: published_models; Type: VIEW; Schema: ml_experiments; Owner: -
--

CREATE VIEW ml_experiments.published_models AS
 SELECT m.id,
    m.name,
    m.run_id,
    r.operator_id,
    r.family,
    r.condition,
    r.parent_model_id,
    r.calibration_subset_id,
    r.manifest_id,
    r.manifest_sha256,
    r.feature_contract,
    m.adaptation_method,
    a.sha256,
    a.size_bytes,
    m.published_at
   FROM ((ml_experiments.model_versions m
     JOIN ml_experiments.experiment_runs r ON ((r.id = m.run_id)))
     JOIN ml_experiments.artifacts a ON ((a.id = m.artifact_id)))
  WHERE ((m.state = 'published'::text) AND (r.status = 'succeeded'::text));


--
-- Name: reviewer_results; Type: VIEW; Schema: ml_experiments; Owner: -
--

CREATE VIEW ml_experiments.reviewer_results AS
 SELECT e.id,
    e.model_id,
    e.run_id,
    r.family,
    r.condition,
    r.manifest_id,
    r.manifest_sha256,
    r.target_participant_id,
    r.calibration_subset_id,
    r.feature_contract,
    r.seed,
    r.software_version,
    e.accuracy,
    e.macro_f1,
    e.rest_false_activation_rate,
    e.rest_missing_reason
   FROM (ml_experiments.evaluations e
     JOIN ml_experiments.experiment_runs r ON ((r.id = e.run_id)))
  WHERE (r.status = 'succeeded'::text);


--
-- Name: signal_summary_jobs; Type: TABLE; Schema: ml_experiments; Owner: -
--

CREATE TABLE ml_experiments.signal_summary_jobs (
    id uuid NOT NULL,
    split_id uuid NOT NULL,
    status character varying(20) NOT NULL,
    split_checksum character varying(64),
    result jsonb,
    error character varying(100),
    CONSTRAINT signal_summary_jobs_check CHECK (((((status)::text = 'running'::text) AND (result IS NULL) AND (error IS NULL) AND (split_checksum IS NULL)) OR (((status)::text = 'succeeded'::text) AND (result IS NOT NULL) AND (error IS NULL) AND ((split_checksum)::text ~ '^[0-9a-f]{64}$'::text)) OR (((status)::text = 'failed'::text) AND (result IS NULL) AND (error IS NOT NULL) AND (split_checksum IS NULL)))),
    CONSTRAINT signal_summary_jobs_status_check CHECK (((status)::text = ANY ((ARRAY['running'::character varying, 'succeeded'::character varying, 'failed'::character varying])::text[])))
);


--
-- Name: source_lda_runs; Type: TABLE; Schema: ml_experiments; Owner: -
--

CREATE TABLE ml_experiments.source_lda_runs (
    id uuid NOT NULL,
    manifest_id uuid NOT NULL,
    target_participant_id uuid NOT NULL,
    status character varying(20) NOT NULL,
    manifest_checksum character varying(64),
    snapshot jsonb,
    model jsonb,
    metrics jsonb,
    error text,
    created_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    completed_at timestamp with time zone,
    model_checksum character varying(64),
    started_at timestamp with time zone,
    heartbeat_at timestamp with time zone,
    idempotency_key character varying(100),
    correlation_id character varying(64) DEFAULT 'legacy'::character varying NOT NULL,
    trace_context jsonb DEFAULT '{}'::jsonb NOT NULL,
    CONSTRAINT source_lda_runs_state_v2 CHECK (((((status)::text = 'queued'::text) AND (started_at IS NULL) AND (heartbeat_at IS NULL) AND (completed_at IS NULL) AND (manifest_checksum IS NULL) AND (snapshot IS NULL) AND (model IS NULL) AND (metrics IS NULL) AND (error IS NULL)) OR (((status)::text = 'running'::text) AND (started_at IS NOT NULL) AND (heartbeat_at IS NOT NULL) AND (completed_at IS NULL) AND (manifest_checksum IS NULL) AND (snapshot IS NULL) AND (model IS NULL) AND (metrics IS NULL) AND (error IS NULL)) OR (((status)::text = 'succeeded'::text) AND (completed_at IS NOT NULL) AND (manifest_checksum IS NOT NULL) AND ((manifest_checksum)::text ~ '^[0-9a-f]{64}$'::text) AND (snapshot IS NOT NULL) AND (model IS NOT NULL) AND (metrics IS NOT NULL) AND (error IS NULL)) OR (((status)::text = ANY ((ARRAY['failed'::character varying, 'interrupted'::character varying])::text[])) AND (completed_at IS NOT NULL) AND (snapshot IS NULL) AND (model IS NULL) AND (metrics IS NULL) AND (error IS NOT NULL)))),
    CONSTRAINT source_lda_runs_status_v2 CHECK (((status)::text = ANY ((ARRAY['queued'::character varying, 'running'::character varying, 'succeeded'::character varying, 'failed'::character varying, 'interrupted'::character varying])::text[]))),
    CONSTRAINT source_lda_runs_trace_context_check CHECK ((jsonb_typeof(trace_context) = 'object'::text))
);


--
-- Name: service_schema_migrations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.service_schema_migrations (
    service text NOT NULL,
    name text NOT NULL,
    checksum character(64) NOT NULL,
    applied_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: desktop_sessions; Type: TABLE; Schema: recognition; Owner: -
--

CREATE TABLE recognition.desktop_sessions (
    id uuid DEFAULT gen_random_uuid() NOT NULL,
    operator_id uuid NOT NULL,
    client_id uuid NOT NULL,
    local_session_id uuid NOT NULL,
    model_version_id uuid NOT NULL,
    model_sha256 text NOT NULL,
    feature_version text NOT NULL,
    mode text NOT NULL,
    recording_id uuid,
    status text NOT NULL,
    started_at timestamp with time zone NOT NULL,
    ended_at timestamp with time zone NOT NULL,
    termination_reason text NOT NULL,
    neutral_confirmed boolean NOT NULL,
    prediction_count bigint NOT NULL,
    processing_p95_ms double precision,
    display_p95_ms double precision,
    timing_scope text NOT NULL,
    payload_sha256 text NOT NULL,
    received_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT desktop_sessions_check CHECK ((ended_at >= started_at)),
    CONSTRAINT desktop_sessions_check1 CHECK (((mode <> 'replay'::text) OR (recording_id IS NOT NULL))),
    CONSTRAINT desktop_sessions_display_p95_ms_check CHECK (((display_p95_ms >= (0)::double precision) AND (display_p95_ms < 'Infinity'::double precision))),
    CONSTRAINT desktop_sessions_feature_version_check CHECK ((length(btrim(feature_version)) > 0)),
    CONSTRAINT desktop_sessions_mode_check CHECK ((mode = ANY (ARRAY['live'::text, 'replay'::text]))),
    CONSTRAINT desktop_sessions_model_sha256_check CHECK ((model_sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT desktop_sessions_payload_sha256_check CHECK ((payload_sha256 ~ '^[0-9a-f]{64}$'::text)),
    CONSTRAINT desktop_sessions_prediction_count_check CHECK ((prediction_count >= 0)),
    CONSTRAINT desktop_sessions_processing_p95_ms_check CHECK (((processing_p95_ms >= (0)::double precision) AND (processing_p95_ms < 'Infinity'::double precision))),
    CONSTRAINT desktop_sessions_status_check CHECK ((status = ANY (ARRAY['completed'::text, 'stopped'::text, 'interrupted'::text, 'failed'::text]))),
    CONSTRAINT desktop_sessions_termination_reason_check CHECK ((length(btrim(termination_reason)) > 0)),
    CONSTRAINT desktop_sessions_timing_scope_check CHECK ((length(btrim(timing_scope)) > 0))
);


--
-- Name: TABLE desktop_sessions; Type: COMMENT; Schema: recognition; Owner: -
--

COMMENT ON TABLE recognition.desktop_sessions IS 'Terminal synchronized summaries only; local active sessions do not require cloud availability. Model, identity and recording references are validated through owning APIs.';


--
-- Name: COLUMN desktop_sessions.neutral_confirmed; Type: COMMENT; Schema: recognition; Owner: -
--

COMMENT ON COLUMN recognition.desktop_sessions.neutral_confirmed IS 'Recorded evidence, not an invented guarantee. False records an unconfirmed/failed neutral transition for incident review; runtime acceptance still requires neutral behaviour.';


--
-- Name: model_events; Type: TABLE; Schema: recognition; Owner: -
--

CREATE TABLE recognition.model_events (
    event_id uuid NOT NULL,
    model_run_id uuid NOT NULL,
    manifest_id uuid NOT NULL,
    correlation_id character varying(64) NOT NULL,
    received_at timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL
);


--
-- Name: replay_sessions; Type: TABLE; Schema: recognition; Owner: -
--

CREATE TABLE recognition.replay_sessions (
    id uuid NOT NULL,
    model_run_id uuid NOT NULL,
    recording_id uuid NOT NULL,
    status character varying(20) NOT NULL,
    model_checksum character varying(64),
    result jsonb,
    error character varying(200),
    CONSTRAINT replay_sessions_check CHECK (((((status)::text = 'running'::text) AND (model_checksum IS NULL) AND (result IS NULL) AND (error IS NULL)) OR (((status)::text = 'succeeded'::text) AND (model_checksum IS NOT NULL) AND ((model_checksum)::text ~ '^[0-9a-f]{64}$'::text) AND (result IS NOT NULL) AND (error IS NULL)) OR (((status)::text = 'failed'::text) AND (result IS NOT NULL) AND (error IS NOT NULL)))),
    CONSTRAINT replay_sessions_status_check CHECK (((status)::text = ANY ((ARRAY['running'::character varying, 'succeeded'::character varying, 'failed'::character varying])::text[])))
);


--
-- Name: calibration_items calibration_items_pkey; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.calibration_items
    ADD CONSTRAINT calibration_items_pkey PRIMARY KEY (subset_id, unit_id);


--
-- Name: calibration_subsets calibration_subsets_manifest_id_participant_id_selection_ve_key; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.calibration_subsets
    ADD CONSTRAINT calibration_subsets_manifest_id_participant_id_selection_ve_key UNIQUE (manifest_id, participant_id, selection_version, budget_per_gesture);


--
-- Name: calibration_subsets calibration_subsets_pkey; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.calibration_subsets
    ADD CONSTRAINT calibration_subsets_pkey PRIMARY KEY (id);


--
-- Name: client_publications client_publications_operator_id_client_id_local_recording_i_key; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.client_publications
    ADD CONSTRAINT client_publications_operator_id_client_id_local_recording_i_key UNIQUE (operator_id, client_id, local_recording_id);


--
-- Name: client_publications client_publications_pkey; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.client_publications
    ADD CONSTRAINT client_publications_pkey PRIMARY KEY (id);


--
-- Name: client_publications client_publications_recording_id_key; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.client_publications
    ADD CONSTRAINT client_publications_recording_id_key UNIQUE (recording_id);


--
-- Name: labelled_segments labelled_segments_pkey; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.labelled_segments
    ADD CONSTRAINT labelled_segments_pkey PRIMARY KEY (id);


--
-- Name: labelled_segments labelled_segments_recording_id_repetition_key_key; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.labelled_segments
    ADD CONSTRAINT labelled_segments_recording_id_repetition_key_key UNIQUE (recording_id, repetition_key);


--
-- Name: manifest_participants manifest_participants_manifest_id_participant_id_category_key; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.manifest_participants
    ADD CONSTRAINT manifest_participants_manifest_id_participant_id_category_key UNIQUE (manifest_id, participant_id, category);


--
-- Name: manifest_participants manifest_participants_pkey; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.manifest_participants
    ADD CONSTRAINT manifest_participants_pkey PRIMARY KEY (manifest_id, participant_id);


--
-- Name: manifest_units manifest_units_manifest_id_segment_id_role_key; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.manifest_units
    ADD CONSTRAINT manifest_units_manifest_id_segment_id_role_key UNIQUE (manifest_id, segment_id, role);


--
-- Name: manifest_units manifest_units_pkey; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.manifest_units
    ADD CONSTRAINT manifest_units_pkey PRIMARY KEY (id);


--
-- Name: participants participants_pkey; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.participants
    ADD CONSTRAINT participants_pkey PRIMARY KEY (id);


--
-- Name: participants participants_pseudonym_key; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.participants
    ADD CONSTRAINT participants_pseudonym_key UNIQUE (pseudonym);


--
-- Name: protocol_versions protocol_versions_name_version_key; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.protocol_versions
    ADD CONSTRAINT protocol_versions_name_version_key UNIQUE (name, version);


--
-- Name: protocol_versions protocol_versions_pkey; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.protocol_versions
    ADD CONSTRAINT protocol_versions_pkey PRIMARY KEY (id);


--
-- Name: recording_provenance recording_provenance_pkey; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.recording_provenance
    ADD CONSTRAINT recording_provenance_pkey PRIMARY KEY (recording_id);


--
-- Name: recordings recordings_pkey; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.recordings
    ADD CONSTRAINT recordings_pkey PRIMARY KEY (id);


--
-- Name: research_manifests research_manifests_name_version_key; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.research_manifests
    ADD CONSTRAINT research_manifests_name_version_key UNIQUE (name, version);


--
-- Name: research_manifests research_manifests_pkey; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.research_manifests
    ADD CONSTRAINT research_manifests_pkey PRIMARY KEY (id);


--
-- Name: synthetic_splits synthetic_splits_pkey; Type: CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.synthetic_splits
    ADD CONSTRAINT synthetic_splits_pkey PRIMARY KEY (id);


--
-- Name: access_sessions access_sessions_pkey; Type: CONSTRAINT; Schema: identity; Owner: -
--

ALTER TABLE ONLY identity.access_sessions
    ADD CONSTRAINT access_sessions_pkey PRIMARY KEY (id);


--
-- Name: access_sessions access_sessions_token_sha256_key; Type: CONSTRAINT; Schema: identity; Owner: -
--

ALTER TABLE ONLY identity.access_sessions
    ADD CONSTRAINT access_sessions_token_sha256_key UNIQUE (token_sha256);


--
-- Name: clients clients_id_operator_id_key; Type: CONSTRAINT; Schema: identity; Owner: -
--

ALTER TABLE ONLY identity.clients
    ADD CONSTRAINT clients_id_operator_id_key UNIQUE (id, operator_id);


--
-- Name: clients clients_pkey; Type: CONSTRAINT; Schema: identity; Owner: -
--

ALTER TABLE ONLY identity.clients
    ADD CONSTRAINT clients_pkey PRIMARY KEY (id);


--
-- Name: operators operators_email_key; Type: CONSTRAINT; Schema: identity; Owner: -
--

ALTER TABLE ONLY identity.operators
    ADD CONSTRAINT operators_email_key UNIQUE (email);


--
-- Name: operators operators_pkey; Type: CONSTRAINT; Schema: identity; Owner: -
--

ALTER TABLE ONLY identity.operators
    ADD CONSTRAINT operators_pkey PRIMARY KEY (id);


--
-- Name: artifacts artifacts_pkey; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.artifacts
    ADD CONSTRAINT artifacts_pkey PRIMARY KEY (id);


--
-- Name: artifacts artifacts_storage_key_key; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.artifacts
    ADD CONSTRAINT artifacts_storage_key_key UNIQUE (storage_key);


--
-- Name: confusion_counts confusion_counts_pkey; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.confusion_counts
    ADD CONSTRAINT confusion_counts_pkey PRIMARY KEY (evaluation_id, actual_class, predicted_class);


--
-- Name: evaluations evaluations_id_model_id_key; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.evaluations
    ADD CONSTRAINT evaluations_id_model_id_key UNIQUE (id, model_id);


--
-- Name: evaluations evaluations_pkey; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.evaluations
    ADD CONSTRAINT evaluations_pkey PRIMARY KEY (id);


--
-- Name: evaluations evaluations_run_id_key; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.evaluations
    ADD CONSTRAINT evaluations_run_id_key UNIQUE (run_id);


--
-- Name: experiment_runs experiment_runs_operator_id_submission_key_key; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.experiment_runs
    ADD CONSTRAINT experiment_runs_operator_id_submission_key_key UNIQUE (operator_id, submission_key);


--
-- Name: experiment_runs experiment_runs_pkey; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.experiment_runs
    ADD CONSTRAINT experiment_runs_pkey PRIMARY KEY (id);


--
-- Name: model_classes model_classes_model_id_position_key; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.model_classes
    ADD CONSTRAINT model_classes_model_id_position_key UNIQUE (model_id, "position");


--
-- Name: model_classes model_classes_pkey; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.model_classes
    ADD CONSTRAINT model_classes_pkey PRIMARY KEY (model_id, code);


--
-- Name: model_package_items model_package_items_pkey; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.model_package_items
    ADD CONSTRAINT model_package_items_pkey PRIMARY KEY (model_id, purpose);


--
-- Name: model_versions model_versions_pkey; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.model_versions
    ADD CONSTRAINT model_versions_pkey PRIMARY KEY (id);


--
-- Name: model_versions model_versions_run_id_key; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.model_versions
    ADD CONSTRAINT model_versions_run_id_key UNIQUE (run_id);


--
-- Name: outbox_events outbox_events_pkey; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.outbox_events
    ADD CONSTRAINT outbox_events_pkey PRIMARY KEY (id);


--
-- Name: outbox_events outbox_events_run_id_key; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.outbox_events
    ADD CONSTRAINT outbox_events_run_id_key UNIQUE (run_id);


--
-- Name: signal_summary_jobs signal_summary_jobs_pkey; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.signal_summary_jobs
    ADD CONSTRAINT signal_summary_jobs_pkey PRIMARY KEY (id);


--
-- Name: source_lda_runs source_lda_runs_idempotency_key_key; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.source_lda_runs
    ADD CONSTRAINT source_lda_runs_idempotency_key_key UNIQUE (idempotency_key);


--
-- Name: source_lda_runs source_lda_runs_pkey; Type: CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.source_lda_runs
    ADD CONSTRAINT source_lda_runs_pkey PRIMARY KEY (id);


--
-- Name: service_schema_migrations service_schema_migrations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.service_schema_migrations
    ADD CONSTRAINT service_schema_migrations_pkey PRIMARY KEY (service, name);


--
-- Name: desktop_sessions desktop_sessions_operator_id_client_id_local_session_id_key; Type: CONSTRAINT; Schema: recognition; Owner: -
--

ALTER TABLE ONLY recognition.desktop_sessions
    ADD CONSTRAINT desktop_sessions_operator_id_client_id_local_session_id_key UNIQUE (operator_id, client_id, local_session_id);


--
-- Name: desktop_sessions desktop_sessions_pkey; Type: CONSTRAINT; Schema: recognition; Owner: -
--

ALTER TABLE ONLY recognition.desktop_sessions
    ADD CONSTRAINT desktop_sessions_pkey PRIMARY KEY (id);


--
-- Name: model_events model_events_pkey; Type: CONSTRAINT; Schema: recognition; Owner: -
--

ALTER TABLE ONLY recognition.model_events
    ADD CONSTRAINT model_events_pkey PRIMARY KEY (event_id);


--
-- Name: replay_sessions replay_sessions_pkey; Type: CONSTRAINT; Schema: recognition; Owner: -
--

ALTER TABLE ONLY recognition.replay_sessions
    ADD CONSTRAINT replay_sessions_pkey PRIMARY KEY (id);


--
-- Name: recording_provenance_operator; Type: INDEX; Schema: data_protocol; Owner: -
--

CREATE INDEX recording_provenance_operator ON data_protocol.recording_provenance USING btree (operator_id);


--
-- Name: recording_source_identity; Type: INDEX; Schema: data_protocol; Owner: -
--

CREATE INDEX recording_source_identity ON data_protocol.recording_provenance USING btree (source_name, source_version, original_signal_key);


--
-- Name: access_sessions_operator; Type: INDEX; Schema: identity; Owner: -
--

CREATE INDEX access_sessions_operator ON identity.access_sessions USING btree (operator_id);


--
-- Name: clients_operator; Type: INDEX; Schema: identity; Owner: -
--

CREATE INDEX clients_operator ON identity.clients USING btree (operator_id);


--
-- Name: experiment_runs_history; Type: INDEX; Schema: ml_experiments; Owner: -
--

CREATE INDEX experiment_runs_history ON ml_experiments.experiment_runs USING btree (operator_id, created_at DESC);


--
-- Name: experiment_runs_queue; Type: INDEX; Schema: ml_experiments; Owner: -
--

CREATE INDEX experiment_runs_queue ON ml_experiments.experiment_runs USING btree (operator_id, execution_location, created_at) WHERE (status = 'queued'::text);


--
-- Name: experiment_runs_stale; Type: INDEX; Schema: ml_experiments; Owner: -
--

CREATE INDEX experiment_runs_stale ON ml_experiments.experiment_runs USING btree (lease_expires_at) WHERE (status = 'running'::text);


--
-- Name: model_package_artifact; Type: INDEX; Schema: ml_experiments; Owner: -
--

CREATE INDEX model_package_artifact ON ml_experiments.model_package_items USING btree (artifact_id);


--
-- Name: outbox_unpublished; Type: INDEX; Schema: ml_experiments; Owner: -
--

CREATE INDEX outbox_unpublished ON ml_experiments.outbox_events USING btree (created_at) WHERE (published_at IS NULL);


--
-- Name: source_lda_runs_heartbeat; Type: INDEX; Schema: ml_experiments; Owner: -
--

CREATE INDEX source_lda_runs_heartbeat ON ml_experiments.source_lda_runs USING btree (heartbeat_at) WHERE ((status)::text = 'running'::text);


--
-- Name: source_lda_runs_queue; Type: INDEX; Schema: ml_experiments; Owner: -
--

CREATE INDEX source_lda_runs_queue ON ml_experiments.source_lda_runs USING btree (created_at) WHERE ((status)::text = 'queued'::text);


--
-- Name: desktop_sessions_model; Type: INDEX; Schema: recognition; Owner: -
--

CREATE INDEX desktop_sessions_model ON recognition.desktop_sessions USING btree (model_version_id);


--
-- Name: desktop_sessions_operator_time; Type: INDEX; Schema: recognition; Owner: -
--

CREATE INDEX desktop_sessions_operator_time ON recognition.desktop_sessions USING btree (operator_id, started_at DESC);


--
-- Name: model_events_by_model; Type: INDEX; Schema: recognition; Owner: -
--

CREATE INDEX model_events_by_model ON recognition.model_events USING btree (model_run_id);


--
-- Name: calibration_items guard_calibration_item; Type: TRIGGER; Schema: data_protocol; Owner: -
--

CREATE TRIGGER guard_calibration_item BEFORE INSERT OR DELETE OR UPDATE ON data_protocol.calibration_items FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_calibration_item();


--
-- Name: calibration_subsets guard_calibration_subset; Type: TRIGGER; Schema: data_protocol; Owner: -
--

CREATE TRIGGER guard_calibration_subset BEFORE INSERT OR DELETE OR UPDATE ON data_protocol.calibration_subsets FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_calibration_subset();


--
-- Name: manifest_participants guard_manifest_participants; Type: TRIGGER; Schema: data_protocol; Owner: -
--

CREATE TRIGGER guard_manifest_participants BEFORE INSERT OR DELETE OR UPDATE ON data_protocol.manifest_participants FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_manifest_membership();


--
-- Name: manifest_units guard_manifest_units; Type: TRIGGER; Schema: data_protocol; Owner: -
--

CREATE TRIGGER guard_manifest_units BEFORE INSERT OR DELETE OR UPDATE ON data_protocol.manifest_units FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_manifest_membership();


--
-- Name: research_manifests guard_research_manifest; Type: TRIGGER; Schema: data_protocol; Owner: -
--

CREATE TRIGGER guard_research_manifest BEFORE INSERT OR DELETE OR UPDATE ON data_protocol.research_manifests FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_research_manifest();


--
-- Name: protocol_versions guard_research_protocol; Type: TRIGGER; Schema: data_protocol; Owner: -
--

CREATE TRIGGER guard_research_protocol BEFORE DELETE OR UPDATE ON data_protocol.protocol_versions FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_research_dependencies();


--
-- Name: recordings guard_research_recording; Type: TRIGGER; Schema: data_protocol; Owner: -
--

CREATE TRIGGER guard_research_recording BEFORE DELETE OR UPDATE ON data_protocol.recordings FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_research_dependencies();


--
-- Name: labelled_segments guard_research_segment; Type: TRIGGER; Schema: data_protocol; Owner: -
--

CREATE TRIGGER guard_research_segment BEFORE DELETE OR UPDATE ON data_protocol.labelled_segments FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_research_dependencies();


--
-- Name: recordings guard_split_recording; Type: TRIGGER; Schema: data_protocol; Owner: -
--

CREATE TRIGGER guard_split_recording BEFORE DELETE OR UPDATE ON data_protocol.recordings FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_split_recording();


--
-- Name: synthetic_splits guard_synthetic_split; Type: TRIGGER; Schema: data_protocol; Owner: -
--

CREATE TRIGGER guard_synthetic_split BEFORE DELETE OR UPDATE ON data_protocol.synthetic_splits FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_synthetic_split();


--
-- Name: client_publications immutable_client_publication; Type: TRIGGER; Schema: data_protocol; Owner: -
--

CREATE TRIGGER immutable_client_publication BEFORE DELETE OR UPDATE ON data_protocol.client_publications FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_publication_metadata();


--
-- Name: recording_provenance immutable_recording_provenance; Type: TRIGGER; Schema: data_protocol; Owner: -
--

CREATE TRIGGER immutable_recording_provenance BEFORE DELETE OR UPDATE ON data_protocol.recording_provenance FOR EACH ROW EXECUTE FUNCTION data_protocol.guard_publication_metadata();


--
-- Name: protocol_versions validate_protocol_gestures; Type: TRIGGER; Schema: data_protocol; Owner: -
--

CREATE TRIGGER validate_protocol_gestures BEFORE INSERT OR UPDATE ON data_protocol.protocol_versions FOR EACH ROW EXECUTE FUNCTION data_protocol.validate_protocol_gestures();


--
-- Name: labelled_segments validate_segment; Type: TRIGGER; Schema: data_protocol; Owner: -
--

CREATE TRIGGER validate_segment BEFORE INSERT OR UPDATE ON data_protocol.labelled_segments FOR EACH ROW EXECUTE FUNCTION data_protocol.validate_segment();


--
-- Name: synthetic_splits validate_synthetic_split; Type: TRIGGER; Schema: data_protocol; Owner: -
--

CREATE TRIGGER validate_synthetic_split BEFORE INSERT ON data_protocol.synthetic_splits FOR EACH ROW EXECUTE FUNCTION data_protocol.validate_synthetic_split();


--
-- Name: access_sessions guard_access_session; Type: TRIGGER; Schema: identity; Owner: -
--

CREATE TRIGGER guard_access_session BEFORE INSERT OR DELETE OR UPDATE ON identity.access_sessions FOR EACH ROW EXECUTE FUNCTION identity.guard_access_session();


--
-- Name: clients guard_client; Type: TRIGGER; Schema: identity; Owner: -
--

CREATE TRIGGER guard_client BEFORE DELETE OR UPDATE ON identity.clients FOR EACH ROW EXECUTE FUNCTION identity.guard_client();


--
-- Name: operators touch_operator; Type: TRIGGER; Schema: identity; Owner: -
--

CREATE TRIGGER touch_operator BEFORE DELETE OR UPDATE ON identity.operators FOR EACH ROW EXECUTE FUNCTION identity.touch_operator();


--
-- Name: experiment_runs guard_experiment_run; Type: TRIGGER; Schema: ml_experiments; Owner: -
--

CREATE TRIGGER guard_experiment_run BEFORE INSERT OR DELETE OR UPDATE ON ml_experiments.experiment_runs FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_experiment_run();


--
-- Name: model_classes guard_model_classes; Type: TRIGGER; Schema: ml_experiments; Owner: -
--

CREATE TRIGGER guard_model_classes BEFORE INSERT OR DELETE OR UPDATE ON ml_experiments.model_classes FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_model_members();


--
-- Name: model_package_items guard_model_package_items; Type: TRIGGER; Schema: ml_experiments; Owner: -
--

CREATE TRIGGER guard_model_package_items BEFORE INSERT OR DELETE OR UPDATE ON ml_experiments.model_package_items FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_model_members();


--
-- Name: model_versions guard_model_version; Type: TRIGGER; Schema: ml_experiments; Owner: -
--

CREATE TRIGGER guard_model_version BEFORE INSERT OR DELETE OR UPDATE ON ml_experiments.model_versions FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_model_version();


--
-- Name: artifacts guard_registry_artifact; Type: TRIGGER; Schema: ml_experiments; Owner: -
--

CREATE TRIGGER guard_registry_artifact BEFORE DELETE OR UPDATE ON ml_experiments.artifacts FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_registry_artifact();


--
-- Name: confusion_counts guard_registry_confusion; Type: TRIGGER; Schema: ml_experiments; Owner: -
--

CREATE TRIGGER guard_registry_confusion BEFORE INSERT OR DELETE OR UPDATE ON ml_experiments.confusion_counts FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_evaluation_members();


--
-- Name: evaluations guard_registry_evaluation; Type: TRIGGER; Schema: ml_experiments; Owner: -
--

CREATE TRIGGER guard_registry_evaluation BEFORE INSERT OR DELETE OR UPDATE ON ml_experiments.evaluations FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_evaluation_members();


--
-- Name: source_lda_runs guard_source_lda_run; Type: TRIGGER; Schema: ml_experiments; Owner: -
--

CREATE TRIGGER guard_source_lda_run BEFORE DELETE OR UPDATE ON ml_experiments.source_lda_runs FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_source_lda_run();


--
-- Name: source_lda_runs guard_trace_context; Type: TRIGGER; Schema: ml_experiments; Owner: -
--

CREATE TRIGGER guard_trace_context BEFORE UPDATE ON ml_experiments.source_lda_runs FOR EACH ROW EXECUTE FUNCTION ml_experiments.guard_trace_context();


--
-- Name: experiment_runs validate_run_output; Type: TRIGGER; Schema: ml_experiments; Owner: -
--

CREATE CONSTRAINT TRIGGER validate_run_output AFTER INSERT OR UPDATE ON ml_experiments.experiment_runs DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION ml_experiments.validate_run_output();


--
-- Name: source_lda_runs z_set_model_checksum; Type: TRIGGER; Schema: ml_experiments; Owner: -
--

CREATE TRIGGER z_set_model_checksum BEFORE UPDATE ON ml_experiments.source_lda_runs FOR EACH ROW EXECUTE FUNCTION ml_experiments.set_model_checksum();


--
-- Name: desktop_sessions immutable_desktop_session; Type: TRIGGER; Schema: recognition; Owner: -
--

CREATE TRIGGER immutable_desktop_session BEFORE DELETE OR UPDATE ON recognition.desktop_sessions FOR EACH ROW EXECUTE FUNCTION recognition.guard_desktop_session();


--
-- Name: calibration_items calibration_items_subset_id_fkey; Type: FK CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.calibration_items
    ADD CONSTRAINT calibration_items_subset_id_fkey FOREIGN KEY (subset_id) REFERENCES data_protocol.calibration_subsets(id) ON DELETE RESTRICT;


--
-- Name: calibration_items calibration_items_unit_id_fkey; Type: FK CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.calibration_items
    ADD CONSTRAINT calibration_items_unit_id_fkey FOREIGN KEY (unit_id) REFERENCES data_protocol.manifest_units(id) ON DELETE RESTRICT;


--
-- Name: calibration_subsets calibration_subsets_manifest_id_participant_id_category_fkey; Type: FK CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.calibration_subsets
    ADD CONSTRAINT calibration_subsets_manifest_id_participant_id_category_fkey FOREIGN KEY (manifest_id, participant_id, category) REFERENCES data_protocol.manifest_participants(manifest_id, participant_id, category) ON DELETE RESTRICT;


--
-- Name: client_publications client_publications_recording_id_fkey; Type: FK CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.client_publications
    ADD CONSTRAINT client_publications_recording_id_fkey FOREIGN KEY (recording_id) REFERENCES data_protocol.recordings(id) ON DELETE RESTRICT;


--
-- Name: labelled_segments labelled_segments_recording_id_fkey; Type: FK CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.labelled_segments
    ADD CONSTRAINT labelled_segments_recording_id_fkey FOREIGN KEY (recording_id) REFERENCES data_protocol.recordings(id) ON DELETE RESTRICT;


--
-- Name: manifest_participants manifest_participants_manifest_id_fkey; Type: FK CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.manifest_participants
    ADD CONSTRAINT manifest_participants_manifest_id_fkey FOREIGN KEY (manifest_id) REFERENCES data_protocol.research_manifests(id) ON DELETE RESTRICT;


--
-- Name: manifest_participants manifest_participants_participant_id_fkey; Type: FK CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.manifest_participants
    ADD CONSTRAINT manifest_participants_participant_id_fkey FOREIGN KEY (participant_id) REFERENCES data_protocol.participants(id) ON DELETE RESTRICT;


--
-- Name: manifest_units manifest_units_manifest_id_participant_id_category_fkey; Type: FK CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.manifest_units
    ADD CONSTRAINT manifest_units_manifest_id_participant_id_category_fkey FOREIGN KEY (manifest_id, participant_id, category) REFERENCES data_protocol.manifest_participants(manifest_id, participant_id, category) ON DELETE RESTRICT;


--
-- Name: manifest_units manifest_units_segment_id_fkey; Type: FK CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.manifest_units
    ADD CONSTRAINT manifest_units_segment_id_fkey FOREIGN KEY (segment_id) REFERENCES data_protocol.labelled_segments(id) ON DELETE RESTRICT;


--
-- Name: recording_provenance recording_provenance_recording_id_fkey; Type: FK CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.recording_provenance
    ADD CONSTRAINT recording_provenance_recording_id_fkey FOREIGN KEY (recording_id) REFERENCES data_protocol.recordings(id) ON DELETE RESTRICT;


--
-- Name: recordings recordings_participant_id_fkey; Type: FK CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.recordings
    ADD CONSTRAINT recordings_participant_id_fkey FOREIGN KEY (participant_id) REFERENCES data_protocol.participants(id) ON DELETE RESTRICT;


--
-- Name: research_manifests research_manifests_protocol_id_fkey; Type: FK CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.research_manifests
    ADD CONSTRAINT research_manifests_protocol_id_fkey FOREIGN KEY (protocol_id) REFERENCES data_protocol.protocol_versions(id) ON DELETE RESTRICT;


--
-- Name: synthetic_splits synthetic_splits_source_recording_id_fkey; Type: FK CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.synthetic_splits
    ADD CONSTRAINT synthetic_splits_source_recording_id_fkey FOREIGN KEY (source_recording_id) REFERENCES data_protocol.recordings(id) ON DELETE RESTRICT;


--
-- Name: synthetic_splits synthetic_splits_test_recording_id_fkey; Type: FK CONSTRAINT; Schema: data_protocol; Owner: -
--

ALTER TABLE ONLY data_protocol.synthetic_splits
    ADD CONSTRAINT synthetic_splits_test_recording_id_fkey FOREIGN KEY (test_recording_id) REFERENCES data_protocol.recordings(id) ON DELETE RESTRICT;


--
-- Name: access_sessions access_sessions_client_id_operator_id_fkey; Type: FK CONSTRAINT; Schema: identity; Owner: -
--

ALTER TABLE ONLY identity.access_sessions
    ADD CONSTRAINT access_sessions_client_id_operator_id_fkey FOREIGN KEY (client_id, operator_id) REFERENCES identity.clients(id, operator_id) ON DELETE RESTRICT;


--
-- Name: access_sessions access_sessions_operator_id_fkey; Type: FK CONSTRAINT; Schema: identity; Owner: -
--

ALTER TABLE ONLY identity.access_sessions
    ADD CONSTRAINT access_sessions_operator_id_fkey FOREIGN KEY (operator_id) REFERENCES identity.operators(id) ON DELETE RESTRICT;


--
-- Name: clients clients_operator_id_fkey; Type: FK CONSTRAINT; Schema: identity; Owner: -
--

ALTER TABLE ONLY identity.clients
    ADD CONSTRAINT clients_operator_id_fkey FOREIGN KEY (operator_id) REFERENCES identity.operators(id) ON DELETE RESTRICT;


--
-- Name: confusion_counts confusion_counts_evaluation_id_model_id_fkey; Type: FK CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.confusion_counts
    ADD CONSTRAINT confusion_counts_evaluation_id_model_id_fkey FOREIGN KEY (evaluation_id, model_id) REFERENCES ml_experiments.evaluations(id, model_id) ON DELETE RESTRICT;


--
-- Name: confusion_counts confusion_counts_model_id_actual_class_fkey; Type: FK CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.confusion_counts
    ADD CONSTRAINT confusion_counts_model_id_actual_class_fkey FOREIGN KEY (model_id, actual_class) REFERENCES ml_experiments.model_classes(model_id, code) ON DELETE RESTRICT;


--
-- Name: confusion_counts confusion_counts_model_id_predicted_class_fkey; Type: FK CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.confusion_counts
    ADD CONSTRAINT confusion_counts_model_id_predicted_class_fkey FOREIGN KEY (model_id, predicted_class) REFERENCES ml_experiments.model_classes(model_id, code) ON DELETE RESTRICT;


--
-- Name: evaluations evaluations_model_id_fkey; Type: FK CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.evaluations
    ADD CONSTRAINT evaluations_model_id_fkey FOREIGN KEY (model_id) REFERENCES ml_experiments.model_versions(id) ON DELETE RESTRICT;


--
-- Name: evaluations evaluations_run_id_fkey; Type: FK CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.evaluations
    ADD CONSTRAINT evaluations_run_id_fkey FOREIGN KEY (run_id) REFERENCES ml_experiments.experiment_runs(id) ON DELETE RESTRICT;


--
-- Name: experiment_runs experiment_runs_evaluated_model_id_fkey; Type: FK CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.experiment_runs
    ADD CONSTRAINT experiment_runs_evaluated_model_id_fkey FOREIGN KEY (evaluated_model_id) REFERENCES ml_experiments.model_versions(id) ON DELETE RESTRICT;


--
-- Name: experiment_runs experiment_runs_parent_model_id_fkey; Type: FK CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.experiment_runs
    ADD CONSTRAINT experiment_runs_parent_model_id_fkey FOREIGN KEY (parent_model_id) REFERENCES ml_experiments.model_versions(id) ON DELETE RESTRICT;


--
-- Name: experiment_runs experiment_runs_retry_of_id_fkey; Type: FK CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.experiment_runs
    ADD CONSTRAINT experiment_runs_retry_of_id_fkey FOREIGN KEY (retry_of_id) REFERENCES ml_experiments.experiment_runs(id) ON DELETE RESTRICT;


--
-- Name: model_classes model_classes_model_id_fkey; Type: FK CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.model_classes
    ADD CONSTRAINT model_classes_model_id_fkey FOREIGN KEY (model_id) REFERENCES ml_experiments.model_versions(id) ON DELETE RESTRICT;


--
-- Name: model_package_items model_package_items_artifact_id_fkey; Type: FK CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.model_package_items
    ADD CONSTRAINT model_package_items_artifact_id_fkey FOREIGN KEY (artifact_id) REFERENCES ml_experiments.artifacts(id) ON DELETE RESTRICT;


--
-- Name: model_package_items model_package_items_model_id_fkey; Type: FK CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.model_package_items
    ADD CONSTRAINT model_package_items_model_id_fkey FOREIGN KEY (model_id) REFERENCES ml_experiments.model_versions(id) ON DELETE RESTRICT;


--
-- Name: model_versions model_versions_artifact_id_fkey; Type: FK CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.model_versions
    ADD CONSTRAINT model_versions_artifact_id_fkey FOREIGN KEY (artifact_id) REFERENCES ml_experiments.artifacts(id) ON DELETE RESTRICT;


--
-- Name: model_versions model_versions_run_id_fkey; Type: FK CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.model_versions
    ADD CONSTRAINT model_versions_run_id_fkey FOREIGN KEY (run_id) REFERENCES ml_experiments.experiment_runs(id) ON DELETE RESTRICT;


--
-- Name: outbox_events outbox_events_run_id_fkey; Type: FK CONSTRAINT; Schema: ml_experiments; Owner: -
--

ALTER TABLE ONLY ml_experiments.outbox_events
    ADD CONSTRAINT outbox_events_run_id_fkey FOREIGN KEY (run_id) REFERENCES ml_experiments.source_lda_runs(id) ON DELETE RESTRICT;


--
-- PostgreSQL database dump complete
--

--
-- PostgreSQL database dump
--

-- Dumped from database version 16.3
-- Dumped by pg_dump version 16.3

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: service_schema_migrations; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.service_schema_migrations (service, name, checksum, applied_at) VALUES ('identity', '0001_operators.sql', 'dc60ee1b626c5f7ca1c20d6242f19fa576177187c0f2876ba989204297638baa', '2026-11-23 21:25:33.162284+01');
INSERT INTO public.service_schema_migrations (service, name, checksum, applied_at) VALUES ('data_protocol', '0001_participants.sql', '6853cc658ad0338ce06e8739fecd7ccd2282560abf78f643f8767be52d5d863b', '2026-11-23 21:25:33.162284+01');
INSERT INTO public.service_schema_migrations (service, name, checksum, applied_at) VALUES ('data_protocol', '0002_recordings.sql', 'c797fabc72e4cdc54c50a4c6ad6b7d62481ee9bdec071c14ad626f5b8adf71f1', '2026-11-23 21:25:33.162284+01');
INSERT INTO public.service_schema_migrations (service, name, checksum, applied_at) VALUES ('data_protocol', '0003_synthetic_splits.sql', '1a562688bd19f3d5502194c60c7eee4f404d23d8feb7087a66316f7d25660a2e', '2026-11-23 21:25:33.162284+01');
INSERT INTO public.service_schema_migrations (service, name, checksum, applied_at) VALUES ('data_protocol', '0004_research_splits.sql', '8324dfa833f9af3bb8ff7ed67670ab51c573e5c4a8c75159e5b8d705b28b4567', '2026-11-23 21:25:33.162284+01');
INSERT INTO public.service_schema_migrations (service, name, checksum, applied_at) VALUES ('data_protocol', '0005_calibration.sql', '48a8ccde1ac6f2d4725e0dd21522e13c3546ac0c94971584c626c6f34625f1c4', '2026-11-23 21:25:33.162284+01');
INSERT INTO public.service_schema_migrations (service, name, checksum, applied_at) VALUES ('data_protocol', '0006_client_publication.sql', '92d88728b019a4cc1f5bb09b0359dbc33f8aabc904ade926b5a472eb23dc58ff', '2026-11-23 21:25:33.162284+01');
INSERT INTO public.service_schema_migrations (service, name, checksum, applied_at) VALUES ('ml_experiments', '0001_summary_jobs.sql', '80f8480ad32f2eead3d0cd9160b9954d950ed6da02d8539e9f968f9c00648aea', '2026-11-23 21:25:33.162284+01');
INSERT INTO public.service_schema_migrations (service, name, checksum, applied_at) VALUES ('ml_experiments', '0002_source_lda.sql', 'de0557008afc0659102873e978dafc19769c13538868b4fe3f07011bd700a12a', '2026-11-23 21:25:33.162284+01');
INSERT INTO public.service_schema_migrations (service, name, checksum, applied_at) VALUES ('ml_experiments', '0003_model_checksum.sql', '4ec7b33966c124df0484c4911ceca1f1217513bebb526dd2a8035b5eda1b9342', '2026-11-23 21:25:33.162284+01');
INSERT INTO public.service_schema_migrations (service, name, checksum, applied_at) VALUES ('ml_experiments', '0004_model_outbox.sql', '296be3ca06070145379c66ccf7ade293950557d724280904bc9238487c654c81', '2026-11-23 21:25:33.162284+01');
INSERT INTO public.service_schema_migrations (service, name, checksum, applied_at) VALUES ('ml_experiments', '0005_experiment_jobs.sql', 'ba6f8dac74fc3309a1fcf400a9e0ad1f712edea36e936f52de2ebbb81cc64653', '2026-11-23 21:25:33.162284+01');
INSERT INTO public.service_schema_migrations (service, name, checksum, applied_at) VALUES ('ml_experiments', '0006_trace_context.sql', 'a29b8b8e855ec4bcb9a1a5b7d78dd51a1650596cdbb2020133e4fab7c2f708b9', '2026-11-23 21:25:33.162284+01');
INSERT INTO public.service_schema_migrations (service, name, checksum, applied_at) VALUES ('ml_experiments', '0007_cloud_registry.sql', '8517f793a4bd594c3dea9d3fdc2a3ca07ddd36a547d3b83afae242f4d3ebc882', '2026-11-23 21:25:33.162284+01');
INSERT INTO public.service_schema_migrations (service, name, checksum, applied_at) VALUES ('recognition', '0001_replay.sql', '23e9e9291aeaa28da34697ab5983fa94c894b2ac1298735bcd019944ccde1c6f', '2026-11-23 21:25:33.162284+01');
INSERT INTO public.service_schema_migrations (service, name, checksum, applied_at) VALUES ('recognition', '0002_model_events.sql', 'c858104309e61b3446b13f7fdeb6ab3e69951f0d867f4fad431c245517bc01e5', '2026-11-23 21:25:33.162284+01');
INSERT INTO public.service_schema_migrations (service, name, checksum, applied_at) VALUES ('recognition', '0003_desktop_sessions.sql', '5a7a058f25dd96db3a89ec386d6182d4392c6900fe392a48d91542447a572eee', '2026-11-23 21:25:33.162284+01');


--
-- PostgreSQL database dump complete
--
