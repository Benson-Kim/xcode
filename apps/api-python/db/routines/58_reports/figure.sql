-- reports.figure(p_label text, p_value numeric, p_kind text) RETURNS jsonb
-- Purpose: one headline or figure of a report table, {label, value, kind}; a null value reads as 0.
-- Callers: the report builders, api.revenue_export_get, api.expenses_export_get, api.pettycash_export_get.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.figure(p_label text, p_value numeric, p_kind text)
RETURNS jsonb
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT jsonb_build_object('label', p_label, 'value', coalesce(p_value, 0), 'kind', p_kind);
$$;

REVOKE ALL ON FUNCTION reports.figure(text, numeric, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.figure(text, numeric, text) TO xcode_api_executor;
