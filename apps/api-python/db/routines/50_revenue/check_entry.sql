-- revenue.check_entry(p_amount numeric, p_reason text, p_note text, OUT amount numeric, OUT reason smallint, OUT note text) RETURNS record
-- Purpose: the shape of a revenue entry, the first step of every capture: the reason a known no-earnings label, an amount of 0 with a reason is the reason alone, the amount positive with at most two decimals, an amount or a reason required, the note at most 80 characters and only with the reason Other; answers the entry as stored (amount, reason code, trimmed note).
-- Callers: revenue.capture_entry, api.revenue_day_save.
-- Reads: what revenue.reason_code reads. Writes: nothing.
-- Raises: XC422 revenue_reason_invalid, XC422 money_invalid via tenancy.check_money, XC422 revenue_entry_required, XC422 revenue_note_length, XC422 revenue_note_without_other.
-- Tests: tests/db/test_revenue_routines.py, tests/db/test_revenue_day_routines.py.

CREATE OR REPLACE FUNCTION revenue.check_entry(
  p_amount numeric,
  p_reason text,
  p_note text,
  OUT amount numeric,
  OUT reason smallint,
  OUT note text
)
RETURNS record
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  c_other CONSTANT smallint := 4;
  v_reason_text text := tenancy.trim_text(p_reason);
BEGIN
  amount := p_amount;
  note := tenancy.trim_text(p_note);
  IF v_reason_text IS NOT NULL THEN
    reason := revenue.reason_code(v_reason_text);
    IF reason IS NULL THEN
      PERFORM tenancy.refuse('revenue_reason_invalid', 'XC422');
    END IF;
  END IF;
  IF p_amount = 0 AND reason IS NOT NULL THEN
    amount := NULL;
  END IF;
  IF amount IS NOT NULL THEN
    PERFORM tenancy.check_money(amount);
  END IF;
  IF amount IS NULL AND reason IS NULL THEN
    PERFORM tenancy.refuse('revenue_entry_required', 'XC422');
  END IF;
  IF char_length(note) > 80 THEN
    PERFORM tenancy.refuse('revenue_note_length', 'XC422');
  END IF;
  IF note IS NOT NULL AND reason IS DISTINCT FROM c_other THEN
    PERFORM tenancy.refuse('revenue_note_without_other', 'XC422');
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION revenue.check_entry(numeric, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION revenue.check_entry(numeric, text, text) TO xcode_api_executor;
