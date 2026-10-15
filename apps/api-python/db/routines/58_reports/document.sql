-- reports.document(p_table jsonb, p_rows jsonb, p_filters text, p_format text, p_now timestamptz) RETURNS jsonb
-- Purpose: what a file needs, from a table and the rows the export keeps: the table with those rows, their count as total and their footer as totals, plus organization (the branding display name, else XCODE), period (d Mon yyyy, "{from} to {to}", or null for an undated report), filters, exported_by (the actor's name), exported_on, currency, file_name ("{title}[ {period}].{xlsx|pdf}") and content_type.
-- Callers: api.report_export_get, api.revenue_export_get, api.expenses_export_get, api.pettycash_export_get.
-- Reads: tenancy.memberships, and what tenancy.settings_document reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.document(
  p_table jsonb,
  p_rows jsonb,
  p_filters text,
  p_format text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_from date := (p_table ->> 'from_date')::date;
  v_to date := (p_table ->> 'to_date')::date;
  v_period text;
  v_actor text;
BEGIN
  v_period := CASE
                WHEN v_from IS NULL THEN NULL
                WHEN v_from = v_to THEN tenancy.fmt_day(v_from)
                ELSE tenancy.fmt_day(v_from) || ' to ' || tenancy.fmt_day(v_to)
              END;
  SELECT btrim(m.first_name || ' ' || m.last_name)
  INTO v_actor
  FROM tenancy.memberships AS m
  WHERE m.organization_id = tenancy.current_organization() AND m.user_id = tenancy.current_actor();
  RETURN p_table || jsonb_build_object(
    'rows', coalesce(p_rows, '[]'::jsonb),
    'total', jsonb_array_length(coalesce(p_rows, '[]'::jsonb)),
    'totals', reports.totals(p_table -> 'columns', p_rows),
    'organization', coalesce(tenancy.settings_document('branding') ->> 'display_name', 'XCODE'),
    'period', v_period,
    'filters', p_filters,
    'exported_by', coalesce(v_actor, ''),
    'exported_on', p_now,
    'currency', tenancy.settings_document('localization') ->> 'currency',
    'file_name', (p_table ->> 'title') || coalesce(' ' || v_period, '') || '.' || p_format,
    'content_type', CASE p_format
                      WHEN 'pdf' THEN 'application/pdf'
                      ELSE 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                    END
  );
END;
$$;

REVOKE ALL ON FUNCTION reports.document(jsonb, jsonb, text, text, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.document(jsonb, jsonb, text, text, timestamptz) TO xcode_api_executor;
