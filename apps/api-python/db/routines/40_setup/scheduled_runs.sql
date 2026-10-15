-- setup.scheduled_runs(p_vehicle_ids uuid[], p_from date, p_through date, p_today date, p_kinds smallint[] DEFAULT NULL, p_item_ids uuid[] DEFAULT NULL) RETURNS TABLE (item_id uuid, version_id uuid, run_on date, vehicle_id uuid, kind smallint, name text, expense_item_id uuid, note text, amount numeric, state smallint)
-- Purpose: every run of every scheduled version with a share on the vehicles, inside each vehicle's report window, on the version's due days (one version in charge per day, paused days left out; only versions of p_kinds and items of p_item_ids when given): one row per item, day and vehicle at the vehicle's share. state: 0 posted (a cost), 1 saved (a saving without a revenue rule, or decided saved), 2 skipped (decided), 3 held (a saving with a rule and no decision yet). Unordered.
-- Callers: setup.fleet_postings, setup.fleet_totals, setup.decide_saving_runs, setup.saving_balance, api.setup_recurring_list, api.setup_recurring_runs, api.setup_recurring_summary, api.expenses_ledger_get, the reports.
-- Reads: setup.recurring_allocations, setup.recurring_versions, setup.saving_runs, and what setup.report_window and setup.recurring_due_days read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py, tests/db/test_recurring_pause_routines.py.
-- The due days are computed once per version over the union of its shares' windows, then cut
-- to each share's window: a fleet of a thousand shares on twenty items costs twenty walks. A
-- saving's stored decision is read by its key: as a join, planned without the arguments, it
-- probed by item and day and filtered every vehicle of the item; an item never decided skips it.
-- The organization is read once per statement (a scalar subquery), not once per row.

CREATE OR REPLACE FUNCTION setup.scheduled_runs(
  p_vehicle_ids uuid[],
  p_from date,
  p_through date,
  p_today date,
  p_kinds smallint[] DEFAULT NULL,
  p_item_ids uuid[] DEFAULT NULL
)
RETURNS TABLE (
  item_id uuid,
  version_id uuid,
  run_on date,
  vehicle_id uuid,
  kind smallint,
  name text,
  expense_item_id uuid,
  note text,
  amount numeric,
  state smallint
)
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  WITH shares AS MATERIALIZED (
    SELECT a.version_id, a.vehicle_id, a.amount, w.span
    FROM (SELECT DISTINCT u.id FROM unnest(p_vehicle_ids) AS u (id) WHERE u.id IS NOT NULL) AS ids
    CROSS JOIN LATERAL (SELECT setup.report_window(ids.id, p_from, p_through, p_today) AS span) AS w
    JOIN setup.recurring_allocations AS a
      ON a.organization_id = (SELECT tenancy.current_organization()) AND a.vehicle_id = ids.id
    WHERE NOT isempty(w.span)
  ),
  days AS MATERIALIZED (
    SELECT v.id AS version_id, v.item_id, v.kind, v.name, v.expense_item_id, v.note, v.condition_min,
           v.kind = 2 AND v.item_id IN (
             SELECT r.item_id FROM setup.saving_runs AS r
             WHERE r.organization_id = (SELECT tenancy.current_organization())
           ) AS decided,
           due.day
    FROM (
      SELECT s.version_id, min(lower(s.span)) AS first, max(upper(s.span)) - 1 AS last
      FROM shares AS s
      GROUP BY s.version_id
    ) AS b
    JOIN setup.recurring_versions AS v
      ON v.organization_id = (SELECT tenancy.current_organization()) AND v.id = b.version_id
    CROSS JOIN LATERAL setup.recurring_due_days(v, b.first, b.last) AS due (day)
    WHERE (p_kinds IS NULL OR v.kind = ANY (p_kinds))
      AND (p_item_ids IS NULL OR v.item_id = ANY (p_item_ids))
  )
  SELECT d.item_id,
         d.version_id,
         d.day,
         s.vehicle_id,
         d.kind,
         d.name,
         d.expense_item_id,
         d.note,
         s.amount,
         CASE
           WHEN d.kind = 1 THEN 0::smallint
           WHEN NOT d.decided THEN CASE WHEN d.condition_min IS NULL THEN 1::smallint ELSE 3::smallint END
           ELSE coalesce(
             (
               SELECT r.state
               FROM setup.saving_runs AS r
               WHERE r.organization_id = (SELECT tenancy.current_organization())
                 AND r.item_id = d.item_id
                 AND r.run_on = d.day
                 AND r.vehicle_id = s.vehicle_id
             ),
             CASE WHEN d.condition_min IS NULL THEN 1::smallint ELSE 3::smallint END
           )
         END
  FROM shares AS s
  JOIN days AS d ON d.version_id = s.version_id AND s.span @> d.day;
$$;

REVOKE ALL ON FUNCTION setup.scheduled_runs(uuid[], date, date, date, smallint[], uuid[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.scheduled_runs(uuid[], date, date, date, smallint[], uuid[]) TO xcode_api_executor;
