-- reports.pettycash_vehicles(p_from date, p_to date, p_holder_ids uuid[], p_view_all boolean, p_vehicles uuid[], p_today date) RETURNS jsonb
-- Purpose: the By vehicle table: the petty-cash expenses not rejected in the period, on the floats the actor sees, grouped by vehicle, by amount then registration: vehicle, company (only for a vehicle in the actor's scope), entries, waiting (not sent back), approved and amount; headline Expenses, figures Vehicles and Waiting.
-- Callers: reports.build.
-- Reads: what reports.pettycash_entries reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.pettycash_vehicles(
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
  v_vehicles numeric;
  v_waiting numeric;
BEGIN
  WITH lines AS (
    SELECT e.vehicle_id,
           min(e.registration) AS registration,
           min(e.company_name) AS company_name,
           count(*) AS entries,
           coalesce(sum(e.total) FILTER (WHERE e.status = 1 AND e.sent_back_note IS NULL), 0)
             AS waiting,
           coalesce(sum(e.total) FILTER (WHERE e.status = 2), 0) AS approved,
           sum(e.total) AS amount
    FROM reports.pettycash_entries(p_holder_ids, p_view_all, p_vehicles) AS e
    WHERE e.kind = 2 AND e.status <> 4 AND e.entry_date BETWEEN p_from AND p_to
    GROUP BY e.vehicle_id
  )
  SELECT coalesce(
           jsonb_agg(
             jsonb_build_array(
               l.registration, l.company_name, l.entries, l.waiting, l.approved, l.amount
             )
             ORDER BY l.amount DESC, l.registration COLLATE "C", l.vehicle_id),
           '[]'::jsonb
         ),
         coalesce(sum(l.amount), 0),
         count(*),
         coalesce(sum(l.waiting), 0)
  INTO v_rows, v_amount, v_vehicles, v_waiting
  FROM lines AS l;

  RETURN reports.build_table(
    'pettycash',
    'vehicles',
    'By vehicle',
    p_from,
    p_to,
    p_today,
    reports.figure('Expenses', v_amount, 'money'),
    jsonb_build_array(
      reports.figure('Vehicles', v_vehicles, 'count'),
      reports.figure('Waiting', v_waiting, 'money')
    ),
    jsonb_build_array(
      reports.heading('vehicle', 'Vehicle', 'vehicle', false),
      reports.heading('company', 'Company', 'text', false),
      reports.heading('entries', 'Entries', 'count', true),
      reports.heading('waiting', 'Waiting', 'money', true),
      reports.heading('approved', 'Approved', 'money', true),
      reports.heading('amount', 'Amount', 'money', true)
    ),
    v_rows
  );
END;
$$;

REVOKE ALL ON FUNCTION reports.pettycash_vehicles(date, date, uuid[], boolean, uuid[], date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.pettycash_vehicles(date, date, uuid[], boolean, uuid[], date)
  TO xcode_api_executor;
