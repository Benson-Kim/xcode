-- reports.vehicle_figures(p_vehicle_ids uuid[], p_from date, p_through date, p_today date) RETURNS TABLE (vehicle_id uuid, revenue numeric, target numeric, captured integer, no_revenue integer, missing integer, missing_days date[], money_out numeric, saved numeric, saving_runs integer)
-- Purpose: one row per vehicle with days in the period (setup.report_window not empty), set-based: the day series of revenue.vehicle_days summed inside each vehicle's window without building its rows, and setup.fleet_totals: revenue (the amounts recorded), the target (the day targets of the days that count: in the fleet and before the business date or recorded), days captured with an amount, no-revenue days, the missing days (counting, without a record) with their dates, money out (cost postings), saved (saving postings) and the saving runs; the vehicle report's figures by construction.
-- Callers: reports.fleet_net, reports.fleet_target, reports.fleet_gaps.
-- Reads: setup.vehicle_target_sets, setup.vehicle_away_periods, revenue.records, and what setup.report_window and setup.fleet_totals read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py, tests/db/test_revenue_helpers.py.
-- Each vehicle's days and postings are summed before they meet the windows: joined row by row,
-- a year of 500 vehicles filtered 90 million pairs. Only the window's days are made: inside it a
-- day is in the fleet unless away, so the day rules of revenue.vehicle_days reduce to the away
-- periods, the target set in force and the record (a test holds the two forms equal). The
-- organization is read once per statement, not once per record.

CREATE OR REPLACE FUNCTION reports.vehicle_figures(
  p_vehicle_ids uuid[],
  p_from date,
  p_through date,
  p_today date
)
RETURNS TABLE (
  vehicle_id uuid,
  revenue numeric,
  target numeric,
  captured integer,
  no_revenue integer,
  missing integer,
  missing_days date[],
  money_out numeric,
  saved numeric,
  saving_runs integer
)
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  WITH windows AS MATERIALIZED (
    SELECT DISTINCT u.id AS vehicle_id, setup.report_window(u.id, p_from, p_through, p_today) AS span
    FROM unnest(p_vehicle_ids) AS u (id)
    WHERE u.id IS NOT NULL
  ),
  targets AS (
    SELECT t.vehicle_id,
           t.starts_on,
           ARRAY[t.monday, t.tuesday, t.wednesday, t.thursday, t.friday, t.saturday, t.sunday]
             AS figures,
           lead(t.starts_on) OVER (PARTITION BY t.vehicle_id ORDER BY t.starts_on)
             AS superseded_from
    FROM setup.vehicle_target_sets AS t
    WHERE t.organization_id = (SELECT tenancy.current_organization())
      AND t.vehicle_id = ANY (p_vehicle_ids)
      AND t.starts_on <= p_through
  ),
  lines AS (
    SELECT w.vehicle_id,
           g.at::date AS day,
           a.vehicle_id IS NULL AS active,
           r.id AS record_id,
           r.amount,
           coalesce(t.figures[extract(isodow FROM g.at)::integer], 0) AS figure
    FROM windows AS w
    CROSS JOIN LATERAL generate_series(lower(w.span), upper(w.span) - 1, interval '1 day') AS g (at)
    LEFT JOIN setup.vehicle_away_periods AS a
      ON a.organization_id = (SELECT tenancy.current_organization())
     AND a.vehicle_id = w.vehicle_id
     AND g.at::date >= a.left_on
     AND g.at::date < a.returned_on
    LEFT JOIN targets AS t
      ON t.vehicle_id = w.vehicle_id
     AND g.at::date >= t.starts_on
     AND (t.superseded_from IS NULL OR g.at::date < t.superseded_from)
    LEFT JOIN revenue.records AS r
      ON r.organization_id = (SELECT tenancy.current_organization())
     AND r.vehicle_id = w.vehicle_id
     AND r.business_date = g.at::date
    WHERE NOT isempty(w.span)
  ),
  days AS MATERIALIZED (
    SELECT l.vehicle_id,
           sum(l.amount) AS revenue,
           sum(l.figure) FILTER (WHERE l.active AND (l.day < p_today OR l.record_id IS NOT NULL))
             AS target,
           count(*) FILTER (WHERE l.record_id IS NOT NULL AND l.amount IS NOT NULL) AS captured,
           count(*) FILTER (WHERE l.record_id IS NOT NULL AND l.amount IS NULL) AS no_revenue,
           count(*) FILTER (WHERE l.active AND l.day < p_today AND l.record_id IS NULL) AS missing,
           array_agg(l.day ORDER BY l.day)
             FILTER (WHERE l.active AND l.day < p_today AND l.record_id IS NULL) AS missing_days
    FROM lines AS l
    GROUP BY l.vehicle_id
  ),
  postings AS MATERIALIZED (
    SELECT t.vehicle_id, t.money_out, t.saved, t.saving_runs
    FROM setup.fleet_totals(p_vehicle_ids, p_from, p_through, p_today) AS t
  )
  SELECT w.vehicle_id,
         coalesce(d.revenue, 0),
         coalesce(d.target, 0),
         coalesce(d.captured, 0)::integer,
         coalesce(d.no_revenue, 0)::integer,
         coalesce(d.missing, 0)::integer,
         coalesce(d.missing_days, '{}'::date[]),
         coalesce(p.money_out, 0),
         coalesce(p.saved, 0),
         coalesce(p.saving_runs, 0)::integer
  FROM windows AS w
  LEFT JOIN days AS d ON d.vehicle_id = w.vehicle_id
  LEFT JOIN postings AS p ON p.vehicle_id = w.vehicle_id
  WHERE NOT isempty(w.span);
$$;

REVOKE ALL ON FUNCTION reports.vehicle_figures(uuid[], date, date, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.vehicle_figures(uuid[], date, date, date) TO xcode_api_executor;
