-- api.setup_recurring_create(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_name text, p_kind integer, p_amount numeric, p_frequency integer, p_day integer, p_last_day boolean, p_start date, p_end date, p_allocations jsonb, p_expense_item_id uuid, p_note text, p_month integer, p_reason text, p_now timestamptz) RETURNS api.write_result
-- Purpose: add a scheduled expense or saving shared by vehicles in the actor's reach; id is the new item id.
-- Callers: SetupRoutines.create_recurring; CreateRecurring (POST /setup/recurring).
-- Reads: what setup.save_recurring reads. Writes: what setup.save_recurring writes.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC403 permission_missing via tenancy.require_permission (the add right of the kind), XC422 reason_length via setup.save_recurring, XC422 recurring_savings_item via setup.save_recurring, XC422 recurring_item_not_in_use via setup.save_recurring, XC422 recurring_schedule_shape via setup.save_recurring, XC422 recurring_name_length via setup.save_recurring, XC422 money_invalid via setup.save_recurring, XC422 recurring_kind_invalid via setup.save_recurring, XC422 recurring_note_length via setup.save_recurring, XC422 recurring_end_before_start via setup.save_recurring, XC422 recurring_allocations_count via setup.save_recurring, XC422 recurring_allocation_sum via setup.save_recurring, XC422 recurring_daily_retired via setup.save_recurring, XC422 recurring_savings_frequency via setup.save_recurring, XC422 recurring_cost_needs_item via setup.save_recurring, XC422 recurring_start_required via setup.save_recurring, XC422 recurring_start_too_early via setup.save_recurring, XC404 not_found via setup.save_recurring, XC422 recurring_share_inactive via setup.save_recurring.
-- Tests: tests/db/test_setup_recurring_routines.py, tests/api/test_setup_recurring.py.

CREATE OR REPLACE FUNCTION api.setup_recurring_create(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_name text,
  p_kind integer,
  p_amount numeric,
  p_frequency integer,
  p_day integer,
  p_last_day boolean,
  p_start date,
  p_end date,
  p_allocations jsonb,
  p_expense_item_id uuid,
  p_note text,
  p_month integer,
  p_reason text,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['scheduled.add', 'savings.add']);
  IF p_kind IN (1, 2) THEN
    PERFORM tenancy.require_permission(setup.recurring_kind_right(p_kind, 'add'));
  END IF;
  RETURN setup.save_recurring(
    NULL, p_name, p_kind, p_amount, p_frequency, p_day, p_last_day, p_start, p_end, p_allocations,
    p_expense_item_id, p_note, p_month, p_reason, p_now
  );
END;
$$;
