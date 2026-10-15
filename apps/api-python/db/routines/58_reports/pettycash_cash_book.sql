-- reports.pettycash_cash_book(p_from date, p_to date, p_holder_ids uuid[], p_view_all boolean, p_vehicles uuid[], p_today date) RETURNS jsonb
-- Purpose: the Cash book table over the entries the actor sees on the given floats: the opening balance from the entries before the period (cash given less credit notes and expenses not rejected), then one row per day of the period with an entry: date, opening, cash received, expenses (not rejected), credit notes, closing and waiting (expenses waiting, not sent back); headline Closing balance, figures Opening balance, Cash received, Expenses and Credit notes.
-- Callers: reports.build.
-- Reads: what reports.pettycash_entries reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.pettycash_cash_book(
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
  v_opening numeric;
  v_cash numeric;
  v_expenses numeric;
  v_credits numeric;
BEGIN
  WITH entries AS (
    SELECT * FROM reports.pettycash_entries(p_holder_ids, p_view_all, p_vehicles)
  ),
  opening AS (
    SELECT coalesce(sum(pettycash.effect(e.kind, e.status, e.total)), 0) AS amount
    FROM entries AS e
    WHERE e.entry_date < p_from
  ),
  days AS (
    SELECT e.entry_date AS day,
           coalesce(sum(e.total) FILTER (WHERE e.kind = 1), 0) AS cash,
           coalesce(sum(e.total) FILTER (WHERE e.kind = 2 AND e.status <> 4), 0) AS expenses,
           coalesce(sum(e.total) FILTER (WHERE e.kind = 3), 0) AS credits,
           coalesce(
             sum(e.total) FILTER (WHERE e.kind = 2 AND e.status = 1 AND e.sent_back_note IS NULL),
             0
           ) AS waiting
    FROM entries AS e
    WHERE e.entry_date BETWEEN p_from AND p_to
    GROUP BY e.entry_date
  ),
  running AS (
    SELECT d.*,
           o.amount + coalesce(
             sum(d.cash - d.expenses - d.credits) OVER (
               ORDER BY d.day ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
             ),
             0
           ) AS opening
    FROM days AS d
    CROSS JOIN opening AS o
  )
  SELECT coalesce(
           jsonb_agg(
             jsonb_build_array(
               r.day, r.opening, r.cash, r.expenses, r.credits,
               r.opening + r.cash - r.expenses - r.credits, r.waiting
             )
             ORDER BY r.day),
           '[]'::jsonb
         ),
         (SELECT o.amount FROM opening AS o),
         coalesce(sum(r.cash), 0),
         coalesce(sum(r.expenses), 0),
         coalesce(sum(r.credits), 0)
  INTO v_rows, v_opening, v_cash, v_expenses, v_credits
  FROM running AS r;

  RETURN reports.build_table(
    'pettycash',
    'cashBook',
    'Cash book',
    p_from,
    p_to,
    p_today,
    reports.figure('Closing balance', v_opening + v_cash - v_expenses - v_credits, 'money'),
    jsonb_build_array(
      reports.figure('Opening balance', v_opening, 'money'),
      reports.figure('Cash received', v_cash, 'money'),
      reports.figure('Expenses', v_expenses, 'money'),
      reports.figure('Credit notes', v_credits, 'money')
    ),
    jsonb_build_array(
      reports.heading('date', 'Date', 'date', false),
      reports.heading('opening', 'Opening', 'money', false),
      reports.heading('cash', 'Cash received', 'money', true),
      reports.heading('expenses', 'Expenses', 'money', true),
      reports.heading('credits', 'Credit notes', 'money', true),
      reports.heading('closing', 'Closing', 'money', false),
      reports.heading('waiting', 'Waiting', 'money', true)
    ),
    v_rows
  );
END;
$$;

REVOKE ALL ON FUNCTION reports.pettycash_cash_book(date, date, uuid[], boolean, uuid[], date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.pettycash_cash_book(date, date, uuid[], boolean, uuid[], date)
  TO xcode_api_executor;
