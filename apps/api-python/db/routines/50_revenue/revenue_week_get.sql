-- api.revenue_week_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_week_start date, p_company_id uuid, p_vehicle_id uuid, p_page integer, p_page_size integer, p_q text, p_now timestamptz) RETURNS jsonb
-- Purpose: the revenue week grid (RevenueWeekDto): the organization week holding p_week_start (default the business date); the visible vehicles in the fleet on some day of it, optionally of one company and matching p_q (registration or fleet number), by registration, one page of rows with their seven cells, earliest missing day, totals, gap and low days; the totals, percent, gap to target, low days, missing days, seven day totals and the first gap of the whole filtered grid; the low-day threshold and amber band in force; the company options. With p_vehicle_id, exactly that vehicle in any week, never paged.
-- Callers: RevenueRoutines.week; GetRevenueWeek (GET /setup/revenue).
-- Reads: setup.fleet_vehicles, setup.psv_companies, and what tenancy.business_date, tenancy.effective_permissions, tenancy.earliest_writable, tenancy.settings_document, tenancy.check_page, revenue.week_start, setup.visible_vehicles, setup.visible_companies, setup.vehicle_visible, setup.company_active_on, revenue.vehicle_days, revenue.earliest_missing and revenue.vehicle_week read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 time_zone_invalid via tenancy.business_date, XC422 page_out_of_range via tenancy.check_page, XC422 revenue_search_length, XC422 revenue_week_range, XC404 not_found.
-- Tests: tests/db/test_revenue_routines.py, tests/api/test_revenue.py.
-- Without page and pageSize the grid lists its first 500 vehicles and says truncated when it
-- holds more, as released clients expect; either one turns paging on (page 1, size 100 by
-- default). The search is applied with the company filter before paging, so every whole-grid
-- figure covers the matches. The gap is the revenue less the day targets of the days that count
-- so far (every day in the fleet before the business date, and the business date once
-- recorded). The first gap is the earliest day that still needs capture over the whole grid (a
-- vehicle's earliest missing day, or the business date while it has no record yet), the first
-- vehicle in registration order winning a tie; it is shown to every viewer of the week.

CREATE OR REPLACE FUNCTION api.revenue_week_get(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_week_start date,
  p_company_id uuid,
  p_vehicle_id uuid,
  p_page integer,
  p_page_size integer,
  p_q text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  c_legacy_limit CONSTANT integer := 500;
  c_default_size CONSTANT integer := 100;
  v_paged boolean := p_vehicle_id IS NULL AND (p_page IS NOT NULL OR p_page_size IS NOT NULL);
  v_page integer := 1;
  v_size integer := c_legacy_limit;
  v_q text := tenancy.trim_text(p_q);
  v_pattern text;
  v_permissions text[];
  v_capture boolean;
  v_correct boolean;
  v_settings jsonb;
  v_threshold numeric;
  v_amber numeric;
  v_today date;
  v_earliest date;
  v_current_start date;
  v_start date;
  v_through date;
  v_grid uuid[];
  v_shown uuid[];
  v_companies jsonb;
  v_document jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'revenue.view');
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  v_capture := 'revenue.capture' = ANY (v_permissions);
  v_correct := 'revenue.correct' = ANY (v_permissions);
  v_earliest := tenancy.earliest_writable(p_organization_id, p_actor_id, v_today);
  v_settings := tenancy.settings_document('revenue');
  v_threshold := (v_settings ->> 'low_day_threshold')::numeric;
  v_amber := (v_settings ->> 'gap_amber_percent')::numeric;
  IF v_paged THEN
    v_page := coalesce(p_page, 1);
    v_size := coalesce(p_page_size, c_default_size);
    PERFORM tenancy.check_page(v_page, v_size);
  END IF;
  IF char_length(v_q) > 40 THEN
    PERFORM tenancy.refuse('revenue_search_length', 'XC422');
  END IF;
  v_pattern := '%' || replace(replace(replace(v_q, '\', '\\'), '%', '\%'), '_', '\_') || '%';
  v_current_start := revenue.week_start(v_today);
  v_start := revenue.week_start(coalesce(p_week_start, v_today));
  IF v_start > v_current_start OR v_start < v_current_start - 3650 THEN
    PERFORM tenancy.refuse('revenue_week_range', 'XC422');
  END IF;
  v_through := v_start + 6;

  SELECT coalesce(array_agg(f.id ORDER BY f.registration, f.id), '{}') INTO v_grid
  FROM setup.fleet_vehicles AS f
  WHERE f.organization_id = p_organization_id
    AND f.id IN (SELECT setup.visible_vehicles())
    AND (p_company_id IS NULL OR f.company_id = p_company_id)
    AND (v_pattern IS NULL OR f.registration ILIKE v_pattern OR f.fleet_number ILIKE v_pattern)
    AND CASE
          WHEN p_vehicle_id IS NULL THEN
            f.joined_on <= v_through AND (f.left_on IS NULL OR f.left_on > v_start)
          ELSE f.id = p_vehicle_id
        END;
  IF p_vehicle_id IS NOT NULL AND cardinality(v_grid) = 0
     AND NOT setup.vehicle_visible(p_vehicle_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  v_shown := v_grid[(v_page - 1) * v_size + 1 : v_page * v_size];

  SELECT coalesce(jsonb_agg(jsonb_build_object('id', c.id, 'name', c.name) ORDER BY c.name, c.id), '[]')
  INTO v_companies
  FROM setup.psv_companies AS c
  WHERE c.organization_id = p_organization_id
    AND c.id IN (SELECT setup.visible_companies())
    AND (
      setup.company_active_on(c.id, v_today)
      OR EXISTS (
        SELECT 1
        FROM setup.fleet_vehicles AS f
        WHERE f.organization_id = c.organization_id
          AND f.company_id = c.id
          AND f.id IN (SELECT setup.visible_vehicles())
          AND f.joined_on <= v_through
          AND (f.left_on IS NULL OR f.left_on > v_start)
      )
    );

  WITH days AS MATERIALIZED (
    SELECT d AS fact, d.vehicle_id, d.day, d.active, d.target, d.counted, d.record_id, d.amount
    FROM revenue.vehicle_days(v_grid, v_start, v_through, v_today) AS d
  ),
  missing AS MATERIALIZED (
    SELECT m.vehicle_id, m.earliest_missing
    FROM revenue.earliest_missing(v_grid, v_today) AS m
  ),
  weeks AS (
    SELECT d.vehicle_id, array_agg(d.fact ORDER BY d.day) AS facts
    FROM days AS d
    WHERE d.vehicle_id = ANY (v_shown)
    GROUP BY d.vehicle_id
  ),
  rows AS (
    SELECT s.ord,
           jsonb_build_object(
             'id', f.id,
             'company_id', f.company_id,
             'company_name', c.name,
             'registration', f.registration,
             'joined_on', f.joined_on,
             'left_on', f.left_on,
             'earliest_missing', m.earliest_missing,
             'fleet_number', f.fleet_number
           ) || revenue.vehicle_week(
                  w.facts, v_today, v_capture, v_correct, v_earliest, v_threshold, v_amber
                ) AS document
    FROM unnest(v_shown) WITH ORDINALITY AS s (id, ord)
    JOIN setup.fleet_vehicles AS f ON f.organization_id = p_organization_id AND f.id = s.id
    JOIN setup.psv_companies AS c ON c.organization_id = f.organization_id AND c.id = f.company_id
    LEFT JOIN missing AS m ON m.vehicle_id = s.id
    JOIN weeks AS w ON w.vehicle_id = s.id
  ),
  totals AS (
    SELECT coalesce(sum(d.amount) FILTER (WHERE d.counted), 0) AS amount,
           coalesce(sum(d.target) FILTER (WHERE d.counted), 0) AS target,
           count(*) FILTER (
             WHERE d.counted AND d.record_id IS NOT NULL
               AND coalesce(d.amount < v_threshold, true)
           ) AS low_days,
           count(*) FILTER (WHERE d.counted AND d.record_id IS NULL) AS missing_days
    FROM days AS d
  ),
  day_totals AS (
    SELECT v_start + n.offset_days AS day,
           coalesce(sum(d.amount) FILTER (WHERE d.active AND d.day <= v_today), 0) AS amount,
           coalesce(sum(d.target) FILTER (WHERE d.counted), 0) AS target
    FROM generate_series(0, 6) AS n (offset_days)
    LEFT JOIN days AS d ON d.day = v_start + n.offset_days
    GROUP BY n.offset_days
  ),
  gap AS (
    SELECT g.id, o.day
    FROM unnest(v_grid) WITH ORDINALITY AS g (id, ord)
    LEFT JOIN missing AS m ON m.vehicle_id = g.id
    LEFT JOIN days AS t ON t.vehicle_id = g.id AND t.day = v_today
    CROSS JOIN LATERAL (
      SELECT coalesce(
               m.earliest_missing,
               CASE WHEN t.active AND t.record_id IS NULL THEN v_today END
             ) AS day
    ) AS o
    WHERE o.day IS NOT NULL
    ORDER BY o.day, g.ord
    LIMIT 1
  )
  SELECT jsonb_build_object(
           'week_start', v_start,
           'week_through', v_through,
           'current_week_start', v_current_start,
           'business_date', v_today,
           'companies', v_companies,
           'vehicles', coalesce((SELECT jsonb_agg(r.document ORDER BY r.ord) FROM rows AS r), '[]'),
           'total_amount', round(t.amount, 2),
           'total_expected', round(t.target, 2),
           'percent', revenue.percent(t.amount, t.target),
           'page_number', v_page,
           'page_size', v_size,
           'total_vehicles', cardinality(v_grid),
           'truncated', NOT v_paged AND p_vehicle_id IS NULL AND cardinality(v_grid) > c_legacy_limit,
           'day_totals', (
             SELECT jsonb_agg(
                      jsonb_build_object(
                        'day', dt.day,
                        'amount', round(dt.amount, 2),
                        'expected', round(dt.target, 2)
                      ) ORDER BY dt.day
                    )
             FROM day_totals AS dt
           ),
           'first_gap', (SELECT jsonb_build_object('vehicle_id', g.id, 'day', g.day) FROM gap AS g),
           'low_day_threshold', v_threshold,
           'gap_amber_percent', v_amber,
           'gap', round(t.amount - t.target, 2),
           'gap_band', revenue.gap_band(t.amount - t.target, t.target, v_amber),
           'below_threshold_days', t.low_days,
           'missing_days', t.missing_days
         )
  INTO v_document
  FROM totals AS t;
  RETURN v_document;
END;
$$;
