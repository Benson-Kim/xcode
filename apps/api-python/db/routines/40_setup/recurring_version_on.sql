-- setup.recurring_version_on(p_item_id uuid, p_day date) RETURNS setup.recurring_versions
-- Purpose: the version in charge of the item on the day: the highest revision whose effective_from is on or before it; a row of nulls when none is.
-- Callers: the revenue and petty-cash readers of scheduled postings.
-- Reads: setup.recurring_versions. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.recurring_version_on(p_item_id uuid, p_day date)
RETURNS setup.recurring_versions
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT v.*
  FROM setup.recurring_versions AS v
  WHERE v.organization_id = tenancy.current_organization()
    AND v.item_id = p_item_id
    AND v.effective_from <= p_day
  ORDER BY v.revision DESC
  LIMIT 1;
$$;

REVOKE ALL ON FUNCTION setup.recurring_version_on(uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.recurring_version_on(uuid, date) TO xcode_api_executor;
