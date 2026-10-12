-- setup.recurring_current_version(p_item_id uuid) RETURNS setup.recurring_versions
-- Purpose: the item's latest version (the highest revision); a row of nulls for an unknown item.
-- Callers: setup.save_recurring, api.setup_recurring_stop, api.setup_recurring_cancel_stop.
-- Reads: setup.recurring_versions. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.recurring_current_version(p_item_id uuid)
RETURNS setup.recurring_versions
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT v.*
  FROM setup.recurring_versions AS v
  WHERE v.organization_id = tenancy.current_organization() AND v.item_id = p_item_id
  ORDER BY v.revision DESC
  LIMIT 1;
$$;

REVOKE ALL ON FUNCTION setup.recurring_current_version(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.recurring_current_version(uuid) TO xcode_api_executor;
