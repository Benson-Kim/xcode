-- reports.row_matches(p_columns jsonb, p_row jsonb, p_words text[]) RETURNS boolean
-- Purpose: whether every word (lower case) appears in what the row's cells show (reports.cell_text, joined), ignoring case; true for no words.
-- Callers: reports.matching_rows.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.row_matches(p_columns jsonb, p_row jsonb, p_words text[])
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT coalesce(bool_and(position(w.word IN t.shown) > 0), true)
  FROM (
    SELECT lower(coalesce(
             string_agg(reports.cell_text(c.cell, col.heading ->> 'kind'), ' | ' ORDER BY c.ord),
             ''
           )) AS shown
    FROM jsonb_array_elements(p_row) WITH ORDINALITY AS c (cell, ord)
    LEFT JOIN jsonb_array_elements(p_columns) WITH ORDINALITY AS col (heading, ord)
      ON col.ord = c.ord
  ) AS t
  CROSS JOIN unnest(p_words) AS w (word);
$$;

REVOKE ALL ON FUNCTION reports.row_matches(jsonb, jsonb, text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.row_matches(jsonb, jsonb, text[]) TO xcode_api_executor;
