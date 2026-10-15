-- expenses.check_vehicle(p_vehicle_id uuid, p_date date) RETURNS text
-- Purpose: a central expense's vehicle on its date, read FOR SHARE: known and visible to the actor, then in the fleet that day (joined, not left, not away); answers its registration.
-- Callers: api.expenses_entry_create, api.expenses_entry_update.
-- Reads: setup.fleet_vehicles, and what setup.vehicle_visible and setup.vehicle_active_on read. Writes: nothing.
-- Raises: XC422 expense_vehicle_not_yours, XC422 expense_vehicle_inactive.
-- Tests: tests/db/test_expense_routines.py.

CREATE OR REPLACE FUNCTION expenses.check_vehicle(p_vehicle_id uuid, p_date date)
RETURNS text
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_registration text;
BEGIN
  SELECT f.registration INTO v_registration
  FROM setup.fleet_vehicles AS f
  WHERE f.organization_id = tenancy.current_organization() AND f.id = p_vehicle_id
  FOR SHARE;
  IF v_registration IS NULL OR NOT setup.vehicle_visible(p_vehicle_id) THEN
    PERFORM tenancy.refuse('expense_vehicle_not_yours', 'XC422');
  END IF;
  IF NOT setup.vehicle_active_on(p_vehicle_id, p_date) THEN
    PERFORM tenancy.refuse(
      'expense_vehicle_inactive', 'XC422', jsonb_build_object('registration', v_registration)
    );
  END IF;
  RETURN v_registration;
END;
$$;

REVOKE ALL ON FUNCTION expenses.check_vehicle(uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION expenses.check_vehicle(uuid, date) TO xcode_api_executor;
