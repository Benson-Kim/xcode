-- reports.pettycash_items(p_from date, p_to date, p_holder_ids uuid[], p_view_all boolean, p_vehicles uuid[], p_today date) RETURNS jsonb
-- Purpose: the By item table: the petty-cash expenses not rejected in the period, on the floats the actor sees, grouped by expense item, by amount then item: category, item, entries, quantity (the units) and amount; headline Expenses, figures Items and Entries.
-- Callers: reports.build.
-- Reads: what reports.pettycash_entries reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.pettycash_items(
  p_from date,
  p_to date,
  p_holder_ids uuid[],
  p_view_all boolean,
  p_vehicles uuid[],
  p_today date
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_rows jsonb;
  v_amount numeric;
  v_items numeric;
  v_entries numeric;
BEGIN
  WITH lines AS (
    SELECT e.expense_item_id,
           min(e.category_name) AS category_name,
           min(e.item_name) AS item_name,
           count(*) AS entries,
           sum(e.units) AS quantity,
           sum(e.total) AS amount
    FROM reports.pettycash_entries(p_holder_ids, p_view_all, p_vehicles) AS e
    WHERE e.kind = 2 AND e.status <> 4 AND e.entry_date BETWEEN p_from AND p_to
    GROUP BY e.expense_item_id
  )
  SELECT coalesce(
           jsonb_agg(
             jsonb_build_array(l.category_name, l.item_name, l.entries, l.quantity, l.amount)
             ORDER BY l.amount DESC, l.item_name COLLATE "C", l.expense_item_id),
           '[]'::jsonb
         ),
         coalesce(sum(l.amount), 0),
         count(*),
         coalesce(sum(l.entries), 0)
  INTO v_rows, v_amount, v_items, v_entries
  FROM lines AS l;

  RETURN reports.build_table(
    'pettycash',
    'items',
    'By item',
    p_from,
    p_to,
    p_today,
    reports.figure('Expenses', v_amount, 'money'),
    jsonb_build_array(
      reports.figure('Items', v_items, 'count'),
      reports.figure('Entries', v_entries, 'count')
    ),
    jsonb_build_array(
      reports.heading('category', 'Category', 'text', false),
      reports.heading('item', 'Item', 'text', false),
      reports.heading('entries', 'Entries', 'count', true),
      reports.heading('quantity', 'Quantity', 'quantity', true),
      reports.heading('amount', 'Amount', 'money', true)
    ),
    v_rows
  );
END;
$$;

REVOKE ALL ON FUNCTION reports.pettycash_items(date, date, uuid[], boolean, uuid[], date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.pettycash_items(date, date, uuid[], boolean, uuid[], date)
  TO xcode_api_executor;
