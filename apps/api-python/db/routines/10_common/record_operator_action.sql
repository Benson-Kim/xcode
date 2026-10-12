-- ops.record_operator_action(p_operator text, p_action text, p_target text, p_detail jsonb, p_now timestamptz)
-- Purpose: append one audit row for an operator or runner action; used by every api.ops_* routine and the runner.
-- Callers: api.ops_record_operator_action and later api.ops_* routines; db/migrate.py records runner actions directly.
-- Reads: nothing. Writes: ops.operator_actions.
-- Raises: none (the operator length CHECK on the table rejects bad input as a bug).
-- Tests: tests/db/test_ops_routines.py.

CREATE OR REPLACE FUNCTION ops.record_operator_action(
  p_operator text,
  p_action text,
  p_target text,
  p_detail jsonb,
  p_now timestamptz
)
RETURNS void
LANGUAGE sql
SECURITY INVOKER
SET search_path = pg_catalog, pg_temp
AS $$
  INSERT INTO ops.operator_actions (operator, action, target, detail, recorded_at)
  VALUES (p_operator, p_action, p_target, coalesce(p_detail, '{}'::jsonb), p_now);
$$;

REVOKE ALL ON FUNCTION ops.record_operator_action(text, text, text, jsonb, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ops.record_operator_action(text, text, text, jsonb, timestamptz) TO xcode_api_executor;
