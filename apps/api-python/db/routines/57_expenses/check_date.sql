-- expenses.check_date(p_date date, p_today date) RETURNS void
-- Purpose: a central expense's date against the business date: not after it, and not more than 3 650 days before it.
-- Callers: api.expenses_entry_create, api.expenses_entry_update, api.expenses_options_get.
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 expense_date_future, XC422 expense_date_too_old.
-- Tests: tests/db/test_expense_routines.py.

CREATE OR REPLACE FUNCTION expenses.check_date(p_date date, p_today date)
RETURNS void
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF p_date > p_today THEN
    PERFORM tenancy.refuse('expense_date_future', 'XC422');
  END IF;
  IF p_date < p_today - 3650 THEN
    PERFORM tenancy.refuse('expense_date_too_old', 'XC422');
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION expenses.check_date(date, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION expenses.check_date(date, date) TO xcode_api_executor;
