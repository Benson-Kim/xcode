-- api.people_delete(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_user_id uuid, p_now timestamptz) RETURNS api.write_result
-- Purpose: delete a person nothing refers to: this organization's membership with its role, overrides, data scope and preferences (its invitations and pending notices go by their declared cascades), and the account too when it belongs to no other organization (its codes, devices, tokens, invitations and App Review login go by their declared cascades). Any other reference (change log or audit rows they wrote, revenue, petty cash, expenses, investments, targets, the sign-in log) refuses with in_use, so the person is to be blocked instead. Clears their email and mobile number from this organization's earlier people and sign-in history (tenancy.forget_contact_history; names stay), then logs one people change whose before is the person without them.
-- Callers: TenancyRoutines.delete_person; DeletePerson (DELETE /setup/people/{id}).
-- Reads: tenancy.memberships, identity.users, and what tenancy.person_in_view, tenancy.role_of, tenancy.person_snapshot and tenancy.belongs_elsewhere read. Writes: tenancy.permission_overrides, tenancy.data_scope_companies, tenancy.data_scope_vehicles, tenancy.data_scopes, tenancy.person_roles, tenancy.user_preferences, tenancy.memberships, identity.users, tenancy.change_log and tenancy.audit_events through tenancy.forget_contact_history, and through tenancy.record_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC403 people_self_delete, XC404 not_found, XC403 people_owner_edit, XC409 in_use.
-- Tests: tests/db/test_people_delete_routine.py, tests/api/test_person_delete.py.
-- Every column that refers to a person has a foreign key (tests/db/test_people_delete_routine.py
-- holds the list), so the deletes below refuse exactly when something still refers to them.

CREATE OR REPLACE FUNCTION api.people_delete(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_user_id uuid,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_member tenancy.memberships;
  v_name text;
  v_elsewhere boolean;
  v_before json;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'people.block');
  IF p_user_id = p_actor_id THEN
    PERFORM tenancy.refuse('people_self_delete', 'XC403');
  END IF;
  IF p_user_id IS NULL OR NOT tenancy.person_in_view(p_user_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  -- The membership NO KEY first, then the account, as every person write takes them: a sign-in
  -- holding the account takes KEY SHARE on the membership for its change-log row.
  SELECT m.* INTO v_member
  FROM tenancy.memberships AS m
  WHERE m.organization_id = p_organization_id AND m.user_id = p_user_id
  FOR NO KEY UPDATE;
  PERFORM identity.lock_user(p_user_id);
  IF lower(coalesce(tenancy.role_of(p_actor_id), '')) <> 'owner'
     AND lower(coalesce(tenancy.role_of(p_user_id), '')) = 'owner' THEN
    PERFORM tenancy.refuse('people_owner_edit', 'XC403');
  END IF;

  v_name := v_member.first_name || ' ' || v_member.last_name;
  v_elsewhere := tenancy.belongs_elsewhere(p_organization_id, p_user_id);
  v_before := tenancy.contactless_snapshot(tenancy.person_snapshot(p_user_id)::text)::json;

  DELETE FROM tenancy.permission_overrides
  WHERE organization_id = p_organization_id AND user_id = p_user_id;
  DELETE FROM tenancy.data_scope_companies
  WHERE organization_id = p_organization_id AND user_id = p_user_id;
  DELETE FROM tenancy.data_scope_vehicles
  WHERE organization_id = p_organization_id AND user_id = p_user_id;
  DELETE FROM tenancy.data_scopes
  WHERE organization_id = p_organization_id AND user_id = p_user_id;
  DELETE FROM tenancy.person_roles
  WHERE organization_id = p_organization_id AND user_id = p_user_id;
  DELETE FROM tenancy.user_preferences
  WHERE organization_id = p_organization_id AND user_id = p_user_id;
  BEGIN
    DELETE FROM tenancy.memberships
    WHERE organization_id = p_organization_id AND user_id = p_user_id;
    IF NOT v_elsewhere THEN
      DELETE FROM identity.users WHERE id = p_user_id;
    END IF;
  EXCEPTION
    WHEN foreign_key_violation THEN
      PERFORM tenancy.refuse('in_use', 'XC409', jsonb_build_object('name', v_name, 'use', 'person_records'));
  END;
  PERFORM tenancy.forget_contact_history(p_organization_id, p_user_id);

  PERFORM tenancy.record_change(
    'people', p_user_id, NULL, v_before, 'null'::json, 'Deleted ' || v_name,
    'person.deleted', p_user_id::text, v_before::jsonb, NULL, p_now
  );
  RETURN ROW(p_user_id, v_member.version + 1, 'updated')::api.write_result;
END;
$$;
