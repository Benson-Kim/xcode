-- api.setup_vehicle_create(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_company_id uuid, p_registration text, p_fleet_number text, p_joined_on date, p_day_targets numeric[], p_initial_investment numeric, p_reason text, p_now timestamptz) RETURNS api.write_result
-- Purpose: add a vehicle with a new registration and a fleet number new to its company to a visible company in use, joining on or before the business date, with its first target set of seven day figures from the join date and an optional initial investment (0 is stored as empty); an actor scoped to vehicles only may not.
-- Callers: SetupRoutines.create_vehicle; CreateVehicle (POST /setup/vehicles).
-- Reads: setup.fleet_vehicles, setup.psv_companies, and what tenancy.business_date, tenancy.actor_scope, tenancy.settings_document and setup.company_visible read. Writes: setup.fleet_vehicles, setup.vehicle_target_sets, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 reason_length via tenancy.check_typed_reason, XC422 vehicle_registration_format via setup.registration_normalize, XC422 vehicle_fleet_required via setup.fleet_number, XC422 vehicle_fleet_length via setup.fleet_number, XC422 target_days_required via setup.check_day_targets, XC422 money_invalid via setup.check_day_targets, XC422 money_invalid via tenancy.check_money, XC422 time_zone_invalid via tenancy.business_date, XC422 vehicle_joined_future, XC404 not_found, XC422 vehicle_company_inactive, XC403 permission_missing, XC422 vehicle_registration_taken, XC422 vehicle_fleet_taken.
-- Tests: tests/db/test_setup_vehicle_routines.py, tests/api/test_setup_vehicles.py.
-- A unique_violation from a concurrent create of the same registration or fleet number surfaces as unique_conflict.

CREATE OR REPLACE FUNCTION api.setup_vehicle_create(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_company_id uuid,
  p_registration text,
  p_fleet_number text,
  p_joined_on date,
  p_day_targets numeric[],
  p_initial_investment numeric,
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
  v_registration text;
  v_fleet_number text;
  v_investment numeric;
  v_today date;
  v_scope tenancy.scope;
  v_company_name text;
  v_id uuid;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'vehicles.add');
  v_reason := tenancy.check_typed_reason(p_reason);
  v_registration := setup.registration_normalize(p_registration);
  v_fleet_number := setup.fleet_number(p_fleet_number);
  PERFORM setup.check_day_targets(p_day_targets);
  v_investment := nullif(p_initial_investment, 0);
  IF v_investment IS NOT NULL THEN
    PERFORM tenancy.check_money(v_investment);
  END IF;
  v_today := tenancy.business_date(p_organization_id, p_now);
  IF p_joined_on IS NULL OR p_joined_on > v_today THEN
    PERFORM tenancy.refuse('vehicle_joined_future', 'XC422');
  END IF;
  -- Locked so an archive of the company commits before this check or waits for this write.
  SELECT c.name INTO v_company_name
  FROM setup.psv_companies AS c
  WHERE c.organization_id = p_organization_id AND c.id = p_company_id
  FOR SHARE;
  IF NOT FOUND OR NOT setup.company_visible(p_company_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  IF NOT setup.company_active_on(p_company_id, v_today) THEN
    PERFORM tenancy.refuse('vehicle_company_inactive', 'XC422');
  END IF;
  v_scope := tenancy.actor_scope();
  IF NOT (v_scope.all_companies OR p_company_id = ANY (v_scope.company_ids)) THEN
    PERFORM tenancy.refuse('permission_missing', 'XC403');
  END IF;
  IF EXISTS (
    SELECT 1 FROM setup.fleet_vehicles AS f
    WHERE f.organization_id = p_organization_id AND f.registration = v_registration
  ) THEN
    PERFORM tenancy.refuse('vehicle_registration_taken', 'XC422');
  END IF;
  IF EXISTS (
    SELECT 1 FROM setup.fleet_vehicles AS f
    WHERE f.organization_id = p_organization_id
      AND f.company_id = p_company_id
      AND f.normalized_fleet_number = upper(v_fleet_number COLLATE "C")
  ) THEN
    PERFORM tenancy.refuse('vehicle_fleet_taken', 'XC422', jsonb_build_object('fleet', v_fleet_number));
  END IF;

  INSERT INTO setup.fleet_vehicles (
    organization_id, company_id, registration, fleet_number, joined_on, initial_investment,
    created_at, updated_at
  )
  VALUES (
    p_organization_id, p_company_id, v_registration, v_fleet_number, p_joined_on, v_investment,
    p_now, p_now
  )
  RETURNING id INTO v_id;
  INSERT INTO setup.vehicle_target_sets (
    organization_id, vehicle_id, starts_on, monday, tuesday, wednesday, thursday, friday,
    saturday, sunday, created_at, created_by
  )
  VALUES (
    p_organization_id, v_id, p_joined_on, p_day_targets[1], p_day_targets[2], p_day_targets[3],
    p_day_targets[4], p_day_targets[5], p_day_targets[6], p_day_targets[7], p_now, p_actor_id
  );
  v_version := setup.record_setup_change(
    'vehicles', v_id, v_id, 'null'::json, setup.vehicle_snapshot(v_id),
    tenancy.compose_reason(
      'Added vehicle ' || v_registration || ', fleet number ' || v_fleet_number || ', to '
        || v_company_name || ' with a weekly target of '
        || (tenancy.settings_document('localization') ->> 'currency') || ' '
        || tenancy.fmt_money(setup.week_total(setup.target_set_on(v_id, p_joined_on)))
        || ' from ' || tenancy.fmt_iso(p_joined_on),
      v_reason
    ),
    p_now
  );
  RETURN ROW(v_id, v_version, 'created')::api.write_result;
END;
$$;
