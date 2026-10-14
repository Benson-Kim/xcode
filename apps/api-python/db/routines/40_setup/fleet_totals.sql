-- setup.fleet_totals(p_vehicle_ids uuid[], p_from date, p_through date, p_today date, p_kinds smallint[] DEFAULT NULL) RETURNS TABLE (vehicle_id uuid, money_out numeric, saved numeric, saving_runs integer)
-- Purpose: per listed vehicle, the sums of its setup.fleet_postings without building the postings: money out (the central expenses not removed, the approved petty-cash expenses not removed and the scheduled costs, inside its report window), saved (the savings saved) and the count of saved runs; only the kinds of p_kinds when given (setup.fleet_postings' rule); zeros for a vehicle with none. Unordered.
-- Callers: setup.vehicle_net, reports.vehicle_figures, reports.fleet_investment.
-- Reads: expenses.entries, pettycash.entries, and what setup.report_window and setup.scheduled_runs read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.
-- The readers that only sum read this instead of setup.fleet_postings: a year of ten times the
-- demo fleet is a quarter of a million postings, each carrying names the sums never read.

CREATE OR REPLACE FUNCTION setup.fleet_totals(
  p_vehicle_ids uuid[],
  p_from date,
  p_through date,
  p_today date,
  p_kinds smallint[] DEFAULT NULL
)
RETURNS TABLE (
  vehicle_id uuid,
  money_out numeric,
  saved numeric,
  saving_runs integer
)
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.current_organization();
BEGIN
  RETURN QUERY
  WITH windows AS MATERIALIZED (
    SELECT DISTINCT u.id AS vehicle_id, setup.report_window(u.id, p_from, p_through, p_today) AS span
    FROM unnest(p_vehicle_ids) AS u (id)
    WHERE u.id IS NOT NULL
  ),
  central AS MATERIALIZED (
    SELECT e.vehicle_id, sum(e.total) AS amount
    FROM windows AS w
    JOIN expenses.entries AS e
      ON e.organization_id = v_organization_id
     AND e.vehicle_id = w.vehicle_id
     AND e.removed_at IS NULL
     AND e.entry_date >= lower(w.span)
     AND e.entry_date < upper(w.span)
     AND (p_kinds IS NULL OR 1 = ANY (p_kinds))
    GROUP BY e.vehicle_id
  ),
  petty AS MATERIALIZED (
    SELECT e.vehicle_id, sum(e.total) AS amount
    FROM windows AS w
    JOIN pettycash.entries AS e
      ON e.organization_id = v_organization_id
     AND e.vehicle_id = w.vehicle_id
     AND e.kind = 2
     AND e.status = 2
     AND e.removed_at IS NULL
     AND e.entry_date >= lower(w.span)
     AND e.entry_date < upper(w.span)
     AND (p_kinds IS NULL OR 1 = ANY (p_kinds))
    GROUP BY e.vehicle_id
  ),
  runs AS MATERIALIZED (
    SELECT r.vehicle_id,
           sum(r.amount) FILTER (WHERE r.kind = 1) AS cost,
           sum(r.amount) FILTER (WHERE r.kind = 2) AS saved,
           count(*) FILTER (WHERE r.kind = 2) AS saving_runs
    FROM setup.scheduled_runs(
           ARRAY(SELECT w.vehicle_id FROM windows AS w), p_from, p_through, p_today, p_kinds
         ) AS r
    WHERE r.state IN (0, 1)
    GROUP BY r.vehicle_id
  )
  SELECT w.vehicle_id,
         coalesce(c.amount, 0) + coalesce(p.amount, 0) + coalesce(r.cost, 0),
         coalesce(r.saved, 0),
         coalesce(r.saving_runs, 0)::integer
  FROM windows AS w
  LEFT JOIN central AS c ON c.vehicle_id = w.vehicle_id
  LEFT JOIN petty AS p ON p.vehicle_id = w.vehicle_id
  LEFT JOIN runs AS r ON r.vehicle_id = w.vehicle_id;
END;
$$;

REVOKE ALL ON FUNCTION setup.fleet_totals(uuid[], date, date, date, smallint[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.fleet_totals(uuid[], date, date, date, smallint[]) TO xcode_api_executor;
