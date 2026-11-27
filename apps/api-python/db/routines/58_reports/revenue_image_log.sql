-- api.revenue_image_log(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_week_start date, p_company_id uuid, p_q text, p_now timestamptz) RETURNS void
-- Purpose: the audit row of the Revenue Summary image, which the device draws from the week on screen: the organization week holding p_week_start (the current week at the latest, at most ten years back), the company filter (one the actor can see) and the search (at most 40 characters) as the screen used them; one change-log row through reports.log_export, reason "Exported Revenue for {week}[, searched for "{q}"] to Summary image", snapshot {screen, weekStart, companyId, q, format png}. The figures are neither read nor checked.
-- Callers: ReportsRoutines.log_revenue_image; LogRevenueSummaryImage (POST /setup/revenue/export/image).
-- Reads: setup.psv_companies, and what tenancy.require_permission, tenancy.business_date, revenue.week_start and setup.visible_companies read. Writes: what reports.log_export writes.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC403 permission_missing via tenancy.require_permission, XC422 revenue_search_length, XC422 time_zone_invalid via tenancy.business_date, XC422 revenue_week_range, XC404 not_found.
-- Tests: tests/db/test_revenue_image_routine.py, tests/api/test_revenue_image.py.

CREATE OR REPLACE FUNCTION api.revenue_image_log(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_week_start date,
  p_company_id uuid,
  p_q text,
  p_now timestamptz
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_q text := tenancy.trim_text(p_q);
  v_current_start date;
  v_start date;
  v_filters text := 'All companies';
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'revenue.export');
  PERFORM tenancy.require_permission('revenue.view');
  IF char_length(v_q) > 40 THEN
    PERFORM tenancy.refuse('revenue_search_length', 'XC422');
  END IF;
  v_current_start := revenue.week_start(tenancy.business_date(p_organization_id, p_now));
  v_start := revenue.week_start(p_week_start);
  IF v_start IS NULL OR v_start > v_current_start OR v_start < v_current_start - 3650 THEN
    PERFORM tenancy.refuse('revenue_week_range', 'XC422');
  END IF;
  IF p_company_id IS NOT NULL THEN
    SELECT c.name INTO v_filters
    FROM setup.psv_companies AS c
    WHERE c.organization_id = p_organization_id
      AND c.id = p_company_id
      AND c.id IN (SELECT setup.visible_companies());
    IF NOT FOUND THEN
      PERFORM tenancy.refuse('not_found', 'XC404');
    END IF;
  END IF;
  PERFORM reports.log_export(
    jsonb_build_object('title', 'Revenue', 'from_date', v_start, 'to_date', v_start + 6),
    NULL,
    v_filters,
    v_q,
    'png',
    jsonb_build_object(
      'screen', 'revenue',
      'weekStart', v_start,
      'companyId', p_company_id,
      'q', v_q,
      'format', 'png'
    ),
    p_now
  );
END;
$$;
