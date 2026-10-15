-- reports.money_out_by_main(p_vehicle_ids uuid[], p_from date, p_through date, p_today date) RETURNS TABLE (vehicle_id uuid, main_category_id uuid, main_category_name text, amount numeric)
-- Purpose: the cost postings of the vehicles in the period (setup.fleet_postings, kind 1) summed per vehicle and main category; a null main category is the "No main category" column.
-- Callers: reports.fleet_net.
-- Reads: what setup.fleet_postings reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.money_out_by_main(
  p_vehicle_ids uuid[],
  p_from date,
  p_through date,
  p_today date
)
RETURNS TABLE (vehicle_id uuid, main_category_id uuid, main_category_name text, amount numeric)
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT p.vehicle_id, p.main_category_id, p.main_category_name, sum(p.amount)
  FROM setup.fleet_postings(p_vehicle_ids, p_from, p_through, p_today, '{1}') AS p
  WHERE p.kind = 1
  GROUP BY p.vehicle_id, p.main_category_id, p.main_category_name;
$$;

REVOKE ALL ON FUNCTION reports.money_out_by_main(uuid[], date, date, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.money_out_by_main(uuid[], date, date, date) TO xcode_api_executor;
