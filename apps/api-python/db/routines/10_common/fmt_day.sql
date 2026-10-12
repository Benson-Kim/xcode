-- tenancy.fmt_day(p_day date) RETURNS text
-- Purpose: a day as .NET's "d MMM yyyy" with invariant month abbreviations (8 Oct 2026); used by revenue reasons.
-- Callers: the reasons of revenue writes.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.fmt_day(p_day date)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT to_char(p_day, 'FMDD Mon YYYY');
$$;

REVOKE ALL ON FUNCTION tenancy.fmt_day(date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.fmt_day(date) TO xcode_api_executor;
