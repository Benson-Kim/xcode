-- setup.decide_fleet_saving_runs(p_vehicle_ids uuid[], p_first date, p_last date, p_now timestamptz) RETURNS integer
-- Purpose: setup.decide_saving_runs for many vehicles at once: the held saving runs of the vehicles that days 
--          p_first..p_last can affect (run dates from p_first to 29 days after p_last, none after the business date) 
--          whose revenue window is complete are decided in one statement, saved when the window's revenue reaches 
--          the version's minimum, else skipped. A decision is stored once and never changes. Answers the number decided.
-- Callers: setup.decide_saving_runs, api.revenue_day_save.
-- Reads: setup.recurring_versions, and what tenancy.business_date, setup.scheduled_runs and setup.saving_window_revenue read. Writes: setup.saving_runs.
-- Raises: none.
-- Tests: tests/db/test_revenue_day_routines.py, tests/db/test_recurring_pause_routines.py.
-- Callers lock the vehicle rows before calling (never the other way round). The advisory locks,
-- one per vehicle taken in ascending id order, serialise deciders of a vehicle; the insert is a
-- later statement, so it reads every record committed before the last lock was granted.

CREATE OR REPLACE FUNCTION setup.decide_fleet_saving_runs(
  p_vehicle_ids uuid[],
  p_first date,
  p_last date,
  p_now timestamptz
)
RETURNS integer
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.current_organization();
  v_ids uuid[];
  v_id uuid;
  v_today date;
  v_count integer;
BEGIN
  v_ids := ARRAY(
    SELECT DISTINCT v.id FROM unnest(p_vehicle_ids) AS v (id) WHERE v.id IS NOT NULL ORDER BY v.id
  );
  IF cardinality(v_ids) = 0 OR p_first IS NULL OR p_last IS NULL OR p_first > p_last THEN
    RETURN 0;
  END IF;
  v_today := tenancy.business_date(v_organization_id, p_now);
  IF p_first > v_today THEN
    RETURN 0;
  END IF;
  FOREACH v_id IN ARRAY v_ids LOOP
    PERFORM pg_advisory_xact_lock(
      hashtextextended('xcode.saving_runs:' || v_organization_id::text || ':' || v_id::text, 0)
    );
  END LOOP;
  INSERT INTO setup.saving_runs (
    organization_id, item_id, run_on, vehicle_id, version_id, amount, state, revenue, decided_at
  )
  SELECT v_organization_id,
         r.item_id,
         r.run_on,
         r.vehicle_id,
         r.version_id,
         r.amount,
         CASE WHEN w.revenue >= v.condition_min THEN 1 ELSE 2 END,
         w.revenue,
         p_now
  FROM setup.scheduled_runs(v_ids, p_first, least(p_last + 29, v_today), v_today, '{2}') AS r
  JOIN setup.recurring_versions AS v ON v.organization_id = v_organization_id AND v.id = r.version_id
  CROSS JOIN LATERAL setup.saving_window_revenue(r.vehicle_id, r.run_on, v.condition_days) AS w
  WHERE r.state = 3 AND w.complete
  ON CONFLICT DO NOTHING;
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count;
END;
$$;

REVOKE ALL ON FUNCTION setup.decide_fleet_saving_runs(uuid[], date, date, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.decide_fleet_saving_runs(uuid[], date, date, timestamptz) TO xcode_api_executor;
