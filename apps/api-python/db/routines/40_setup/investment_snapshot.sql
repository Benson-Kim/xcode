-- setup.investment_snapshot(p_id uuid) RETURNS json
-- Purpose: the change-log snapshot of an investment entry, compact JSON with the .NET keys Id, VehicleId, Date, Description, Amount; the JSON null for an unknown entry.
-- Callers: the investment write routines.
-- Reads: setup.vehicle_investments. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.investment_snapshot(p_id uuid)
RETURNS json
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT tenancy.compact_json(coalesce(
    (
      SELECT json_build_object(
               'Id', e.id,
               'VehicleId', e.vehicle_id,
               'Date', e.invested_on,
               'Description', e.description,
               'Amount', trim_scale(e.amount)
             )
      FROM setup.vehicle_investments AS e
      WHERE e.organization_id = tenancy.current_organization() AND e.id = p_id
    ),
    'null'::json
  ));
$$;

REVOKE ALL ON FUNCTION setup.investment_snapshot(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.investment_snapshot(uuid) TO xcode_api_executor;
