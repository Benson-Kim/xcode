-- api.setup_expense_item_set_stopped(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_item_id uuid, p_stopped boolean, p_now timestamptz) RETURNS api.write_result
-- Purpose: turn an expense item off from the business date, or back on (cancelling a stop dated later too); turning it off again on the same date, or on when it is on, answers unchanged.
-- Callers: SetupRoutines.set_expense_item_stopped; SetExpenseItemStopped (POST /setup/expense-items/{id}/stop and /restore).
-- Reads: setup.expense_items, and what tenancy.business_date reads. Writes: setup.expense_items, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 time_zone_invalid via tenancy.business_date, XC404 not_found, XC422 expense_already_stopped.
-- Tests: tests/db/test_setup_expense_routines.py, tests/api/test_setup_expenses.py.

CREATE OR REPLACE FUNCTION api.setup_expense_item_set_stopped(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_item_id uuid,
  p_stopped boolean,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_today date;
  v_item setup.expense_items;
  v_before json;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'catalog.stop');
  v_today := tenancy.business_date(p_organization_id, p_now);
  SELECT i.* INTO v_item
  FROM setup.expense_items AS i
  WHERE i.organization_id = p_organization_id AND i.id = p_item_id
  FOR UPDATE;
  IF NOT FOUND OR p_stopped IS NULL THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  IF p_stopped THEN
    IF v_item.stopped_on = v_today THEN
      RETURN setup.unchanged_result(p_item_id);
    END IF;
    IF v_item.stopped_on IS NOT NULL THEN
      PERFORM tenancy.refuse('expense_already_stopped', 'XC422');
    END IF;
  ELSIF v_item.stopped_on IS NULL THEN
    RETURN setup.unchanged_result(p_item_id);
  END IF;

  v_before := setup.expense_item_snapshot(p_item_id);
  UPDATE setup.expense_items
  SET stopped_on = CASE WHEN p_stopped THEN v_today END, updated_at = p_now
  WHERE organization_id = p_organization_id AND id = p_item_id;
  v_version := setup.record_setup_change(
    'expenses', p_item_id, NULL, v_before, setup.expense_item_snapshot(p_item_id),
    CASE WHEN p_stopped THEN 'Turned off' ELSE 'Turned on' END || ' expense item ' || v_item.name,
    p_now
  );
  RETURN ROW(p_item_id, v_version, 'updated')::api.write_result;
END;
$$;
