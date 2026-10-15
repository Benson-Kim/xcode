-- reports.pettycash_rejected(p_from date, p_to date, p_holder_ids uuid[], p_view_all boolean, p_vehicles uuid[], p_today date) RETURNS jsonb
-- Purpose: the Rejected and reopened table: the petty-cash expenses of the period that are rejected, or were reopened, on the floats the actor sees, by date: date, manager, vehicle, item, amount, the status word (Rejected, Reopened), the reason and who decided; headline Rejected (the rejected amounts), figures Rejected and Reopened (counts).
-- Callers: reports.build.
-- Reads: what reports.pettycash_entries reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.pettycash_rejected(
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
  v_rejected numeric;
  v_reopened numeric;
BEGIN
  SELECT coalesce(
           jsonb_agg(
             jsonb_build_array(
               e.entry_date, e.holder_name, e.registration, e.item_name, e.total,
               CASE WHEN e.status = 4 THEN 'Rejected' ELSE 'Reopened' END,
               CASE WHEN e.status = 4 THEN e.reject_reason ELSE e.reopen_reason END,
               e.reviewed_by_name
             )
             ORDER BY e.entry_date, e.id),
           '[]'::jsonb
         ),
         coalesce(sum(e.total) FILTER (WHERE e.status = 4), 0),
         count(*) FILTER (WHERE e.status = 4),
         count(*) FILTER (WHERE e.status <> 4)
  INTO v_rows, v_amount, v_rejected, v_reopened
  FROM reports.pettycash_entries(p_holder_ids, p_view_all, p_vehicles) AS e
  WHERE e.kind = 2
    AND (e.status = 4 OR e.reopen_reason IS NOT NULL)
    AND e.entry_date BETWEEN p_from AND p_to;

  RETURN reports.build_table(
    'pettycash',
    'rejected',
    'Rejected and reopened',
    p_from,
    p_to,
    p_today,
    reports.figure('Rejected', v_amount, 'money'),
    jsonb_build_array(
      reports.figure('Rejected', v_rejected, 'count'),
      reports.figure('Reopened', v_reopened, 'count')
    ),
    jsonb_build_array(
      reports.heading('date', 'Date', 'date', false),
      reports.heading('manager', 'Manager', 'text', false),
      reports.heading('vehicle', 'Vehicle', 'vehicle', false),
      reports.heading('item', 'Item', 'text', false),
      reports.heading('amount', 'Amount', 'money', true),
      reports.heading('status', 'Status', 'text', false),
      reports.heading('reason', 'Reason', 'text', false),
      reports.heading('decidedBy', 'Decided by', 'text', false)
    ),
    v_rows
  );
END;
$$;

REVOKE ALL ON FUNCTION reports.pettycash_rejected(date, date, uuid[], boolean, uuid[], date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.pettycash_rejected(date, date, uuid[], boolean, uuid[], date)
  TO xcode_api_executor;
