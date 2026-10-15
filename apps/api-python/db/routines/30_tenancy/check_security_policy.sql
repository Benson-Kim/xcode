-- tenancy.check_security_policy(p_document jsonb) RETURNS void
-- Purpose: validate a security-policy document (document keys, values already of the right JSON type): PIN sign-in stays on, and every number lies within the bounds of the table's CHECK constraints.
-- Callers: api.organization_settings_set (the merged section).
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 security_policy_pin_sign_in, XC422 security_policy_invalid.
-- Tests: tests/db/test_organization_routines.py.

CREATE OR REPLACE FUNCTION tenancy.check_security_policy(p_document jsonb)
RETURNS void
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF NOT coalesce((p_document ->> 'allow_pin_sign_in')::boolean, false) THEN
    PERFORM tenancy.refuse('security_policy_pin_sign_in', 'XC422');
  END IF;
  IF coalesce((p_document ->> 'password_min_length')::numeric NOT BETWEEN 12 AND 128, true)
     OR coalesce((p_document ->> 'password_history')::numeric NOT BETWEEN 0 AND 24, true)
     OR coalesce((p_document ->> 'pin_length')::numeric NOT BETWEEN 4 AND 8, true)
     OR coalesce((p_document ->> 'lockout_threshold')::numeric NOT BETWEEN 3 AND 10, true)
     OR coalesce((p_document ->> 'lockout_minutes')::numeric NOT BETWEEN 1 AND 60, true)
     OR coalesce((p_document ->> 'access_token_minutes')::numeric NOT BETWEEN 1 AND 15, true)
     OR coalesce((p_document ->> 'refresh_token_days')::numeric NOT BETWEEN 1 AND 90, true)
     OR coalesce((p_document ->> 'idle_unlock_seconds')::numeric NOT BETWEEN 30 AND 3600, true)
     OR (p_document ->> 'password_complexity') IS NULL THEN
    PERFORM tenancy.refuse('security_policy_invalid', 'XC422');
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.check_security_policy(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.check_security_policy(jsonb) TO xcode_api_executor;
