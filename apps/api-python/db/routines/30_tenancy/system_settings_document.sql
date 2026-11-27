-- tenancy.system_settings_document() RETURNS jsonb
-- Purpose: the system settings of the current organization as GET /setup/settings serves them: {settings: [{key, label, on}]} in catalogue order, each on or off by the organization's choice, else by its default.
-- Callers: api.setup_settings_get, api.setup_settings_set.
-- Reads: tenancy.system_settings, tenancy.organization_system_settings. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_system_settings_routines.py.

CREATE OR REPLACE FUNCTION tenancy.system_settings_document()
RETURNS jsonb
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT jsonb_build_object(
           'settings',
           coalesce(
             jsonb_agg(
               jsonb_build_object(
                 'key', s.key,
                 'label', s.label,
                 'on', coalesce(o.enabled, s.default_enabled)
               ) ORDER BY s.sort_order),
             '[]'::jsonb
           )
         )
  FROM tenancy.system_settings AS s
  LEFT JOIN tenancy.organization_system_settings AS o
    ON o.organization_id = tenancy.current_organization() AND o.key = s.key;
$$;

REVOKE ALL ON FUNCTION tenancy.system_settings_document() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.system_settings_document() TO xcode_api_executor;
