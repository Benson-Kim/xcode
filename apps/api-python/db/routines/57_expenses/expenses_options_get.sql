-- api.expenses_options_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_date date, p_now timestamptz) RETURNS jsonb
-- Purpose: what the central-expense form picks from on p_date (default the business date) (ExpenseOptionsDto with snake_case keys): the vehicles the actor sees that are in the fleet that day (joined, not left, not away), by registration, with their company and fleet number; the items whose item and category are in use that day, by category name, item name and id, with the category's bucket (2 when it has none) and main category.
-- Callers: ExpensesRoutines.options; GetExpenseOptions (GET /setup/expenses/options).
-- Reads: setup.fleet_vehicles, setup.psv_companies, setup.expense_items, setup.expense_categories, setup.expense_main_categories, and what tenancy.business_date, setup.visible_vehicles and setup.vehicle_active_on read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 time_zone_invalid via tenancy.business_date, XC422 expense_date_future via expenses.check_date, XC422 expense_date_too_old via expenses.check_date.
-- Tests: tests/db/test_expense_routines.py, tests/api/test_expenses.py.

CREATE OR REPLACE FUNCTION api.expenses_options_get(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_date date,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_today date;
  v_date date;
  v_vehicles jsonb;
  v_items jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['expenses.capture', 'expenses.correct']);
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_date := coalesce(p_date, v_today);
  PERFORM expenses.check_date(v_date, v_today);

  SELECT coalesce(jsonb_agg(
           jsonb_build_object(
             'id', f.id,
             'company_id', f.company_id,
             'company_name', c.name,
             'registration', f.registration,
             'active', true,
             'fleet_number', f.fleet_number
           ) ORDER BY f.registration, f.id), '[]'::jsonb)
  INTO v_vehicles
  FROM setup.fleet_vehicles AS f
  JOIN setup.psv_companies AS c ON c.organization_id = f.organization_id AND c.id = f.company_id
  WHERE f.organization_id = p_organization_id
    AND f.id IN (SELECT visible.id FROM setup.visible_vehicles() AS visible (id))
    AND setup.vehicle_active_on(f.id, v_date);

  SELECT coalesce(jsonb_agg(
           jsonb_build_object(
             'id', i.id,
             'name', i.name,
             'category_id', c.id,
             'category_name', c.name,
             'bucket', coalesce(c.bucket, 2::smallint),
             'main_category_name', m.name
           ) ORDER BY c.name, i.name, i.id), '[]'::jsonb)
  INTO v_items
  FROM setup.expense_items AS i
  JOIN setup.expense_categories AS c ON c.organization_id = i.organization_id AND c.id = i.category_id
  LEFT JOIN setup.expense_main_categories AS m
    ON m.organization_id = c.organization_id AND m.id = c.main_category_id
  WHERE i.organization_id = p_organization_id
    AND (i.stopped_on IS NULL OR i.stopped_on > v_date)
    AND (c.stopped_on IS NULL OR c.stopped_on > v_date);

  RETURN jsonb_build_object('vehicles', v_vehicles, 'items', v_items);
END;
$$;
