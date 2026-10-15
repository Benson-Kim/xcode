-- api.report_export_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_group text, p_report text, p_from date, p_to date, p_company_id uuid, p_holder_id uuid, p_q text, p_format text, p_now timestamptz) RETURNS jsonb
-- Purpose: a report as a file's document (reports.document) in one transaction with its audit row (reports.log_export): the format first, then the search text, then the report built as api.report_get builds it, every row the search leaves (no paging), the 10,000-row cap, the filters text (the company or "All companies"; the float or "All floats"), the document, and the change-log row in section reports with {group, report, from, to, holderId, companyId, q, rows, format}.
-- Callers: ReportsRoutines.export_report; ExportReport (GET /setup/reports/{group}/{report}/export).
-- Reads: setup.psv_companies, and what tenancy.business_date, tenancy.require_permission, tenancy.has_permission, reports.check_export, reports.check_query, reports.build, reports.matching_rows, pettycash.visible_holders, setup.visible_companies and reports.document read. Writes: what reports.log_export writes.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC403 permission_missing via tenancy.require_permission, XC422 export_format_invalid via reports.check_export, XC422 report_search_length via reports.check_query, XC422 time_zone_invalid via tenancy.business_date, XC404 not_found via reports.build, XC403 report_investment_permission via reports.build, XC403 report_pettycash_permission via reports.build, XC422 report_period_both via reports.build, XC422 report_period_order via reports.build, XC422 report_period_length via reports.build, XC422 report_period_future via reports.build, XC422 export_too_many_rows via reports.check_export.
-- Tests: tests/db/test_report_routines.py, tests/api/test_reports.py.

CREATE OR REPLACE FUNCTION api.report_export_get(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_group text,
  p_report text,
  p_from date,
  p_to date,
  p_company_id uuid,
  p_holder_id uuid,
  p_q text,
  p_format text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_format text;
  v_q text;
  v_today date;
  v_table jsonb;
  v_rows jsonb;
  v_count integer;
  v_filters text;
  v_document jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'reports.export');
  PERFORM tenancy.require_permission('reports.view');
  v_format := reports.check_export(p_format, NULL);
  v_q := reports.check_query(p_q, NULL, NULL);
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_table := reports.build(p_group, p_report, p_from, p_to, p_company_id, p_holder_id, v_today);
  v_rows := reports.matching_rows(v_table, v_q);
  v_count := jsonb_array_length(v_rows);
  PERFORM reports.check_export(v_format, v_count);
  IF p_group = 'pettycash' THEN
    v_filters := coalesce(
      (
        SELECT h.name
        FROM pettycash.visible_holders(tenancy.has_permission('pettycash.view_all')) AS h
        WHERE h.user_id = p_holder_id
      ),
      'All floats'
    );
  ELSE
    v_filters := coalesce(
      (
        SELECT c.name
        FROM setup.psv_companies AS c
        WHERE c.organization_id = p_organization_id
          AND c.id = p_company_id
          AND c.id IN (SELECT setup.visible_companies())
      ),
      'All companies'
    );
  END IF;
  v_document := reports.document(v_table, v_rows, v_filters, v_format, p_now);
  PERFORM reports.log_export(
    v_table,
    v_count,
    v_filters,
    v_q,
    v_format,
    jsonb_build_object(
      'group', p_group,
      'report', p_report,
      'from', v_table -> 'from_date',
      'to', v_table -> 'to_date',
      'holderId', p_holder_id,
      'companyId', p_company_id,
      'q', v_q,
      'rows', v_count,
      'format', v_format
    ),
    p_now
  );
  RETURN v_document;
END;
$$;
