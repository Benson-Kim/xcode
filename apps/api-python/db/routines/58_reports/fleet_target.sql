-- reports.fleet_target(p_from date, p_to date, p_company_id uuid, p_today date) RETURNS jsonb
-- Purpose: the Revenue against target table: one row per visible vehicle with days in the period, by reached (lowest first, no target last) then registration: vehicle, company, days captured, no-revenue days, missing days, revenue, target (the day targets of the days that count), reached (percent, one decimal) and against (revenue less target); headline Revenue, figures Target, Reached (of the totals, 0 without a target) and Missing days.
-- Callers: reports.build.
-- Reads: what reports.vehicles and reports.vehicle_figures read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.fleet_target(p_from date, p_to date, p_company_id uuid, p_today date)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_ids uuid[] := ARRAY(SELECT v.vehicle_id FROM reports.vehicles(p_company_id) AS v);
  v_rows jsonb;
  v_revenue numeric;
  v_target numeric;
  v_missing numeric;
BEGIN
  WITH lines AS (
    SELECT v.vehicle_id,
           v.registration,
           v.company_name,
           f.captured,
           f.no_revenue,
           f.missing,
           f.revenue,
           f.target,
           reports.ratio(f.revenue, f.target) AS reached,
           f.revenue - f.target AS against
    FROM reports.vehicle_figures(v_ids, p_from, p_to, p_today) AS f
    JOIN reports.vehicles(p_company_id) AS v ON v.vehicle_id = f.vehicle_id
  )
  SELECT coalesce(
           jsonb_agg(
             jsonb_build_array(
               l.registration, l.company_name, l.captured, l.no_revenue, l.missing,
               l.revenue, l.target, l.reached, l.against
             )
             ORDER BY (l.reached IS NULL), l.reached, l.registration COLLATE "C", l.vehicle_id),
           '[]'::jsonb
         ),
         coalesce(sum(l.revenue), 0),
         coalesce(sum(l.target), 0),
         coalesce(sum(l.missing), 0)
  INTO v_rows, v_revenue, v_target, v_missing
  FROM lines AS l;

  RETURN reports.build_table(
    'fleet',
    'target',
    'Revenue against target',
    p_from,
    p_to,
    p_today,
    reports.figure('Revenue', v_revenue, 'money'),
    jsonb_build_array(
      reports.figure('Target', v_target, 'money'),
      reports.figure('Reached', coalesce(reports.ratio(v_revenue, v_target), 0), 'percent'),
      reports.figure('Missing days', v_missing, 'count')
    ),
    jsonb_build_array(
      reports.heading('vehicle', 'Vehicle', 'vehicle', false),
      reports.heading('company', 'Company', 'text', false),
      reports.heading('captured', 'Captured', 'count', true),
      reports.heading('noRevenue', 'No revenue', 'count', true),
      reports.heading('missing', 'Missing', 'count', true),
      reports.heading('revenue', 'Revenue', 'money', true),
      reports.heading('target', 'Target', 'money', true),
      reports.heading('reached', 'Reached', 'percent', false),
      reports.heading('against', 'Against target', 'net', true)
    ),
    v_rows
  );
END;
$$;

REVOKE ALL ON FUNCTION reports.fleet_target(date, date, uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.fleet_target(date, date, uuid, date) TO xcode_api_executor;
