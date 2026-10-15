-- api.setup_vehicle_restore(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_vehicle_id uuid, p_returned_on date, p_reason text, p_now timestamptz) RETURNS api.write_result
-- Purpose: bring a retired visible vehicle of a company in use back into the fleet on a return date (the business date when none) from its leave date through the business date, recording the days between as an away period, then deciding the saving runs those days complete; a vehicle that is not retired answers unchanged.
-- Callers: SetupRoutines.restore_vehicle; RestoreVehicle (POST /setup/vehicles/{id}/restore).
-- Reads: setup.fleet_vehicles, and what tenancy.business_date, setup.vehicle_visible, setup.company_visible and setup.company_active_on read. Writes: setup.fleet_vehicles, setup.vehicle_away_periods, setup.saving_runs through setup.decide_saving_runs, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 reason_length via tenancy.check_typed_reason, XC422 time_zone_invalid via tenancy.business_date, XC404 not_found, XC422 vehicle_company_archived_restore, XC422 vehicle_return_date_range.
-- Tests: tests/db/test_setup_vehicle_routines.py, tests/db/test_recurring_pause_routines.py, tests/api/test_setup_vehicles.py.

CREATE OR REPLACE FUNCTION api.setup_vehicle_restore(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_vehicle_id uuid,
  p_returned_on date,
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
  v_returned_on date;
  v_vehicle setup.fleet_vehicles;
  v_automatic text;
  v_before json;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'vehicles.edit');
  v_reason := tenancy.check_typed_reason(p_reason);
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_returned_on := coalesce(p_returned_on, v_today);
  SELECT f.* INTO v_vehicle
  FROM setup.fleet_vehicles AS f
  WHERE f.organization_id = p_organization_id AND f.id = p_vehicle_id
  FOR UPDATE;
  IF NOT FOUND OR NOT setup.vehicle_visible(p_vehicle_id)
     OR NOT setup.company_visible(v_vehicle.company_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  -- Locked so an archive of the company commits before this check or waits for this write.
  PERFORM 1
  FROM setup.psv_companies AS c
  WHERE c.organization_id = p_organization_id AND c.id = v_vehicle.company_id
  FOR SHARE;
  IF NOT setup.company_active_on(v_vehicle.company_id, v_today) THEN
    PERFORM tenancy.refuse('vehicle_company_archived_restore', 'XC422');
  END IF;
  IF v_vehicle.left_on IS NULL THEN
    RETURN setup.unchanged_result(p_vehicle_id);
  END IF;
  IF v_returned_on < v_vehicle.left_on OR v_returned_on > v_today THEN
    PERFORM tenancy.refuse('vehicle_return_date_range', 'XC422');
  END IF;

  v_before := setup.vehicle_snapshot(p_vehicle_id);
  v_automatic := 'Vehicle ' || v_vehicle.registration || ' returned to the fleet on '
    || tenancy.fmt_iso(v_returned_on);
  IF v_returned_on > v_vehicle.left_on THEN
    INSERT INTO setup.vehicle_away_periods (organization_id, vehicle_id, left_on, returned_on, created_at)
    VALUES (p_organization_id, p_vehicle_id, v_vehicle.left_on, v_returned_on, p_now);
    v_automatic := v_automatic || '; it was away from ' || tenancy.fmt_iso(v_vehicle.left_on)
      || ' to ' || tenancy.fmt_iso(v_returned_on - 1);
  END IF;
  UPDATE setup.fleet_vehicles
  SET left_on = NULL, updated_at = p_now
  WHERE organization_id = p_organization_id AND id = p_vehicle_id;
  PERFORM setup.decide_saving_runs(p_vehicle_id, v_vehicle.left_on, v_today, p_now);
  v_version := setup.record_setup_change(
    'vehicles', p_vehicle_id, p_vehicle_id, v_before, setup.vehicle_snapshot(p_vehicle_id),
    tenancy.compose_reason(v_automatic, v_reason), p_now
  );
  RETURN ROW(p_vehicle_id, v_version, 'updated')::api.write_result;
END;
$$;
