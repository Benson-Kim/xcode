-- api.setup_expense_main_category_create(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_name text, p_now timestamptz) RETURNS api.write_result
-- Purpose: add a main category with a name no other main category has.
-- Callers: SetupRoutines.create_expense_main_category; CreateExpenseMainCategory (POST /setup/expense-main-categories).
-- Reads: setup.expense_main_categories. Writes: setup.expense_main_categories, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 expense_name_length, XC422 expense_main_taken.
-- Tests: tests/db/test_setup_main_category_routines.py, tests/api/test_setup_expenses.py.
-- A unique_violation from a concurrent create with the same name surfaces as unique_conflict.

CREATE OR REPLACE FUNCTION api.setup_expense_main_category_create(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
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
  v_id uuid;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'catalog.add');
  IF v_name IS NULL OR char_length(v_name) > 100 THEN
    PERFORM tenancy.refuse('expense_name_length', 'XC422');
  END IF;
  IF EXISTS (
    SELECT 1 FROM setup.expense_main_categories AS m
    WHERE m.organization_id = p_organization_id AND m.normalized_name = upper(v_name COLLATE "C")
  ) THEN
    PERFORM tenancy.refuse('expense_main_taken', 'XC422');
  END IF;

  INSERT INTO setup.expense_main_categories (organization_id, name, created_at, updated_at)
  VALUES (p_organization_id, v_name, p_now, p_now)
  RETURNING id INTO v_id;
  v_version := setup.record_setup_change(
    'expenses', v_id, NULL, 'null'::json, setup.expense_main_category_snapshot(v_id),
    'Added main category ' || v_name, p_now
  );
  RETURN ROW(v_id, v_version, 'created')::api.write_result;
END;
$$;
