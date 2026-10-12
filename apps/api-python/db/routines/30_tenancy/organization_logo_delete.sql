-- api.organization_logo_delete(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_reason text, p_now timestamptz) RETURNS api.write_result
-- Purpose: remove the organization's logo and log it; unchanged, with nothing logged, when there is none.
-- Callers: TenancyRoutines.delete_logo; DeleteOrganizationLogo (DELETE /setup/organization/logo).
-- Reads: tenancy.organizations, tenancy.organization_logos. Writes: tenancy.organization_logos, and through tenancy.record_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 reason_length via tenancy.check_typed_reason.
-- Tests: tests/db/test_organization_routines.py, tests/api/test_organization_settings.py.

CREATE OR REPLACE FUNCTION api.organization_logo_delete(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_reason text,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_reason text;
  v_organization tenancy.organizations;
  v_before json;
  v_final text;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'organization.manage');
  v_reason := tenancy.check_typed_reason(p_reason);
  SELECT o.* INTO v_organization
  FROM tenancy.organizations AS o
  WHERE o.id = p_organization_id
  FOR UPDATE;
  IF NOT EXISTS (
    SELECT 1 FROM tenancy.organization_logos AS g WHERE g.organization_id = p_organization_id
  ) THEN
    RETURN ROW(p_organization_id, v_organization.settings_version, 'unchanged')::api.write_result;
  END IF;
  v_before := tenancy.logo_snapshot();
  DELETE FROM tenancy.organization_logos WHERE organization_id = p_organization_id;
  v_final := tenancy.compose_reason('Removed the logo', v_reason);
  v_version := tenancy.record_change(
    'logo', p_organization_id, NULL, v_before, 'null'::json, v_final,
    'organization.settings.updated', 'logo', v_before::jsonb,
    jsonb_build_object('value', NULL, 'reason', v_final), p_now
  );
  RETURN ROW(p_organization_id, v_version, 'updated')::api.write_result;
END;
$$;
