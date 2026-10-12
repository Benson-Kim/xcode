-- tenancy.person_in_view(p_user_id uuid) RETURNS boolean
-- Purpose: whether the current actor may see this person: a member of the current organization with a role, among tenancy.people_visible of the actor.
-- Callers: api.people_get, tenancy.save_person, api.people_set_active, api.people_sign_out.
-- Reads: tenancy.person_roles, and what tenancy.people_visible reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_access_routines.py.

CREATE OR REPLACE FUNCTION tenancy.person_in_view(p_user_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT EXISTS (
    SELECT 1
    FROM tenancy.person_roles AS pr
    WHERE pr.organization_id = tenancy.current_organization()
      AND pr.user_id = p_user_id
      AND p_user_id IN (
        SELECT visible.id FROM tenancy.people_visible(tenancy.current_actor()) AS visible (id)
      )
  );
$$;

REVOKE ALL ON FUNCTION tenancy.person_in_view(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.person_in_view(uuid) TO xcode_api_executor;
