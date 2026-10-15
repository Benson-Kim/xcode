-- identity.mask_email(p_email text) RETURNS text
-- Purpose: the masked address of verification_required: the first character, ***, then everything from the first @; *** alone when there is no @ or it comes first.
-- Callers: api.auth_sign_in.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.mask_email(p_email text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
           WHEN p_email IS NULL OR strpos(p_email, '@') <= 1 THEN '***'
           ELSE left(p_email, 1) || '***' || substr(p_email, strpos(p_email, '@'))
         END;
$$;

REVOKE ALL ON FUNCTION identity.mask_email(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.mask_email(text) TO xcode_api_executor;
