-- tenancy.enter_organization_as_operator(p_organization_id uuid) RETURNS void
-- Purpose: set only the transaction-local organization setting, so an operator routine can create or seed that organization's rows under row-level security.
-- Callers: api.ops_provision_user, api.ops_seed_demo.
-- Reads: nothing. Writes: nothing (a transaction-local setting only).
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py.

CREATE OR REPLACE FUNCTION tenancy.enter_organization_as_operator(p_organization_id uuid)
RETURNS void
LANGUAGE sql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT set_config('xcode.organization_id', p_organization_id::text, true);
  SELECT set_config('xcode.actor_id', '', true);
$$;

REVOKE ALL ON FUNCTION tenancy.enter_organization_as_operator(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.enter_organization_as_operator(uuid) TO xcode_api_executor;
