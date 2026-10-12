-- api.setup_expense_item_create(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_category_id uuid, p_name text, p_now timestamptz) RETURNS api.write_result
-- Purpose: add an item to an expense category (a category that is turned off still accepts items) with a name no other item of that category has; id is the new item id.
-- Callers: SetupRoutines.create_expense_item; CreateExpenseItem (POST /setup/expense-categories/{id}/items).
-- Reads: setup.expense_categories, setup.expense_items. Writes: setup.expense_items, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC404 not_found, XC422 expense_name_length, XC422 expense_item_taken.
-- Tests: tests/db/test_setup_expense_routines.py, tests/api/test_setup_expenses.py.
-- A unique_violation from a concurrent create with the same name surfaces as unique_conflict.

CREATE OR REPLACE FUNCTION api.setup_expense_item_create(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_category_id uuid,
  p_name text,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_name text := tenancy.trim_text(p_name);
  v_category_name text;
  v_id uuid;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'catalog.add');
  SELECT c.name INTO v_category_name
  FROM setup.expense_categories AS c
  WHERE c.organization_id = p_organization_id AND c.id = p_category_id;
  IF NOT FOUND THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  IF v_name IS NULL OR char_length(v_name) > 100 THEN
    PERFORM tenancy.refuse('expense_name_length', 'XC422');
  END IF;
  IF EXISTS (
    SELECT 1 FROM setup.expense_items AS i
    WHERE i.organization_id = p_organization_id
      AND i.category_id = p_category_id
      AND i.normalized_name = upper(v_name COLLATE "C")
  ) THEN
    PERFORM tenancy.refuse('expense_item_taken', 'XC422');
  END IF;

  INSERT INTO setup.expense_items (organization_id, category_id, name, created_at, updated_at)
  VALUES (p_organization_id, p_category_id, v_name, p_now, p_now)
  RETURNING id INTO v_id;
  v_version := setup.record_setup_change(
    'expenses', v_id, NULL, 'null'::json, setup.expense_item_snapshot(v_id),
    'Added expense item ' || v_name || ' under ' || v_category_name, p_now
  );
  RETURN ROW(v_id, v_version, 'created')::api.write_result;
END;
$$;
