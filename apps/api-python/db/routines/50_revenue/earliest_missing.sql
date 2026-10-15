-- revenue.earliest_missing(p_vehicle_ids uuid[], p_today date) RETURNS TABLE (vehicle_id uuid, earliest_missing date)
-- Purpose: for each listed vehicle of the current organization, the first day from its join date, before p_today and before its leave date, on which it is in the fleet (not away) and has no record; NULL when every such day is recorded.
-- Callers: api.revenue_week_get (each row's earliestMissing and the week's firstGap).
-- Reads: setup.fleet_vehicles, setup.vehicle_away_periods, revenue.records. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_revenue_helpers.py.
-- The day before the earliest missing day is before the join date, recorded or away, so that day
-- is the join date, the day after a record whose next day has none, or a return from time away:
-- the first of those that is neither recorded nor away. An open join date answers at once;
-- otherwise the records are walked in date order and the walk stops at the first open day after
-- one, so only a history without a gap is read to its end. Each vehicle's time away is gathered
-- once into a multirange.

CREATE OR REPLACE FUNCTION revenue.earliest_missing(p_vehicle_ids uuid[], p_today date)
RETURNS TABLE (vehicle_id uuid, earliest_missing date)
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  WITH vehicles AS (
    SELECT f.organization_id,
           f.id,
           f.joined_on,
           CASE WHEN f.left_on < p_today THEN f.left_on ELSE p_today END AS end_on
    FROM setup.fleet_vehicles AS f
    WHERE f.organization_id = tenancy.current_organization() AND f.id = ANY (p_vehicle_ids)
  ),
  away AS (
    SELECT a.vehicle_id,
           range_agg(daterange(a.left_on, a.returned_on)) AS spans,
           array_agg(a.returned_on) AS returns
    FROM setup.vehicle_away_periods AS a
    WHERE a.organization_id = tenancy.current_organization() AND a.vehicle_id = ANY (p_vehicle_ids)
    GROUP BY a.vehicle_id
  )
  SELECT v.id,
         CASE
           WHEN v.end_on <= v.joined_on THEN NULL
           WHEN NOT coalesce(w.spans @> v.joined_on, false)
                AND NOT EXISTS (
                  SELECT 1
                  FROM revenue.records AS r
                  WHERE r.organization_id = v.organization_id
                    AND r.vehicle_id = v.id
                    AND r.business_date = v.joined_on
                )
             THEN v.joined_on
           ELSE least(
             (
               SELECT g.next_day
               FROM (
                 SELECT r.business_date,
                        r.business_date + 1 AS next_day,
                        lead(r.business_date) OVER (ORDER BY r.business_date) AS following
                 FROM revenue.records AS r
                 WHERE r.organization_id = v.organization_id
                   AND r.vehicle_id = v.id
                   AND r.business_date >= v.joined_on
                   AND r.business_date < v.end_on
               ) AS g
               WHERE g.following IS DISTINCT FROM g.next_day
                 AND g.next_day < v.end_on
                 AND NOT coalesce(w.spans @> g.next_day, false)
               ORDER BY g.business_date
               LIMIT 1
             ),
             (
               SELECT min(x.day)
               FROM unnest(w.returns) AS x (day)
               WHERE x.day > v.joined_on
                 AND x.day < v.end_on
                 AND NOT w.spans @> x.day
                 AND NOT EXISTS (
                   SELECT 1
                   FROM revenue.records AS r
                   WHERE r.organization_id = v.organization_id
                     AND r.vehicle_id = v.id
                     AND r.business_date = x.day
                 )
             )
           )
         END
  FROM vehicles AS v
  LEFT JOIN away AS w ON w.vehicle_id = v.id;
$$;

REVOKE ALL ON FUNCTION revenue.earliest_missing(uuid[], date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION revenue.earliest_missing(uuid[], date) TO xcode_api_executor;
