-- tenancy.seed_roles(p_organization_id uuid) RETURNS void
-- Purpose: insert the four catalog roles (Owner, Office admin, Fleet manager, Revenue clerk) the organization lacks, matched ignoring case.
-- Callers: api.ops_provision_user, api.ops_seed_demo (the organization setting must name p_organization_id).
-- Reads: tenancy.roles. Writes: tenancy.roles.
-- Raises: none.
-- Tests: tests/db/test_tenancy_helpers.py, tests/db/test_ops_routines.py.

CREATE OR REPLACE FUNCTION tenancy.seed_roles(p_organization_id uuid)
RETURNS void
LANGUAGE sql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
  INSERT INTO tenancy.roles (organization_id, name)
  SELECT p_organization_id, catalog.name
  FROM unnest(ARRAY['Owner', 'Office admin', 'Fleet manager', 'Revenue clerk'])
         WITH ORDINALITY AS catalog (name, ord)
  WHERE NOT EXISTS (
    SELECT 1 FROM tenancy.roles AS r
    WHERE r.organization_id = p_organization_id AND lower(r.name) = lower(catalog.name)
  )
  ORDER BY catalog.ord;
$$;

REVOKE ALL ON FUNCTION tenancy.seed_roles(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.seed_roles(uuid) TO xcode_api_executor;
