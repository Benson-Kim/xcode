-- reports.fleet_money_out(p_from date, p_to date, p_company_id uuid, p_today date) RETURNS jsonb
-- Purpose: the Money out table: the cost postings of the visible vehicles in the period from every source, grouped by expense item (a scheduled cost without one by its name), by amount then item: main category ("Not set" without one), category (the bucket's label without one), item, entries, quantity (a shared purchase counts its group units times the row's amount over the group total, at the group's unit cost, so the lowest and highest unit costs are what was paid), amount and share of the total; headline Money out, one figure per main category holding money ("No main category" last).
-- Callers: reports.build.
-- Reads: setup.expense_buckets, and what reports.vehicles and setup.fleet_postings read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.fleet_money_out(p_from date, p_to date, p_company_id uuid, p_today date)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_ids uuid[] := ARRAY(SELECT v.vehicle_id FROM reports.vehicles(p_company_id) AS v);
  v_rows jsonb;
  v_total numeric;
  v_figures jsonb;
BEGIN
  WITH postings AS (
    SELECT p.*,
           coalesce(p.group_unit_amount, p.unit_amount) AS unit_cost,
           CASE
             WHEN p.group_id IS NOT NULL AND coalesce(p.group_total, 0) <> 0 THEN
               round(p.group_units * p.amount / p.group_total, 3)
             ELSE p.units
           END AS quantity,
           coalesce(p.expense_item_id::text, 'name:' || p.name) AS item_key,
           coalesce(p.item_name, p.name) AS item_label,
           coalesce(
             p.category_name,
             (SELECT b.label FROM setup.expense_buckets AS b WHERE b.code = p.bucket)
           ) AS category_label
    FROM setup.fleet_postings(v_ids, p_from, p_to, p_today, '{1}') AS p
    WHERE p.kind = 1
  ),
  groups AS (
    SELECT g.item_key,
           min(g.main_category_name) AS main_name,
           min(g.category_label) AS category_label,
           min(g.item_label) AS item_label,
           count(*) AS entries,
           sum(g.quantity) AS quantity,
           min(g.unit_cost) AS low,
           max(g.unit_cost) AS high,
           sum(g.amount) AS amount
    FROM postings AS g
    GROUP BY g.item_key
  ),
  total AS (
    SELECT coalesce(sum(p.amount), 0) AS amount FROM postings AS p
  )
  SELECT coalesce(
           (
             SELECT jsonb_agg(
                      jsonb_build_array(
                        coalesce(g.main_name, 'Not set'), g.category_label, g.item_label,
                        g.entries, g.quantity, g.low, g.high, g.amount,
                        reports.ratio(g.amount, t.amount)
                      )
                      ORDER BY g.amount DESC, g.item_label COLLATE "C", g.item_key)
             FROM groups AS g
             CROSS JOIN total AS t
           ),
           '[]'::jsonb
         ),
         (SELECT t.amount FROM total AS t),
         coalesce(
           (
             SELECT jsonb_agg(
                      reports.figure(coalesce(m.main_name, 'No main category'), m.amount, 'money')
                      ORDER BY (m.main_id IS NULL), m.main_name COLLATE "C", m.main_id)
             FROM (
               SELECT p.main_category_id AS main_id,
                      p.main_category_name AS main_name,
                      sum(p.amount) AS amount
               FROM postings AS p
               GROUP BY p.main_category_id, p.main_category_name
             ) AS m
           ),
           '[]'::jsonb
         )
  INTO v_rows, v_total, v_figures;

  RETURN reports.build_table(
    'fleet',
    'moneyOut',
    'Money out',
    p_from,
    p_to,
    p_today,
    reports.figure('Money out', v_total, 'money'),
    v_figures,
    jsonb_build_array(
      reports.heading('mainCategory', 'Main category', 'text', false),
      reports.heading('category', 'Category', 'text', false),
      reports.heading('item', 'Item', 'text', false),
      reports.heading('entries', 'Entries', 'count', true),
      reports.heading('quantity', 'Quantity', 'quantity', true),
      reports.heading('low', 'Lowest unit cost', 'money', false),
      reports.heading('high', 'Highest unit cost', 'money', false),
      reports.heading('amount', 'Amount', 'money', true),
      reports.heading('share', 'Share', 'percent', false)
    ),
    v_rows
  );
END;
$$;

REVOKE ALL ON FUNCTION reports.fleet_money_out(date, date, uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.fleet_money_out(date, date, uuid, date) TO xcode_api_executor;
