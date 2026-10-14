-- expenses.check_ledger(p_from date, p_to date, p_source text, p_q text) RETURNS text
-- Purpose: the query checks the ledger and its export share, in order: both dates given, the first not after the last, at most 367 days, the source a word of central, pettycash or scheduled in any case (blank is all), the search at most 200 characters once trimmed; answers the source word in lower case, NULL for all.
-- Callers: api.expenses_ledger_get, api.expenses_export_get.
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 expense_period_required, XC422 expense_period_order, XC422 expense_period_length, XC422 expense_source_invalid, XC422 expense_search_length.
-- Tests: tests/db/test_expense_routines.py.

CREATE OR REPLACE FUNCTION expenses.check_ledger(p_from date, p_to date, p_source text, p_q text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_source text := lower(tenancy.trim_text(p_source));
BEGIN
  IF p_from IS NULL OR p_to IS NULL THEN
    PERFORM tenancy.refuse('expense_period_required', 'XC422');
  END IF;
  IF p_from > p_to THEN
    PERFORM tenancy.refuse('expense_period_order', 'XC422');
  END IF;
  IF p_to - p_from > 366 THEN
    PERFORM tenancy.refuse('expense_period_length', 'XC422');
  END IF;
  IF v_source IS NOT NULL AND v_source NOT IN ('central', 'pettycash', 'scheduled') THEN
    PERFORM tenancy.refuse('expense_source_invalid', 'XC422');
  END IF;
  IF char_length(tenancy.trim_text(p_q)) > 200 THEN
    PERFORM tenancy.refuse('expense_search_length', 'XC422');
  END IF;
  RETURN v_source;
END;
$$;

REVOKE ALL ON FUNCTION expenses.check_ledger(date, date, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION expenses.check_ledger(date, date, text, text) TO xcode_api_executor;
