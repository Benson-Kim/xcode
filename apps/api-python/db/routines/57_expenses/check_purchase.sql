-- expenses.check_purchase(p_date date, p_expense_item_id uuid, p_units numeric, p_unit_amount numeric, p_note text, p_allocations jsonb) RETURNS TABLE (vehicle_id uuid, units numeric, unit_amount numeric)
-- Purpose: a purchase for 1 to 50 vehicles checked before any row: the vehicles (an array of 1 to 50 distinct vehicle ids, each with an amount), the line as a petty-cash expense line with the first vehicle, then each vehicle's amount (a JSON number or a decimal string, read exactly from its text: not zero, at most two decimals), its sign and their sum against units x unit amount rounded half away from zero; answers one row per vehicle in the order sent: one vehicle takes the purchase as typed; equal amounts take units / n at the unit amount when that share has at most three decimals and costs exactly the amount; any other split one unit at the vehicle's amount. The note arrives trimmed.
-- Callers: api.expenses_entry_create, api.pettycash_entry_create.
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 expense_vehicles_invalid, XC422 pettycash_line_date_required via pettycash.check_line, XC422 pettycash_line_amount_zero via pettycash.check_line, XC422 pettycash_line_amount_decimals via pettycash.check_line, XC422 pettycash_line_units via pettycash.check_line, XC422 pettycash_line_total_zero via pettycash.check_line, XC422 pettycash_line_total_large via pettycash.check_line, XC422 pettycash_line_note_length via pettycash.check_line, XC422 pettycash_line_item_required via pettycash.check_line, XC422 expense_allocation_amount, XC422 expense_allocation_sign, XC422 expense_allocation_sum.
-- Tests: tests/db/test_expense_routines.py, tests/db/test_pettycash_routines.py.

CREATE OR REPLACE FUNCTION expenses.check_purchase(
  p_date date,
  p_expense_item_id uuid,
  p_units numeric,
  p_unit_amount numeric,
  p_note text,
  p_allocations jsonb
)
RETURNS TABLE (vehicle_id uuid, units numeric, unit_amount numeric)
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  c_uuid CONSTANT text := '^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$';
  c_none CONSTANT uuid := '00000000-0000-0000-0000-000000000000';
  v_count integer;
  v_vehicles uuid[];
  v_amounts numeric[];
  v_total numeric;
  v_share numeric;
BEGIN
  IF jsonb_typeof(p_allocations) IS DISTINCT FROM 'array'
     OR jsonb_array_length(p_allocations) NOT BETWEEN 1 AND 50
     OR EXISTS (
       SELECT 1
       FROM jsonb_array_elements(p_allocations) AS a (item)
       WHERE jsonb_typeof(a.item) IS DISTINCT FROM 'object'
          OR jsonb_typeof(a.item -> 'vehicle_id') IS DISTINCT FROM 'string'
          OR CASE
               WHEN (a.item ->> 'vehicle_id') ~ c_uuid THEN (a.item ->> 'vehicle_id')::uuid = c_none
               ELSE true
             END
     ) THEN
    PERFORM tenancy.refuse('expense_vehicles_invalid', 'XC422');
  END IF;
  SELECT array_agg((a.item ->> 'vehicle_id')::uuid ORDER BY a.position),
         count(DISTINCT (a.item ->> 'vehicle_id')::uuid)
  INTO v_vehicles, v_count
  FROM jsonb_array_elements(p_allocations) WITH ORDINALITY AS a (item, position);
  IF v_count <> cardinality(v_vehicles) THEN
    PERFORM tenancy.refuse('expense_vehicles_invalid', 'XC422');
  END IF;

  PERFORM pettycash.check_line(
    2::smallint, p_date, p_unit_amount, p_units, v_vehicles[1], p_expense_item_id, NULL, p_note, false
  );

  IF EXISTS (
    SELECT 1
    FROM jsonb_array_elements(p_allocations) AS a (item)
    WHERE CASE
            WHEN jsonb_typeof(a.item -> 'amount') IN ('number', 'string')
                 AND (a.item ->> 'amount') ~ '^-?[0-9]+(\.[0-9]+)?$' THEN
              (a.item ->> 'amount')::numeric = 0
              OR (a.item ->> 'amount')::numeric <> round((a.item ->> 'amount')::numeric, 2)
            ELSE true
          END
  ) THEN
    PERFORM tenancy.refuse('expense_allocation_amount', 'XC422');
  END IF;
  SELECT array_agg((a.item ->> 'amount')::numeric ORDER BY a.position)
  INTO v_amounts
  FROM jsonb_array_elements(p_allocations) WITH ORDINALITY AS a (item, position);
  v_total := round(p_units * p_unit_amount, 2);
  IF EXISTS (SELECT 1 FROM unnest(v_amounts) AS m (amount) WHERE sign(m.amount) <> sign(v_total)) THEN
    PERFORM tenancy.refuse('expense_allocation_sign', 'XC422');
  END IF;
  IF (SELECT sum(m.amount) FROM unnest(v_amounts) AS m (amount)) <> v_total THEN
    PERFORM tenancy.refuse('expense_allocation_sum', 'XC422');
  END IF;

  IF cardinality(v_vehicles) = 1 THEN
    RETURN QUERY SELECT v_vehicles[1], p_units, p_unit_amount;
    RETURN;
  END IF;
  v_share := p_units / cardinality(v_vehicles);
  IF (SELECT count(DISTINCT m.amount) FROM unnest(v_amounts) AS m (amount)) = 1
     AND v_share = round(v_share, 3)
     AND round(round(v_share, 3) * p_unit_amount, 2) = v_amounts[1] THEN
    RETURN QUERY
    SELECT s.vehicle, round(v_share, 3), p_unit_amount
    FROM unnest(v_vehicles) WITH ORDINALITY AS s (vehicle, position)
    ORDER BY s.position;
    RETURN;
  END IF;
  RETURN QUERY
  SELECT s.vehicle, 1::numeric, s.amount
  FROM unnest(v_vehicles, v_amounts) WITH ORDINALITY AS s (vehicle, amount, position)
  ORDER BY s.position;
END;
$$;

REVOKE ALL ON FUNCTION expenses.check_purchase(date, uuid, numeric, numeric, text, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION expenses.check_purchase(date, uuid, numeric, numeric, text, jsonb) TO xcode_api_executor;
