-- api.setup_target_set_save(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_vehicle_id uuid, p_starts_on date, p_days numeric[], p_low_below numeric, p_now timestamptz) RETURNS api.write_result
-- Purpose: give a visible vehicle in the fleet a target set of seven day figures and a low revenue figure starting on the business date or later; days not given keep those in force that day (seven zeros for a vehicle with none while Targets is off), a figure not given keeps the one in force; the set already starting that day (not started yet, or starting today) is replaced, a set whose days and figure both equal the one in force on that day is refused, and a set that started before today is never touched.
-- Callers: SetupRoutines.save_target_set; SaveVehicleTargets (POST /setup/vehicles/{id}/targets).
-- Reads: setup.fleet_vehicles, setup.vehicle_target_sets, and what tenancy.business_date, tenancy.setting_enabled, tenancy.settings_document, setup.vehicle_visible, setup.target_set_on and setup.low_below_on read. Writes: setup.vehicle_target_sets, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 target_start_required, XC422 target_days_required via setup.check_day_targets, XC422 money_invalid via setup.check_day_targets, XC422 money_invalid via setup.check_low_below, XC422 time_zone_invalid via tenancy.business_date, XC404 not_found, XC422 vehicle_retired_edit, XC422 target_start_past, XC422 target_set_unchanged.
-- Tests: tests/db/test_setup_target_routines.py, tests/api/test_setup_targets.py.
-- The vehicle row is locked first, so two saves, or a save and a removal, on one vehicle run one after the other.

CREATE OR REPLACE FUNCTION api.setup_target_set_save(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_vehicle_id uuid,
  p_starts_on date,
  p_days numeric[],
  p_low_below numeric,
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
  v_vehicle setup.fleet_vehicles;
  v_current setup.vehicle_target_sets;
  v_days numeric[];
  v_low_below numeric;
  v_id uuid;
  v_outcome text := 'updated';
  v_before json;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'vehicles.target');
  IF p_starts_on IS NULL THEN
    PERFORM tenancy.refuse('target_start_required', 'XC422');
  END IF;
  IF p_days IS NOT NULL THEN
    PERFORM setup.check_day_targets(p_days);
  END IF;
  IF p_low_below IS NOT NULL THEN
    PERFORM setup.check_low_below(p_low_below);
  END IF;
  v_today := tenancy.business_date(p_organization_id, p_now);
  SELECT f.* INTO v_vehicle
  FROM setup.fleet_vehicles AS f
  WHERE f.organization_id = p_organization_id AND f.id = p_vehicle_id
  FOR UPDATE;
  IF NOT FOUND OR NOT setup.vehicle_visible(p_vehicle_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  IF v_vehicle.left_on IS NOT NULL THEN
    PERFORM tenancy.refuse('vehicle_retired_edit', 'XC422');
  END IF;
  IF p_starts_on < v_today THEN
    PERFORM tenancy.refuse('target_start_past', 'XC422');
  END IF;
  v_current := setup.target_set_on(p_vehicle_id, p_starts_on);
  IF p_days IS NOT NULL THEN
    v_days := p_days;
  ELSIF v_current.id IS NOT NULL THEN
    v_days := ARRAY[v_current.monday, v_current.tuesday, v_current.wednesday,
                    v_current.thursday, v_current.friday, v_current.saturday, v_current.sunday];
  ELSIF NOT tenancy.setting_enabled('targets') THEN
    v_days := array_fill(0::numeric, ARRAY[7]);
  ELSE
    PERFORM setup.check_day_targets(NULL);
  END IF;
  v_low_below := coalesce(p_low_below, setup.low_below_on(p_vehicle_id, p_starts_on));
  IF v_current.id IS NOT NULL
     AND ARRAY[v_current.monday, v_current.tuesday, v_current.wednesday, v_current.thursday,
               v_current.friday, v_current.saturday, v_current.sunday] = v_days
     AND v_current.low_below = v_low_below THEN
    PERFORM tenancy.refuse(
      'target_set_unchanged', 'XC422', jsonb_build_object('date', tenancy.fmt_iso(p_starts_on))
    );
  END IF;

  v_before := setup.vehicle_snapshot(p_vehicle_id);
  UPDATE setup.vehicle_target_sets
  SET monday = v_days[1], tuesday = v_days[2], wednesday = v_days[3], thursday = v_days[4],
      friday = v_days[5], saturday = v_days[6], sunday = v_days[7], low_below = v_low_below,
      created_at = p_now, created_by = p_actor_id
  WHERE organization_id = p_organization_id
    AND vehicle_id = p_vehicle_id
    AND starts_on = p_starts_on
  RETURNING id INTO v_id;
  IF v_id IS NULL THEN
    INSERT INTO setup.vehicle_target_sets (
      organization_id, vehicle_id, starts_on, monday, tuesday, wednesday, thursday, friday,
      saturday, sunday, low_below, created_at, created_by
    )
    VALUES (
      p_organization_id, p_vehicle_id, p_starts_on, v_days[1], v_days[2], v_days[3], v_days[4],
      v_days[5], v_days[6], v_days[7], v_low_below, p_now, p_actor_id
    )
    RETURNING id INTO v_id;
    v_outcome := 'created';
  END IF;
  v_version := setup.record_setup_change(
    'vehicles', p_vehicle_id, p_vehicle_id, v_before, setup.vehicle_snapshot(p_vehicle_id),
    tenancy.compose_reason(
      'Target set, ' || v_vehicle.registration || ', low below '
        || (tenancy.settings_document('localization') ->> 'currency') || ' '
        || tenancy.fmt_money(v_low_below),
      NULL
    ),
    p_now
  );
  RETURN ROW(v_id, v_version, v_outcome)::api.write_result;
END;
$$;
