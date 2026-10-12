-- api.setup_company_options(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_now timestamptz) RETURNS jsonb
-- Purpose: the companies a vehicle can be placed in: visible and in use on the business date, by name then id; [{id, name}].
-- Callers: SetupRoutines.company_options; ListCompanyOptions (GET /setup/vehicles/company-options).
-- Reads: setup.psv_companies, and what tenancy.business_date and setup.visible_companies read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_setup_vehicle_routines.py, tests/api/test_setup_vehicles.py.

CREATE OR REPLACE FUNCTION api.setup_company_options(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_today date;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['vehicles.add', 'vehicles.edit']);
  v_today := tenancy.business_date(p_organization_id, p_now);
  RETURN (
    SELECT coalesce(
             jsonb_agg(jsonb_build_object('id', c.id, 'name', c.name) ORDER BY c.name, c.id),
             '[]'::jsonb)
    FROM setup.psv_companies AS c
    WHERE c.organization_id = p_organization_id
      AND c.id IN (SELECT visible.id FROM setup.visible_companies() AS visible (id))
      AND (c.archived_on IS NULL OR c.archived_on > v_today)
  );
END;
$$;
