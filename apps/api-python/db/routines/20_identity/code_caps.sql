-- identity.code_caps(p_user_id uuid, p_skip_cooldown boolean, p_replacement boolean, p_now timestamptz) RETURNS boolean
-- Purpose: whether a new code may be issued to the person, across purposes and devices: false while a non-withdrawn code is under a minute old (not for a replacement after three wrong tries, nor with development codes), or with five in the last hour or ten in the last day; superseded and voided codes count, withdrawn ones do not.
-- Callers: identity.issue_code.
-- Reads: identity.verification_codes. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.code_caps(
  p_user_id uuid,
  p_skip_cooldown boolean,
  p_replacement boolean,
  p_now timestamptz
)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  WITH counted AS (
    -- A withdrawn code (consumed with expires_at = created_at) counts for nothing.
    SELECT c.created_at
    FROM identity.verification_codes AS c
    WHERE c.user_id = p_user_id
      AND NOT (c.consumed AND c.expires_at <= c.created_at)
      AND c.created_at > p_now - interval '1 day'
  )
  SELECT NOT (
    (
      NOT coalesce(p_skip_cooldown, false)
      AND NOT coalesce(p_replacement, false)
      AND EXISTS (SELECT 1 FROM counted WHERE counted.created_at + interval '1 minute' > p_now)
    )
    OR (SELECT count(*) FROM counted WHERE counted.created_at > p_now - interval '1 hour') >= 5
    OR (SELECT count(*) FROM counted) >= 10
  );
$$;

REVOKE ALL ON FUNCTION identity.code_caps(uuid, boolean, boolean, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.code_caps(uuid, boolean, boolean, timestamptz) TO xcode_api_executor;
