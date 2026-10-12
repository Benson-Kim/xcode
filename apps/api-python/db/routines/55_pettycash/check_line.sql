-- pettycash.check_line(p_kind smallint, p_date date, p_unit_amount numeric, p_units numeric, p_vehicle_id uuid, p_expense_item_id uuid, p_payee text, p_note text, p_reimbursable boolean) RETURNS void
-- Purpose: the line checks of an entry, in order: kind, date, amount, decimals, units, units only on an expense, total not zero, total not too large, note length, then the kind's shape (an expense needs a vehicle and an item and has no payee; a credit note has no vehicle and a payee of at most 80 characters; cash has only an amount, a date and a note). Payee and note arrive trimmed, blank as NULL; the empty uuid counts as none.
-- Callers: api.pettycash_entry_create, api.pettycash_entry_update.
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 pettycash_kind_invalid, XC422 pettycash_line_date_required, XC422 pettycash_line_amount_zero, XC422 pettycash_line_amount_decimals, XC422 pettycash_line_units, XC422 pettycash_line_units_only_expense, XC422 pettycash_line_total_zero, XC422 pettycash_line_total_large, XC422 pettycash_line_note_length, XC422 pettycash_line_vehicle_required, XC422 pettycash_line_item_required, XC422 pettycash_line_expense_payee, XC422 pettycash_line_credit_vehicle, XC422 pettycash_line_payee_length, XC422 pettycash_line_cash_shape.
-- Tests: tests/db/test_pettycash_helpers.py, tests/db/test_pettycash_routines.py.

CREATE OR REPLACE FUNCTION pettycash.check_line(
  p_kind smallint,
  p_date date,
  p_unit_amount numeric,
  p_units numeric,
  p_vehicle_id uuid,
  p_expense_item_id uuid,
  p_payee text,
  p_note text,
  p_reimbursable boolean
)
RETURNS void
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  c_none CONSTANT uuid := '00000000-0000-0000-0000-000000000000';
  c_largest CONSTANT numeric := 999999999999.99;
  v_vehicle uuid := nullif(p_vehicle_id, c_none);
  v_item uuid := nullif(p_expense_item_id, c_none);
  v_total numeric;
BEGIN
  IF p_kind IS NULL OR p_kind NOT IN (1, 2, 3) THEN
    PERFORM tenancy.refuse('pettycash_kind_invalid', 'XC422');
  END IF;
  IF p_date IS NULL OR p_date = date '0001-01-01' THEN
    PERFORM tenancy.refuse('pettycash_line_date_required', 'XC422');
  END IF;
  IF p_unit_amount IS NULL OR p_unit_amount = 0 THEN
    PERFORM tenancy.refuse('pettycash_line_amount_zero', 'XC422');
  END IF;
  IF p_unit_amount <> round(p_unit_amount, 2) OR abs(p_unit_amount) > c_largest THEN
    PERFORM tenancy.refuse('pettycash_line_amount_decimals', 'XC422');
  END IF;
  IF p_units IS NULL OR p_units <= 0 OR p_units > 999999999.999 OR p_units <> round(p_units, 3) THEN
    PERFORM tenancy.refuse('pettycash_line_units', 'XC422');
  END IF;
  IF p_kind <> 2 AND p_units <> 1 THEN
    PERFORM tenancy.refuse('pettycash_line_units_only_expense', 'XC422');
  END IF;
  v_total := round(p_units * p_unit_amount, 2);
  IF v_total = 0 THEN
    PERFORM tenancy.refuse('pettycash_line_total_zero', 'XC422');
  END IF;
  IF abs(v_total) > c_largest THEN
    PERFORM tenancy.refuse('pettycash_line_total_large', 'XC422');
  END IF;
  IF char_length(p_note) > 80 THEN
    PERFORM tenancy.refuse('pettycash_line_note_length', 'XC422');
  END IF;
  IF p_kind = 2 THEN
    IF v_vehicle IS NULL THEN
      PERFORM tenancy.refuse('pettycash_line_vehicle_required', 'XC422');
    END IF;
    IF v_item IS NULL THEN
      PERFORM tenancy.refuse('pettycash_line_item_required', 'XC422');
    END IF;
    IF p_payee IS NOT NULL OR p_reimbursable THEN
      PERFORM tenancy.refuse('pettycash_line_expense_payee', 'XC422');
    END IF;
  ELSIF p_kind = 3 THEN
    IF v_vehicle IS NOT NULL OR v_item IS NOT NULL THEN
      PERFORM tenancy.refuse('pettycash_line_credit_vehicle', 'XC422');
    END IF;
    IF char_length(p_payee) > 80 THEN
      PERFORM tenancy.refuse('pettycash_line_payee_length', 'XC422');
    END IF;
  ELSIF v_vehicle IS NOT NULL OR v_item IS NOT NULL OR p_payee IS NOT NULL OR p_reimbursable THEN
    PERFORM tenancy.refuse('pettycash_line_cash_shape', 'XC422');
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION pettycash.check_line(smallint, date, numeric, numeric, uuid, uuid, text, text, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.check_line(smallint, date, numeric, numeric, uuid, uuid, text, text, boolean) TO xcode_api_executor;
