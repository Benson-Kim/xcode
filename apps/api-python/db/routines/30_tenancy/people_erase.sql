-- api.people_erase(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_user_id uuid, p_expected_version bigint, p_reason text, p_now timestamptz) RETURNS api.write_result
-- Purpose: erase a blocked person who belongs to this organization only (a typed reason required): the account loses its email, mobile number and PIN and is marked erased, the membership becomes Former member, this organization's people and sign-in history of the person loses their name and contact details, and device names, open codes, the live invitation, unsent sign-in notices and an App Review sign-in code go; money and history rows keep the id. Repeating on an erased person the actor can see answers unchanged without a version.
-- Callers: TenancyRoutines.erase_person; ErasePerson (POST /setup/people/{id}/erasure).
-- Reads: tenancy.memberships, identity.users, and what tenancy.person_in_view, tenancy.people_visible, tenancy.role_of and tenancy.belongs_elsewhere read. Writes: identity.users, tenancy.memberships, identity.trusted_devices, identity.refresh_tokens, identity.verification_codes, identity.invitations (revoked 'removed'), tenancy.sign_in_notices (pending ones dropped, without their address), identity.review_accounts through identity.erase_review_login, tenancy.change_log and tenancy.audit_events through tenancy.erase_person_history, and through tenancy.record_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 people_self_erase, XC404 not_found, XC403 people_owner_edit, XC422 people_erase_active, XC422 people_erase_shared, XC409 version_conflict, XC422 reason_length.
-- Tests: tests/db/test_erasure_routines.py, tests/db/test_fakes_match_routines.py, tests/api/test_person_erasure.py.

CREATE OR REPLACE FUNCTION api.people_erase(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_user_id uuid,
  p_expected_version bigint,
  p_reason text,
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
  v_reason text;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'people.block');
  IF p_user_id = p_actor_id THEN
    PERFORM tenancy.refuse('people_self_erase', 'XC422');
  END IF;
  IF p_user_id IS NULL
     OR NOT (
       tenancy.person_in_view(p_user_id)
       OR (
         EXISTS (SELECT 1 FROM identity.users AS u WHERE u.id = p_user_id AND u.erased_at IS NOT NULL)
         AND p_user_id IN (SELECT visible.id FROM tenancy.people_visible(p_actor_id) AS visible (id))
       )
     ) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  -- NO KEY: a sign-in routine holding this user's row writes a change-log row whose actor
  -- key check needs KEY SHARE on this membership; FOR UPDATE would deadlock with it.
  SELECT m.* INTO v_member
  FROM tenancy.memberships AS m
  WHERE m.organization_id = p_organization_id AND m.user_id = p_user_id
  FOR NO KEY UPDATE;
  -- Gone when a delete or erase held it meanwhile.
  IF NOT FOUND THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  PERFORM identity.lock_user(p_user_id);
  SELECT u.* INTO v_user FROM identity.users AS u WHERE u.id = p_user_id;
  IF v_user.erased_at IS NOT NULL THEN
    RETURN ROW(p_user_id, v_member.version, 'unchanged')::api.write_result;
  END IF;
  IF lower(coalesce(tenancy.role_of(p_actor_id), '')) <> 'owner'
     AND lower(coalesce(tenancy.role_of(p_user_id), '')) = 'owner' THEN
    PERFORM tenancy.refuse('people_owner_edit', 'XC403');
  END IF;
  IF v_member.active OR v_user.status <> 'removed' THEN
    PERFORM tenancy.refuse('people_erase_active', 'XC422');
  END IF;
  IF tenancy.belongs_elsewhere(p_organization_id, p_user_id) THEN
    PERFORM tenancy.refuse('people_erase_shared', 'XC422');
  END IF;
  IF p_expected_version IS NULL OR p_expected_version <> v_member.version THEN
    PERFORM tenancy.refuse('version_conflict', 'XC409');
  END IF;
  v_reason := tenancy.check_typed_reason(p_reason);
  IF v_reason IS NULL THEN
    PERFORM tenancy.refuse('reason_length', 'XC422');
  END IF;

  UPDATE identity.users
  SET erased_at = p_now,
      email = NULL,
      phone_number = NULL,
      pin_hash = NULL,
      pin_reset_required = false,
      security_version = security_version + 1,
      updated_at = p_now
  WHERE id = p_user_id;
  PERFORM identity.erase_review_login(p_user_id);
  -- Before the rename: the history rewrite reads the name it replaces from the membership.
  PERFORM tenancy.erase_person_history(p_organization_id, p_user_id);
  UPDATE tenancy.memberships
  SET first_name = 'Former', last_name = 'member', version = version + 1, updated_at = p_now
  WHERE organization_id = p_organization_id AND user_id = p_user_id AND version = p_expected_version;
  PERFORM identity.revoke_devices(p_user_id);
  PERFORM identity.revoke_tokens(p_user_id);
  UPDATE identity.trusted_devices SET name = 'Device', updated_at = p_now
  WHERE user_id = p_user_id AND name IS DISTINCT FROM 'Device';
  UPDATE identity.verification_codes SET consumed = true WHERE user_id = p_user_id AND NOT consumed;
  PERFORM identity.revoke_invitations(p_user_id, 'removed', p_now);
  UPDATE tenancy.sign_in_notices SET state = 'dropped', address = NULL
  WHERE organization_id = p_organization_id AND user_id = p_user_id AND state = 'pending';
  PERFORM identity.touch_version(p_user_id);
  PERFORM tenancy.record_change(
    'people', p_user_id, NULL, '{"Erased":false}'::json, '{"Erased":true}'::json,
    tenancy.compose_reason('Erased the personal details of a former member', v_reason),
    'person.erased', p_user_id::text, '{"erased":false}'::jsonb, '{"erased":true}'::jsonb, p_now
  );
  RETURN ROW(p_user_id, v_member.version + 1, 'updated')::api.write_result;
END;
$$;
