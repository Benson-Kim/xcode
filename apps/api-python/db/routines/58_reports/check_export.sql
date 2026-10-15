-- reports.check_export(p_format text, p_row_count integer) RETURNS text
-- Purpose: the checks every export shares: the format (null, blank or xlsx is Excel, pdf is PDF, in any case; anything else refused) and, when a row count is given, at most 10,000 rows (the count in the refusal with thousands separators); answers xlsx or pdf.
-- Callers: api.report_export_get, api.revenue_export_get, api.expenses_export_get, api.pettycash_export_get.
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 export_format_invalid, XC422 export_too_many_rows.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.check_export(p_format text, p_row_count integer)
RETURNS text
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_format text := coalesce(lower(tenancy.trim_text(p_format)), 'xlsx');
BEGIN
  IF v_format NOT IN ('xlsx', 'pdf') THEN
    PERFORM tenancy.refuse('export_format_invalid', 'XC422');
  END IF;
  IF p_row_count > 10000 THEN
    PERFORM tenancy.refuse(
      'export_too_many_rows',
      'XC422',
      jsonb_build_object('count', to_char(p_row_count, 'FM999,999,999,990'))
    );
  END IF;
  RETURN v_format;
END;
$$;

REVOKE ALL ON FUNCTION reports.check_export(text, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.check_export(text, integer) TO xcode_api_executor;
