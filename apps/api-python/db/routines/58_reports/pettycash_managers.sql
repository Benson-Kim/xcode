-- reports.pettycash_managers(p_from date, p_to date, p_holder_ids uuid[], p_view_all boolean, p_vehicles uuid[], p_today date) RETURNS jsonb
-- Purpose: the By manager table over the entries the actor sees on the given floats: one row per float with an entry in the period or a balance, by name: manager, cash received, expenses (not rejected), credit notes, waiting (not sent back), rejected and the balance as at the period's last day; headline Expenses, figures Cash received, Waiting, Rejected and Balance.
-- Callers: reports.build.
-- Reads: what reports.pettycash_entries reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.pettycash_managers(
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
  v_expenses numeric;
  v_cash numeric;
  v_waiting numeric;
  v_rejected numeric;
  v_balance numeric;
BEGIN
  WITH entries AS (
    SELECT e.*, e.entry_date BETWEEN p_from AND p_to AS in_period
    FROM reports.pettycash_entries(p_holder_ids, p_view_all, p_vehicles) AS e
  ),
  lines AS (
    SELECT e.holder_id,
           min(e.holder_name) AS manager,
           coalesce(sum(e.total) FILTER (WHERE e.in_period AND e.kind = 1), 0) AS cash,
           coalesce(sum(e.total) FILTER (WHERE e.in_period AND e.kind = 2 AND e.status <> 4), 0)
             AS expenses,
           coalesce(sum(e.total) FILTER (WHERE e.in_period AND e.kind = 3), 0) AS credits,
           coalesce(
             sum(e.total) FILTER (
               WHERE e.in_period AND e.kind = 2 AND e.status = 1 AND e.sent_back_note IS NULL
             ),
             0
           ) AS waiting,
           coalesce(sum(e.total) FILTER (WHERE e.in_period AND e.kind = 2 AND e.status = 4), 0)
             AS rejected,
           coalesce(
             sum(pettycash.effect(e.kind, e.status, e.total)) FILTER (WHERE e.entry_date <= p_to),
             0
           ) AS balance
    FROM entries AS e
    GROUP BY e.holder_id
    HAVING bool_or(e.in_period)
        OR coalesce(
             sum(pettycash.effect(e.kind, e.status, e.total)) FILTER (WHERE e.entry_date <= p_to),
             0
           ) <> 0
  )
  SELECT coalesce(
           jsonb_agg(
             jsonb_build_array(
               l.manager, l.cash, l.expenses, l.credits, l.waiting, l.rejected, l.balance
             )
             ORDER BY upper(l.manager) COLLATE "C", l.holder_id),
           '[]'::jsonb
         ),
         coalesce(sum(l.expenses), 0),
         coalesce(sum(l.cash), 0),
         coalesce(sum(l.waiting), 0),
         coalesce(sum(l.rejected), 0),
         coalesce(sum(l.balance), 0)
  INTO v_rows, v_expenses, v_cash, v_waiting, v_rejected, v_balance
  FROM lines AS l;

  RETURN reports.build_table(
    'pettycash',
    'managers',
    'By manager',
    p_from,
    p_to,
    p_today,
    reports.figure('Expenses', v_expenses, 'money'),
    jsonb_build_array(
      reports.figure('Cash received', v_cash, 'money'),
      reports.figure('Waiting', v_waiting, 'money'),
      reports.figure('Rejected', v_rejected, 'money'),
      reports.figure('Balance', v_balance, 'money')
    ),
    jsonb_build_array(
      reports.heading('manager', 'Manager', 'text', false),
      reports.heading('cashReceived', 'Cash received', 'money', true),
      reports.heading('expenses', 'Expenses', 'money', true),
      reports.heading('creditNotes', 'Credit notes', 'money', true),
      reports.heading('waiting', 'Waiting', 'money', true),
      reports.heading('rejected', 'Rejected', 'money', true),
      reports.heading('balance', 'Balance', 'money', true)
    ),
    v_rows
  );
END;
$$;

REVOKE ALL ON FUNCTION reports.pettycash_managers(date, date, uuid[], boolean, uuid[], date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.pettycash_managers(date, date, uuid[], boolean, uuid[], date)
  TO xcode_api_executor;
