-- api.setup_vehicle_retire(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_vehicle_id uuid, p_left_on date, p_reason text, p_now timestamptz) RETURNS api.write_result
-- Purpose: take a visible vehicle out of the fleet from a leave date between its join date (and its last return) and the business date, never on or before a day it has revenue for; the same leave date again answers unchanged.
-- Callers: SetupRoutines.retire_vehicle; RetireVehicle (POST /setup/vehicles/{id}/retire).
-- Reads: setup.fleet_vehicles, setup.vehicle_away_periods, revenue.records, and what tenancy.business_date and setup.vehicle_visible read. Writes: setup.fleet_vehicles, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 reason_length via tenancy.check_typed_reason, XC422 time_zone_invalid via tenancy.business_date, XC404 not_found, XC422 vehicle_leave_before_revenue, XC422 vehicle_leave_date_range, XC422 vehicle_leave_before_return, XC422 vehicle_already_retired.
-- Tests: tests/db/test_setup_vehicle_routines.py, tests/api/test_setup_vehicles.py.

CREATE OR REPLACE FUNCTION api.setup_vehicle_retire(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_vehicle_id uuid,
  p_left_on date,
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
  v_vehicle setup.fleet_vehicles;
  v_last_record date;
  v_last_return date;
  v_before json;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'vehicles.edit');
  v_reason := tenancy.check_typed_reason(p_reason);
  v_today := tenancy.business_date(p_organization_id, p_now);
  SELECT f.* INTO v_vehicle
  FROM setup.fleet_vehicles AS f
  WHERE f.organization_id = p_organization_id AND f.id = p_vehicle_id
  FOR UPDATE;
  IF NOT FOUND OR NOT setup.vehicle_visible(p_vehicle_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  SELECT max(r.business_date) INTO v_last_record
  FROM revenue.records AS r
  WHERE r.organization_id = p_organization_id
    AND r.vehicle_id = p_vehicle_id
    AND r.business_date >= p_left_on;
  IF v_last_record IS NOT NULL THEN
    PERFORM tenancy.refuse(
      'vehicle_leave_before_revenue', 'XC422',
      jsonb_build_object('registration', v_vehicle.registration, 'date', tenancy.fmt_iso(v_last_record))
    );
  END IF;
  IF p_left_on IS NULL OR p_left_on > v_today OR p_left_on < v_vehicle.joined_on THEN
    PERFORM tenancy.refuse('vehicle_leave_date_range', 'XC422');
  END IF;
  SELECT max(a.returned_on) INTO v_last_return
  FROM setup.vehicle_away_periods AS a
  WHERE a.organization_id = p_organization_id AND a.vehicle_id = p_vehicle_id;
  IF p_left_on < v_last_return THEN
    PERFORM tenancy.refuse('vehicle_leave_before_return', 'XC422');
  END IF;
  IF v_vehicle.left_on = p_left_on THEN
    RETURN setup.unchanged_result(p_vehicle_id);
  END IF;
  IF v_vehicle.left_on IS NOT NULL THEN
    PERFORM tenancy.refuse('vehicle_already_retired', 'XC422');
  END IF;

  v_before := setup.vehicle_snapshot(p_vehicle_id);
  UPDATE setup.fleet_vehicles
  SET left_on = p_left_on, updated_at = p_now
  WHERE organization_id = p_organization_id AND id = p_vehicle_id;
  v_version := setup.record_setup_change(
    'vehicles', p_vehicle_id, p_vehicle_id, v_before, setup.vehicle_snapshot(p_vehicle_id),
    tenancy.compose_reason(
      'Vehicle ' || v_vehicle.registration || ' left the fleet on ' || tenancy.fmt_iso(p_left_on),
      v_reason
    ),
    p_now
  );
  RETURN ROW(p_vehicle_id, v_version, 'updated')::api.write_result;
END;
$$;
