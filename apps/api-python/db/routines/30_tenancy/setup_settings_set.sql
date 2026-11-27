-- api.setup_settings_set(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_key text, p_on boolean, p_now timestamptz) RETURNS jsonb
-- Purpose: switch one system setting on or off for the whole organization at once and return the settings as api.setup_settings_get serves them; the change is logged in the organization section as "Setting, Targets, On to Off"; switching to the state it is already in changes and logs nothing. Stored data the setting hides (targets) is never changed.
-- Callers: TenancyRoutines.set_system_setting; SetSystemSetting (PUT /setup/settings/{key}).
-- Reads: tenancy.system_settings, tenancy.organizations, and what tenancy.setting_enabled and tenancy.system_settings_document read. Writes: tenancy.organization_system_settings, and through tenancy.record_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC404 not_found, XC422 setting_state_required.
-- Tests: tests/db/test_system_settings_routines.py, tests/api/test_system_settings.py.
-- The organization row is locked first, so two switches of one organization run one after the other.

CREATE OR REPLACE FUNCTION api.setup_settings_set(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_key text,
  p_on boolean,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_setting tenancy.system_settings;
  v_was boolean;
  v_before text;
  v_after text;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'settings.edit');
  SELECT s.* INTO v_setting FROM tenancy.system_settings AS s WHERE s.key = p_key;
  IF NOT FOUND THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  IF p_on IS NULL THEN
    PERFORM tenancy.refuse('setting_state_required', 'XC422');
  END IF;
  PERFORM 1 FROM tenancy.organizations AS o WHERE o.id = p_organization_id FOR UPDATE;
  v_was := tenancy.setting_enabled(p_key);
  IF v_was = p_on THEN
    RETURN tenancy.system_settings_document();
  END IF;

  INSERT INTO tenancy.organization_system_settings AS o (
    organization_id, key, enabled, created_at, updated_at
  )
  VALUES (p_organization_id, p_key, p_on, p_now, p_now)
  ON CONFLICT (organization_id, key) DO UPDATE
  SET enabled = EXCLUDED.enabled, updated_at = p_now;
  v_before := CASE WHEN v_was THEN 'On' ELSE 'Off' END;
  v_after := CASE WHEN p_on THEN 'On' ELSE 'Off' END;
  PERFORM tenancy.record_change(
    'organization', p_organization_id, NULL,
    json_build_object(v_setting.label, v_before), json_build_object(v_setting.label, v_after),
    'Setting, ' || v_setting.label || ', ' || v_before || ' to ' || v_after,
    'organization.settings.updated', 'system_settings',
    jsonb_build_object('key', p_key, 'on', v_was), jsonb_build_object('key', p_key, 'on', p_on),
    p_now
  );
  RETURN tenancy.system_settings_document();
END;
$$;
