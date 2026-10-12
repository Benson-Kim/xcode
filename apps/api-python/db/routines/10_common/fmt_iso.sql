-- tenancy.fmt_iso(p_day date) RETURNS text
-- Purpose: a day as yyyy-MM-dd; used by every reason that names a date except revenue.
-- Callers: the reasons of settings, vehicle and scheduled-item writes.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.fmt_iso(p_day date)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT to_char(p_day, 'YYYY-MM-DD');
$$;

REVOKE ALL ON FUNCTION tenancy.fmt_iso(date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.fmt_iso(date) TO xcode_api_executor;
