-- identity.code_check (code_id uuid, refusal text, voided boolean, tries_left integer)
-- Purpose: the verdict on a presented verification code: the matching code's id, or the refusal (wrong_code, code_expired) whether this wrong try voided the code (the third), and the tries left on it after a wrong try.
-- Callers: identity.matching_code and the api.auth_* routines that check codes.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.
-- Created once; a changed type is a versioned migration that drops and recreates it with its dependants.

DO $$
BEGIN
  IF pg_catalog.to_regtype('identity.code_check') IS NULL THEN
    CREATE TYPE identity.code_check AS (
      code_id uuid,
      refusal text,
      voided boolean,
      tries_left integer
    );
  END IF;
END
$$;
