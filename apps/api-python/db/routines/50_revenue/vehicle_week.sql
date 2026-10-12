-- revenue.vehicle_week(p_days revenue.vehicle_day[], p_today date, p_can_capture boolean, p_can_correct boolean, p_earliest date, p_threshold numeric, p_amber_percent numeric) RETURNS jsonb
-- Purpose: a vehicle's row of the week from its seven days, given in day order: the cells, total_amount (the amounts of the days that count), total_expected (the day targets of the days that count), percent (NULL when nothing is expected), gap (total_amount - total_expected, signed), gap_band, and below_threshold_days (days that count whose record holds a reason alone or an amount below p_threshold).
-- Callers: api.revenue_week_get.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_revenue_helpers.py.
-- A day counts when the vehicle is in the fleet and the day is before the business date or has a
-- record: later days and today before capture are not shortfalls, while a missing or no-revenue
-- day counts against the vehicle. A low day is judged by its amount against today's threshold, so
-- a record saved before the rule, or before the threshold moved, counts by the figure itself.
-- plpgsql keeps the plans of the helpers it calls across a grid's rows; a SQL body is executed
-- afresh per row and planned the helpers again each time.

CREATE OR REPLACE FUNCTION revenue.vehicle_week(
  p_days revenue.vehicle_day[],
  p_today date,
  p_can_capture boolean,
  p_can_correct boolean,
  p_earliest date,
  p_threshold numeric,
  p_amber_percent numeric
)
RETURNS jsonb
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_day revenue.vehicle_day;
  v_cells jsonb[] := '{}';
  v_amount numeric := 0;
  v_target numeric := 0;
  v_low integer := 0;
BEGIN
  FOREACH v_day IN ARRAY coalesce(p_days, '{}') LOOP
    v_cells := v_cells || revenue.cell(v_day, p_today, p_can_capture, p_can_correct, p_earliest);
    IF v_day.counted THEN
      v_amount := v_amount + coalesce(v_day.amount, 0);
      v_target := v_target + v_day.target;
      IF v_day.record_id IS NOT NULL AND coalesce(v_day.amount < p_threshold, true) THEN
        v_low := v_low + 1;
      END IF;
    END IF;
  END LOOP;
  RETURN jsonb_build_object(
    'days', to_jsonb(v_cells),
    'total_amount', round(v_amount, 2),
    'total_expected', round(v_target, 2),
    'percent', revenue.percent(v_amount, v_target),
    'gap', round(v_amount - v_target, 2),
    'gap_band', revenue.gap_band(v_amount - v_target, v_target, p_amber_percent),
    'below_threshold_days', v_low
  );
END;
$$;

REVOKE ALL ON FUNCTION revenue.vehicle_week(
  revenue.vehicle_day[], date, boolean, boolean, date, numeric, numeric
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION revenue.vehicle_week(
  revenue.vehicle_day[], date, boolean, boolean, date, numeric, numeric
) TO xcode_api_executor;
