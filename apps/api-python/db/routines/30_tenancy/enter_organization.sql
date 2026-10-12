-- tenancy.enter_organization(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_permission text DEFAULT NULL) RETURNS void
-- Purpose: set the transaction-local organization, actor and request settings, then require an active membership and, when named, the permission.
-- Callers: the first statement of every tenant-scoped api.* routine.
-- Reads: tenancy.memberships, and what tenancy.effective_permissions reads. Writes: nothing (transaction-local settings only).
-- Raises: XC403 not_member, XC403 permission_missing.
-- Tests: tests/db/test_tenancy_helpers.py, tests/db/test_tenancy_isolation.py.

CREATE OR REPLACE FUNCTION tenancy.enter_organization(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_permission text DEFAULT NULL
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF p_actor_id IS NULL OR p_organization_id IS NULL OR p_request_id IS NULL THEN
    PERFORM tenancy.refuse('not_member', 'XC403');
  END IF;
  PERFORM set_config('xcode.organization_id', p_organization_id::text, true);
  PERFORM set_config('xcode.actor_id', p_actor_id::text, true);
  PERFORM set_config('xcode.request_id', p_request_id, true);
  IF NOT EXISTS (
    SELECT 1
    FROM tenancy.memberships AS m
    WHERE m.organization_id = p_organization_id
      AND m.user_id = p_actor_id
      AND m.active
  ) THEN
    PERFORM tenancy.refuse('not_member', 'XC403');
  END IF;
  IF p_permission IS NOT NULL
     AND NOT p_permission = ANY (tenancy.effective_permissions(p_organization_id, p_actor_id)) THEN
    PERFORM tenancy.refuse('permission_missing', 'XC403');
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.enter_organization(uuid, uuid, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.enter_organization(uuid, uuid, text, text) TO xcode_api_executor;
