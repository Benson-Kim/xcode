-- reports.pettycash_waiting(p_holder_ids uuid[], p_view_all boolean, p_vehicles uuid[], p_today date) RETURNS jsonb
-- Purpose: the undated Waiting for approval table: every petty-cash expense still waiting (not sent back) up to the business date on the floats the actor sees, oldest first: date, manager, vehicle, item, amount, days waiting and who recorded it; headline Waiting, figure Entries.
-- Callers: reports.build.
-- Reads: what reports.pettycash_entries reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.pettycash_waiting(
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
               p_today - e.entry_date, e.recorded_by_name
             )
             ORDER BY e.entry_date, e.id),
           '[]'::jsonb
         ),
         coalesce(sum(e.total), 0),
         count(*)
  INTO v_rows, v_amount, v_entries
  FROM reports.pettycash_entries(p_holder_ids, p_view_all, p_vehicles) AS e
  WHERE e.kind = 2 AND e.status = 1 AND e.sent_back_note IS NULL AND e.entry_date <= p_today;

  RETURN reports.build_table(
    'pettycash',
    'waiting',
    'Waiting for approval',
    NULL,
    NULL,
    p_today,
    reports.figure('Waiting', v_amount, 'money'),
    jsonb_build_array(reports.figure('Entries', v_entries, 'count')),
    jsonb_build_array(
      reports.heading('date', 'Date', 'date', false),
      reports.heading('manager', 'Manager', 'text', false),
      reports.heading('vehicle', 'Vehicle', 'vehicle', false),
      reports.heading('item', 'Item', 'text', false),
      reports.heading('amount', 'Amount', 'money', true),
      reports.heading('daysWaiting', 'Days waiting', 'count', false),
      reports.heading('recordedBy', 'Recorded by', 'text', false)
    ),
    v_rows
  );
END;
$$;

REVOKE ALL ON FUNCTION reports.pettycash_waiting(uuid[], boolean, uuid[], date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.pettycash_waiting(uuid[], boolean, uuid[], date) TO xcode_api_executor;
