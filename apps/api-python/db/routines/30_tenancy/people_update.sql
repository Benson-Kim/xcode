-- api.people_update(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_user_id uuid, p_first_name text, p_last_name text, p_email text, p_phone text, p_role text, p_scope_mode text, p_company_ids uuid[], p_vehicle_ids uuid[], p_permissions text[], p_approval_limit numeric, p_back_limit_mode text, p_back_limit_count integer, p_back_limit_from date, p_expected_version bigint, p_now timestamptz) RETURNS api.write_result
-- Purpose: change a visible person's name, sign-in details, role, single permissions, data scope, approval limit or how far back they may change records (unchanged when no mode is given) under the people rules; unchanged when nothing differs; a new email or number ends their sessions and devices.
-- Callers: TenancyRoutines.update_person; UpdatePerson (PUT /setup/people/{id}).
-- Reads: what tenancy.save_person reads. Writes: what tenancy.save_person writes.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC404 not_found, XC422 people_names_required via tenancy.save_person, XC422 people_email_invalid via tenancy.save_person, XC422 people_phone_invalid via tenancy.save_person, XC422 people_scope_mode via tenancy.save_person, XC422 people_scope_empty via tenancy.save_person, XC422 people_scope_duplicate via tenancy.save_person, XC422 people_permissions_invalid via tenancy.save_person, XC422 people_role_unknown via tenancy.save_person, XC422 people_back_limit_invalid via tenancy.save_person, XC422 people_back_limit_date_future via tenancy.save_person, XC422 people_version_required via tenancy.save_person, XC409 version_conflict via tenancy.save_person, XC403 people_all_companies_needs_all via tenancy.check_person_grant, XC422 people_companies_unknown via tenancy.check_person_grant, XC422 people_vehicles_unknown via tenancy.check_person_grant, XC403 people_companies_outside_scope via tenancy.check_person_grant, XC403 people_vehicles_outside_scope via tenancy.check_person_grant, XC403 people_hidden_scope_kind via tenancy.check_person_grant, XC422 people_self_edit via tenancy.check_person_grant, XC403 people_owner_grant via tenancy.check_person_grant, XC403 people_owner_edit via tenancy.check_person_grant, XC422 people_permission_unknown via tenancy.check_person_grant, XC403 people_role_not_held via tenancy.check_person_grant, XC403 people_access_manage_needed via tenancy.check_person_grant, XC403 people_permission_not_held via tenancy.check_person_grant, XC403 people_sign_in_scope via tenancy.check_person_grant, XC403 people_sign_in_holdings via tenancy.check_person_grant, XC422 people_contact_taken via tenancy.save_person.
-- Tests: tests/db/test_access_routines.py, tests/api/test_people.py.

CREATE OR REPLACE FUNCTION api.people_update(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_user_id uuid,
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
  p_expected_version bigint,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'people.edit');
  IF p_user_id IS NULL THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  RETURN tenancy.save_person(
    p_user_id, p_first_name, p_last_name, p_email, p_phone, p_role, p_scope_mode, p_company_ids,
    p_vehicle_ids, p_permissions, p_approval_limit, p_back_limit_mode, p_back_limit_count,
    p_back_limit_from, p_expected_version, p_now
  );
END;
$$;
