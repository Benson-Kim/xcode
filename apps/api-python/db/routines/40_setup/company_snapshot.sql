-- setup.company_snapshot(p_id uuid) RETURNS json
-- Purpose: the change-log snapshot of a company, compact JSON with the .NET keys Id, Name, ArchivedOn, Active (no archive date, whatever the business date, as .NET's snapshot); the JSON null for an unknown company.
-- Callers: the company write routines.
-- Reads: setup.psv_companies. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.company_snapshot(p_id uuid)
RETURNS json
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT tenancy.compact_json(coalesce(
    (
      SELECT json_build_object(
               'Id', c.id,
               'Name', c.name,
               'ArchivedOn', c.archived_on,
               'Active', c.archived_on IS NULL
             )
      FROM setup.psv_companies AS c
      WHERE c.organization_id = tenancy.current_organization() AND c.id = p_id
    ),
    'null'::json
  ));
$$;

REVOKE ALL ON FUNCTION setup.company_snapshot(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.company_snapshot(uuid) TO xcode_api_executor;
