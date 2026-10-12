-- api.access_scope_options(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_now timestamptz) RETURNS jsonb
-- Purpose: what the actor may hand on as a data scope: their companies not archived on the business date (by name), and the vehicles of their scope that are in the fleet on the business date with an active company (by registration).
-- Callers: TenancyRoutines.scope_options; GetAccessScopeOptions (GET /setup/access/scope-options).
-- Reads: setup.psv_companies, setup.fleet_vehicles, and what tenancy.require_any_permission, tenancy.actor_scope and tenancy.business_date read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission (people.add or people.edit), XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_access_routines.py, tests/api/test_access.py.

CREATE OR REPLACE FUNCTION api.access_scope_options(
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
  v_scope tenancy.scope;
  v_today date;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['people.add', 'people.edit']);
  v_scope := tenancy.actor_scope();
  v_today := tenancy.business_date(p_organization_id, p_now);
  RETURN jsonb_build_object(
    'companies', (
      SELECT coalesce(jsonb_agg(jsonb_build_object('id', c.id, 'name', c.name) ORDER BY c.name, c.id), '[]'::jsonb)
      FROM setup.psv_companies AS c
      WHERE c.organization_id = p_organization_id
        AND (v_scope.all_companies OR c.id = ANY (v_scope.company_ids))
        AND (c.archived_on IS NULL OR c.archived_on > v_today)
    ),
    'vehicles', (
      SELECT coalesce(
               jsonb_agg(
                 jsonb_build_object('id', f.id, 'registration', f.registration, 'fleet_number', f.fleet_number, 'company_id', f.company_id)
                 ORDER BY f.registration, f.id),
               '[]'::jsonb)
      FROM setup.fleet_vehicles AS f
      JOIN setup.psv_companies AS c ON c.organization_id = f.organization_id AND c.id = f.company_id
      WHERE f.organization_id = p_organization_id
        AND (v_scope.all_companies
             OR f.id = ANY (v_scope.vehicle_ids)
             OR f.company_id = ANY (v_scope.company_ids))
        AND f.joined_on <= v_today
        AND (f.left_on IS NULL OR f.left_on > v_today)
        AND (c.archived_on IS NULL OR c.archived_on > v_today)
    )
  );
END;
$$;
