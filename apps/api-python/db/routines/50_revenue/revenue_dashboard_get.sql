-- api.revenue_dashboard_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_period text, p_company_id uuid, p_now timestamptz) RETURNS jsonb
-- Purpose: the revenue dashboard cards (RevenueDashboardDto) from the first day of the period (today, week or month; week when NULL) through the business date, over the visible vehicles in the fleet in that window, optionally of one company; each card NULL unless the caller holds its own permission.
-- Callers: RevenueRoutines.dashboard; GetRevenueDashboard (GET /setup/revenue/dashboard).
-- Reads: setup.fleet_vehicles, and what tenancy.effective_permissions, tenancy.business_date, revenue.week_start, setup.visible_vehicles and revenue.vehicle_days read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing, XC422 time_zone_invalid via tenancy.business_date, XC422 dashboard_period_invalid.
-- Tests: tests/db/test_revenue_routines.py, tests/api/test_revenue.py.
-- One aggregate over the vehicles' days in the window, always fresh (no cache). Revenue sums the
-- amounts of the days in the fleet; expected adds the day targets of the days that count (in the
-- fleet and before the business date, or recorded on it); a day in the fleet before the business
-- date without a record is missing; captured today counts the vehicles recorded on the business
-- date, vehicles today those in the fleet on it; edited counts the records changed after their
-- day. Cards: revenue, expected, percent and edited_records need dash.net; captured_today,
-- vehicles_today, missing_days and missing_vehicles dash.gaps.

CREATE OR REPLACE FUNCTION api.revenue_dashboard_get(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_period text,
  p_company_id uuid,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_period text := coalesce(p_period, 'week');
  v_permissions text[];
  v_net_card boolean;
  v_gaps_card boolean;
  v_today date;
  v_from date;
  v_fleet uuid[];
  v_figures record;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  IF NOT v_permissions && ARRAY['dash.net', 'dash.gaps'] THEN
    PERFORM tenancy.refuse('permission_missing', 'XC403');
  END IF;
  v_net_card := 'dash.net' = ANY (v_permissions);
  v_gaps_card := 'dash.gaps' = ANY (v_permissions);
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_from := CASE v_period
              WHEN 'today' THEN v_today
              WHEN 'week' THEN revenue.week_start(v_today)
              WHEN 'month' THEN date_trunc('month', v_today)::date
            END;
  IF v_from IS NULL THEN
    PERFORM tenancy.refuse('dashboard_period_invalid', 'XC422');
  END IF;

  SELECT coalesce(array_agg(f.id), '{}') INTO v_fleet
  FROM setup.fleet_vehicles AS f
  WHERE f.organization_id = p_organization_id
    AND f.id IN (SELECT setup.visible_vehicles())
    AND (p_company_id IS NULL OR f.company_id = p_company_id)
    AND f.joined_on <= v_today
    AND (f.left_on IS NULL OR f.left_on > v_from);

  SELECT coalesce(sum(v.revenue), 0) AS revenue,
         coalesce(sum(v.target), 0) AS target,
         coalesce(sum(v.recorded_today), 0) AS captured_today,
         coalesce(sum(v.active_today), 0) AS vehicles_today,
         coalesce(sum(v.active_before - v.recorded_before), 0) AS missing_days,
         count(*) FILTER (WHERE v.active_before > v.recorded_before) AS missing_vehicles,
         coalesce(sum(v.edited), 0) AS edited_records
  INTO v_figures
  FROM (
    SELECT d.vehicle_id,
           sum(d.amount) FILTER (WHERE d.active) AS revenue,
           sum(d.target) FILTER (WHERE d.counted) AS target,
           count(*) FILTER (WHERE d.active AND d.day < v_today) AS active_before,
           count(*) FILTER (WHERE d.active AND d.day < v_today AND d.record_id IS NOT NULL)
             AS recorded_before,
           count(*) FILTER (WHERE d.active AND d.day = v_today) AS active_today,
           count(*) FILTER (WHERE d.active AND d.day = v_today AND d.record_id IS NOT NULL)
             AS recorded_today,
           count(*) FILTER (WHERE d.active AND d.corrected_after_date) AS edited
    FROM revenue.vehicle_days(v_fleet, v_from, v_today, v_today) AS d
    GROUP BY d.vehicle_id
  ) AS v;

  RETURN jsonb_build_object(
    'period', v_period,
    'from_date', v_from,
    'through', v_today,
    'business_date', v_today,
    'revenue', CASE WHEN v_net_card THEN round(v_figures.revenue, 2) END,
    'expected', CASE WHEN v_net_card THEN round(v_figures.target, 2) END,
    'percent', CASE WHEN v_net_card THEN revenue.percent(v_figures.revenue, v_figures.target) END,
    'captured_today', CASE WHEN v_gaps_card THEN v_figures.captured_today END,
    'vehicles_today', CASE WHEN v_gaps_card THEN v_figures.vehicles_today END,
    'missing_days', CASE WHEN v_gaps_card THEN v_figures.missing_days END,
    'missing_vehicles', CASE WHEN v_gaps_card THEN v_figures.missing_vehicles END,
    'edited_records', CASE WHEN v_net_card THEN v_figures.edited_records END
  );
END;
$$;
