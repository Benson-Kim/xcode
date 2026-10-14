-- expenses.check_item(p_expense_item_id uuid, p_date date) RETURNS void
-- Purpose: the item of a central expense and its category in use on the date, both read FOR SHARE so a stop that commits meanwhile is waited for and then seen; an unknown item is not in use.
-- Callers: api.expenses_entry_create, api.expenses_entry_update.
-- Reads: setup.expense_items, setup.expense_categories. Writes: nothing.
-- Raises: XC422 expense_item_not_in_use.
-- Tests: tests/db/test_expense_routines.py.

CREATE OR REPLACE FUNCTION expenses.check_item(p_expense_item_id uuid, p_date date)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM 1
  FROM setup.expense_items AS i
  JOIN setup.expense_categories AS c
    ON c.organization_id = i.organization_id AND c.id = i.category_id
  WHERE i.organization_id = tenancy.current_organization()
    AND i.id = p_expense_item_id
    AND (i.stopped_on IS NULL OR i.stopped_on > p_date)
    AND (c.stopped_on IS NULL OR c.stopped_on > p_date)
  FOR SHARE OF i, c;
  IF NOT FOUND THEN
    PERFORM tenancy.refuse('expense_item_not_in_use', 'XC422');
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION expenses.check_item(uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION expenses.check_item(uuid, date) TO xcode_api_executor;
