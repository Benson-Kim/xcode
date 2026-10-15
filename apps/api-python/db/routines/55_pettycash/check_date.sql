-- pettycash.check_date(p_date date, p_today date) RETURNS void
-- Purpose: the date window of an entry and of the day reads: not after the business date, not more than 3650 days before it.
-- Callers: api.pettycash_entry_create, api.pettycash_entry_update, api.pettycash_overview_get, api.pettycash_options_get, api.pettycash_day_approve.
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 pettycash_future_date, XC422 pettycash_too_old.
-- Tests: tests/db/test_pettycash_helpers.py.

CREATE OR REPLACE FUNCTION pettycash.check_date(p_date date, p_today date)
RETURNS void
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF p_date > p_today THEN
    PERFORM tenancy.refuse('pettycash_future_date', 'XC422');
  END IF;
  IF p_date < p_today - 3650 THEN
    PERFORM tenancy.refuse('pettycash_too_old', 'XC422');
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION pettycash.check_date(date, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.check_date(date, date) TO xcode_api_executor;
