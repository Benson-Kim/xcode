-- setup.vehicle_snapshot(p_id uuid) RETURNS json
-- Purpose: the change-log snapshot of a vehicle, compact JSON with the keys Id, Registration, FleetNumber, CompanyId, JoinedOn, LeftOn, InitialInvestment, TargetSets [{StartsOn, Monday, ..., Sunday}] by start date and Away [{LeftOn, ReturnedOn}] by leave date; the JSON null for an unknown vehicle.
-- Callers: the vehicle write routines.
-- Reads: setup.fleet_vehicles, setup.vehicle_target_sets, setup.vehicle_away_periods. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.vehicle_snapshot(p_id uuid)
RETURNS json
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT tenancy.compact_json(coalesce(
    (
      SELECT json_build_object(
               'Id', f.id,
               'Registration', f.registration,
               'FleetNumber', f.fleet_number,
               'CompanyId', f.company_id,
               'JoinedOn', f.joined_on,
               'LeftOn', f.left_on,
               'InitialInvestment', trim_scale(f.initial_investment),
               'TargetSets', (
                 SELECT coalesce(
                          json_agg(
                            json_build_object(
                              'StartsOn', t.starts_on,
                              'Monday', trim_scale(t.monday),
                              'Tuesday', trim_scale(t.tuesday),
                              'Wednesday', trim_scale(t.wednesday),
                              'Thursday', trim_scale(t.thursday),
                              'Friday', trim_scale(t.friday),
                              'Saturday', trim_scale(t.saturday),
                              'Sunday', trim_scale(t.sunday)
                            ) ORDER BY t.starts_on),
                          '[]'::json)
                 FROM setup.vehicle_target_sets AS t
                 WHERE t.organization_id = f.organization_id AND t.vehicle_id = f.id
               ),
               'Away', (
                 SELECT coalesce(
                          json_agg(
                            json_build_object('LeftOn', a.left_on, 'ReturnedOn', a.returned_on)
                            ORDER BY a.left_on),
                          '[]'::json)
                 FROM setup.vehicle_away_periods AS a
                 WHERE a.organization_id = f.organization_id AND a.vehicle_id = f.id
               )
             )
      FROM setup.fleet_vehicles AS f
      WHERE f.organization_id = tenancy.current_organization() AND f.id = p_id
    ),
    'null'::json
  ));
$$;

REVOKE ALL ON FUNCTION setup.vehicle_snapshot(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.vehicle_snapshot(uuid) TO xcode_api_executor;
