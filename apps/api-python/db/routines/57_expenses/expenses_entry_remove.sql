-- api.expenses_entry_remove(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_id uuid, p_expected_version bigint, p_reason text, p_now timestamptz) RETURNS jsonb
-- Purpose: remove one central expense the actor sees, softly: a typed reason of 1 to 500 characters is required; the row not removed, else not found; who may remove it (expenses.correct any row; expenses.capture alone the actor's own row of the business date); the back-dating limit on its date; the version. Records who, when and why, version + 1; the row leaves the ledger and every figure. Logs "Removed {subject}. Reason: {reason}."; answers {id, version}.
-- Callers: ExpensesRoutines.remove; RemoveExpense (POST /setup/expenses/entries/{id}/remove).
-- Reads: expenses.entries, and what tenancy.effective_permissions, tenancy.business_date, tenancy.earliest_writable, tenancy.check_writable, setup.vehicle_visible, tenancy.check_typed_reason, expenses.entry_snapshot and expenses.row_document read. Writes: expenses.entries, and what expenses.log writes.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 reason_length via tenancy.check_typed_reason, XC422 reason_length, XC404 not_found, XC422 time_zone_invalid via tenancy.business_date, XC403 expense_change_other, XC403 expense_change_earlier_day, XC422 record_too_old via tenancy.check_writable, XC422 expense_version_required, XC409 expense_version_conflict.
-- Tests: tests/db/test_expense_routines.py, tests/api/test_expenses.py.

CREATE OR REPLACE FUNCTION api.expenses_entry_remove(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_id uuid,
  p_expected_version bigint,
  p_reason text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_reason text;
  v_permissions text[];
  v_capture boolean;
  v_correct boolean;
  v_today date;
  v_entry expenses.entries;
  v_before json;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['expenses.capture', 'expenses.correct']);
  v_reason := tenancy.check_typed_reason(p_reason);
  IF v_reason IS NULL THEN
    PERFORM tenancy.refuse('reason_length', 'XC422');
  END IF;

  SELECT e.* INTO v_entry
  FROM expenses.entries AS e
  WHERE e.organization_id = p_organization_id AND e.id = p_id AND e.removed_at IS NULL
  FOR UPDATE;
  IF NOT FOUND OR NOT setup.vehicle_visible(v_entry.vehicle_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;

  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  v_capture := 'expenses.capture' = ANY (v_permissions);
  v_correct := 'expenses.correct' = ANY (v_permissions);
  v_today := tenancy.business_date(p_organization_id, p_now);
  IF NOT v_correct THEN
    IF v_entry.recorded_by <> p_actor_id THEN
      PERFORM tenancy.refuse('expense_change_other', 'XC403');
    END IF;
    IF v_entry.entry_date <> v_today THEN
      PERFORM tenancy.refuse('expense_change_earlier_day', 'XC403');
    END IF;
  END IF;
  PERFORM tenancy.check_writable(v_entry.entry_date, p_now);
  IF p_expected_version IS NULL THEN
    PERFORM tenancy.refuse('expense_version_required', 'XC422');
  END IF;
  IF p_expected_version <> v_entry.version THEN
    PERFORM tenancy.refuse(
      'expense_version_conflict',
      'XC409',
      jsonb_build_object(
        'current',
        expenses.row_document(
          v_entry.id, v_today, tenancy.earliest_writable(p_organization_id, p_actor_id, v_today),
          v_capture, v_correct
        )
      )
    );
  END IF;

  v_before := expenses.entry_snapshot(v_entry.id);
  UPDATE expenses.entries AS e
  SET removed_by = p_actor_id,
      removed_at = p_now,
      removal_reason = v_reason,
      updated_by = p_actor_id,
      updated_at = p_now,
      version = e.version + 1
  WHERE e.organization_id = p_organization_id AND e.id = v_entry.id;

  PERFORM expenses.log(v_entry.id, v_before, 'Removed', v_reason, p_now);
  RETURN jsonb_build_object('id', v_entry.id, 'version', v_entry.version + 1);
END;
$$;
