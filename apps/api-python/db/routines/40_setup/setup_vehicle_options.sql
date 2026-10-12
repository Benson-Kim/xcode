-- api.setup_vehicle_options(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_now timestamptz) RETURNS jsonb
-- Purpose: the vehicles a new scheduled share can use: visible, in the fleet on the business date (away periods are not considered) and in a company in use, by registration; [{id, company_id, company_name, registration, active, fleet_number}] with active always true.
-- Callers: SetupRoutines.vehicle_options; ListVehicleOptions (GET /setup/recurring/vehicle-options).
-- Reads: setup.fleet_vehicles, setup.psv_companies, and what tenancy.business_date and setup.visible_vehicles read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_setup_recurring_routines.py, tests/api/test_setup_recurring.py.

CREATE OR REPLACE FUNCTION api.setup_vehicle_options(
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
  PERFORM tenancy.require_any_permission(
    ARRAY['scheduled.add', 'scheduled.edit', 'savings.add', 'savings.edit']
  );
  v_today := tenancy.business_date(p_organization_id, p_now);
  RETURN (
    SELECT coalesce(
             jsonb_agg(
               jsonb_build_object(
                 'id', f.id,
                 'company_id', f.company_id,
                 'company_name', c.name,
                 'registration', f.registration,
                 'active', true,
                 'fleet_number', f.fleet_number
               ) ORDER BY f.registration, f.id),
             '[]'::jsonb)
    FROM setup.fleet_vehicles AS f
    JOIN setup.psv_companies AS c ON c.organization_id = f.organization_id AND c.id = f.company_id
    WHERE f.organization_id = p_organization_id
      AND f.id IN (SELECT visible.id FROM setup.visible_vehicles() AS visible (id))
      AND f.joined_on <= v_today
      AND (f.left_on IS NULL OR f.left_on > v_today)
      AND (c.archived_on IS NULL OR c.archived_on > v_today)
  );
END;
$$;
