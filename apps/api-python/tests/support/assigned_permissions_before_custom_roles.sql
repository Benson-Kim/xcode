-- tenancy.assigned_permissions as it stood before custom roles (migration 0022), when every role read tenancy.role_defaults by name: the resolver of what each person could do on a database migrated only part way.

CREATE OR REPLACE FUNCTION tenancy.assigned_permissions(p_organization_id uuid, p_user_id uuid)
RETURNS text[]
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  WITH RECURSIVE
  member AS (
    SELECT m.organization_id, m.user_id
    FROM tenancy.memberships AS m
    WHERE m.organization_id = p_organization_id
      AND m.user_id = p_user_id
  ),
  overrides AS (
    SELECT o.permission, o.granted
    FROM member
    JOIN tenancy.permission_overrides AS o
      ON o.organization_id = member.organization_id AND o.user_id = member.user_id
  ),
  starting AS (
    SELECT d.permission
    FROM member
    JOIN tenancy.person_roles AS pr
      ON pr.organization_id = member.organization_id AND pr.user_id = member.user_id
    JOIN tenancy.roles AS r
      ON r.organization_id = pr.organization_id AND r.id = pr.role_id
    JOIN tenancy.role_defaults AS d
      ON lower(d.role_name) = lower(r.name)
    UNION
    SELECT overrides.permission FROM overrides WHERE overrides.granted
  ),
  expanded (permission) AS (
    SELECT starting.permission FROM starting
    UNION
    SELECT dep.needs
    FROM expanded
    JOIN tenancy.permission_dependencies AS dep ON dep.permission = expanded.permission
  ),
  held AS (
    SELECT expanded.permission FROM expanded
    EXCEPT
    SELECT overrides.permission FROM overrides WHERE NOT overrides.granted
  ),
  -- Removing keys whose direct dependencies are missing until nothing changes keeps exactly
  -- the keys whose transitive dependencies are all held.
  closure (root, permission) AS (
    SELECT held.permission, held.permission FROM held
    UNION
    SELECT closure.root, dep.needs
    FROM closure
    JOIN tenancy.permission_dependencies AS dep ON dep.permission = closure.permission
  )
  SELECT coalesce(array_agg(p.key ORDER BY p.group_order, p.item_order), '{}'::text[])
  FROM held
  JOIN tenancy.permissions AS p ON p.key = held.permission
  WHERE NOT EXISTS (
    SELECT 1
    FROM closure
    WHERE closure.root = held.permission
      AND closure.permission NOT IN (SELECT held_again.permission FROM held AS held_again)
  );
$$;

REVOKE ALL ON FUNCTION tenancy.assigned_permissions(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.assigned_permissions(uuid, uuid) TO xcode_api_executor;
