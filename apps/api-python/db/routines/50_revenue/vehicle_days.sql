-- revenue.vehicle_days(p_vehicle_ids uuid[], p_from date, p_through date, p_today date) RETURNS SETOF revenue.vehicle_day
-- Purpose: every day from p_from through p_through of each listed vehicle of the current organization, set-based: in the fleet (joined, not yet left, not away), the day target (that weekday's figure in the target set in force; 0 when not in the fleet or no set has started), whether the day counts towards the figures (in the fleet and before p_today or recorded), and the record of the day; ordered by vehicle and day.
-- Callers: api.revenue_week_get, api.revenue_dashboard_get, api.revenue_capture (the current cell of a conflict).
-- Reads: setup.fleet_vehicles, setup.vehicle_away_periods, setup.vehicle_target_sets, revenue.records, revenue.no_earnings_reasons. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_revenue_helpers.py.
-- The set form of setup.vehicle_active_on and setup.day_target, which answer one vehicle and one
-- day each; a test holds the two forms equal. Target sets are joined as ranges (each start until
-- the next start), so no lookup runs per day. Records are read for the period only: a function
-- body is planned without its arguments, and an unbounded join hashed the organization's whole
-- history even for one vehicle's week.
-- The days and the records are materialized so that they join on vehicle and day: planned
-- without its arguments, the body merged on the vehicle alone and filtered every record of the
-- vehicle against every day (a year of 500 vehicles: 61 million rows, 22 s, against 1.2 s).

CREATE OR REPLACE FUNCTION revenue.vehicle_days(
  p_vehicle_ids uuid[],
  p_from date,
  p_through date,
  p_today date
)
RETURNS SETOF revenue.vehicle_day
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  WITH vehicles AS (
    SELECT f.id, f.joined_on, f.left_on
    FROM setup.fleet_vehicles AS f
    WHERE f.organization_id = tenancy.current_organization() AND f.id = ANY (p_vehicle_ids)
  ),
  targets AS (
    SELECT t.vehicle_id,
           t.starts_on,
           ARRAY[t.monday, t.tuesday, t.wednesday, t.thursday, t.friday, t.saturday, t.sunday]
             AS figures,
           lead(t.starts_on) OVER (PARTITION BY t.vehicle_id ORDER BY t.starts_on)
             AS superseded_from
    FROM setup.vehicle_target_sets AS t
    WHERE t.organization_id = tenancy.current_organization()
      AND t.vehicle_id = ANY (p_vehicle_ids)
      AND t.starts_on <= p_through
  ),
  days AS MATERIALIZED (
    SELECT v.id AS vehicle_id,
           p_from + n.offset_days AS day,
           v.joined_on <= p_from + n.offset_days
             AND (v.left_on IS NULL OR p_from + n.offset_days < v.left_on)
             AND a.vehicle_id IS NULL AS active,
           a.vehicle_id IS NOT NULL AS away
    FROM vehicles AS v
    CROSS JOIN generate_series(0, p_through - p_from) AS n (offset_days)
    LEFT JOIN setup.vehicle_away_periods AS a
      ON a.organization_id = tenancy.current_organization()
     AND a.vehicle_id = v.id
     AND p_from + n.offset_days >= a.left_on
     AND p_from + n.offset_days < a.returned_on
  ),
  records AS MATERIALIZED (
    SELECT r.vehicle_id, r.business_date, r.id, r.amount, r.reason, r.note,
           r.corrected_after_date, r.version
    FROM revenue.records AS r
    WHERE r.organization_id = tenancy.current_organization()
      AND r.vehicle_id = ANY (p_vehicle_ids)
      AND r.business_date BETWEEN p_from AND p_through
  )
  SELECT d.vehicle_id,
         d.day,
         d.active,
         d.away,
         CASE
           WHEN d.active THEN coalesce(t.figures[extract(isodow FROM d.day)::integer], 0)
           ELSE 0
         END,
         d.active AND (d.day < p_today OR r.id IS NOT NULL),
         r.id,
         r.amount,
         r.reason,
         l.label,
         r.note,
         r.corrected_after_date,
         r.version
  FROM days AS d
  LEFT JOIN targets AS t
    ON t.vehicle_id = d.vehicle_id
   AND d.day >= t.starts_on
   AND (t.superseded_from IS NULL OR d.day < t.superseded_from)
  LEFT JOIN records AS r ON r.vehicle_id = d.vehicle_id AND r.business_date = d.day
  LEFT JOIN revenue.no_earnings_reasons AS l ON l.code = r.reason
  ORDER BY d.vehicle_id, d.day;
$$;

REVOKE ALL ON FUNCTION revenue.vehicle_days(uuid[], date, date, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION revenue.vehicle_days(uuid[], date, date, date) TO xcode_api_executor;
