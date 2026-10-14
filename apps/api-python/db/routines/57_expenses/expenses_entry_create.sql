-- api.expenses_entry_create(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_id uuid, p_date date, p_expense_item_id uuid, p_units numeric, p_unit_amount numeric, p_note text, p_allocations jsonb, p_now timestamptz) RETURNS jsonb
-- Purpose: record one purchase for 1 to 50 vehicles as one central expense per vehicle sharing the purchase (the group: p_id, or a new id): one vehicle's row takes the group id, several get new ids; each row keeps the purchase as bought. A purchase recorded again under p_id answers the rows it already made (expenses.retried), checked under the purchase's advisory lock so a racing duplicate waits and then answers as a retry. Logs "Recorded {subject}" per row; answers {ids (in the order sent), total}.
-- Callers: ExpensesRoutines.record; RecordExpense (POST /setup/expenses/entries).
-- Reads: setup.fleet_vehicles, and what tenancy.business_date, tenancy.check_writable, expenses.check_purchase, expenses.retried, expenses.check_date, expenses.check_vehicle and expenses.check_item read. Writes: expenses.entries, and what expenses.log writes.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 expense_vehicles_invalid via expenses.check_purchase, XC422 pettycash_line_date_required via expenses.check_purchase, XC422 pettycash_line_amount_zero via expenses.check_purchase, XC422 pettycash_line_amount_decimals via expenses.check_purchase, XC422 pettycash_line_units via expenses.check_purchase, XC422 pettycash_line_total_zero via expenses.check_purchase, XC422 pettycash_line_total_large via expenses.check_purchase, XC422 pettycash_line_note_length via expenses.check_purchase, XC422 pettycash_line_item_required via expenses.check_purchase, XC422 expense_allocation_amount via expenses.check_purchase, XC422 expense_allocation_sign via expenses.check_purchase, XC422 expense_allocation_sum via expenses.check_purchase, XC409 expense_saved_by_other via expenses.retried, XC422 time_zone_invalid via tenancy.business_date, XC422 expense_date_future via expenses.check_date, XC422 expense_date_too_old via expenses.check_date, XC422 record_too_old via tenancy.check_writable, XC422 expense_vehicle_not_yours via expenses.check_vehicle, XC422 expense_vehicle_inactive via expenses.check_vehicle, XC422 expense_item_not_in_use via expenses.check_item, XC409 expense_saved_by_other.
-- Tests: tests/db/test_expense_routines.py, tests/api/test_expenses.py.
-- The vehicles are read FOR SHARE in id order before any is checked, so two purchases over
-- the same vehicles never wait on each other in opposite orders. The unique violation
-- handler is a backstop: the advisory lock already makes a duplicate wait and answer as a retry.

CREATE OR REPLACE FUNCTION api.expenses_entry_create(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_id uuid,
  p_date date,
  p_expense_item_id uuid,
  p_units numeric,
  p_unit_amount numeric,
  p_note text,
  p_allocations jsonb,
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
  v_id uuid := nullif(p_id, c_none);
  v_note text := tenancy.trim_text(p_note);
  v_vehicles uuid[];
  v_units numeric[];
  v_unit_amounts numeric[];
  v_retried jsonb;
  v_today date;
  v_group uuid;
  v_size integer;
  v_ids uuid[] := ARRAY[]::uuid[];
  v_row uuid;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'expenses.capture');
  SELECT array_agg(c.vehicle_id ORDER BY c.position),
         array_agg(c.units ORDER BY c.position),
         array_agg(c.unit_amount ORDER BY c.position)
  INTO v_vehicles, v_units, v_unit_amounts
  FROM expenses.check_purchase(
         p_date, p_expense_item_id, p_units, p_unit_amount, v_note, p_allocations
       ) WITH ORDINALITY AS c (vehicle_id, units, unit_amount, position);

  IF v_id IS NOT NULL THEN
    PERFORM pg_advisory_xact_lock(
      hashtextextended('xcode.expense_purchase:' || p_organization_id::text || ':' || v_id::text, 0)
    );
    v_retried := expenses.retried(v_id, p_actor_id);
    IF v_retried IS NOT NULL THEN
      RETURN v_retried;
    END IF;
  END IF;

  v_today := tenancy.business_date(p_organization_id, p_now);
  PERFORM expenses.check_date(p_date, v_today);
  PERFORM tenancy.check_writable(p_date, p_now);
  PERFORM 1
  FROM setup.fleet_vehicles AS f
  WHERE f.organization_id = p_organization_id AND f.id = ANY (v_vehicles)
  ORDER BY f.id
  FOR SHARE;
  FOR i IN 1 .. cardinality(v_vehicles) LOOP
    PERFORM expenses.check_vehicle(v_vehicles[i], p_date);
  END LOOP;
  PERFORM expenses.check_item(p_expense_item_id, p_date);

  v_group := coalesce(v_id, gen_random_uuid());
  v_size := cardinality(v_vehicles);
  BEGIN
    FOR i IN 1 .. v_size LOOP
      v_row := CASE WHEN v_size = 1 THEN v_group ELSE gen_random_uuid() END;
      INSERT INTO expenses.entries (
        organization_id, id, entry_date, vehicle_id, expense_item_id, units, unit_amount, note,
        group_id, group_size, group_total, group_units, group_unit_amount, recorded_by, recorded_at,
        updated_by, updated_at
      )
      VALUES (
        p_organization_id, v_row, p_date, v_vehicles[i], p_expense_item_id, v_units[i],
        v_unit_amounts[i], v_note, v_group, v_size, round(p_units * p_unit_amount, 2), p_units,
        p_unit_amount, p_actor_id, p_now, p_actor_id, p_now
      );
      v_ids := v_ids || v_row;
    END LOOP;
  EXCEPTION
    WHEN unique_violation THEN
      v_retried := expenses.retried(v_group, p_actor_id);
      IF v_retried IS NOT NULL THEN
        RETURN v_retried;
      END IF;
      PERFORM tenancy.refuse('expense_saved_by_other', 'XC409');
  END;

  FOR i IN 1 .. v_size LOOP
    PERFORM expenses.log(v_ids[i], 'null'::json, 'Recorded', NULL, p_now);
  END LOOP;
  RETURN jsonb_build_object('ids', to_jsonb(v_ids), 'total', round(p_units * p_unit_amount, 2));
END;
$$;
