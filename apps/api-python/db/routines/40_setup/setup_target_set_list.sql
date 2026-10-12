-- api.setup_target_set_list(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_vehicle_id uuid, p_now timestamptz) RETURNS jsonb
-- Purpose: the target sets of a visible vehicle, newest start first, each with its seven day figures, week total, whether it is the set in force on the business date, and whether the actor may remove it (it has not started and the actor holds vehicles.target).
-- Callers: SetupRoutines.list_target_sets; ListVehicleTargets (GET /setup/vehicles/{id}/targets).
-- Reads: setup.fleet_vehicles, setup.vehicle_target_sets, and what tenancy.business_date, tenancy.has_permission, setup.vehicle_visible and setup.target_set_on read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 time_zone_invalid via tenancy.business_date, XC404 not_found.
-- Tests: tests/db/test_setup_target_routines.py, tests/api/test_setup_targets.py.

CREATE OR REPLACE FUNCTION api.setup_target_set_list(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_vehicle_id uuid,
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
  v_in_force uuid;
  v_can_remove boolean;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'vehicles.view');
  v_today := tenancy.business_date(p_organization_id, p_now);
  IF NOT EXISTS (
    SELECT 1 FROM setup.fleet_vehicles AS f
    WHERE f.organization_id = p_organization_id AND f.id = p_vehicle_id
  ) OR NOT setup.vehicle_visible(p_vehicle_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  v_in_force := (setup.target_set_on(p_vehicle_id, v_today)).id;
  v_can_remove := tenancy.has_permission('vehicles.target');
  RETURN (
    SELECT coalesce(
             jsonb_agg(
               jsonb_build_object(
                 'id', s.id,
                 'starts_on', s.starts_on,
                 'days', jsonb_build_array(
                   s.monday, s.tuesday, s.wednesday, s.thursday, s.friday, s.saturday, s.sunday
                 ),
                 'week_total', setup.week_total(s),
                 'in_force', s.id IS NOT DISTINCT FROM v_in_force,
                 'can_remove', v_can_remove AND s.starts_on > v_today
               ) ORDER BY s.starts_on DESC),
             '[]'::jsonb)
    FROM setup.vehicle_target_sets AS s
    WHERE s.organization_id = p_organization_id AND s.vehicle_id = p_vehicle_id
  );
END;
$$;
