-- tenancy.trim_text(p_value text) RETURNS text
-- Purpose: trim Unicode white space from both ends as .NET Trim() does; NULL and blank both give NULL.
-- Callers: tenancy.check_typed_reason, the api.ops_* user routines, and every later routine that trims input.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.trim_text(p_value text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT nullif(
    regexp_replace(
      p_value,
      '^[\u0009-\u000D\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+'
      '|[\u0009-\u000D\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+$',
      '',
      'g'
    ),
    ''
  );
$$;

REVOKE ALL ON FUNCTION tenancy.trim_text(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.trim_text(text) TO xcode_api_executor;
