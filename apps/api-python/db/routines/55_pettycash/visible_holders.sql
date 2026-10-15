-- pettycash.visible_holders(p_view_all boolean) RETURNS TABLE (user_id uuid, name text, active boolean)
-- Purpose: the floats the current actor may see, in the order of pettycash.holders: every float with pettycash.view_all, else the actor's own when they have one, else none.
-- Callers: api.pettycash_overview_get, api.pettycash_entry_list, api.pettycash_dashboard_get, api.pettycash_day_approve.
-- Reads: what pettycash.holders reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_pettycash_helpers.py.

CREATE OR REPLACE FUNCTION pettycash.visible_holders(p_view_all boolean)
RETURNS TABLE (user_id uuid, name text, active boolean)
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  RETURN QUERY
  SELECT h.user_id, h.name, h.active
  FROM pettycash.holders() WITH ORDINALITY AS h (user_id, name, active, position)
  WHERE p_view_all OR h.user_id = tenancy.current_actor()
  ORDER BY h.position;
END;
$$;

REVOKE ALL ON FUNCTION pettycash.visible_holders(boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.visible_holders(boolean) TO xcode_api_executor;
