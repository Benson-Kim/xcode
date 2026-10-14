-- reports.matching_rows(p_table jsonb, p_q text) RETURNS jsonb
-- Purpose: the rows of a table that hold every word of the search text (split on white space, ignoring case, matched against what the cells show), in the table's order and unpaged; every row for no search text.
-- Callers: reports.page, api.report_export_get.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.matching_rows(p_table jsonb, p_q text)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_q text := tenancy.trim_text(p_q);
  v_words text[];
  v_rows jsonb;
BEGIN
  IF v_q IS NULL THEN
    RETURN coalesce(p_table -> 'rows', '[]'::jsonb);
  END IF;
  v_words := regexp_split_to_array(lower(v_q), '\s+');
  SELECT coalesce(jsonb_agg(r.cells ORDER BY r.ord), '[]'::jsonb)
  INTO v_rows
  FROM jsonb_array_elements(p_table -> 'rows') WITH ORDINALITY AS r (cells, ord)
  WHERE reports.row_matches(p_table -> 'columns', r.cells, v_words);
  RETURN v_rows;
END;
$$;

REVOKE ALL ON FUNCTION reports.matching_rows(jsonb, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.matching_rows(jsonb, text) TO xcode_api_executor;
