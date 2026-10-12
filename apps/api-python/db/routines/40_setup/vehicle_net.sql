-- setup.vehicle_net(p_vehicle_id uuid, p_from date, p_through date, p_today date) RETURNS numeric
-- Purpose: the vehicle's net contribution for a range, as its report counts it: money in less money out (the scheduled costs and the approved petty-cash expenses; savings and investment are not money out) over setup.report_window; may be negative.
-- Callers: api.setup_vehicle_report (net), api.setup_investment_get (returned).
-- Reads: what setup.report_window, setup.vehicle_money_in, setup.vehicle_postings and pettycash.vehicle_postings read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_vehicle_routines.py, tests/db/test_setup_investment_routines.py, tests/db/test_pettycash_routines.py.

CREATE OR REPLACE FUNCTION setup.vehicle_net(
  p_vehicle_id uuid,
  p_from date,
  p_through date,
  p_today date
)
RETURNS numeric
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_window daterange := setup.report_window(p_vehicle_id, p_from, p_through, p_today);
BEGIN
  RETURN setup.vehicle_money_in(p_vehicle_id, v_window) - coalesce(
    (SELECT sum(p.amount) FROM setup.vehicle_postings(p_vehicle_id, v_window) AS p WHERE p.kind = 1),
    0
  ) - coalesce(
    (SELECT sum(p.amount) FROM pettycash.vehicle_postings(p_vehicle_id, v_window) AS p),
    0
  );
END;
$$;

REVOKE ALL ON FUNCTION setup.vehicle_net(uuid, date, date, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.vehicle_net(uuid, date, date, date) TO xcode_api_executor;
