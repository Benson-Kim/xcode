-- api.people_set_active(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_user_id uuid, p_active boolean, p_expected_version bigint, p_reason text, p_now timestamptz) RETURNS api.write_result
-- Purpose: deactivate (membership inactive, user removed, sessions and devices ended; a typed reason required) or reactivate a visible person; repeating a finished transition answers unchanged without a version.
-- Callers: TenancyRoutines.set_person_active; SetPersonActive (POST /setup/people/{id}/activate, /deactivate).
-- Reads: tenancy.memberships, identity.users, and what tenancy.person_in_view and tenancy.role_of read. Writes: tenancy.memberships, identity.users, identity.trusted_devices, identity.refresh_tokens, and through tenancy.record_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 people_self_deactivate, XC404 not_found, XC403 people_owner_edit, XC409 version_conflict, XC422 reason_length.
-- Tests: tests/db/test_access_routines.py, tests/api/test_people.py.

CREATE OR REPLACE FUNCTION api.people_set_active(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_user_id uuid,
  p_active boolean,
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
  v_reason text;
  v_name text;
  v_before json;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'people.block');
  IF p_user_id = p_actor_id THEN
    PERFORM tenancy.refuse('people_self_deactivate', 'XC422');
  END IF;
  IF p_user_id IS NULL OR p_active IS NULL OR NOT tenancy.person_in_view(p_user_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  -- NO KEY: a sign-in routine holding this user's row writes a change-log row whose actor
  -- key check needs KEY SHARE on this membership; FOR UPDATE would deadlock with it.
  SELECT m.* INTO v_member
  FROM tenancy.memberships AS m
  WHERE m.organization_id = p_organization_id AND m.user_id = p_user_id
  FOR NO KEY UPDATE;
  PERFORM identity.lock_user(p_user_id);
  IF lower(coalesce(tenancy.role_of(p_actor_id), '')) <> 'owner'
     AND lower(coalesce(tenancy.role_of(p_user_id), '')) = 'owner' THEN
    PERFORM tenancy.refuse('people_owner_edit', 'XC403');
  END IF;
  IF v_member.active = p_active THEN
    RETURN ROW(p_user_id, v_member.version, 'unchanged')::api.write_result;
  END IF;
  IF p_expected_version IS NULL OR p_expected_version <> v_member.version THEN
    PERFORM tenancy.refuse('version_conflict', 'XC409');
  END IF;

  IF NOT p_active THEN
    v_reason := tenancy.check_typed_reason(p_reason);
    IF v_reason IS NULL THEN
      PERFORM tenancy.refuse('reason_length', 'XC422');
    END IF;
  END IF;

  v_name := v_member.first_name || ' ' || v_member.last_name;
  v_before := tenancy.person_snapshot(p_user_id);
  UPDATE tenancy.memberships
  SET active = p_active, version = version + 1, updated_at = p_now
  WHERE organization_id = p_organization_id AND user_id = p_user_id AND version = p_expected_version;

  IF p_active THEN
    UPDATE identity.users SET status = 'active', updated_at = p_now WHERE id = p_user_id;
    PERFORM identity.touch_version(p_user_id);
    PERFORM tenancy.record_change(
      'people', p_user_id, NULL, v_before, tenancy.person_snapshot(p_user_id),
      'Restored access for ' || v_name,
      'person.activated', p_user_id::text, v_before::jsonb,
      tenancy.person_snapshot(p_user_id)::jsonb, p_now
    );
  ELSE
    UPDATE identity.users
    SET status = 'removed', security_version = security_version + 1, updated_at = p_now
    WHERE id = p_user_id;
    PERFORM identity.revoke_devices(p_user_id);
    PERFORM identity.revoke_tokens(p_user_id);
    PERFORM identity.touch_version(p_user_id);
    PERFORM tenancy.record_change(
      'people', p_user_id, NULL, v_before, tenancy.person_snapshot(p_user_id),
      tenancy.compose_reason('Removed access for ' || v_name, v_reason),
      'person.deactivated', p_user_id::text, v_before::jsonb,
      tenancy.person_snapshot(p_user_id)::jsonb, p_now
    );
  END IF;
  RETURN ROW(p_user_id, v_member.version + 1, 'updated')::api.write_result;
END;
$$;
