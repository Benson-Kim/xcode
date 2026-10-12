-- setup.report_window(p_vehicle_id uuid, p_from date, p_through date, p_today date) RETURNS daterange
-- Purpose: the days a vehicle's figures cover for a requested range: from the later of p_from and its join date through the earlier of p_through and the business date, ending the day before it left when it left by then; empty when nothing is left or the vehicle is unknown.
-- Callers: setup.vehicle_net, api.setup_vehicle_report.
-- Reads: setup.fleet_vehicles. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_vehicle_routines.py.

CREATE OR REPLACE FUNCTION setup.report_window(
  p_vehicle_id uuid,
  p_from date,
  p_through date,
  p_today date
)
RETURNS daterange
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT coalesce(
    (
      SELECT CASE WHEN w.first <= w.last THEN daterange(w.first, w.last, '[]') ELSE 'empty'::daterange END
      FROM (
        SELECT greatest(p_from, f.joined_on) AS first,
               CASE
                 WHEN f.left_on IS NOT NULL AND f.left_on <= least(p_through, p_today) THEN f.left_on - 1
                 ELSE least(p_through, p_today)
               END AS last
        FROM setup.fleet_vehicles AS f
        WHERE f.organization_id = tenancy.current_organization() AND f.id = p_vehicle_id
      ) AS w
    ),
    'empty'::daterange
  );
$$;

REVOKE ALL ON FUNCTION setup.report_window(uuid, date, date, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.report_window(uuid, date, date, date) TO xcode_api_executor;
