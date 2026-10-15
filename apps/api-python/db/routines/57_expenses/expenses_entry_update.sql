-- api.expenses_entry_update(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_id uuid, p_date date, p_vehicle_id uuid, p_expense_item_id uuid, p_units numeric, p_unit_amount numeric, p_note text, p_expected_version bigint, p_now timestamptz) RETURNS jsonb
-- Purpose: change one central expense the actor sees and that is not removed: the line is checked first; an identical line answers the row as it is before any right or version check; then who may change it (expenses.correct any row; expenses.capture alone the actor's own row of the business date, its date unchanged), the back-dating limit on the stored date, the version, the new date and its limit, the vehicle for a new date or vehicle (visible, in the fleet, not already in the purchase, removed rows included), the item for a new date or item. A new item, units or unit amount takes the row out of its group (it becomes its own purchase; the group id stays); a new date, vehicle or note keeps it. Version + 1; logs "Changed {subject}" (read after); answers {id, version}.
-- Callers: ExpensesRoutines.change; ChangeExpense (PUT /setup/expenses/entries/{id}).
-- Reads: expenses.entries, and what tenancy.effective_permissions, tenancy.business_date, tenancy.earliest_writable, tenancy.check_writable, setup.vehicle_visible, pettycash.check_line, expenses.check_date, expenses.check_vehicle, expenses.check_item, expenses.entry_snapshot and expenses.row_document read. Writes: expenses.entries, and what expenses.log writes.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 pettycash_line_date_required via pettycash.check_line, XC422 pettycash_line_amount_zero via pettycash.check_line, XC422 pettycash_line_amount_decimals via pettycash.check_line, XC422 pettycash_line_units via pettycash.check_line, XC422 pettycash_line_total_zero via pettycash.check_line, XC422 pettycash_line_total_large via pettycash.check_line, XC422 pettycash_line_note_length via pettycash.check_line, XC422 pettycash_line_vehicle_required via pettycash.check_line, XC422 pettycash_line_item_required via pettycash.check_line, XC404 not_found, XC403 expense_change_other, XC403 expense_change_earlier_day, XC403 expense_change_date, XC422 time_zone_invalid via tenancy.business_date, XC422 record_too_old via tenancy.check_writable, XC422 expense_version_required, XC409 expense_version_conflict, XC422 expense_date_future via expenses.check_date, XC422 expense_date_too_old via expenses.check_date, XC422 expense_vehicle_not_yours via expenses.check_vehicle, XC422 expense_vehicle_inactive via expenses.check_vehicle, XC422 expense_purchase_has_vehicle, XC422 expense_item_not_in_use via expenses.check_item.
-- Tests: tests/db/test_expense_routines.py, tests/api/test_expenses.py.

CREATE OR REPLACE FUNCTION api.expenses_entry_update(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_id uuid,
  p_date date,
  p_vehicle_id uuid,
  p_expense_item_id uuid,
  p_units numeric,
  p_unit_amount numeric,
  p_note text,
  p_expected_version bigint,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  c_none CONSTANT uuid := '00000000-0000-0000-0000-000000000000';
  v_vehicle uuid := nullif(p_vehicle_id, c_none);
  v_item uuid := nullif(p_expense_item_id, c_none);
  v_note text := tenancy.trim_text(p_note);
  v_permissions text[];
  v_capture boolean;
  v_correct boolean;
  v_today date;
  v_entry expenses.entries;
  v_before json;
  v_date_changed boolean;
  v_vehicle_changed boolean;
  v_detach boolean;
  v_registration text;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['expenses.capture', 'expenses.correct']);
  PERFORM pettycash.check_line(
    2::smallint, p_date, p_unit_amount, p_units, v_vehicle, v_item, NULL, v_note, false
  );

  SELECT e.* INTO v_entry
  FROM expenses.entries AS e
  WHERE e.organization_id = p_organization_id AND e.id = p_id AND e.removed_at IS NULL
  FOR UPDATE;
  IF NOT FOUND OR NOT setup.vehicle_visible(v_entry.vehicle_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  IF v_entry.entry_date = p_date
     AND v_entry.vehicle_id = v_vehicle
     AND v_entry.expense_item_id = v_item
     AND v_entry.units = p_units
     AND v_entry.unit_amount = p_unit_amount
     AND v_entry.note IS NOT DISTINCT FROM v_note THEN
    RETURN jsonb_build_object('id', v_entry.id, 'version', v_entry.version);
  END IF;

  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  v_capture := 'expenses.capture' = ANY (v_permissions);
  v_correct := 'expenses.correct' = ANY (v_permissions);
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_date_changed := p_date <> v_entry.entry_date;
  v_vehicle_changed := v_vehicle <> v_entry.vehicle_id;
  IF NOT v_correct THEN
    IF v_entry.recorded_by <> p_actor_id THEN
      PERFORM tenancy.refuse('expense_change_other', 'XC403');
    END IF;
    IF v_entry.entry_date <> v_today THEN
      PERFORM tenancy.refuse('expense_change_earlier_day', 'XC403');
    END IF;
    IF v_date_changed THEN
      PERFORM tenancy.refuse('expense_change_date', 'XC403');
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
  IF v_date_changed THEN
    PERFORM expenses.check_date(p_date, v_today);
    PERFORM tenancy.check_writable(p_date, p_now);
  END IF;
  IF v_date_changed OR v_vehicle_changed THEN
    v_registration := expenses.check_vehicle(v_vehicle, p_date);
    IF v_vehicle_changed AND EXISTS (
      SELECT 1
      FROM expenses.entries AS e
      WHERE e.organization_id = p_organization_id
        AND e.group_id = v_entry.group_id
        AND e.vehicle_id = v_vehicle
    ) THEN
      PERFORM tenancy.refuse(
        'expense_purchase_has_vehicle', 'XC422', jsonb_build_object('registration', v_registration)
      );
    END IF;
  END IF;
  IF v_date_changed OR v_item <> v_entry.expense_item_id THEN
    PERFORM expenses.check_item(v_item, p_date);
  END IF;

  v_before := expenses.entry_snapshot(v_entry.id);
  v_detach := v_item <> v_entry.expense_item_id
    OR p_units <> v_entry.units
    OR p_unit_amount <> v_entry.unit_amount;
  UPDATE expenses.entries AS e
  SET entry_date = p_date,
      vehicle_id = v_vehicle,
      expense_item_id = v_item,
      units = p_units,
      unit_amount = p_unit_amount,
      note = v_note,
      group_size = CASE WHEN v_detach THEN 1 ELSE e.group_size END,
      group_total = CASE WHEN v_detach THEN round(p_units * p_unit_amount, 2) ELSE e.group_total END,
      group_units = CASE WHEN v_detach THEN p_units ELSE e.group_units END,
      group_unit_amount = CASE WHEN v_detach THEN p_unit_amount ELSE e.group_unit_amount END,
      updated_by = p_actor_id,
      updated_at = p_now,
      version = e.version + 1
  WHERE e.organization_id = p_organization_id AND e.id = v_entry.id;

  PERFORM expenses.log(v_entry.id, v_before, 'Changed', NULL, p_now);
  RETURN jsonb_build_object('id', v_entry.id, 'version', v_entry.version + 1);
END;
$$;
