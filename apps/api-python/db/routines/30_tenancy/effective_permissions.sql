-- tenancy.effective_permissions(p_organization_id uuid, p_user_id uuid) RETURNS text[]
-- Purpose: the permissions a member holds now: for an active membership, tenancy.assigned_permissions plus every key outside the catalogue that one of them is a source of (the retired keys v2.11 phones still read) unless an override denies that key (no writer stores one since the catalogue change; a denial still wins), in catalogue order; {} otherwise. The resolution itself lives in tenancy.assigned_permissions alone.
-- Callers: tenancy.enter_organization, tenancy.has_permission, tenancy.require_any_permission, tenancy.check_person_grant, identity.policy_for (token claims).
-- Reads: tenancy.memberships, tenancy.permission_sources, tenancy.permissions, tenancy.permission_overrides, and through tenancy.assigned_permissions tenancy.person_roles, tenancy.roles, tenancy.role_defaults, tenancy.permission_overrides, tenancy.permission_dependencies. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_tenancy_helpers.py.
-- Reads tenant rows under row-level security: the organization setting must already name p_organization_id.

CREATE OR REPLACE FUNCTION tenancy.effective_permissions(p_organization_id uuid, p_user_id uuid)
RETURNS text[]
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
           WHEN EXISTS (
             SELECT 1
             FROM tenancy.memberships AS m
             WHERE m.organization_id = p_organization_id
               AND m.user_id = p_user_id
               AND m.active
           ) THEN (
             WITH assigned AS (
               SELECT held.key
               FROM unnest(tenancy.assigned_permissions(p_organization_id, p_user_id)) AS held (key)
             )
             SELECT coalesce(array_agg(p.key ORDER BY p.group_order, p.item_order), '{}'::text[])
             FROM tenancy.permissions AS p
             WHERE p.key IN (SELECT assigned.key FROM assigned)
                OR (
                  EXISTS (
                    SELECT 1
                    FROM tenancy.permission_sources AS s
                    WHERE s.permission = p.key
                      AND s.source IN (SELECT assigned.key FROM assigned)
                  )
                  AND NOT EXISTS (
                    SELECT 1
                    FROM tenancy.permission_overrides AS o
                    WHERE o.organization_id = p_organization_id
                      AND o.user_id = p_user_id
                      AND o.permission = p.key
                      AND NOT o.granted
                  )
                )
           )
           ELSE '{}'::text[]
         END;
$$;

REVOKE ALL ON FUNCTION tenancy.effective_permissions(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.effective_permissions(uuid, uuid) TO xcode_api_executor;
