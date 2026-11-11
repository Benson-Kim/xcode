-- api.people_invite(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_user_id uuid, p_token_hash text, p_code_hash text, p_now timestamptz) RETURNS api.write_result
-- Purpose: "Send the invitation again": a visible, active person without a PIN gets a new invitation (identity.invite, which revokes the live one as replaced); logged in the signIn section as "Invitation sent, {First Last}"; refused for a person with a PIN or without access.
-- Callers: TenancyRoutines.invite_person; InvitePerson (POST /setup/people/{id}/invitation).
-- Reads: tenancy.memberships, identity.users, and what tenancy.person_in_view, tenancy.role_of and tenancy.sign_in_snapshot read. Writes: identity.invitations, and through tenancy.record_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 people_self_sign_in, XC404 not_found, XC403 people_owner_edit, XC422 people_invite_not_needed.
-- Tests: tests/db/test_invitations.py.

CREATE OR REPLACE FUNCTION api.people_invite(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_user_id uuid,
  p_token_hash text,
  p_code_hash text,
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
  v_user identity.users;
  v_snapshot json;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'people.sign_in');
  IF p_user_id = p_actor_id THEN
    PERFORM tenancy.refuse('people_self_sign_in', 'XC422');
  END IF;
  IF p_user_id IS NULL OR NOT tenancy.person_in_view(p_user_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  IF lower(coalesce(tenancy.role_of(p_actor_id), '')) <> 'owner'
     AND lower(coalesce(tenancy.role_of(p_user_id), '')) = 'owner' THEN
    PERFORM tenancy.refuse('people_owner_edit', 'XC403');
  END IF;
  -- NO KEY, then the user row: the order of every people routine.
  SELECT m.* INTO v_member
  FROM tenancy.memberships AS m
  WHERE m.organization_id = p_organization_id AND m.user_id = p_user_id
  FOR NO KEY UPDATE;
  v_user := identity.lock_user(p_user_id);
  IF v_user.pin_hash IS NOT NULL OR v_user.status <> 'active' OR NOT v_member.active THEN
    PERFORM tenancy.refuse('people_invite_not_needed', 'XC422');
  END IF;

  PERFORM identity.invite(p_user_id, p_organization_id, p_actor_id, p_token_hash, p_code_hash, p_now);
  v_snapshot := tenancy.sign_in_snapshot(p_user_id, p_now);
  PERFORM tenancy.record_change(
    'signIn', p_user_id, NULL, v_snapshot, v_snapshot,
    'Invitation sent, ' || v_member.first_name || ' ' || v_member.last_name,
    'person.invited', p_user_id::text, v_snapshot::jsonb, v_snapshot::jsonb, p_now
  );
  RETURN ROW(p_user_id, v_member.version, 'updated')::api.write_result;
END;
$$;
