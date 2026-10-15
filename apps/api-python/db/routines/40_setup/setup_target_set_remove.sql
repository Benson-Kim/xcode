-- api.setup_target_set_remove(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_set_id uuid, p_now timestamptz) RETURNS api.write_result
-- Purpose: remove a target set of a visible vehicle that has not started yet; an unknown set and a set of a vehicle the actor cannot see answer the same not found.
-- Callers: SetupRoutines.remove_target_set; RemoveVehicleTargets (POST /setup/vehicle-targets/{id}/remove).
-- Reads: setup.vehicle_target_sets, setup.fleet_vehicles, and what tenancy.business_date and setup.vehicle_visible read. Writes: setup.vehicle_target_sets, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 time_zone_invalid via tenancy.business_date, XC404 not_found, XC422 target_set_started.
-- Tests: tests/db/test_setup_target_routines.py, tests/api/test_setup_targets.py.
-- The vehicle row is locked before the set is read again, as api.setup_target_set_save locks it.

CREATE OR REPLACE FUNCTION api.setup_target_set_remove(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_set_id uuid,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_today date;
  v_vehicle_id uuid;
  v_registration text;
  v_starts_on date;
  v_before json;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'vehicles.target');
  v_today := tenancy.business_date(p_organization_id, p_now);
  SELECT s.vehicle_id INTO v_vehicle_id
  FROM setup.vehicle_target_sets AS s
  WHERE s.organization_id = p_organization_id AND s.id = p_set_id;
  IF v_vehicle_id IS NOT NULL THEN
    SELECT f.registration INTO v_registration
    FROM setup.fleet_vehicles AS f
    WHERE f.organization_id = p_organization_id AND f.id = v_vehicle_id
    FOR UPDATE;
    SELECT s.starts_on INTO v_starts_on
    FROM setup.vehicle_target_sets AS s
    WHERE s.organization_id = p_organization_id AND s.id = p_set_id AND s.vehicle_id = v_vehicle_id;
  END IF;
  IF v_starts_on IS NULL OR NOT setup.vehicle_visible(v_vehicle_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  IF v_starts_on <= v_today THEN
    PERFORM tenancy.refuse('target_set_started', 'XC422');
  END IF;

  v_before := setup.vehicle_snapshot(v_vehicle_id);
  DELETE FROM setup.vehicle_target_sets
  WHERE organization_id = p_organization_id AND id = p_set_id;
  v_version := setup.record_setup_change(
    'vehicles', v_vehicle_id, v_vehicle_id, v_before, setup.vehicle_snapshot(v_vehicle_id),
    tenancy.compose_reason('Target removed before it started, ' || v_registration, NULL), p_now
  );
  RETURN ROW(p_set_id, v_version, 'updated')::api.write_result;
END;
$$;
