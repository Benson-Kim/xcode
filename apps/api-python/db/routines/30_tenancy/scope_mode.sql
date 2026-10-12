-- tenancy.scope_mode(p_organization_id uuid, p_user_id uuid) RETURNS text
-- Purpose: a person's data scope mode as the wire shows it: all when the all-companies row is set, else companies when any company row exists, else vehicles.
-- Callers: the people documents and snapshots.
-- Reads: tenancy.data_scopes, tenancy.data_scope_companies. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.scope_mode(p_organization_id uuid, p_user_id uuid)
RETURNS text
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
           WHEN EXISTS (
             SELECT 1 FROM tenancy.data_scopes AS s
             WHERE s.organization_id = p_organization_id
               AND s.user_id = p_user_id
               AND s.all_companies
           ) THEN 'all'
           WHEN EXISTS (
             SELECT 1 FROM tenancy.data_scope_companies AS c
             WHERE c.organization_id = p_organization_id AND c.user_id = p_user_id
           ) THEN 'companies'
           ELSE 'vehicles'
         END;
$$;

REVOKE ALL ON FUNCTION tenancy.scope_mode(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.scope_mode(uuid, uuid) TO xcode_api_executor;
