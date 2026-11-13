-- api.setup_expense_main_category_delete(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_id uuid, p_now timestamptz) RETURNS api.write_result
-- Purpose: delete a main category nothing refers to, such as one added by mistake; the foreign keys decide, so a main category that has categories (or that any table refers to later) is refused. The change log keeps what it held (after is the JSON null).
-- Callers: SetupRoutines.delete_setup_record; DeleteSetupRecord (DELETE /setup/expense-main-categories/{id}).
-- Reads: setup.expense_main_categories, and through the foreign keys every table that refers to it. Writes: setup.expense_main_categories, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC404 not_found, XC409 in_use via setup.refuse_in_use.
-- Tests: tests/db/test_setup_delete_routines.py, tests/api/test_setup_deletes.py.

CREATE OR REPLACE FUNCTION api.setup_expense_main_category_delete(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_id uuid,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_name text;
  v_before json;
  v_schema text;
  v_table text;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'catalog.stop');
  SELECT m.name INTO v_name
  FROM setup.expense_main_categories AS m
  WHERE m.organization_id = p_organization_id AND m.id = p_id
  FOR UPDATE;
  IF NOT FOUND THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;

  v_before := setup.expense_main_category_snapshot(p_id);
  BEGIN
    DELETE FROM setup.expense_main_categories
    WHERE organization_id = p_organization_id AND id = p_id;
  EXCEPTION WHEN foreign_key_violation THEN
    GET STACKED DIAGNOSTICS v_schema = SCHEMA_NAME, v_table = TABLE_NAME;
    PERFORM setup.refuse_in_use('main_category', v_name, v_schema || '.' || v_table);
  END;
  v_version := setup.record_setup_change(
    'expenses', p_id, NULL, v_before, 'null'::json, 'Deleted main category ' || v_name, p_now
  );
  RETURN ROW(p_id, v_version, 'updated')::api.write_result;
END;
$$;
