-- tenancy.person_reach(p_user_id uuid) RETURNS tenancy.scope
-- Purpose: what a person reaches in the current organization: the all-companies flag, their companies, and their vehicles together with every vehicle of their companies (ids sorted).
-- Callers: tenancy.person_document (what a viewer is shown), tenancy.check_person_grant (what an editor may hand on), api.people_list, api.people_get, api.history_list (people redaction).
-- Reads: setup.fleet_vehicles, and what tenancy.person_scope reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_access_routines.py.

CREATE OR REPLACE FUNCTION tenancy.person_reach(p_user_id uuid)
RETURNS tenancy.scope
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_scope tenancy.scope := tenancy.person_scope(p_user_id);
BEGIN
  RETURN ROW(
    v_scope.all_companies,
    v_scope.company_ids,
    coalesce(
      (SELECT array_agg(reached.id ORDER BY reached.id)
       FROM (
         SELECT own.id FROM unnest(v_scope.vehicle_ids) AS own (id)
         UNION
         SELECT f.id
         FROM setup.fleet_vehicles AS f
         WHERE f.organization_id = tenancy.current_organization()
           AND f.company_id = ANY (v_scope.company_ids)
       ) AS reached),
      '{}'::uuid[]
    )
  )::tenancy.scope;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.person_reach(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.person_reach(uuid) TO xcode_api_executor;
