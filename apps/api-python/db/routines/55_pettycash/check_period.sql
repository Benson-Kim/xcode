-- pettycash.check_period(p_from date, p_to date, p_today date) RETURNS void
-- Purpose: a period asked for with a first and last day: both or neither, the first not after the last, at most 367 days, starting on or before the business date and not more than 3650 days before it; the last day may be after today.
-- Callers: api.pettycash_overview_get, api.pettycash_day_approve.
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 pettycash_range_both, XC422 history_dates_order, XC422 pettycash_range_length, XC422 pettycash_range_start, XC422 pettycash_too_old.
-- Tests: tests/db/test_pettycash_helpers.py.

CREATE OR REPLACE FUNCTION pettycash.check_period(p_from date, p_to date, p_today date)
RETURNS void
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF p_from IS NULL OR p_to IS NULL THEN
    PERFORM tenancy.refuse('pettycash_range_both', 'XC422');
  END IF;
  IF p_from > p_to THEN
    PERFORM tenancy.refuse('history_dates_order', 'XC422');
  END IF;
  IF p_to - p_from + 1 > 367 THEN
    PERFORM tenancy.refuse('pettycash_range_length', 'XC422');
  END IF;
  IF p_from > p_today THEN
    PERFORM tenancy.refuse('pettycash_range_start', 'XC422');
  END IF;
  IF p_from < p_today - 3650 THEN
    PERFORM tenancy.refuse('pettycash_too_old', 'XC422');
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION pettycash.check_period(date, date, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.check_period(date, date, date) TO xcode_api_executor;
