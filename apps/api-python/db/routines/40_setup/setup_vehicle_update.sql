-- api.setup_vehicle_update(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_vehicle_id uuid, p_company_id uuid, p_registration text, p_fleet_number text, p_joined_on date, p_initial_investment numeric, p_reason text, p_now timestamptz) RETURNS api.write_result
-- Purpose: move a visible vehicle in the fleet to another company in use, change its join date (never past a day it has revenue for), its fleet number (new to the company it ends in) or its initial investment (0 or null clears it); targets change only through api.setup_target_set_save, except that a join date before the first set copies the first set to it; a new join date decides the saving runs the moved days complete; nothing changed answers unchanged.
-- Callers: SetupRoutines.update_vehicle; UpdateVehicle (PUT /setup/vehicles/{id}).
-- Reads: setup.fleet_vehicles, setup.psv_companies, setup.vehicle_target_sets, revenue.records, and what tenancy.business_date, tenancy.settings_document, setup.company_visible, setup.vehicle_visible read. Writes: setup.fleet_vehicles, setup.vehicle_target_sets, setup.saving_runs through setup.decide_saving_runs, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 reason_length via tenancy.check_typed_reason, XC422 vehicle_registration_format via setup.registration_normalize, XC422 vehicle_fleet_required via setup.fleet_number, XC422 vehicle_fleet_length via setup.fleet_number, XC422 money_invalid via tenancy.check_money, XC422 time_zone_invalid via tenancy.business_date, XC422 vehicle_joined_future, XC404 not_found, XC422 vehicle_company_inactive, XC422 vehicle_retired_edit, XC422 vehicle_registration_change, XC422 vehicle_join_after_revenue, XC422 vehicle_fleet_taken.
-- Tests: tests/db/test_setup_vehicle_routines.py, tests/db/test_recurring_pause_routines.py, tests/api/test_setup_vehicles.py.
-- A unique_violation from a concurrent save of the same fleet number in the company surfaces as unique_conflict.

CREATE OR REPLACE FUNCTION api.setup_vehicle_update(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_vehicle_id uuid,
  p_company_id uuid,
  p_registration text,
  p_fleet_number text,
  p_joined_on date,
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
  v_company_name text;
  v_vehicle setup.fleet_vehicles;
  v_first_record date;
  v_first setup.vehicle_target_sets;
  v_parts text[] := '{}';
  v_automatic text;
  v_currency text;
  v_before json;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'vehicles.edit');
  v_reason := tenancy.check_typed_reason(p_reason);
  v_registration := setup.registration_normalize(p_registration);
  v_fleet_number := setup.fleet_number(p_fleet_number);
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
  IF v_vehicle.registration <> v_registration THEN
    PERFORM tenancy.refuse('vehicle_registration_change', 'XC422');
  END IF;
  SELECT min(r.business_date) INTO v_first_record
  FROM revenue.records AS r
  WHERE r.organization_id = p_organization_id AND r.vehicle_id = p_vehicle_id;
  IF p_joined_on > v_vehicle.joined_on AND v_first_record < p_joined_on THEN
    PERFORM tenancy.refuse(
      'vehicle_join_after_revenue', 'XC422',
      jsonb_build_object('registration', v_vehicle.registration, 'date', tenancy.fmt_iso(v_first_record))
    );
  END IF;
  IF EXISTS (
    SELECT 1 FROM setup.fleet_vehicles AS f
    WHERE f.organization_id = p_organization_id
      AND f.company_id = p_company_id
      AND f.normalized_fleet_number = upper(v_fleet_number COLLATE "C")
      AND f.id <> p_vehicle_id
  ) THEN
    PERFORM tenancy.refuse('vehicle_fleet_taken', 'XC422', jsonb_build_object('fleet', v_fleet_number));
  END IF;

  v_before := setup.vehicle_snapshot(p_vehicle_id);
  v_currency := tenancy.settings_document('localization') ->> 'currency';
  IF v_vehicle.company_id <> p_company_id THEN
    v_parts := v_parts || ('moved ' || v_vehicle.registration || ' to ' || v_company_name);
  END IF;
  IF v_vehicle.joined_on <> p_joined_on THEN
    v_parts := v_parts || (
      'changed when ' || v_vehicle.registration || ' joined the fleet to ' || tenancy.fmt_iso(p_joined_on)
    );
  END IF;
  IF v_vehicle.fleet_number IS DISTINCT FROM v_fleet_number THEN
    v_parts := v_parts || (
      'changed the fleet number of ' || v_vehicle.registration || ' to ' || v_fleet_number
    );
  END IF;
  IF v_vehicle.initial_investment IS DISTINCT FROM v_investment THEN
    v_parts := v_parts || CASE
      WHEN v_investment IS NULL THEN 'cleared the initial investment of ' || v_vehicle.registration
      ELSE 'changed the initial investment of ' || v_vehicle.registration || ' to ' || v_currency
             || ' ' || tenancy.fmt_money(v_investment)
    END;
  END IF;
  IF cardinality(v_parts) = 0 THEN
    RETURN setup.unchanged_result(p_vehicle_id);
  END IF;

  UPDATE setup.fleet_vehicles
  SET company_id = p_company_id,
      joined_on = p_joined_on,
      fleet_number = v_fleet_number,
      initial_investment = v_investment,
      updated_at = p_now
  WHERE organization_id = p_organization_id AND id = p_vehicle_id;
  SELECT t.* INTO v_first
  FROM setup.vehicle_target_sets AS t
  WHERE t.organization_id = p_organization_id AND t.vehicle_id = p_vehicle_id
  ORDER BY t.starts_on
  LIMIT 1;
  IF p_joined_on < v_vehicle.joined_on AND v_first.starts_on > p_joined_on THEN
    INSERT INTO setup.vehicle_target_sets (
      organization_id, vehicle_id, starts_on, monday, tuesday, wednesday, thursday, friday,
      saturday, sunday, created_at, created_by
    )
    VALUES (
      p_organization_id, p_vehicle_id, p_joined_on, v_first.monday, v_first.tuesday,
      v_first.wednesday, v_first.thursday, v_first.friday, v_first.saturday, v_first.sunday,
      p_now, p_actor_id
    );
  END IF;

  v_automatic := array_to_string(v_parts, '; ');
  v_automatic := upper(left(v_automatic, 1)) || substr(v_automatic, 2);
  IF v_vehicle.joined_on <> p_joined_on THEN
    PERFORM setup.decide_saving_runs(
      p_vehicle_id, least(v_vehicle.joined_on, p_joined_on), greatest(v_vehicle.joined_on, p_joined_on), p_now
    );
  END IF;
  v_version := setup.record_setup_change(
    'vehicles', p_vehicle_id, p_vehicle_id, v_before, setup.vehicle_snapshot(p_vehicle_id),
    tenancy.compose_reason(v_automatic, v_reason), p_now
  );
  RETURN ROW(p_vehicle_id, v_version, 'updated')::api.write_result;
END;
$$;
