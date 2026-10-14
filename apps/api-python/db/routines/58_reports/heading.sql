-- reports.heading(p_key text, p_label text, p_kind text, p_sum boolean) RETURNS jsonb
-- Purpose: one column of a report table, {key, label, kind, sum}: the kind tells a client how to render the cells, sum whether the footer adds the column up.
-- Callers: the report builders, api.revenue_export_get, api.expenses_export_get, api.pettycash_export_get.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.heading(p_key text, p_label text, p_kind text, p_sum boolean)
RETURNS jsonb
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT jsonb_build_object('key', p_key, 'label', p_label, 'kind', p_kind, 'sum', p_sum);
$$;

REVOKE ALL ON FUNCTION reports.heading(text, text, text, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.heading(text, text, text, boolean) TO xcode_api_executor;
