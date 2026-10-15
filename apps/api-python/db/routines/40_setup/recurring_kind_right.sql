-- setup.recurring_kind_right(p_kind integer, p_verb text) RETURNS text
-- Purpose: the right a scheduled item of the kind needs for the verb (view, add, edit): savings.<verb> for savings (2), scheduled.<verb> for every other kind.
-- Callers: setup.recurring_visible, setup.save_recurring, api.setup_recurring_create, api.setup_recurring_stop, api.setup_recurring_cancel_stop.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_recurring_routines.py.

CREATE OR REPLACE FUNCTION setup.recurring_kind_right(p_kind integer, p_verb text)
RETURNS text
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE WHEN p_kind = 2 THEN 'savings.' ELSE 'scheduled.' END || p_verb;
$$;

REVOKE ALL ON FUNCTION setup.recurring_kind_right(integer, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.recurring_kind_right(integer, text) TO xcode_api_executor;
