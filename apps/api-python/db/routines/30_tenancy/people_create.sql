-- api.people_create(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_first_name text, p_last_name text, p_email text, p_phone text, p_role text, p_scope_mode text, p_company_ids uuid[], p_vehicle_ids uuid[], p_permissions text[], p_approval_limit numeric, p_back_limit_mode text, p_back_limit_count integer, p_back_limit_from date, p_invite_token_hash text, p_invite_code_hash text, p_now timestamptz) RETURNS api.write_result
-- Purpose: add a person (active, no PIN yet) with a role, a data scope, single permissions and how far back they may change records (7 days when no mode is given), under the people rules, and invite them (identity.invite) when an invitation hash is given; id is the new user id.
-- Callers: TenancyRoutines.create_person; CreatePerson (POST /setup/people).
-- Reads: what tenancy.save_person and identity.invite read. Writes: what tenancy.save_person and identity.invite write.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 people_names_required via tenancy.save_person, XC422 people_email_invalid via tenancy.save_person, XC422 people_phone_invalid via tenancy.save_person, XC422 people_scope_mode via tenancy.save_person, XC422 people_scope_empty via tenancy.save_person, XC422 people_scope_duplicate via tenancy.save_person, XC422 people_permissions_invalid via tenancy.save_person, XC422 people_role_unknown via tenancy.save_person, XC422 people_back_limit_invalid via tenancy.save_person, XC422 people_back_limit_date_future via tenancy.save_person, XC403 people_all_companies_needs_all via tenancy.check_person_grant, XC422 people_companies_unknown via tenancy.check_person_grant, XC422 people_vehicles_unknown via tenancy.check_person_grant, XC403 people_companies_outside_scope via tenancy.check_person_grant, XC403 people_vehicles_outside_scope via tenancy.check_person_grant, XC403 people_owner_grant via tenancy.check_person_grant, XC422 people_permission_unknown via tenancy.check_person_grant, XC403 people_role_not_held via tenancy.check_person_grant, XC403 people_access_manage_needed via tenancy.check_person_grant, XC403 people_permission_not_held via tenancy.check_person_grant, XC422 people_contact_taken via tenancy.save_person.
-- Tests: tests/db/test_access_routines.py, tests/db/test_invitations.py, tests/api/test_people.py.

CREATE OR REPLACE FUNCTION api.people_create(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_first_name text,
  p_last_name text,
  p_email text,
  p_phone text,
  p_role text,
  p_scope_mode text,
  p_company_ids uuid[],
  p_vehicle_ids uuid[],
  p_permissions text[],
  p_approval_limit numeric,
  p_back_limit_mode text,
  p_back_limit_count integer,
  p_back_limit_from date,
  p_invite_token_hash text,
  p_invite_code_hash text,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_result api.write_result;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'people.add');
  v_result := tenancy.save_person(
    NULL, p_first_name, p_last_name, p_email, p_phone, p_role, p_scope_mode, p_company_ids,
    p_vehicle_ids, p_permissions, p_approval_limit, p_back_limit_mode, p_back_limit_count,
    p_back_limit_from, NULL, p_now
  );
  IF p_invite_token_hash IS NOT NULL OR p_invite_code_hash IS NOT NULL THEN
    PERFORM identity.invite(
      v_result.id, p_organization_id, p_actor_id, p_invite_token_hash, p_invite_code_hash, p_now
    );
  END IF;
  RETURN v_result;
END;
$$;
