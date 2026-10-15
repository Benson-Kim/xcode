-- revenue.cell(p_day revenue.vehicle_day, p_today date, p_can_capture boolean, p_can_correct boolean, p_earliest date) RETURNS jsonb
-- Purpose: one RevenueCellDto: status none (not in the fleet), future (after the business date), missing (no record), amount (an amount, with a reason on a low day) or reason (a reason alone); expected = the day target; the record's amount, reason label, note, edited-after-capture flag and version; can_edit = capture for a missing day and correct for a recorded one, each only on or after p_earliest (the viewer's earliest writable date, NULL for any date), never for none or future.
-- Callers: revenue.vehicle_week (the week grid) and api.revenue_capture (the current cell of a conflict), so both answer the same cell.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_revenue_helpers.py.
-- Days are captured in any order, so a missing day is open to anyone who may capture.

CREATE OR REPLACE FUNCTION revenue.cell(
  p_day revenue.vehicle_day,
  p_today date,
  p_can_capture boolean,
  p_can_correct boolean,
  p_earliest date
)
RETURNS jsonb
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_status text;
BEGIN
  v_status := CASE
    WHEN NOT coalesce(p_day.active, false) THEN 'none'
    WHEN p_day.day > p_today THEN 'future'
    WHEN p_day.record_id IS NULL THEN 'missing'
    WHEN p_day.amount IS NOT NULL THEN 'amount'
    ELSE 'reason'
  END;
  RETURN jsonb_build_object(
    'day', p_day.day,
    'status', v_status,
    'expected', round(coalesce(p_day.target, 0), 2),
    'amount', p_day.amount,
    'reason', p_day.reason_label,
    'note', p_day.note,
    'can_edit', (p_earliest IS NULL OR p_day.day >= p_earliest)
                AND CASE v_status
                      WHEN 'missing' THEN p_can_capture
                      WHEN 'amount' THEN p_can_correct
                      WHEN 'reason' THEN p_can_correct
                      ELSE false
                    END,
    'edited_after_capture', coalesce(p_day.corrected_after_date, false),
    'version', p_day.version
  );
END;
$$;

REVOKE ALL ON FUNCTION revenue.cell(revenue.vehicle_day, date, boolean, boolean, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION revenue.cell(revenue.vehicle_day, date, boolean, boolean, date)
  TO xcode_api_executor;
