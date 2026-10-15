-- api.revenue_day_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_date date, p_company_id uuid, p_now timestamptz) RETURNS jsonb
-- Purpose: one day of the fleet for capture: {date, business_date, vehicles, truncated}; vehicles are the visible ones in the fleet and not away that day, of the company when given, by registration (ordinal) then id, at most 500 (truncated when more), each {id, company_id, registration, fleet_number, day, last_week}: day is the week grid's cell for the date with the viewer's rights and earliest writable date, last_week the record seven days earlier as {amount, reason (label)} or null. p_date NULL is the business date.
-- Callers: RevenueRoutines.day; GetRevenueDay (GET /setup/revenue/day).
-- Reads: setup.fleet_vehicles, revenue.records, and what tenancy.business_date, tenancy.effective_permissions, tenancy.earliest_writable, setup.visible_vehicles, setup.vehicle_away_on, revenue.vehicle_days, revenue.cell and revenue.reason_label read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 time_zone_invalid via tenancy.business_date, XC422 revenue_day_date_range.
-- Tests: tests/db/test_revenue_day_routines.py, tests/api/test_revenue_day.py.

CREATE OR REPLACE FUNCTION api.revenue_day_get(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_date date,
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
  c_limit CONSTANT integer := 500;
  v_today date;
  v_day date;
  v_permissions text[];
  v_earliest date;
  v_ids uuid[];
  v_truncated boolean;
  v_vehicles jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'revenue.view');
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_day := coalesce(p_date, v_today);
  IF v_day > v_today OR v_day < v_today - 3650 THEN
    PERFORM tenancy.refuse('revenue_day_date_range', 'XC422');
  END IF;
  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  v_earliest := tenancy.earliest_writable(p_organization_id, p_actor_id, v_today);

  v_ids := ARRAY(
    SELECT f.id
    FROM setup.fleet_vehicles AS f
    WHERE f.organization_id = p_organization_id
      AND f.id IN (SELECT visible.id FROM setup.visible_vehicles() AS visible (id))
      AND (p_company_id IS NULL OR f.company_id = p_company_id)
      AND f.joined_on <= v_day
      AND (f.left_on IS NULL OR f.left_on > v_day)
      AND NOT setup.vehicle_away_on(f.id, v_day)
    ORDER BY f.registration COLLATE "C", f.id
    LIMIT c_limit + 1
  );
  v_truncated := cardinality(v_ids) > c_limit;
  v_ids := v_ids[1:c_limit];

  SELECT jsonb_agg(
           jsonb_build_object(
             'id', f.id,
             'company_id', f.company_id,
             'registration', f.registration,
             'fleet_number', f.fleet_number,
             'day', revenue.cell(
                      d,
                      v_today,
                      'revenue.capture' = ANY (v_permissions),
                      'revenue.correct' = ANY (v_permissions),
                      v_earliest
                    ),
             'last_week', CASE
                            WHEN w.id IS NOT NULL THEN jsonb_build_object(
                              'amount', w.amount, 'reason', revenue.reason_label(w.reason)
                            )
                          END
           ) ORDER BY s.ord)
  INTO v_vehicles
  FROM unnest(v_ids) WITH ORDINALITY AS s (id, ord)
  JOIN setup.fleet_vehicles AS f ON f.organization_id = p_organization_id AND f.id = s.id
  JOIN revenue.vehicle_days(v_ids, v_day, v_day, v_today) AS d ON d.vehicle_id = s.id
  LEFT JOIN revenue.records AS w
    ON w.organization_id = p_organization_id AND w.vehicle_id = s.id AND w.business_date = v_day - 7;

  RETURN jsonb_build_object(
    'date', v_day,
    'business_date', v_today,
    'vehicles', coalesce(v_vehicles, '[]'::jsonb),
    'truncated', v_truncated
  );
END;
$$;
