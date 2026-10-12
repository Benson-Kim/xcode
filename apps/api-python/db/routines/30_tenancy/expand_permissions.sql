-- tenancy.expand_permissions(p_keys text[]) RETURNS text[]
-- Purpose: the catalogue keys among p_keys together with every permission they need, transitively, in catalogue order; keys outside the catalogue (unknown, retired or hidden) are left out.
-- Callers: tenancy.role_permissions, tenancy.check_person_grant, tenancy.save_person.
-- Reads: tenancy.permissions, tenancy.permission_dependencies. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_access_routines.py.

CREATE OR REPLACE FUNCTION tenancy.expand_permissions(p_keys text[])
RETURNS text[]
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  WITH RECURSIVE expanded (permission) AS (
    SELECT requested.key FROM unnest(p_keys) AS requested (key)
    UNION
    SELECT dep.needs
    FROM expanded
    JOIN tenancy.permission_dependencies AS dep ON dep.permission = expanded.permission
  )
  SELECT coalesce(array_agg(p.key ORDER BY p.group_order, p.item_order), '{}'::text[])
  FROM tenancy.permissions AS p
  WHERE p.catalogue
    AND p.key IN (SELECT expanded.permission FROM expanded);
$$;

REVOKE ALL ON FUNCTION tenancy.expand_permissions(text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.expand_permissions(text[]) TO xcode_api_executor;
