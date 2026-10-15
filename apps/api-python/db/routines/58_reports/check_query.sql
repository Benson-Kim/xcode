-- reports.check_query(p_q text, p_page integer, p_page_size integer) RETURNS text
-- Purpose: the query checks of a report read: the page and page size (tenancy.check_page, skipped only when both are null, as for an export), then the search text at most 200 characters once trimmed; answers the trimmed text, null for none.
-- Callers: api.report_get, api.report_export_get.
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 page_out_of_range via tenancy.check_page, XC422 report_search_length.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.check_query(p_q text, p_page integer, p_page_size integer)
RETURNS text
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_q text := tenancy.trim_text(p_q);
BEGIN
  IF p_page IS NOT NULL OR p_page_size IS NOT NULL THEN
    PERFORM tenancy.check_page(p_page, p_page_size);
  END IF;
  IF char_length(v_q) > 200 THEN
    PERFORM tenancy.refuse('report_search_length', 'XC422');
  END IF;
  RETURN v_q;
END;
$$;

REVOKE ALL ON FUNCTION reports.check_query(text, integer, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.check_query(text, integer, integer) TO xcode_api_executor;
