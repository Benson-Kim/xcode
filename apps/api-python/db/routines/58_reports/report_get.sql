-- api.report_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_group text, p_report text, p_from date, p_to date, p_company_id uuid, p_holder_id uuid, p_q text, p_page integer, p_page_size integer, p_now timestamptz) RETURNS jsonb
-- Purpose: one page of a report (ReportTableDto): the page and search text checked first (reports.check_query), then the report built for the actor (reports.build: unknown report, the report's right, the holder, the period), then the rows matching every word of the search, paged, with their count and footer (reports.page); the headline and figures cover the whole report.
-- Callers: ReportsRoutines.report; GetFleetReport (GET /setup/reports/fleet/{report}), GetPettyCashReport (GET /setup/reports/pettycash/{report}).
-- Reads: what tenancy.business_date, reports.check_query, reports.build and reports.page read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 page_out_of_range via reports.check_query, XC422 report_search_length via reports.check_query, XC422 time_zone_invalid via tenancy.business_date, XC404 not_found via reports.build, XC403 report_investment_permission via reports.build, XC403 report_pettycash_permission via reports.build, XC422 report_period_both via reports.build, XC422 report_period_order via reports.build, XC422 report_period_length via reports.build, XC422 report_period_future via reports.build.
-- Tests: tests/db/test_report_routines.py, tests/api/test_reports.py.

CREATE OR REPLACE FUNCTION api.report_get(
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
  p_page integer,
  p_page_size integer,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_q text;
  v_today date;
  v_table jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'reports.view');
  v_q := reports.check_query(p_q, coalesce(p_page, 0), coalesce(p_page_size, 0));
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_table := reports.build(p_group, p_report, p_from, p_to, p_company_id, p_holder_id, v_today);
  RETURN reports.page(v_table, v_q, p_page, p_page_size);
END;
$$;
