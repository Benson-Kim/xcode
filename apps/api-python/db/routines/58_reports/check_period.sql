-- reports.check_period(p_from date, p_to date, p_today date) RETURNS daterange
-- Purpose: the period of a dated report, in check order: both days given, the first not after the last, at most 367 days counted inclusive, the first on or before the business date; answers the days covered with the last cut to the business date.
-- Callers: reports.build.
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 report_period_both, XC422 report_period_order, XC422 report_period_length, XC422 report_period_future.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.check_period(p_from date, p_to date, p_today date)
RETURNS daterange
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF p_from IS NULL OR p_to IS NULL THEN
    PERFORM tenancy.refuse('report_period_both', 'XC422');
  END IF;
  IF p_from > p_to THEN
    PERFORM tenancy.refuse('report_period_order', 'XC422');
  END IF;
  IF p_to - p_from + 1 > 367 THEN
    PERFORM tenancy.refuse('report_period_length', 'XC422');
  END IF;
  IF p_from > p_today THEN
    PERFORM tenancy.refuse('report_period_future', 'XC422');
  END IF;
  RETURN daterange(p_from, least(p_to, p_today), '[]');
END;
$$;

REVOKE ALL ON FUNCTION reports.check_period(date, date, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.check_period(date, date, date) TO xcode_api_executor;
