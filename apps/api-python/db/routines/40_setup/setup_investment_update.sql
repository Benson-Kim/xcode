-- api.setup_investment_update(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_entry_id uuid, p_invested_on date, p_description text, p_amount numeric, p_now timestamptz) RETURNS api.write_result
-- Purpose: change the date, description or amount of an investment entry on a visible vehicle (the recorder and instant stay); the same values answer unchanged; logged against the vehicle.
-- Callers: SetupRoutines.update_investment; UpdateInvestment (PUT /setup/investment/{id}).
-- Reads: setup.vehicle_investments, setup.fleet_vehicles, and what tenancy.business_date and setup.vehicle_visible read. Writes: setup.vehicle_investments, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 time_zone_invalid via tenancy.business_date, XC404 not_found, XC422 investment_date_invalid, XC422 investment_description_length, XC422 money_invalid via tenancy.check_money.
-- Tests: tests/db/test_setup_investment_routines.py, tests/api/test_setup_investment.py.

CREATE OR REPLACE FUNCTION api.setup_investment_update(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_entry_id uuid,
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
  v_entry setup.vehicle_investments;
  v_registration text;
  v_description text := tenancy.trim_text(p_description);
  v_before json;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'vehicles.edit');
  v_today := tenancy.business_date(p_organization_id, p_now);
  SELECT e.* INTO v_entry
  FROM setup.vehicle_investments AS e
  WHERE e.organization_id = p_organization_id AND e.id = p_entry_id
  FOR UPDATE;
  IF NOT FOUND OR NOT setup.vehicle_visible(v_entry.vehicle_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  IF p_invested_on IS NULL OR p_invested_on > v_today THEN
    PERFORM tenancy.refuse('investment_date_invalid', 'XC422');
  END IF;
  IF v_description IS NULL OR char_length(v_description) > 160 THEN
    PERFORM tenancy.refuse('investment_description_length', 'XC422');
  END IF;
  PERFORM tenancy.check_money(p_amount);
  IF v_entry.invested_on = p_invested_on AND v_entry.description = v_description
     AND v_entry.amount = p_amount THEN
    RETURN setup.unchanged_result(p_entry_id);
  END IF;

  SELECT f.registration INTO v_registration
  FROM setup.fleet_vehicles AS f
  WHERE f.organization_id = p_organization_id AND f.id = v_entry.vehicle_id;
  v_before := setup.investment_snapshot(p_entry_id);
  UPDATE setup.vehicle_investments
  SET invested_on = p_invested_on, description = v_description, amount = p_amount, updated_at = p_now
  WHERE organization_id = p_organization_id AND id = p_entry_id;
  v_version := setup.record_setup_change(
    'investment', v_entry.vehicle_id, v_entry.vehicle_id, v_before, setup.investment_snapshot(p_entry_id),
    'Changed investment ' || v_description || ' on ' || v_registration, p_now
  );
  RETURN ROW(p_entry_id, v_version, 'updated')::api.write_result;
END;
$$;
