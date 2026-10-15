-- api.setup_expense_category_update(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_category_id uuid, p_name text, p_main_category_id uuid, p_main_category_given boolean, p_now timestamptz) RETURNS api.write_result
-- Purpose: rename an expense category, or move it under another main category or none when p_main_category_given (every expense of its items follows at once, nothing is stored on them); nothing different answers unchanged.
-- Callers: SetupRoutines.update_expense_category; UpdateExpenseCategory (PUT /setup/expense-categories/{id}).
-- Reads: setup.expense_categories, setup.expense_main_categories. Writes: setup.expense_categories, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 expense_name_length, XC404 not_found (the category, then the main category), XC422 expense_category_taken.
-- Tests: tests/db/test_setup_expense_routines.py, tests/api/test_setup_expenses.py.

CREATE OR REPLACE FUNCTION api.setup_expense_category_update(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_category_id uuid,
  p_name text,
  p_main_category_id uuid,
  p_main_category_given boolean,
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
  v_category setup.expense_categories;
  v_main_id uuid;
  v_main text;
  v_parts text[] := '{}';
  v_before json;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'catalog.edit');
  IF v_name IS NULL OR char_length(v_name) > 100 THEN
    PERFORM tenancy.refuse('expense_name_length', 'XC422');
  END IF;
  SELECT c.* INTO v_category
  FROM setup.expense_categories AS c
  WHERE c.organization_id = p_organization_id AND c.id = p_category_id
  FOR UPDATE;
  IF NOT FOUND THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  v_main_id := CASE WHEN coalesce(p_main_category_given, false) THEN p_main_category_id
                    ELSE v_category.main_category_id END;
  IF v_main_id IS NOT NULL THEN
    SELECT m.name INTO v_main
    FROM setup.expense_main_categories AS m
    WHERE m.organization_id = p_organization_id AND m.id = v_main_id;
    IF NOT FOUND THEN
      PERFORM tenancy.refuse('not_found', 'XC404');
    END IF;
  END IF;
  IF EXISTS (
    SELECT 1 FROM setup.expense_categories AS c
    WHERE c.organization_id = p_organization_id
      AND c.id <> p_category_id
      AND c.normalized_name = upper(v_name COLLATE "C")
  ) THEN
    PERFORM tenancy.refuse('expense_category_taken', 'XC422');
  END IF;
  IF v_category.name <> v_name THEN
    v_parts := v_parts || ('Renamed expense category ' || v_category.name || ' to ' || v_name);
  END IF;
  IF v_category.main_category_id IS DISTINCT FROM v_main_id THEN
    v_parts := v_parts || (
      CASE WHEN cardinality(v_parts) = 0 THEN 'Moved expense category ' || v_name || ' to '
           ELSE 'moved to ' END
        || coalesce('main category ' || v_main, 'no main category')
    );
  END IF;
  IF cardinality(v_parts) = 0 THEN
    RETURN setup.unchanged_result(p_category_id);
  END IF;

  v_before := setup.expense_category_snapshot(p_category_id);
  UPDATE setup.expense_categories
  SET name = v_name, main_category_id = v_main_id, updated_at = p_now
  WHERE organization_id = p_organization_id AND id = p_category_id;
  v_version := setup.record_setup_change(
    'expenses', p_category_id, NULL, v_before, setup.expense_category_snapshot(p_category_id),
    array_to_string(v_parts, ', '), p_now
  );
  RETURN ROW(p_category_id, v_version, 'updated')::api.write_result;
END;
$$;
