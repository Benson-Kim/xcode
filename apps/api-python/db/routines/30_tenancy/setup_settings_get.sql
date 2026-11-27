-- api.setup_settings_get(p_actor_id uuid, p_organization_id uuid, p_request_id text) RETURNS jsonb
-- Purpose: the organization's system settings for the Settings page, {settings: [{key, label, on}]}; settings.edit only.
-- Callers: TenancyRoutines.system_settings; GetSystemSettings (GET /setup/settings).
-- Reads: what tenancy.system_settings_document reads. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization.
-- Tests: tests/db/test_system_settings_routines.py, tests/api/test_system_settings.py.

CREATE OR REPLACE FUNCTION api.setup_settings_get(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'settings.edit');
  RETURN tenancy.system_settings_document();
END;
$$;
