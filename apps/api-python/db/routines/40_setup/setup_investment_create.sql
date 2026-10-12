-- api.setup_investment_create(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_vehicle_id uuid, p_invested_on date, p_description text, p_amount numeric, p_now timestamptz) RETURNS api.write_result
-- Purpose: record money put into a visible vehicle on or before the business date, with what it was; the actor and p_now are the recorder and instant; logged against the vehicle; id is the new entry id.
-- Callers: SetupRoutines.create_investment; CreateInvestment (POST /setup/vehicles/{id}/investment).
-- Reads: setup.fleet_vehicles, and what tenancy.business_date and setup.vehicle_visible read. Writes: setup.vehicle_investments, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 time_zone_invalid via tenancy.business_date, XC404 not_found, XC422 investment_date_invalid, XC422 investment_description_length, XC422 money_invalid via tenancy.check_money.
-- Tests: tests/db/test_setup_investment_routines.py, tests/api/test_setup_investment.py.

CREATE OR REPLACE FUNCTION api.setup_investment_create(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_vehicle_id uuid,
  p_invested_on date,
  p_description text,
  p_amount numeric,
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
  v_registration text;
  v_description text := tenancy.trim_text(p_description);
  v_id uuid;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'vehicles.edit');
  v_today := tenancy.business_date(p_organization_id, p_now);
  SELECT f.registration INTO v_registration
  FROM setup.fleet_vehicles AS f
  WHERE f.organization_id = p_organization_id AND f.id = p_vehicle_id;
  IF NOT FOUND OR NOT setup.vehicle_visible(p_vehicle_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  IF p_invested_on IS NULL OR p_invested_on > v_today THEN
    PERFORM tenancy.refuse('investment_date_invalid', 'XC422');
  END IF;
  IF v_description IS NULL OR char_length(v_description) > 160 THEN
    PERFORM tenancy.refuse('investment_description_length', 'XC422');
  END IF;
  PERFORM tenancy.check_money(p_amount);

  INSERT INTO setup.vehicle_investments (
    organization_id, vehicle_id, invested_on, description, amount, recorded_by, recorded_at, updated_at
  )
  VALUES (
    p_organization_id, p_vehicle_id, p_invested_on, v_description, p_amount, p_actor_id, p_now, p_now
  )
  RETURNING id INTO v_id;
  v_version := setup.record_setup_change(
    'investment', p_vehicle_id, p_vehicle_id, 'null'::json, setup.investment_snapshot(v_id),
    'Recorded investment ' || v_description || ' on ' || v_registration, p_now
  );
  RETURN ROW(v_id, v_version, 'created')::api.write_result;
END;
$$;
