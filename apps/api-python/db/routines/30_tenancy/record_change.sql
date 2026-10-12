-- tenancy.record_change(p_section text, p_entity_id uuid, p_vehicle_id uuid, p_before json, p_after json, p_reason text, p_audit_action text, p_audit_entity text, p_audit_before jsonb, p_audit_after jsonb, p_now timestamptz) RETURNS bigint
-- Purpose: log one change: bump the organization's settings_version (the per-organization serialisation point), write the change-log row and the audit row with the current actor and request id, and return the new version.
-- Callers: every logged write, exactly once and last.
-- Reads: tenancy.organizations. Writes: tenancy.organizations.settings_version, tenancy.change_log, tenancy.audit_events.
-- Raises: XC403 not_member.
-- Tests: tests/db/test_tenancy_helpers.py.
-- The only writer of tenancy.change_log and tenancy.audit_events and the only statement that moves settings_version.

CREATE OR REPLACE FUNCTION tenancy.record_change(
  p_section text,
  p_entity_id uuid,
  p_vehicle_id uuid,
  p_before json,
  p_after json,
  p_reason text,
  p_audit_action text,
  p_audit_entity text,
  p_audit_before jsonb,
  p_audit_after jsonb,
  p_now timestamptz
)
RETURNS bigint
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.current_organization();
  v_actor_id uuid := tenancy.current_actor();
  v_request_id text := tenancy.current_request();
  v_version bigint;
BEGIN
  IF v_organization_id IS NULL OR v_actor_id IS NULL OR v_request_id IS NULL THEN
    PERFORM tenancy.refuse('not_member', 'XC403');
  END IF;

  UPDATE tenancy.organizations
  SET settings_version = settings_version + 1, updated_at = p_now
  WHERE id = v_organization_id
  RETURNING settings_version INTO v_version;
  IF v_version IS NULL THEN
    PERFORM tenancy.refuse('not_member', 'XC403');
  END IF;

  INSERT INTO tenancy.change_log (
    organization_id, version, section, entity_id, vehicle_id, actor_id, reason, occurred_at,
    before, after, request_id
  )
  VALUES (
    v_organization_id, v_version, p_section, p_entity_id, p_vehicle_id, v_actor_id, p_reason, p_now,
    p_before::text, p_after::text, v_request_id
  );

  INSERT INTO tenancy.audit_events (
    organization_id, actor_id, action, entity, before, after, occurred_at, request_id
  )
  VALUES (
    v_organization_id, v_actor_id, p_audit_action, p_audit_entity, p_audit_before, p_audit_after,
    p_now, v_request_id
  );

  RETURN v_version;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.record_change(
  text, uuid, uuid, json, json, text, text, text, jsonb, jsonb, timestamptz
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.record_change(
  text, uuid, uuid, json, json, text, text, text, jsonb, jsonb, timestamptz
) TO xcode_api_executor;
