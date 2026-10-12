-- api.setup_investment_delete(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_entry_id uuid, p_now timestamptz) RETURNS api.write_result
-- Purpose: remove an investment entry on a visible vehicle, the one hard delete of the setup area; the change log keeps what it held (after is the JSON null) and is logged against the vehicle.
-- Callers: SetupRoutines.delete_investment; DeleteInvestment (DELETE /setup/investment/{id}).
-- Reads: setup.vehicle_investments, setup.fleet_vehicles, and what setup.vehicle_visible reads. Writes: setup.vehicle_investments, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC404 not_found.
-- Tests: tests/db/test_setup_investment_routines.py, tests/api/test_setup_investment.py.

CREATE OR REPLACE FUNCTION api.setup_investment_delete(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_entry_id uuid,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_entry setup.vehicle_investments;
  v_registration text;
  v_before json;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'vehicles.edit');
  SELECT e.* INTO v_entry
  FROM setup.vehicle_investments AS e
  WHERE e.organization_id = p_organization_id AND e.id = p_entry_id
  FOR UPDATE;
  IF NOT FOUND OR NOT setup.vehicle_visible(v_entry.vehicle_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;

  SELECT f.registration INTO v_registration
  FROM setup.fleet_vehicles AS f
  WHERE f.organization_id = p_organization_id AND f.id = v_entry.vehicle_id;
  v_before := setup.investment_snapshot(p_entry_id);
  DELETE FROM setup.vehicle_investments
  WHERE organization_id = p_organization_id AND id = p_entry_id;
  v_version := setup.record_setup_change(
    'investment', v_entry.vehicle_id, v_entry.vehicle_id, v_before, 'null'::json,
    'Removed investment ' || v_entry.description || ' on ' || v_registration, p_now
  );
  RETURN ROW(p_entry_id, v_version, 'updated')::api.write_result;
END;
$$;
