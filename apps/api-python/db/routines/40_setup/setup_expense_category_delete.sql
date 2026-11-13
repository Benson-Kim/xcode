-- api.setup_expense_category_delete(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_category_id uuid, p_now timestamptz) RETURNS api.write_result
-- Purpose: delete an expense category nothing refers to, such as one added by mistake; the foreign keys decide, so a category that has items (or that any table refers to later) is refused and keeps the stop path. The change log keeps what it held (after is the JSON null).
-- Callers: SetupRoutines.delete_setup_record; DeleteSetupRecord (DELETE /setup/expense-categories/{id}).
-- Reads: setup.expense_categories, and through the foreign keys every table that refers to it. Writes: setup.expense_categories, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC404 not_found, XC409 in_use via setup.refuse_in_use.
-- Tests: tests/db/test_setup_delete_routines.py, tests/api/test_setup_deletes.py.

CREATE OR REPLACE FUNCTION api.setup_expense_category_delete(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_category_id uuid,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_category setup.expense_categories;
  v_before json;
  v_schema text;
  v_table text;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'catalog.stop');
  SELECT c.* INTO v_category
  FROM setup.expense_categories AS c
  WHERE c.organization_id = p_organization_id AND c.id = p_category_id
  FOR UPDATE;
  IF NOT FOUND THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;

  v_before := setup.expense_category_snapshot(p_category_id);
  BEGIN
    DELETE FROM setup.expense_categories
    WHERE organization_id = p_organization_id AND id = p_category_id;
  EXCEPTION WHEN foreign_key_violation THEN
    GET STACKED DIAGNOSTICS v_schema = SCHEMA_NAME, v_table = TABLE_NAME;
    PERFORM setup.refuse_in_use('category', v_category.name, v_schema || '.' || v_table);
  END;
  v_version := setup.record_setup_change(
    'expenses', p_category_id, NULL, v_before, 'null'::json,
    'Deleted expense category ' || v_category.name, p_now
  );
  RETURN ROW(p_category_id, v_version, 'updated')::api.write_result;
END;
$$;
