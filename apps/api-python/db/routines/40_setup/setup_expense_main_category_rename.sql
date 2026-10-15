-- api.setup_expense_main_category_rename(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_id uuid, p_name text, p_now timestamptz) RETURNS api.write_result
-- Purpose: rename a main category to a name no other main category has; the same name answers unchanged.
-- Callers: SetupRoutines.rename_expense_main_category; RenameExpenseMainCategory (PUT /setup/expense-main-categories/{id}).
-- Reads: setup.expense_main_categories. Writes: setup.expense_main_categories, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 expense_name_length, XC404 not_found, XC422 expense_main_taken.
-- Tests: tests/db/test_setup_main_category_routines.py, tests/api/test_setup_expenses.py.

CREATE OR REPLACE FUNCTION api.setup_expense_main_category_rename(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_id uuid,
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
  v_old text;
  v_before json;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'catalog.edit');
  IF v_name IS NULL OR char_length(v_name) > 100 THEN
    PERFORM tenancy.refuse('expense_name_length', 'XC422');
  END IF;
  SELECT m.name INTO v_old
  FROM setup.expense_main_categories AS m
  WHERE m.organization_id = p_organization_id AND m.id = p_id
  FOR UPDATE;
  IF NOT FOUND THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  IF EXISTS (
    SELECT 1 FROM setup.expense_main_categories AS m
    WHERE m.organization_id = p_organization_id
      AND m.id <> p_id
      AND m.normalized_name = upper(v_name COLLATE "C")
  ) THEN
    PERFORM tenancy.refuse('expense_main_taken', 'XC422');
  END IF;
  IF v_old = v_name THEN
    RETURN setup.unchanged_result(p_id);
  END IF;

  v_before := setup.expense_main_category_snapshot(p_id);
  UPDATE setup.expense_main_categories
  SET name = v_name, updated_at = p_now
  WHERE organization_id = p_organization_id AND id = p_id;
  v_version := setup.record_setup_change(
    'expenses', p_id, NULL, v_before, setup.expense_main_category_snapshot(p_id),
    'Renamed main category ' || v_old || ' to ' || v_name, p_now
  );
  RETURN ROW(p_id, v_version, 'updated')::api.write_result;
END;
$$;
