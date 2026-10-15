-- tenancy.back_limit_earliest(p_mode text, p_count integer, p_from date, p_today date) RETURNS date
-- Purpose: the earliest date a back-dating limit allows on p_today: days -> p_today - count; months -> the same day count months before (the last day of that month when the day does not exist); then the later of that and p_from; NULL when neither is set (any date).
-- Callers: tenancy.earliest_writable, tenancy.save_person.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_back_limit.py.

CREATE OR REPLACE FUNCTION tenancy.back_limit_earliest(
  p_mode text,
  p_count integer,
  p_from date,
  p_today date
)
RETURNS date
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
           WHEN rolling.day IS NULL THEN p_from
           WHEN p_from IS NULL THEN rolling.day
           ELSE greatest(rolling.day, p_from)
         END
  FROM (
    SELECT CASE p_mode
             WHEN 'days' THEN p_today - p_count
             WHEN 'months' THEN (p_today - make_interval(months => p_count))::date
           END AS day
  ) AS rolling;
$$;

REVOKE ALL ON FUNCTION tenancy.back_limit_earliest(text, integer, date, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.back_limit_earliest(text, integer, date, date) TO xcode_api_executor;
