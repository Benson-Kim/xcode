-- setup.recurring_change_reason(p_kind integer, p_name text) RETURNS text
-- Purpose: the automatic change-log reason of every scheduled-item write: "Saving, <name>" for savings (2), "Scheduled expense, <name>" for every other kind.
-- Callers: setup.save_recurring, api.setup_recurring_stop, api.setup_recurring_cancel_stop.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_recurring_routines.py.

CREATE OR REPLACE FUNCTION setup.recurring_change_reason(p_kind integer, p_name text)
RETURNS text
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE WHEN p_kind = 2 THEN 'Saving, ' ELSE 'Scheduled expense, ' END || p_name;
$$;

REVOKE ALL ON FUNCTION setup.recurring_change_reason(integer, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.recurring_change_reason(integer, text) TO xcode_api_executor;
