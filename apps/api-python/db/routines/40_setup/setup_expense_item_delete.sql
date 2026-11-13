-- api.setup_expense_item_delete(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_item_id uuid, p_now timestamptz) RETURNS api.write_result
-- Purpose: delete an expense item nothing refers to, such as one added by mistake; the foreign keys decide, so an item that expenses, petty cash entries or scheduled items use (or any table that refers to it later) is refused and keeps the stop path. The change log keeps what it held (after is the JSON null).
-- Callers: SetupRoutines.delete_setup_record; DeleteSetupRecord (DELETE /setup/expense-items/{id}).
-- Reads: setup.expense_items, and through the foreign keys every table that refers to it. Writes: setup.expense_items, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC404 not_found, XC409 in_use via setup.refuse_in_use.
-- Tests: tests/db/test_setup_delete_routines.py, tests/api/test_setup_deletes.py.

CREATE OR REPLACE FUNCTION api.setup_expense_item_delete(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_item_id uuid,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_item setup.expense_items;
  v_before json;
  v_schema text;
  v_table text;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'catalog.stop');
  SELECT i.* INTO v_item
  FROM setup.expense_items AS i
  WHERE i.organization_id = p_organization_id AND i.id = p_item_id
  FOR UPDATE;
  IF NOT FOUND THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;

  v_before := setup.expense_item_snapshot(p_item_id);
  BEGIN
    DELETE FROM setup.expense_items
    WHERE organization_id = p_organization_id AND id = p_item_id;
  EXCEPTION WHEN foreign_key_violation THEN
    GET STACKED DIAGNOSTICS v_schema = SCHEMA_NAME, v_table = TABLE_NAME;
    PERFORM setup.refuse_in_use('item', v_item.name, v_schema || '.' || v_table);
  END;
  v_version := setup.record_setup_change(
    'expenses', p_item_id, NULL, v_before, 'null'::json, 'Deleted expense item ' || v_item.name,
    p_now
  );
  RETURN ROW(p_item_id, v_version, 'updated')::api.write_result;
END;
$$;
