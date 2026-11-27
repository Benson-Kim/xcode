-- tenancy.setting_enabled(p_key text) RETURNS boolean
-- Purpose: whether the system setting is on for the current organization: its own choice, else the setting's default; NULL for a key the catalogue does not hold.
-- Callers: api.setup_vehicle_create, api.setup_target_set_save, tenancy.system_settings_document, api.organization_appearance_get, api.revenue_export_get, api.report_catalog_get.
-- Reads: tenancy.system_settings, tenancy.organization_system_settings. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_system_settings_routines.py.

CREATE OR REPLACE FUNCTION tenancy.setting_enabled(p_key text)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT coalesce(o.enabled, s.default_enabled)
  FROM tenancy.system_settings AS s
  LEFT JOIN tenancy.organization_system_settings AS o
    ON o.organization_id = tenancy.current_organization() AND o.key = s.key
  WHERE s.key = p_key;
$$;

REVOKE ALL ON FUNCTION tenancy.setting_enabled(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.setting_enabled(text) TO xcode_api_executor;
