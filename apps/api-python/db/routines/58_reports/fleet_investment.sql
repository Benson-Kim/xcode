-- reports.fleet_investment(p_company_id uuid, p_today date) RETURNS jsonb
-- Purpose: the undated Investment table: one row per visible vehicle that has joined, by recovered (highest first, those without an investment last) then registration: vehicle, company, join date, invested (the initial investment plus the dated entries, null with neither), net since joining (money in less money out from the join date to the business date, counted as setup.vehicle_net counts them but set-based over every vehicle at once) and recovered (net over invested, one decimal, null without an investment); headline Invested in vehicles, figures Net since joining and Recovered (of the totals, 0 when nothing is invested).
-- Callers: reports.build.
-- Reads: setup.fleet_vehicles, setup.vehicle_investments, revenue.records, and what reports.vehicles, setup.report_window and setup.fleet_totals read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.
CREATE OR REPLACE FUNCTION reports.fleet_investment(p_company_id uuid, p_today date)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.current_organization();
  v_rows jsonb;
  v_invested numeric;
  v_net numeric;
BEGIN
  WITH vehicles AS (
    SELECT v.vehicle_id,
           v.registration,
           v.company_name,
           v.joined_on,
           f.initial_investment,
           setup.report_window(v.vehicle_id, v.joined_on, p_today, p_today) AS span
    FROM reports.vehicles(p_company_id) AS v
    JOIN setup.fleet_vehicles AS f ON f.organization_id = v_organization_id AND f.id = v.vehicle_id
    WHERE v.joined_on <= p_today
  ),
  money_in AS (
    SELECT r.vehicle_id, sum(r.amount) AS amount
    FROM vehicles AS v
    JOIN revenue.records AS r
      ON r.organization_id = v_organization_id
     AND r.vehicle_id = v.vehicle_id
     AND r.business_date >= lower(v.span)
     AND r.business_date < upper(v.span)
    GROUP BY r.vehicle_id
  ),
  money_out AS (
    SELECT t.vehicle_id, t.money_out AS amount
    FROM setup.fleet_totals(
           ARRAY(SELECT v.vehicle_id FROM vehicles AS v),
           coalesce((SELECT min(v.joined_on) FROM vehicles AS v), p_today),
           p_today,
           p_today,
           '{1}'
         ) AS t
  ),
  investments AS (
    SELECT i.vehicle_id, sum(i.amount) AS total
    FROM setup.vehicle_investments AS i
    WHERE i.organization_id = v_organization_id
    GROUP BY i.vehicle_id
  ),
  lines AS (
    SELECT v.vehicle_id,
           v.registration,
           v.company_name,
           v.joined_on,
           CASE
             WHEN v.initial_investment IS NULL AND e.total IS NULL THEN NULL
             ELSE coalesce(v.initial_investment, 0) + coalesce(e.total, 0)
           END AS invested,
           coalesce(m.amount, 0) - coalesce(o.amount, 0) AS net
    FROM vehicles AS v
    LEFT JOIN investments AS e ON e.vehicle_id = v.vehicle_id
    LEFT JOIN money_in AS m ON m.vehicle_id = v.vehicle_id
    LEFT JOIN money_out AS o ON o.vehicle_id = v.vehicle_id
  ),
  rated AS (
    SELECT l.*,
           CASE
             WHEN l.invested IS NULL OR l.invested = 0 THEN NULL
             ELSE reports.ratio(l.net, l.invested)
           END AS recovered
    FROM lines AS l
  )
  SELECT coalesce(
           jsonb_agg(
             jsonb_build_array(
               r.registration, r.company_name, r.joined_on, r.invested, r.net, r.recovered
             )
             ORDER BY (r.recovered IS NULL), r.recovered DESC, r.registration COLLATE "C", r.vehicle_id),
           '[]'::jsonb
         ),
         coalesce(sum(r.invested), 0),
         coalesce(sum(r.net), 0)
  INTO v_rows, v_invested, v_net
  FROM rated AS r;

  RETURN reports.build_table(
    'fleet',
    'investment',
    'Investment',
    NULL,
    NULL,
    p_today,
    reports.figure('Invested in vehicles', v_invested, 'money'),
    jsonb_build_array(
      reports.figure('Net since joining', v_net, 'net'),
      reports.figure('Recovered', coalesce(reports.ratio(v_net, v_invested), 0), 'percent')
    ),
    jsonb_build_array(
      reports.heading('vehicle', 'Vehicle', 'vehicle', false),
      reports.heading('company', 'Company', 'text', false),
      reports.heading('joined', 'Joined', 'date', false),
      reports.heading('invested', 'Invested', 'money', true),
      reports.heading('net', 'Net since joining', 'net', true),
      reports.heading('recovered', 'Recovered', 'percent', false)
    ),
    v_rows
  );
END;
$$;

REVOKE ALL ON FUNCTION reports.fleet_investment(uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.fleet_investment(uuid, date) TO xcode_api_executor;
