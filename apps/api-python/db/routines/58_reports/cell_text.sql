-- reports.cell_text(p_cell jsonb, p_kind text) RETURNS text
-- Purpose: what a cell shows, for the search: a text as is; a date as yyyy-MM-dd and as d Mon yyyy; a number as written (no trailing zeros) and with thousands separators (#,##0, or #,##0.00 when it has cents); null for a null cell.
-- Callers: reports.row_matches.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.cell_text(p_cell jsonb, p_kind text)
RETURNS text
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_text text;
BEGIN
  IF p_cell IS NULL OR jsonb_typeof(p_cell) = 'null' THEN
    RETURN NULL;
  END IF;
  v_text := p_cell #>> '{}';
  IF jsonb_typeof(p_cell) = 'number' THEN
    RETURN CASE
             WHEN position('.' IN v_text) > 0 THEN rtrim(rtrim(v_text, '0'), '.')
             ELSE v_text
           END || ' ' || tenancy.fmt_money(v_text::numeric);
  END IF;
  IF p_kind = 'date' THEN
    RETURN v_text || ' ' || tenancy.fmt_day(v_text::date);
  END IF;
  RETURN v_text;
END;
$$;

REVOKE ALL ON FUNCTION reports.cell_text(jsonb, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.cell_text(jsonb, text) TO xcode_api_executor;
