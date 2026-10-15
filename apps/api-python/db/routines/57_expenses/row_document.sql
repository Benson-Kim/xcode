-- expenses.row_document(p_id uuid, p_today date, p_earliest date, p_can_capture boolean, p_can_correct boolean) RETURNS jsonb
-- Purpose: one central expense as the ledger lists it for the current actor (the ledger row of expenses.ledger_rows on its vehicle and day, snake_case keys), for a 409's current member; NULL when the ledger would not list it (removed, or outside its vehicle's days).
-- Callers: api.expenses_entry_update, api.expenses_entry_remove.
-- Reads: expenses.entries, and what expenses.ledger_rows reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_expense_routines.py.

CREATE OR REPLACE FUNCTION expenses.row_document(
  p_id uuid,
  p_today date,
  p_earliest date,
  p_can_capture boolean,
  p_can_correct boolean
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_entry expenses.entries;
  v_document jsonb;
BEGIN
  SELECT e.* INTO v_entry
  FROM expenses.entries AS e
  WHERE e.organization_id = tenancy.current_organization() AND e.id = p_id;
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;
  SELECT to_jsonb(r) - 'source_order' - 'matched' INTO v_document
  FROM expenses.ledger_rows(
         ARRAY[v_entry.vehicle_id], v_entry.entry_date, v_entry.entry_date, p_today, 'central', NULL,
         tenancy.current_actor(), p_can_capture, p_can_correct, p_earliest
       ) AS r
  WHERE r.id = p_id::text;
  RETURN v_document;
END;
$$;

REVOKE ALL ON FUNCTION expenses.row_document(uuid, date, date, boolean, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION expenses.row_document(uuid, date, date, boolean, boolean) TO xcode_api_executor;
