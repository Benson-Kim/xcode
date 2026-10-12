-- setup.recurring_due_days(p_version setup.recurring_versions, p_from date, p_through date) RETURNS SETOF date
-- Purpose: the days in p_from..p_through on which the version posts, in order: inside its start_on..end_on, before the item's stopped_from, while it is the version in charge (from its effective_from until a higher revision's effective_from), on its weekday, month day (or the month's last day) and, for yearly, its month; daily (legacy) posts every such day.
-- Callers: setup.vehicle_postings (the vehicle report and the investment return).
-- Reads: setup.recurring_versions, setup.recurring_items. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.
-- Each version is stepped arithmetically (weekly from the first matching weekday, monthly and
-- yearly by month starts), so a long window costs a handful of rows, not one test per day.

CREATE OR REPLACE FUNCTION setup.recurring_due_days(
  p_version setup.recurring_versions,
  p_from date,
  p_through date
)
RETURNS SETOF date
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  WITH bounds AS (
    SELECT greatest(p_from, p_version.effective_from, p_version.start_on) AS first,
           least(
             p_through,
             p_version.end_on,
             (
               SELECT min(h.effective_from) - 1
               FROM setup.recurring_versions AS h
               WHERE h.organization_id = p_version.organization_id
                 AND h.item_id = p_version.item_id
                 AND h.revision > p_version.revision
             ),
             (
               SELECT i.stopped_from - 1
               FROM setup.recurring_items AS i
               WHERE i.organization_id = p_version.organization_id AND i.id = p_version.item_id
             )
           ) AS last
    WHERE p_version.id IS NOT NULL AND p_from IS NOT NULL AND p_through IS NOT NULL
  ),
  due AS (
    SELECT g::date AS day
    FROM bounds AS b,
         generate_series(b.first::timestamp, b.last::timestamp, interval '1 day') AS g
    WHERE p_version.frequency = 1
    UNION ALL
    SELECT g::date
    FROM bounds AS b,
         generate_series(
           (b.first + (p_version.day - extract(dow FROM b.first)::integer + 7) % 7)::timestamp,
           b.last::timestamp,
           interval '7 days'
         ) AS g
    WHERE p_version.frequency = 2
    UNION ALL
    SELECT d.day
    FROM bounds AS b,
         generate_series(
           CASE
             WHEN p_version.frequency = 3 THEN date_trunc('month', b.first::timestamp)
             ELSE make_date(extract(year FROM b.first)::integer, p_version.month, 1)::timestamp
           END,
           b.last::timestamp,
           CASE WHEN p_version.frequency = 3 THEN interval '1 month' ELSE interval '1 year' END
         ) AS m,
         LATERAL (
           SELECT CASE
                    WHEN p_version.last_day THEN (m + interval '1 month' - interval '1 day')::date
                    ELSE m::date + (p_version.day - 1)
                  END AS day
         ) AS d
    WHERE p_version.frequency IN (3, 4) AND d.day BETWEEN b.first AND b.last
  )
  SELECT due.day FROM due ORDER BY due.day;
$$;

REVOKE ALL ON FUNCTION setup.recurring_due_days(setup.recurring_versions, date, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.recurring_due_days(setup.recurring_versions, date, date)
  TO xcode_api_executor;
