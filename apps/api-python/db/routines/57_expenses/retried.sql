-- expenses.retried(p_id uuid, p_actor_id uuid) RETURNS jsonb
-- Purpose: the answer to a purchase recorded again under its id: NULL when no central expense of the organization has p_id as its group or its own id (removed rows included); else {ids (by id), total (the first row's stored group total)}, unless one of them belongs to another purchase or another recorder.
-- Callers: api.expenses_entry_create.
-- Reads: expenses.entries. Writes: nothing.
-- Raises: XC409 expense_saved_by_other.
-- Tests: tests/db/test_expense_routines.py.

CREATE OR REPLACE FUNCTION expenses.retried(p_id uuid, p_actor_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_ids uuid[];
  v_totals numeric[];
  v_foreign boolean;
BEGIN
  SELECT array_agg(e.id ORDER BY e.id),
         array_agg(e.group_total ORDER BY e.id),
         bool_or(e.group_id <> p_id OR e.recorded_by <> p_actor_id)
  INTO v_ids, v_totals, v_foreign
  FROM expenses.entries AS e
  WHERE e.organization_id = tenancy.current_organization()
    AND (e.group_id = p_id OR e.id = p_id);
  IF v_ids IS NULL THEN
    RETURN NULL;
  END IF;
  IF v_foreign THEN
    PERFORM tenancy.refuse('expense_saved_by_other', 'XC409');
  END IF;
  RETURN jsonb_build_object('ids', to_jsonb(v_ids), 'total', v_totals[1]);
END;
$$;

REVOKE ALL ON FUNCTION expenses.retried(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION expenses.retried(uuid, uuid) TO xcode_api_executor;
