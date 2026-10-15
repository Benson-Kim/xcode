-- setup.company_active_on(p_company_id uuid, p_day date) RETURNS boolean
-- Purpose: whether the company is in use on the day: not archived, or archived after it; false for an unknown company.
-- Callers: the vehicle and scheduled-item routines.
-- Reads: setup.psv_companies. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.company_active_on(p_company_id uuid, p_day date)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT coalesce(
    (
      SELECT c.archived_on IS NULL OR c.archived_on > p_day
      FROM setup.psv_companies AS c
      WHERE c.organization_id = tenancy.current_organization() AND c.id = p_company_id
    ),
    false
  );
$$;

REVOKE ALL ON FUNCTION setup.company_active_on(uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.company_active_on(uuid, date) TO xcode_api_executor;
