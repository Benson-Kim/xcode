-- api.setup_company_create(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_name text, p_reason text, p_now timestamptz) RETURNS api.write_result
-- Purpose: add a PSV company with a unique name; only an actor who sees every company may.
-- Callers: SetupRoutines.create_company; CreateCompany (POST /setup/companies).
-- Reads: setup.psv_companies, and what tenancy.actor_scope reads. Writes: setup.psv_companies, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 reason_length via tenancy.check_typed_reason, XC422 company_name_length, XC403 permission_missing, XC422 company_name_taken.
-- Tests: tests/db/test_setup_company_routines.py, tests/api/test_setup_companies.py.
-- A unique_violation from a concurrent create with the same name surfaces as unique_conflict.

CREATE OR REPLACE FUNCTION api.setup_company_create(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
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
  v_name text := tenancy.trim_text(p_name);
  v_id uuid;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'companies.add');
  v_reason := tenancy.check_typed_reason(p_reason);
  IF v_name IS NULL OR char_length(v_name) > 160 THEN
    PERFORM tenancy.refuse('company_name_length', 'XC422');
  END IF;
  IF NOT (tenancy.actor_scope()).all_companies THEN
    PERFORM tenancy.refuse('permission_missing', 'XC403');
  END IF;
  IF EXISTS (
    SELECT 1 FROM setup.psv_companies AS c
    WHERE c.organization_id = p_organization_id AND c.normalized_name = upper(v_name COLLATE "C")
  ) THEN
    PERFORM tenancy.refuse('company_name_taken', 'XC422');
  END IF;

  INSERT INTO setup.psv_companies (organization_id, name, created_at, updated_at)
  VALUES (p_organization_id, v_name, p_now, p_now)
  RETURNING id INTO v_id;
  v_version := setup.record_setup_change(
    'companies', v_id, NULL, 'null'::json,
    setup.company_snapshot(v_id),
    tenancy.compose_reason('Added company ' || v_name, v_reason), p_now
  );
  RETURN ROW(v_id, v_version, 'created')::api.write_result;
END;
$$;
