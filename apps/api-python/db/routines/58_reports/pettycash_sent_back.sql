-- reports.pettycash_sent_back(p_from date, p_to date, p_holder_ids uuid[], p_view_all boolean, p_vehicles uuid[], p_today date) RETURNS jsonb
-- Purpose: the Sent back table: the petty-cash expenses of the period that wait with a send-back comment, on the floats the actor sees, by date: date, manager, vehicle, item, amount, the comment and who sent it back; headline Sent back, figure Entries.
-- Callers: reports.build.
-- Reads: what reports.pettycash_entries reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.pettycash_sent_back(
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
  v_entries numeric;
BEGIN
  SELECT coalesce(
           jsonb_agg(
             jsonb_build_array(
               e.entry_date, e.holder_name, e.registration, e.item_name, e.total,
               e.sent_back_note, e.reviewed_by_name
             )
             ORDER BY e.entry_date, e.id),
           '[]'::jsonb
         ),
         coalesce(sum(e.total), 0),
         count(*)
  INTO v_rows, v_amount, v_entries
  FROM reports.pettycash_entries(p_holder_ids, p_view_all, p_vehicles) AS e
  WHERE e.kind = 2
    AND e.status = 1
    AND e.sent_back_note IS NOT NULL
    AND e.entry_date BETWEEN p_from AND p_to;

  RETURN reports.build_table(
    'pettycash',
    'sentBack',
    'Sent back',
    p_from,
    p_to,
    p_today,
    reports.figure('Sent back', v_amount, 'money'),
    jsonb_build_array(reports.figure('Entries', v_entries, 'count')),
    jsonb_build_array(
      reports.heading('date', 'Date', 'date', false),
      reports.heading('manager', 'Manager', 'text', false),
      reports.heading('vehicle', 'Vehicle', 'vehicle', false),
      reports.heading('item', 'Item', 'text', false),
      reports.heading('amount', 'Amount', 'money', true),
      reports.heading('comment', 'Comment', 'text', false),
      reports.heading('sentBackBy', 'Sent back by', 'text', false)
    ),
    v_rows
  );
END;
$$;

REVOKE ALL ON FUNCTION reports.pettycash_sent_back(date, date, uuid[], boolean, uuid[], date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.pettycash_sent_back(date, date, uuid[], boolean, uuid[], date)
  TO xcode_api_executor;
