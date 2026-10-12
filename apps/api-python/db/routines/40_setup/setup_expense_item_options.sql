-- api.setup_expense_item_options(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_now timestamptz) RETURNS jsonb
-- Purpose: the expense items that can be picked: in use on the business date in a category in use, by category name, item name and item id; [{id, name, category_id, category_name, bucket, main_category_id, main_category_name}] (bucket as stored, null for categories made since main categories).
-- Callers: SetupRoutines.expense_item_options; ListExpenseItemOptions (GET /setup/expense-items/options).
-- Reads: setup.expense_items, setup.expense_categories, setup.expense_main_categories, and what tenancy.business_date reads. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_setup_expense_routines.py, tests/api/test_setup_expenses.py.

CREATE OR REPLACE FUNCTION api.setup_expense_item_options(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
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
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(
    ARRAY[
      'catalog.view', 'expenses.view', 'expenses.capture', 'scheduled.view', 'scheduled.add',
      'scheduled.edit', 'pettycash.spend'
    ]
  );
  v_today := tenancy.business_date(p_organization_id, p_now);
  RETURN (
    SELECT coalesce(
             jsonb_agg(
               jsonb_build_object(
                 'id', i.id,
                 'name', i.name,
                 'category_id', c.id,
                 'category_name', c.name,
                 'bucket', c.bucket,
                 'main_category_id', m.id,
                 'main_category_name', m.name
               ) ORDER BY c.name, i.name, i.id),
             '[]'::jsonb)
    FROM setup.expense_items AS i
    JOIN setup.expense_categories AS c ON c.organization_id = i.organization_id AND c.id = i.category_id
    LEFT JOIN setup.expense_main_categories AS m
      ON m.organization_id = c.organization_id AND m.id = c.main_category_id
    WHERE i.organization_id = p_organization_id
      AND (i.stopped_on IS NULL OR i.stopped_on > v_today)
      AND (c.stopped_on IS NULL OR c.stopped_on > v_today)
  );
END;
$$;
