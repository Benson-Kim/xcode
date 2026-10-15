-- api.people_pin_reset(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_user_id uuid, p_now timestamptz) RETURNS api.write_result
-- Purpose: "Make [name] reset the PIN": at once, a visible person's every trusted device, refresh token and unused code is removed, their access tokens stop (security version), and their next sign-in sends a reset code instead of asking for the PIN; logged in the signIn section as "PIN reset required, {First Last}"; unchanged for a person without a PIN or with a reset already due.
-- Callers: TenancyRoutines.require_pin_reset; RequirePersonPinReset (POST /setup/people/{id}/pin-reset).
-- Reads: tenancy.memberships, identity.users, and what tenancy.person_in_view, tenancy.role_of and tenancy.sign_in_snapshot read. Writes: identity.users, identity.trusted_devices, identity.refresh_tokens, identity.verification_codes, and through tenancy.record_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 people_self_sign_in, XC404 not_found, XC403 people_owner_edit.
-- Tests: tests/db/test_access_routines.py, tests/api/test_people.py.

CREATE OR REPLACE FUNCTION api.people_pin_reset(
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
  v_user identity.users;
  v_before json;
  v_after json;
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
  -- NO KEY, then the user row: the order of every people routine (sign-in events hold the user
  -- row and take KEY SHARE on a membership for their change-log row).
  SELECT m.* INTO v_member
  FROM tenancy.memberships AS m
  WHERE m.organization_id = p_organization_id AND m.user_id = p_user_id
  FOR NO KEY UPDATE;
  v_user := identity.lock_user(p_user_id);
  IF v_user.pin_hash IS NULL OR v_user.pin_reset_required THEN
    RETURN ROW(p_user_id, v_member.version, 'unchanged')::api.write_result;
  END IF;

  v_before := tenancy.sign_in_snapshot(p_user_id, p_now);
  PERFORM identity.remove_devices(p_user_id, p_now);
  UPDATE identity.users
  SET pin_reset_required = true,
      security_version = security_version + 1,
      updated_at = p_now
  WHERE id = p_user_id;
  PERFORM identity.touch_version(p_user_id);
  v_after := tenancy.sign_in_snapshot(p_user_id, p_now);
  PERFORM tenancy.record_change(
    'signIn', p_user_id, NULL, v_before, v_after,
    'PIN reset required, ' || v_member.first_name || ' ' || v_member.last_name,
    'person.pin_reset_required', p_user_id::text, v_before::jsonb, v_after::jsonb, p_now
  );
  RETURN ROW(p_user_id, v_member.version, 'updated')::api.write_result;
END;
$$;
