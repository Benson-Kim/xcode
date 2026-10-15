-- expenses.log(p_id uuid, p_before json, p_verb text, p_typed text, p_now timestamptz) RETURNS void
-- Purpose: log one write on a central expense, read after the write: a change-log row in section centralexpenses (the row's vehicle, the snapshots before and after, the reason "{p_verb} {subject}" with the typed reason after it, within 500 characters) and the audit row expenses.recorded with the same snapshots.
-- Callers: api.expenses_entry_create, api.expenses_entry_update, api.expenses_entry_remove.
-- Reads: expenses.entries, and what expenses.entry_snapshot and expenses.describe read. Writes: what tenancy.record_change writes.
-- Raises: XC403 not_member via tenancy.record_change.
-- Tests: tests/db/test_expense_routines.py.

CREATE OR REPLACE FUNCTION expenses.log(
  p_id uuid,
  p_before json,
  p_verb text,
  p_typed text,
  p_now timestamptz
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_vehicle uuid;
  v_after json := expenses.entry_snapshot(p_id);
BEGIN
  SELECT e.vehicle_id INTO v_vehicle
  FROM expenses.entries AS e
  WHERE e.organization_id = tenancy.current_organization() AND e.id = p_id;
  PERFORM tenancy.record_change(
    'centralexpenses',
    p_id,
    v_vehicle,
    p_before,
    v_after,
    tenancy.compose_reason(p_verb || ' ' || expenses.describe(p_id), p_typed),
    'expenses.recorded',
    p_id::text,
    p_before::jsonb,
    v_after::jsonb,
    p_now
  );
END;
$$;

REVOKE ALL ON FUNCTION expenses.log(uuid, json, text, text, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION expenses.log(uuid, json, text, text, timestamptz) TO xcode_api_executor;
