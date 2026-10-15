-- tenancy.fmt_instant(p_value timestamptz) RETURNS text
-- Purpose: an instant as the snapshots carry it: UTC, six fractional digits and the offset +00:00 (2026-10-07T05:25:29.123456+00:00).
-- Callers: tenancy.logo_snapshot and the later snapshot builders that name an instant.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_organization_routines.py.

CREATE OR REPLACE FUNCTION tenancy.fmt_instant(p_value timestamptz)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT to_char(p_value AT TIME ZONE 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS.US"+00:00"');
$$;

REVOKE ALL ON FUNCTION tenancy.fmt_instant(timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.fmt_instant(timestamptz) TO xcode_api_executor;
