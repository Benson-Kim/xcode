-- pettycash.guard_float(p_holder_id uuid, p_kind smallint, p_delta numeric) RETURNS void
-- Purpose: the float guard: cash that lowers a float (taken back, or positive cash removed) may not leave it below zero without pettycash.issue_negative; expenses and credit notes may. Call after pettycash.lock_float.
-- Callers: api.pettycash_entry_create, api.pettycash_entry_remove.
-- Reads: what pettycash.balance and tenancy.has_permission read. Writes: nothing.
-- Raises: XC422 pettycash_below_zero.
-- Tests: tests/db/test_pettycash_helpers.py, tests/db/test_pettycash_routines.py.

CREATE OR REPLACE FUNCTION pettycash.guard_float(p_holder_id uuid, p_kind smallint, p_delta numeric)
RETURNS void
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_after numeric;
BEGIN
  IF p_kind <> 1 OR p_delta >= 0 THEN
    RETURN;
  END IF;
  v_after := pettycash.balance(p_holder_id) + p_delta;
  IF v_after < 0 AND NOT tenancy.has_permission('pettycash.issue_negative') THEN
    PERFORM tenancy.refuse('pettycash_below_zero', 'XC422', jsonb_build_object('balance_after', v_after));
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION pettycash.guard_float(uuid, smallint, numeric) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.guard_float(uuid, smallint, numeric) TO xcode_api_executor;
