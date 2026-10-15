-- setup.fleet_postings(p_vehicle_ids uuid[], p_from date, p_through date, p_today date, p_kinds smallint[] DEFAULT NULL) RETURNS TABLE (source smallint, kind smallint, day date, vehicle_id uuid, id uuid, version_id uuid, name text, item_name text, expense_item_id uuid, category_name text, main_category_id uuid, main_category_name text, bucket smallint, units numeric, unit_amount numeric, amount numeric, note text, recorded_by uuid, holder_id uuid, group_id uuid, group_size integer, group_total numeric, group_units numeric, group_unit_amount numeric, version bigint)
-- Purpose: every posting of the vehicles, each inside its vehicle's report window: source 1 the central expenses not removed, 2 the approved petty-cash expenses not removed, 3 the scheduled runs that post (costs, and savings saved); kind 1 cost, 2 saving; only the kinds of p_kinds when given (central and petty-cash rows are costs). A stored row's id and version_id are its entry id, a run's the item and version. Names, categories and main categories are read through the item as they are now; a cost's bucket is its category's (a scheduled cost's as saved), recurring charges (2) when none, a saving none. A petty-cash group's size counts its parts not removed and not rejected. Unordered.
-- Callers: api.setup_vehicle_report, api.expenses_ledger_get, expenses.ledger_rows, reports.money_out_by_main, reports.fleet_money_out.
-- Reads: expenses.entries, pettycash.entries, setup.expense_items, setup.expense_categories, setup.expense_main_categories, and what setup.report_window and setup.scheduled_runs read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py, tests/db/test_setup_vehicle_routines.py, tests/db/test_expense_routines.py.

CREATE OR REPLACE FUNCTION setup.fleet_postings(
  p_vehicle_ids uuid[],
  p_from date,
  p_through date,
  p_today date,
  p_kinds smallint[] DEFAULT NULL
)
RETURNS TABLE (
  source smallint,
  kind smallint,
  day date,
  vehicle_id uuid,
  id uuid,
  version_id uuid,
  name text,
  item_name text,
  expense_item_id uuid,
  category_name text,
  main_category_id uuid,
  main_category_name text,
  bucket smallint,
  units numeric,
  unit_amount numeric,
  amount numeric,
  note text,
  recorded_by uuid,
  holder_id uuid,
  group_id uuid,
  group_size integer,
  group_total numeric,
  group_units numeric,
  group_unit_amount numeric,
  version bigint
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
  )
  SELECT 1::smallint,
         1::smallint,
         e.entry_date,
         e.vehicle_id,
         e.id,
         e.id,
         i.name,
         i.name,
         e.expense_item_id,
         c.name,
         m.id,
         m.name,
         coalesce(c.bucket, 2::smallint),
         e.units::numeric,
         e.unit_amount::numeric,
         e.total::numeric,
         e.note,
         e.recorded_by,
         NULL::uuid,
         e.group_id,
         e.group_size,
         e.group_total::numeric,
         e.group_units::numeric,
         e.group_unit_amount::numeric,
         e.version
  FROM windows AS w
  JOIN expenses.entries AS e
    ON e.organization_id = v_organization_id
   AND e.vehicle_id = w.vehicle_id
   AND e.removed_at IS NULL
   AND e.entry_date >= lower(w.span)
   AND e.entry_date < upper(w.span)
   AND (p_kinds IS NULL OR 1 = ANY (p_kinds))
  JOIN setup.expense_items AS i ON i.organization_id = e.organization_id AND i.id = e.expense_item_id
  JOIN setup.expense_categories AS c ON c.organization_id = i.organization_id AND c.id = i.category_id
  LEFT JOIN setup.expense_main_categories AS m
    ON m.organization_id = c.organization_id AND m.id = c.main_category_id
  UNION ALL
  SELECT 2::smallint,
         1::smallint,
         e.entry_date,
         e.vehicle_id,
         e.id,
         e.id,
         i.name,
         i.name,
         e.expense_item_id,
         c.name,
         m.id,
         m.name,
         coalesce(c.bucket, 2::smallint),
         e.units::numeric,
         e.unit_amount::numeric,
         e.total::numeric,
         e.note,
         e.recorded_by,
         e.holder_id,
         e.group_id,
         CASE
           WHEN e.group_id IS NOT NULL THEN (
             SELECT count(*)::integer
             FROM pettycash.entries AS g
             WHERE g.organization_id = e.organization_id
               AND g.group_id = e.group_id
               AND g.removed_at IS NULL
               AND g.status IS DISTINCT FROM 4
           )
         END,
         e.group_total::numeric,
         e.group_units::numeric,
         e.group_unit_amount::numeric,
         e.version
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
  JOIN setup.expense_items AS i ON i.organization_id = e.organization_id AND i.id = e.expense_item_id
  JOIN setup.expense_categories AS c ON c.organization_id = i.organization_id AND c.id = i.category_id
  LEFT JOIN setup.expense_main_categories AS m
    ON m.organization_id = c.organization_id AND m.id = c.main_category_id
  UNION ALL
  SELECT 3::smallint,
         r.kind,
         r.run_on,
         r.vehicle_id,
         r.item_id,
         r.version_id,
         r.name,
         i.name,
         r.expense_item_id,
         c.name,
         m.id,
         m.name,
         CASE WHEN r.kind = 1 THEN coalesce(v.bucket, 2::smallint) END,
         1::numeric,
         r.amount,
         r.amount,
         r.note,
         NULL::uuid,
         NULL::uuid,
         NULL::uuid,
         NULL::integer,
         NULL::numeric,
         NULL::numeric,
         NULL::numeric,
         NULL::bigint
  FROM setup.scheduled_runs(
         ARRAY(SELECT w.vehicle_id FROM windows AS w), p_from, p_through, p_today, p_kinds
       ) AS r
  JOIN setup.recurring_versions AS v ON v.organization_id = v_organization_id AND v.id = r.version_id
  LEFT JOIN setup.expense_items AS i ON i.organization_id = v.organization_id AND i.id = r.expense_item_id
  LEFT JOIN setup.expense_categories AS c ON c.organization_id = i.organization_id AND c.id = i.category_id
  LEFT JOIN setup.expense_main_categories AS m
    ON m.organization_id = c.organization_id AND m.id = c.main_category_id
  WHERE r.state IN (0, 1);
END;
$$;

REVOKE ALL ON FUNCTION setup.fleet_postings(uuid[], date, date, date, smallint[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.fleet_postings(uuid[], date, date, date, smallint[]) TO xcode_api_executor;
