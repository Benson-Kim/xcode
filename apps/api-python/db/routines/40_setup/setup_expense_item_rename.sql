-- api.setup_expense_item_rename(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_item_id uuid, p_name text, p_now timestamptz) RETURNS api.write_result
-- Purpose: rename an expense item to a name no other item of its category has; the same name answers unchanged.
-- Callers: SetupRoutines.rename_expense_item; RenameExpenseItem (PUT /setup/expense-items/{id}).
-- Reads: setup.expense_items. Writes: setup.expense_items, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 expense_name_length, XC404 not_found, XC422 expense_item_taken.
-- Tests: tests/db/test_setup_expense_routines.py, tests/api/test_setup_expenses.py.

CREATE OR REPLACE FUNCTION api.setup_expense_item_rename(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_item_id uuid,
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
  v_item setup.expense_items;
  v_before json;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'catalog.edit');
  IF v_name IS NULL OR char_length(v_name) > 100 THEN
    PERFORM tenancy.refuse('expense_name_length', 'XC422');
  END IF;
  SELECT i.* INTO v_item
  FROM setup.expense_items AS i
  WHERE i.organization_id = p_organization_id AND i.id = p_item_id
  FOR UPDATE;
  IF NOT FOUND THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  IF EXISTS (
    SELECT 1 FROM setup.expense_items AS i
    WHERE i.organization_id = p_organization_id
      AND i.category_id = v_item.category_id
      AND i.id <> p_item_id
      AND i.normalized_name = upper(v_name COLLATE "C")
  ) THEN
    PERFORM tenancy.refuse('expense_item_taken', 'XC422');
  END IF;
  IF v_item.name = v_name THEN
    RETURN setup.unchanged_result(p_item_id);
  END IF;

  v_before := setup.expense_item_snapshot(p_item_id);
  UPDATE setup.expense_items
  SET name = v_name, updated_at = p_now
  WHERE organization_id = p_organization_id AND id = p_item_id;
  v_version := setup.record_setup_change(
    'expenses', p_item_id, NULL, v_before, setup.expense_item_snapshot(p_item_id),
    'Renamed expense item ' || v_item.name || ' to ' || v_name, p_now
  );
  RETURN ROW(p_item_id, v_version, 'updated')::api.write_result;
END;
$$;
