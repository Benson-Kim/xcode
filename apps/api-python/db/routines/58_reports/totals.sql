-- reports.totals(p_columns jsonb, p_rows jsonb) RETURNS jsonb
-- Purpose: the footer of a table: for each column that sums, the sum of its numeric cells over the rows (0 when none), null for every other column; one element per column.
-- Callers: reports.page, reports.document.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.totals(p_columns jsonb, p_rows jsonb)
RETURNS jsonb
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT coalesce(
    jsonb_agg(
      CASE
        WHEN (c.heading ->> 'sum')::boolean THEN to_jsonb(coalesce(
          (
            SELECT sum((r.cells -> (c.ord - 1)::integer)::numeric)
            FROM jsonb_array_elements(coalesce(p_rows, '[]'::jsonb)) AS r (cells)
            WHERE jsonb_typeof(r.cells -> (c.ord - 1)::integer) = 'number'
          ),
          0
        ))
        ELSE 'null'::jsonb
      END
      ORDER BY c.ord
    ),
    '[]'::jsonb
  )
  FROM jsonb_array_elements(p_columns) WITH ORDINALITY AS c (heading, ord);
$$;

REVOKE ALL ON FUNCTION reports.totals(jsonb, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.totals(jsonb, jsonb) TO xcode_api_executor;
