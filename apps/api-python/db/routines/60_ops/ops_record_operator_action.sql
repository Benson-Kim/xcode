-- api.ops_record_operator_action(p_operator text, p_action text, p_target text, p_detail jsonb, p_now timestamptz)
-- Purpose: let a CLI command with no other routine to call record its operator action.
-- Callers: OpsRoutines.record_operator_action (CLI commands that call no other routine; the runner records directly).
-- Reads: nothing. Writes: ops.operator_actions (through ops.record_operator_action).
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py.

CREATE OR REPLACE FUNCTION api.ops_record_operator_action(
  p_operator text,
  p_action text,
  p_target text,
  p_detail jsonb,
  p_now timestamptz
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM ops.record_operator_action(p_operator, p_action, p_target, p_detail, p_now);
END;
$$;
