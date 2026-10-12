-- identity.log_sign_in(p_user_id uuid, p_actor_id uuid, p_phrases text[], p_before json, p_now timestamptz) RETURNS bigint
-- Purpose: write one signIn change-log row for a person's PIN or device event: enter the person's organization as the actor, join the phrases with "; ", add ", {First Last}" of the person when someone else acted, and record the snapshot before (p_before) and now; NULL with nothing written when the person has no active membership.
-- Callers: identity.count_wrong_pin, api.auth_verify_device, api.auth_check_code, api.auth_complete_pin, api.auth_change_pin, api.auth_device_remove, api.auth_revoke_device, and the people sign-in actions.
-- Reads: tenancy.memberships, and what tenancy.sign_in_snapshot and tenancy.record_change read. Writes: what tenancy.record_change writes.
-- Raises: none (the organization exists and the actor is a member, so tenancy.record_change cannot refuse).
-- Tests: tests/db/test_auth_routines.py.

CREATE OR REPLACE FUNCTION identity.log_sign_in(
  p_user_id uuid,
  p_actor_id uuid,
  p_phrases text[],
  p_before json,
  p_now timestamptz
)
RETURNS bigint
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := identity.active_organization(p_user_id);
  v_reason text := array_to_string(p_phrases, '; ');
  v_name text;
  v_after json;
BEGIN
  IF v_organization_id IS NULL OR cardinality(p_phrases) = 0 THEN
    RETURN NULL;
  END IF;
  PERFORM set_config('xcode.organization_id', v_organization_id::text, true);
  PERFORM set_config('xcode.actor_id', p_actor_id::text, true);
  -- A change-log row needs a request id; the routines always set one, a direct call may not.
  PERFORM set_config('xcode.request_id', coalesce(tenancy.current_request(), '-'), true);
  IF p_actor_id <> p_user_id THEN
    SELECT m.first_name || ' ' || m.last_name INTO v_name
    FROM tenancy.memberships AS m
    WHERE m.organization_id = v_organization_id AND m.user_id = p_user_id;
    v_reason := v_reason || ', ' || v_name;
  END IF;
  v_after := tenancy.sign_in_snapshot(p_user_id, p_now);
  RETURN tenancy.record_change(
    'signIn', p_user_id, NULL, p_before, v_after, v_reason, 'person.sign_in', p_user_id::text,
    p_before::jsonb, v_after::jsonb, p_now
  );
END;
$$;

REVOKE ALL ON FUNCTION identity.log_sign_in(uuid, uuid, text[], json, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.log_sign_in(uuid, uuid, text[], json, timestamptz) TO xcode_api_executor;
