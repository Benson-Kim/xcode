-- setup.vehicle_net(p_vehicle_id uuid, p_from date, p_through date, p_today date) RETURNS numeric
-- Purpose: the vehicle's net contribution for a range, as its report counts it: money in over setup.report_window less money out (every cost posting of setup.fleet_postings: central expenses, approved petty-cash expenses and scheduled costs; savings and investment are not money out); may be negative.
-- Callers: api.setup_vehicle_report (net), api.setup_investment_get (returned), reports.fleet_investment.
-- Reads: what setup.report_window, setup.vehicle_money_in, setup.fleet_totals read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_vehicle_routines.py, tests/db/test_setup_investment_routines.py, tests/db/test_pettycash_routines.py, tests/db/test_expense_routines.py.

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
    (
      SELECT sum(t.money_out)
      FROM setup.fleet_totals(ARRAY[p_vehicle_id], p_from, p_through, p_today, '{1}') AS t
    ),
    0
  );
END;
$$;

REVOKE ALL ON FUNCTION setup.vehicle_net(uuid, date, date, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.vehicle_net(uuid, date, date, date) TO xcode_api_executor;
