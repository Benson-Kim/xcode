-- ops.seed_vehicle_plan() RETURNS TABLE (idx integer, registration text, fleet_number text, company_index integer, joined_days_back integer, day_targets numeric[], initial_investment numeric)
-- Purpose: the six vehicles of the demo fleet: registration, fleet number, company (1 first, 2 second), how many days before the business date each joined, the seven day figures of the first target set (Monday first) and an optional initial investment.
-- Callers: ops.seed_fleet_setup, ops.seed_revenue_day, ops.seed_pettycash_day.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py.

CREATE OR REPLACE FUNCTION ops.seed_vehicle_plan()
RETURNS TABLE (
  idx integer,
  registration text,
  fleet_number text,
  company_index integer,
  joined_days_back integer,
  day_targets numeric[],
  initial_investment numeric
)
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT p.idx, p.registration, p.fleet_number, p.company_index, p.joined_days_back,
         p.day_targets, p.initial_investment
  FROM (
    VALUES
      (1, 'KDA 482M', 'Z-01', 1, 42, ARRAY[6000, 6000, 6000, 6000, 6500, 7500, 5000]::numeric[], NULL::numeric),
      (2, 'KDB 117P', 'Z-02', 1, 42, ARRAY[5500, 5500, 5500, 5500, 6000, 7000, 4500]::numeric[], NULL::numeric),
      (3, 'KDC 305T', 'Z-03', 1, 42, ARRAY[6000, 6000, 6000, 6000, 6000, 7000, 5000]::numeric[], NULL::numeric),
      (4, 'KDD 921K', 'M-01', 2, 42, ARRAY[5000, 5000, 5000, 5000, 5500, 6500, 4500]::numeric[], NULL::numeric),
      (5, 'KDE 640J', 'M-02', 2, 42, ARRAY[5500, 5500, 5500, 5500, 5500, 6500, 4500]::numeric[], NULL::numeric),
      (6, 'KDF 758L', 'M-03', 2, 14, ARRAY[6000, 6000, 6000, 6000, 6500, 7500, 5000]::numeric[], 1950000::numeric)
  ) AS p (idx, registration, fleet_number, company_index, joined_days_back, day_targets, initial_investment);
$$;

REVOKE ALL ON FUNCTION ops.seed_vehicle_plan() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ops.seed_vehicle_plan() TO xcode_api_executor;
