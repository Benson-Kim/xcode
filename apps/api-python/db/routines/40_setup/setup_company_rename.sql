-- api.setup_company_rename(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_company_id uuid, p_name text, p_reason text, p_now timestamptz) RETURNS api.write_result
-- Purpose: rename a visible company that is in use to a name no other company has; the same name answers unchanged.
-- Callers: SetupRoutines.rename_company; RenameCompany (PUT /setup/companies/{id}).
-- Reads: setup.psv_companies, and what setup.company_visible and tenancy.business_date read. Writes: setup.psv_companies, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 reason_length via tenancy.check_typed_reason, XC422 time_zone_invalid via tenancy.business_date, XC422 company_name_length, XC404 not_found, XC422 company_archived_rename, XC422 company_name_taken.
-- Tests: tests/db/test_setup_company_routines.py, tests/api/test_setup_companies.py.

CREATE OR REPLACE FUNCTION api.setup_company_rename(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_company_id uuid,
  p_name text,
  p_reason text,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_reason text;
  v_today date;
  v_name text := tenancy.trim_text(p_name);
  v_company setup.psv_companies;
  v_before json;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'companies.edit');
  v_reason := tenancy.check_typed_reason(p_reason);
  v_today := tenancy.business_date(p_organization_id, p_now);
  IF v_name IS NULL OR char_length(v_name) > 160 THEN
    PERFORM tenancy.refuse('company_name_length', 'XC422');
  END IF;
  SELECT c.* INTO v_company
  FROM setup.psv_companies AS c
  WHERE c.organization_id = p_organization_id AND c.id = p_company_id
  FOR UPDATE;
  IF NOT FOUND OR NOT setup.company_visible(p_company_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  IF v_company.archived_on IS NOT NULL AND v_company.archived_on <= v_today THEN
    PERFORM tenancy.refuse('company_archived_rename', 'XC422');
  END IF;
  IF EXISTS (
    SELECT 1 FROM setup.psv_companies AS c
    WHERE c.organization_id = p_organization_id
      AND c.id <> p_company_id
      AND c.normalized_name = upper(v_name COLLATE "C")
  ) THEN
    PERFORM tenancy.refuse('company_name_taken', 'XC422');
  END IF;
  IF v_company.name = v_name THEN
    RETURN setup.unchanged_result(p_company_id);
  END IF;

  v_before := setup.company_snapshot(p_company_id);
  UPDATE setup.psv_companies
  SET name = v_name, updated_at = p_now
  WHERE organization_id = p_organization_id AND id = p_company_id;
  v_version := setup.record_setup_change(
    'companies', p_company_id, NULL, v_before, setup.company_snapshot(p_company_id),
    tenancy.compose_reason('Renamed company ' || v_company.name || ' to ' || v_name, v_reason), p_now
  );
  RETURN ROW(p_company_id, v_version, 'updated')::api.write_result;
END;
$$;
