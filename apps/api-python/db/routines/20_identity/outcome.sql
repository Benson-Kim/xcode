-- identity.outcome(p_outcome text, p_fields jsonb DEFAULT '{}') RETURNS jsonb
-- Purpose: the api.auth_* outcome document: every key present, NULL unless the outcome needs it.
-- Callers: every api.auth_* routine that returns an outcome; identity.issue_session.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION identity.outcome(p_outcome text, p_fields jsonb DEFAULT '{}')
RETURNS jsonb
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT jsonb_build_object(
           'outcome', NULL,
           'refusal', NULL,
           'retry_after_seconds', NULL,
           'masked_email', NULL,
           'code_issued', NULL,
           'code_id', NULL,
           'email', NULL,
           'minimum_pin_length', NULL,
           'user_id', NULL,
           'organization_id', NULL,
           'role', NULL,
           'first_name', NULL,
           'last_name', NULL,
           'permissions', NULL,
           'security_version', NULL,
           'access_token_minutes', NULL,
           'refresh_expires_at', NULL,
           'purpose', NULL,
           'tries_left', NULL,
           'pin_problem', NULL,
           'device_token_issued', NULL
         )
         || coalesce(p_fields, '{}'::jsonb)
         || jsonb_build_object('outcome', p_outcome);
$$;

REVOKE ALL ON FUNCTION identity.outcome(text, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.outcome(text, jsonb) TO xcode_api_executor;
