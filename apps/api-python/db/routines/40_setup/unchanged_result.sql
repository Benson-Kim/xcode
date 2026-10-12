-- setup.unchanged_result(p_id uuid) RETURNS api.write_result
-- Purpose: the answer of a setup write that found nothing to change: the record id, the organization's current settings_version and outcome unchanged; nothing is written or logged.
-- Callers: the setup write routines.
-- Reads: tenancy.organizations. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_company_routines.py.

CREATE OR REPLACE FUNCTION setup.unchanged_result(p_id uuid)
RETURNS api.write_result
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT ROW(p_id, o.settings_version, 'unchanged')::api.write_result
  FROM tenancy.organizations AS o
  WHERE o.id = tenancy.current_organization();
$$;

REVOKE ALL ON FUNCTION setup.unchanged_result(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.unchanged_result(uuid) TO xcode_api_executor;
