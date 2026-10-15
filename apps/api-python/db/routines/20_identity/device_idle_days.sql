-- identity.device_idle_days() RETURNS integer
-- Purpose: the days a trusted device stays live after its last use (90); the twin of domain.policies.TRUSTED_DEVICE_IDLE_DAYS, parity-tested.
-- Callers: identity.device_live.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.device_idle_days()
RETURNS integer
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT 90;
$$;

REVOKE ALL ON FUNCTION identity.device_idle_days() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.device_idle_days() TO xcode_api_executor;
