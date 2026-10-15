-- setup.decide_saving_runs(p_vehicle_id uuid, p_first date, p_last date, p_now timestamptz) RETURNS integer
-- Purpose: decide the held saving runs of a vehicle that days p_first..p_last can affect (run dates from p_first to 29 days after p_last, none after the business date) whose revenue window is complete: saved when the window's revenue reaches the version's minimum, else skipped. A decision is stored once and never changes. Answers the number decided.
-- Callers: revenue.capture_row (the revenue capture), setup.save_recurring, api.setup_vehicle_update, api.setup_vehicle_restore.
-- Reads: what setup.decide_fleet_saving_runs reads. Writes: setup.saving_runs through setup.decide_fleet_saving_runs.
-- Raises: none.
-- Tests: tests/db/test_recurring_pause_routines.py, tests/db/test_revenue_day_routines.py.
-- Callers lock the vehicle row before calling (never the other way round); the steps are
-- setup.decide_fleet_saving_runs's for one vehicle.

CREATE OR REPLACE FUNCTION setup.decide_saving_runs(
  p_vehicle_id uuid,
  p_first date,
  p_last date,
  p_now timestamptz
)
RETURNS integer
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF p_vehicle_id IS NULL THEN
    RETURN 0;
  END IF;
  RETURN setup.decide_fleet_saving_runs(ARRAY[p_vehicle_id], p_first, p_last, p_now);
END;
$$;

REVOKE ALL ON FUNCTION setup.decide_saving_runs(uuid, date, date, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.decide_saving_runs(uuid, date, date, timestamptz) TO xcode_api_executor;
