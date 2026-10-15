-- reports.fleet_net(p_from date, p_to date, p_company_id uuid, p_today date) RETURNS jsonb
-- Purpose: the Net by vehicle table: one row per visible vehicle with days in the period (of the company when given), by net then registration: vehicle, company, revenue, one money-out column per main category holding money in the period (key main:{id}, by name; main:none "No main category" last when it holds money), money out, net and saved; headline Net, figures Revenue, Money out and Saved over the rows.
-- Callers: reports.build.
-- Reads: what reports.vehicles, reports.vehicle_figures and reports.money_out_by_main read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.fleet_net(p_from date, p_to date, p_company_id uuid, p_today date)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_ids uuid[] := ARRAY(SELECT v.vehicle_id FROM reports.vehicles(p_company_id) AS v);
  v_columns jsonb;
  v_rows jsonb;
  v_revenue numeric;
  v_money_out numeric;
  v_saved numeric;
BEGIN
  WITH figures AS (
    SELECT * FROM reports.vehicle_figures(v_ids, p_from, p_to, p_today)
  ),
  by_main AS (
    SELECT * FROM reports.money_out_by_main(v_ids, p_from, p_to, p_today)
  ),
  mains AS (
    SELECT m.main_category_id,
           m.main_category_name,
           row_number() OVER (
             ORDER BY (m.main_category_id IS NULL), m.main_category_name COLLATE "C", m.main_category_id
           ) AS ord
    FROM (
      SELECT b.main_category_id, b.main_category_name
      FROM by_main AS b
      GROUP BY b.main_category_id, b.main_category_name
      HAVING sum(b.amount) <> 0
    ) AS m
  ),
  lines AS (
    SELECT v.vehicle_id,
           v.registration,
           v.company_name,
           f.revenue,
           f.money_out,
           f.revenue - f.money_out AS net,
           f.saved,
           (
             SELECT coalesce(jsonb_agg(coalesce(b.amount, 0) ORDER BY mains.ord), '[]'::jsonb)
             FROM mains
             LEFT JOIN by_main AS b
               ON b.vehicle_id = f.vehicle_id
              AND b.main_category_id IS NOT DISTINCT FROM mains.main_category_id
           ) AS main_cells
    FROM figures AS f
    JOIN reports.vehicles(p_company_id) AS v ON v.vehicle_id = f.vehicle_id
  )
  SELECT jsonb_build_array(
           reports.heading('vehicle', 'Vehicle', 'vehicle', false),
           reports.heading('company', 'Company', 'text', false),
           reports.heading('revenue', 'Revenue', 'money', true)
         )
         || coalesce(
              (
                SELECT jsonb_agg(
                         reports.heading(
                           CASE
                             WHEN mains.main_category_id IS NULL THEN 'main:none'
                             ELSE 'main:' || mains.main_category_id::text
                           END,
                           coalesce(mains.main_category_name, 'No main category'),
                           'money',
                           true
                         ) ORDER BY mains.ord)
                FROM mains
              ),
              '[]'::jsonb
            )
         || jsonb_build_array(
              reports.heading('moneyOut', 'Money out', 'money', true),
              reports.heading('net', 'Net', 'net', true),
              reports.heading('saved', 'Saved', 'money', true)
            ),
         coalesce(
           (
             SELECT jsonb_agg(
                      jsonb_build_array(l.registration, l.company_name, l.revenue)
                      || l.main_cells
                      || jsonb_build_array(l.money_out, l.net, l.saved)
                      ORDER BY l.net DESC, l.registration COLLATE "C", l.vehicle_id)
             FROM lines AS l
           ),
           '[]'::jsonb
         ),
         coalesce((SELECT sum(l.revenue) FROM lines AS l), 0),
         coalesce((SELECT sum(l.money_out) FROM lines AS l), 0),
         coalesce((SELECT sum(l.saved) FROM lines AS l), 0)
  INTO v_columns, v_rows, v_revenue, v_money_out, v_saved;

  RETURN reports.build_table(
    'fleet',
    'net',
    'Net by vehicle',
    p_from,
    p_to,
    p_today,
    reports.figure('Net', v_revenue - v_money_out, 'net'),
    jsonb_build_array(
      reports.figure('Revenue', v_revenue, 'money'),
      reports.figure('Money out', v_money_out, 'money'),
      reports.figure('Saved', v_saved, 'money')
    ),
    v_columns,
    v_rows
  );
END;
$$;

REVOKE ALL ON FUNCTION reports.fleet_net(date, date, uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.fleet_net(date, date, uuid, date) TO xcode_api_executor;
