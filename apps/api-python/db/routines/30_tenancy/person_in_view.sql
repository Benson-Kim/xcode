-- tenancy.person_in_view(p_user_id uuid) RETURNS boolean
-- Purpose: whether the current actor may see this person: a member of the current organization with a role whose account is not erased, among tenancy.people_visible of the actor.
-- Callers: api.people_get, tenancy.save_person, api.people_set_active, api.people_sign_out, api.people_erase.
-- Reads: tenancy.person_roles, identity.users, and what tenancy.people_visible reads. Writes: nothing.
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
      AND NOT EXISTS (
        SELECT 1 FROM identity.users AS u WHERE u.id = p_user_id AND u.erased_at IS NOT NULL
      )
  );
$$;

REVOKE ALL ON FUNCTION tenancy.person_in_view(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.person_in_view(uuid) TO xcode_api_executor;
