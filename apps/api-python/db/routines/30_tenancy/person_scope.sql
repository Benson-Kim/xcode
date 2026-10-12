-- tenancy.person_scope(p_user_id uuid) RETURNS tenancy.scope
-- Purpose: a person's data scope rows in the current organization: the all-companies flag and the company and vehicle ids (sorted; empty arrays when none).
-- Callers: tenancy.actor_scope, tenancy.person_reach, tenancy.person_document, tenancy.check_person_grant, tenancy.save_person.
-- Reads: tenancy.data_scopes, tenancy.data_scope_companies, tenancy.data_scope_vehicles. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_tenancy_helpers.py, tests/db/test_access_routines.py.

CREATE OR REPLACE FUNCTION tenancy.person_scope(p_user_id uuid)
RETURNS tenancy.scope
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT ROW(
    coalesce(
      (SELECT s.all_companies
       FROM tenancy.data_scopes AS s
       WHERE s.organization_id = tenancy.current_organization()
         AND s.user_id = p_user_id),
      false
    ),
    coalesce(
      (SELECT array_agg(c.company_id ORDER BY c.company_id)
       FROM tenancy.data_scope_companies AS c
       WHERE c.organization_id = tenancy.current_organization()
         AND c.user_id = p_user_id),
      '{}'::uuid[]
    ),
    coalesce(
      (SELECT array_agg(v.vehicle_id ORDER BY v.vehicle_id)
       FROM tenancy.data_scope_vehicles AS v
       WHERE v.organization_id = tenancy.current_organization()
         AND v.user_id = p_user_id),
      '{}'::uuid[]
    )
  )::tenancy.scope;
$$;

REVOKE ALL ON FUNCTION tenancy.person_scope(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.person_scope(uuid) TO xcode_api_executor;
