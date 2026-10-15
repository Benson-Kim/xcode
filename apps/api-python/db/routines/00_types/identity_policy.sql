-- identity.policy (organization_id uuid, pin_length integer, lockout_threshold integer, lockout_minutes integer, access_token_minutes integer, refresh_token_days integer, role_name text, first_name text, last_name text, permissions text[])
-- Purpose: the clamped security policy and token claims of a user's single active membership.
-- Callers: identity.policy_for and the api.auth_* routines that count wrong PINs or issue tokens.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.
-- Created once; a changed type is a versioned migration that drops and recreates it with its dependants.

DO $$
BEGIN
  IF pg_catalog.to_regtype('identity.policy') IS NULL THEN
    CREATE TYPE identity.policy AS (
      organization_id uuid,
      pin_length integer,
      lockout_threshold integer,
      lockout_minutes integer,
      access_token_minutes integer,
      refresh_token_days integer,
      role_name text,
      first_name text,
      last_name text,
      permissions text[]
    );
  END IF;
END
$$;
