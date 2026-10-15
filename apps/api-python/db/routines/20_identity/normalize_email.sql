-- identity.normalize_email(p_input text) RETURNS text
-- Purpose: an email address trimmed and lower-cased when it is local@domain with no white space and at most 320 characters; NULL otherwise (the caller decides the refusal).
-- Callers: api.ops_provision_user, tenancy.save_person.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_access_routines.py, tests/db/test_ops_routines.py.

CREATE OR REPLACE FUNCTION identity.normalize_email(p_input text)
RETURNS text
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT candidate.value
  FROM (SELECT lower(tenancy.trim_text(p_input)) AS value) AS candidate
  WHERE char_length(candidate.value) <= 320
    AND candidate.value ~ '^[^@[:space:]]+@[^@[:space:]]+$';
$$;

REVOKE ALL ON FUNCTION identity.normalize_email(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.normalize_email(text) TO xcode_api_executor;
