-- api.setup_company_delete(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_company_id uuid, p_now timestamptz) RETURNS api.write_result
-- Purpose: delete a visible company nothing refers to, such as one added by mistake; the foreign keys decide, so a company with vehicles or a place in a data scope (or that any table refers to later) is refused and keeps the archive path. The change log keeps what it held (after is the JSON null).
-- Callers: SetupRoutines.delete_setup_record; DeleteSetupRecord (DELETE /setup/companies/{id}).
-- Reads: setup.psv_companies, what setup.company_visible reads, and through the foreign keys every table that refers to it. Writes: setup.psv_companies, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC404 not_found, XC409 in_use via setup.refuse_in_use.
-- Tests: tests/db/test_setup_delete_routines.py, tests/api/test_setup_deletes.py.

CREATE OR REPLACE FUNCTION api.setup_company_delete(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_company_id uuid,
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
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'companies.edit');
  SELECT c.name INTO v_name
  FROM setup.psv_companies AS c
  WHERE c.organization_id = p_organization_id AND c.id = p_company_id
  FOR UPDATE;
  IF NOT FOUND OR NOT setup.company_visible(p_company_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;

  v_before := setup.company_snapshot(p_company_id);
  BEGIN
    DELETE FROM setup.psv_companies
    WHERE organization_id = p_organization_id AND id = p_company_id;
  EXCEPTION WHEN foreign_key_violation THEN
    GET STACKED DIAGNOSTICS v_schema = SCHEMA_NAME, v_table = TABLE_NAME;
    PERFORM setup.refuse_in_use('company', v_name, v_schema || '.' || v_table);
  END;
  v_version := setup.record_setup_change(
    'companies', p_company_id, NULL, v_before, 'null'::json, 'Deleted company ' || v_name, p_now
  );
  RETURN ROW(p_company_id, v_version, 'updated')::api.write_result;
END;
$$;
