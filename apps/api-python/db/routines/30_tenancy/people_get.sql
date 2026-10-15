-- api.people_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_user_id uuid, p_now timestamptz) RETURNS jsonb
-- Purpose: one person document with its sign-in pane (tenancy.person_sign_in), when the actor may see that person.
-- Callers: TenancyRoutines.get_person; GetPerson (GET /setup/people/{id}).
-- Reads: what tenancy.person_in_view, tenancy.person_reach, tenancy.person_document and tenancy.person_sign_in read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC404 not_found.
-- Tests: tests/db/test_access_routines.py, tests/api/test_people.py.

CREATE OR REPLACE FUNCTION api.people_get(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_user_id uuid,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'people.view');
  IF p_user_id IS NULL OR NOT tenancy.person_in_view(p_user_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  RETURN tenancy.person_document(p_user_id, tenancy.person_reach(p_actor_id))
         || jsonb_build_object('sign_in', tenancy.person_sign_in(p_user_id, p_now));
END;
$$;
