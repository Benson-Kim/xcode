-- api.account_state (user_id uuid, status text, pin_hash text, phone_number text, security_version integer, failed_attempts integer, untrusted_failed_attempts integer, pin_reset_required boolean, device_trusted boolean, policy jsonb)
-- Purpose: what a PIN check needs before the service verifies the PIN (hash, number, counters, forced reset, device trust, policy); policy is identity.policy as jsonb so every caller role can load it.
-- Callers: api.auth_account_lookup, api.auth_account_lookup_user; adapted to domain.identity.AccountState in db/types.py.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_auth_routines.py.
-- Created once; a changed type is a versioned migration that drops and recreates it with its dependants.

DO $$
BEGIN
  IF pg_catalog.to_regtype('api.account_state') IS NULL THEN
    CREATE TYPE api.account_state AS (
      user_id uuid,
      status text,
      pin_hash text,
      phone_number text,
      security_version integer,
      failed_attempts integer,
      untrusted_failed_attempts integer,
      pin_reset_required boolean,
      device_trusted boolean,
      policy jsonb
    );
  END IF;
END
$$;
