-- api.setup_vehicle_delete(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_vehicle_id uuid, p_now timestamptz) RETURNS api.write_result
-- Purpose: delete a visible vehicle nothing refers to, such as one added by mistake, together with its own target sets (every vehicle gets one when added; the before snapshot keeps them); the foreign keys decide, so a vehicle with revenue, petty cash, expenses, investment entries, away periods, scheduled items, savings or a place in a data scope (or any table that refers to it later) is refused and keeps the retire path. The change log keeps what it held (after is the JSON null) and is logged against the vehicle.
-- Callers: SetupRoutines.delete_setup_record; DeleteSetupRecord (DELETE /setup/vehicles/{id}).
-- Reads: setup.fleet_vehicles, setup.vehicle_target_sets, what setup.vehicle_visible and setup.vehicle_snapshot read, and through the foreign keys every table that refers to the vehicle. Writes: setup.vehicle_target_sets, setup.fleet_vehicles, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC404 not_found, XC409 in_use via setup.refuse_in_use.
-- Tests: tests/db/test_setup_delete_routines.py, tests/api/test_setup_deletes.py.

CREATE OR REPLACE FUNCTION api.setup_vehicle_delete(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_vehicle_id uuid,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_registration text;
  v_before json;
  v_schema text;
  v_table text;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'vehicles.edit');
  SELECT f.registration INTO v_registration
  FROM setup.fleet_vehicles AS f
  WHERE f.organization_id = p_organization_id AND f.id = p_vehicle_id
  FOR UPDATE;
  IF NOT FOUND OR NOT setup.vehicle_visible(p_vehicle_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;

  v_before := setup.vehicle_snapshot(p_vehicle_id);
  BEGIN
    DELETE FROM setup.vehicle_target_sets
    WHERE organization_id = p_organization_id AND vehicle_id = p_vehicle_id;
    DELETE FROM setup.fleet_vehicles
    WHERE organization_id = p_organization_id AND id = p_vehicle_id;
  EXCEPTION WHEN foreign_key_violation THEN
    GET STACKED DIAGNOSTICS v_schema = SCHEMA_NAME, v_table = TABLE_NAME;
    PERFORM setup.refuse_in_use('vehicle', v_registration, v_schema || '.' || v_table);
  END;
  v_version := setup.record_setup_change(
    'vehicles', p_vehicle_id, p_vehicle_id, v_before, 'null'::json,
    'Deleted vehicle ' || v_registration, p_now
  );
  RETURN ROW(p_vehicle_id, v_version, 'updated')::api.write_result;
END;
$$;
