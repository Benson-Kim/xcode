-- api.setup_company_archive(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_company_id uuid, p_reason text, p_now timestamptz) RETURNS api.write_result
-- Purpose: archive a visible company from the business date once none of its vehicles is still in the fleet (vehicles that have not joined yet count); archiving again on the same date answers unchanged.
-- Callers: SetupRoutines.archive_company; ArchiveCompany (POST /setup/companies/{id}/archive).
-- Reads: setup.psv_companies, setup.fleet_vehicles, and what setup.company_visible and tenancy.business_date read. Writes: setup.psv_companies, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 reason_length via tenancy.check_typed_reason, XC422 time_zone_invalid via tenancy.business_date, XC404 not_found, XC422 company_has_vehicles, XC422 company_already_archived.
-- Tests: tests/db/test_setup_company_routines.py, tests/api/test_setup_companies.py.

CREATE OR REPLACE FUNCTION api.setup_company_archive(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_company_id uuid,
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
  v_company setup.psv_companies;
  v_before json;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'companies.edit');
  v_reason := tenancy.check_typed_reason(p_reason);
  v_today := tenancy.business_date(p_organization_id, p_now);
  SELECT c.* INTO v_company
  FROM setup.psv_companies AS c
  WHERE c.organization_id = p_organization_id AND c.id = p_company_id
  FOR UPDATE;
  IF NOT FOUND OR NOT setup.company_visible(p_company_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  IF v_company.archived_on IS NULL AND EXISTS (
    SELECT 1 FROM setup.fleet_vehicles AS f
    WHERE f.organization_id = p_organization_id
      AND f.company_id = p_company_id
      AND (f.left_on IS NULL OR f.left_on > v_today)
  ) THEN
    PERFORM tenancy.refuse('company_has_vehicles', 'XC422');
  END IF;
  IF v_company.archived_on = v_today THEN
    RETURN setup.unchanged_result(p_company_id);
  END IF;
  IF v_company.archived_on IS NOT NULL THEN
    PERFORM tenancy.refuse('company_already_archived', 'XC422');
  END IF;

  v_before := setup.company_snapshot(p_company_id);
  UPDATE setup.psv_companies
  SET archived_on = v_today, updated_at = p_now
  WHERE organization_id = p_organization_id AND id = p_company_id;
  v_version := setup.record_setup_change(
    'companies', p_company_id, NULL, v_before, setup.company_snapshot(p_company_id),
    tenancy.compose_reason('Archived company ' || v_company.name, v_reason), p_now
  );
  RETURN ROW(p_company_id, v_version, 'updated')::api.write_result;
END;
$$;
