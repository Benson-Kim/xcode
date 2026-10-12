-- api.people_sign_out(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_user_id uuid, p_now timestamptz) RETURNS api.write_result
-- Purpose: "Remove all": remove every trusted device of a visible person with their refresh tokens and unused codes (their access tokens fail session resolution at once) and log it in the signIn section as "Trusted device removed, {First Last}"; unchanged when no live device or refresh token is left.
-- Callers: TenancyRoutines.sign_out_person; SignOutPerson (POST /setup/people/{id}/sign-out).
-- Reads: tenancy.memberships, identity.users, identity.trusted_devices, identity.refresh_tokens, and what tenancy.person_in_view, tenancy.role_of and tenancy.sign_in_snapshot read. Writes: identity.trusted_devices, identity.refresh_tokens, identity.verification_codes, and through tenancy.record_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 people_self_sign_out, XC404 not_found, XC403 people_owner_edit.
-- Tests: tests/db/test_access_routines.py, tests/api/test_people.py.

CREATE OR REPLACE FUNCTION api.people_sign_out(
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
  v_before json;
  v_after json;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'people.sign_in');
  IF p_user_id = p_actor_id THEN
    PERFORM tenancy.refuse('people_self_sign_out', 'XC422');
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
  PERFORM identity.lock_user(p_user_id);

  IF NOT EXISTS (
       SELECT 1 FROM identity.trusted_devices AS d
       WHERE d.user_id = p_user_id AND identity.device_live(d, p_now)
     )
     AND NOT EXISTS (
       SELECT 1 FROM identity.refresh_tokens AS t
       WHERE t.user_id = p_user_id AND NOT t.revoked AND t.expires_at > p_now
     ) THEN
    RETURN ROW(p_user_id, v_member.version, 'unchanged')::api.write_result;
  END IF;

  v_before := tenancy.sign_in_snapshot(p_user_id, p_now);
  PERFORM identity.remove_devices(p_user_id, p_now);
  v_after := tenancy.sign_in_snapshot(p_user_id, p_now);
  PERFORM tenancy.record_change(
    'signIn', p_user_id, NULL, v_before, v_after,
    'Trusted device removed, ' || v_member.first_name || ' ' || v_member.last_name,
    'person.sessions_revoked', p_user_id::text, v_before::jsonb, v_after::jsonb, p_now
  );
  RETURN ROW(p_user_id, v_member.version, 'updated')::api.write_result;
END;
$$;
