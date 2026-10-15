-- reports.page(p_table jsonb, p_q text, p_page integer, p_page_size integer) RETURNS jsonb
-- Purpose: a table cut to one page of the rows matching the search text (reports.matching_rows), with page_number, page_size, total (the matching rows) and totals (reports.totals over every matching row); the headline and figures stay those of the whole report.
-- Callers: api.report_get.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.page(p_table jsonb, p_q text, p_page integer, p_page_size integer)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_rows jsonb := reports.matching_rows(p_table, p_q);
  v_page jsonb;
BEGIN
  SELECT coalesce(jsonb_agg(r.cells ORDER BY r.ord), '[]'::jsonb)
  INTO v_page
  FROM jsonb_array_elements(v_rows) WITH ORDINALITY AS r (cells, ord)
  WHERE r.ord > (p_page - 1) * p_page_size AND r.ord <= p_page * p_page_size;
  RETURN p_table || jsonb_build_object(
    'rows', v_page,
    'page_number', p_page,
    'page_size', p_page_size,
    'total', jsonb_array_length(v_rows),
    'totals', reports.totals(p_table -> 'columns', v_rows)
  );
END;
$$;

REVOKE ALL ON FUNCTION reports.page(jsonb, text, integer, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.page(jsonb, text, integer, integer) TO xcode_api_executor;
