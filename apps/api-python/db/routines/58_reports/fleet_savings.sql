-- reports.fleet_savings(p_from date, p_to date, p_company_id uuid, p_today date) RETURNS jsonb
-- Purpose: the Savings table: one row per visible vehicle with a saving run in the period or a balance, by balance then registration: vehicle, company, the runs saved, skipped and held in the period, the amount saved, not saved (the skipped runs' amounts) and the balance as at the period's last day (what setup.saving_balance counts, set-based over every saving and vehicle at once: the openings reached by that day plus the runs saved since each saving began, or since the day after its opening); headline Saved, figures Balance, Not saved, Runs skipped and Waiting for revenue.
-- Callers: reports.build.
-- Reads: setup.recurring_versions, setup.saving_openings, setup.saving_opening_amounts, and what reports.vehicles and setup.scheduled_runs read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.
CREATE OR REPLACE FUNCTION reports.fleet_savings(p_from date, p_to date, p_company_id uuid, p_today date)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.current_organization();
  v_ids uuid[] := ARRAY(SELECT v.vehicle_id FROM reports.vehicles(p_company_id) AS v);
  v_as_of date := least(p_to, p_today);
  v_rows jsonb;
  v_saved numeric;
  v_balance numeric;
  v_not_saved numeric;
  v_skipped numeric;
  v_held numeric;
BEGIN
  WITH runs AS (
    SELECT r.vehicle_id,
           count(*) FILTER (WHERE r.state = 1) AS saved_runs,
           count(*) FILTER (WHERE r.state = 2) AS skipped_runs,
           count(*) FILTER (WHERE r.state = 3) AS held_runs,
           coalesce(sum(r.amount) FILTER (WHERE r.state = 1), 0) AS saved,
           coalesce(sum(r.amount) FILTER (WHERE r.state = 2), 0) AS not_saved
    FROM setup.scheduled_runs(v_ids, p_from, p_to, p_today, '{2}') AS r
    WHERE r.kind = 2
    GROUP BY r.vehicle_id
  ),
  savings AS (
    SELECT ver.item_id,
           o.opened_on,
           CASE
             WHEN o.opened_on IS NULL THEN min(ver.start_on)
             ELSE greatest(min(ver.start_on), o.opened_on + 1)
           END AS first_run
    FROM setup.recurring_versions AS ver
    LEFT JOIN setup.saving_openings AS o
      ON o.organization_id = ver.organization_id AND o.item_id = ver.item_id
    WHERE ver.organization_id = v_organization_id
    GROUP BY ver.item_id, o.opened_on
    HAVING bool_or(ver.kind = 2)
  ),
  saved_since AS (
    SELECT r.vehicle_id, sum(r.amount) AS amount
    FROM setup.scheduled_runs(
           v_ids, coalesce((SELECT min(s.first_run) FROM savings AS s), v_as_of), v_as_of, p_today, '{2}'
         ) AS r
    JOIN savings AS s ON s.item_id = r.item_id AND r.run_on >= s.first_run
    WHERE r.state = 1
    GROUP BY r.vehicle_id
  ),
  openings AS (
    SELECT a.vehicle_id, sum(a.amount) AS amount
    FROM setup.saving_opening_amounts AS a
    JOIN savings AS s ON s.item_id = a.item_id
    WHERE a.organization_id = v_organization_id
      AND s.opened_on <= p_to
      AND a.vehicle_id = ANY (v_ids)
    GROUP BY a.vehicle_id
  ),
  balances AS (
    SELECT b.vehicle_id, sum(b.amount) AS balance
    FROM (
      SELECT o.vehicle_id, o.amount FROM openings AS o
      UNION ALL
      SELECT s.vehicle_id, s.amount FROM saved_since AS s
    ) AS b
    GROUP BY b.vehicle_id
  ),
  lines AS (
    SELECT v.vehicle_id,
           v.registration,
           v.company_name,
           coalesce(r.saved_runs, 0) AS saved_runs,
           coalesce(r.skipped_runs, 0) AS skipped_runs,
           coalesce(r.held_runs, 0) AS held_runs,
           coalesce(r.saved, 0) AS saved,
           coalesce(r.not_saved, 0) AS not_saved,
           coalesce(b.balance, 0) AS balance
    FROM reports.vehicles(p_company_id) AS v
    LEFT JOIN runs AS r ON r.vehicle_id = v.vehicle_id
    LEFT JOIN balances AS b ON b.vehicle_id = v.vehicle_id
    WHERE r.vehicle_id IS NOT NULL OR coalesce(b.balance, 0) <> 0
  )
  SELECT coalesce(
           jsonb_agg(
             jsonb_build_array(
               l.registration, l.company_name, l.saved_runs, l.skipped_runs, l.held_runs,
               l.saved, l.not_saved, l.balance
             )
             ORDER BY l.balance DESC, l.registration COLLATE "C", l.vehicle_id),
           '[]'::jsonb
         ),
         coalesce(sum(l.saved), 0),
         coalesce(sum(l.balance), 0),
         coalesce(sum(l.not_saved), 0),
         coalesce(sum(l.skipped_runs), 0),
         coalesce(sum(l.held_runs), 0)
  INTO v_rows, v_saved, v_balance, v_not_saved, v_skipped, v_held
  FROM lines AS l;

  RETURN reports.build_table(
    'fleet',
    'savings',
    'Savings',
    p_from,
    p_to,
    p_today,
    reports.figure('Saved', v_saved, 'money'),
    jsonb_build_array(
      reports.figure('Balance', v_balance, 'money'),
      reports.figure('Not saved', v_not_saved, 'money'),
      reports.figure('Runs skipped', v_skipped, 'count'),
      reports.figure('Waiting for revenue', v_held, 'count')
    ),
    jsonb_build_array(
      reports.heading('vehicle', 'Vehicle', 'vehicle', false),
      reports.heading('company', 'Company', 'text', false),
      reports.heading('savedRuns', 'Saved runs', 'count', true),
      reports.heading('skippedRuns', 'Skipped runs', 'count', true),
      reports.heading('heldRuns', 'Held runs', 'count', true),
      reports.heading('saved', 'Saved', 'money', true),
      reports.heading('notSaved', 'Not saved', 'money', true),
      reports.heading('balance', 'Balance', 'money', true)
    ),
    v_rows
  );
END;
$$;

REVOKE ALL ON FUNCTION reports.fleet_savings(date, date, uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.fleet_savings(date, date, uuid, date) TO xcode_api_executor;
