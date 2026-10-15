-- reports.build_table(p_group text, p_report text, p_title text, p_from date, p_to date, p_today date, p_headline jsonb, p_figures jsonb, p_columns jsonb, p_rows jsonb) RETURNS jsonb
-- Purpose: the whole table of a report before search and paging: {group, report, title, from_date, to_date, business_date, headline, figures, columns, rows}; from_date and to_date are null for an undated report.
-- Callers: the report builders, api.revenue_export_get, api.expenses_export_get, api.pettycash_export_get.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.build_table(
  p_group text,
  p_report text,
  p_title text,
  p_from date,
  p_to date,
  p_today date,
  p_headline jsonb,
  p_figures jsonb,
  p_columns jsonb,
  p_rows jsonb
)
RETURNS jsonb
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT jsonb_build_object(
           'group', p_group,
           'report', p_report,
           'title', p_title,
           'from_date', p_from,
           'to_date', p_to,
           'business_date', p_today,
           'headline', p_headline,
           'figures', coalesce(p_figures, '[]'::jsonb),
           'columns', p_columns,
           'rows', coalesce(p_rows, '[]'::jsonb)
         );
$$;

REVOKE ALL ON FUNCTION reports.build_table(text, text, text, date, date, date, jsonb, jsonb, jsonb, jsonb)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.build_table(text, text, text, date, date, date, jsonb, jsonb, jsonb, jsonb)
  TO xcode_api_executor;
