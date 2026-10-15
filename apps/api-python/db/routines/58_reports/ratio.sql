-- reports.ratio(p_part numeric, p_whole numeric) RETURNS numeric
-- Purpose: what a part is of a whole as a percentage with one decimal, rounded half away from zero (a report's reached, recovered and share figures); null when the whole is null or zero.
-- Callers: reports.fleet_target, reports.fleet_money_out, reports.fleet_investment.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.ratio(p_part numeric, p_whole numeric)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
           WHEN p_whole IS NULL OR p_whole = 0 THEN NULL
           ELSE round(coalesce(p_part, 0) * 100 / p_whole, 1)
         END;
$$;

REVOKE ALL ON FUNCTION reports.ratio(numeric, numeric) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.ratio(numeric, numeric) TO xcode_api_executor;
