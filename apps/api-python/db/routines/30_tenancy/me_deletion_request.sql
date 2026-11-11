-- api.me_deletion_request(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_now timestamptz) RETURNS jsonb
-- Purpose: the member's own "Delete my account". Records the request once in the people section
--   (audit action person.deletion_requested) and returns, for notifying the administrators who can
--   block and erase members, the requester's and organization's names and the recipients (active
--   members with an active account who hold people.block, the requester excluded). A repeat within
--   24 hours is a no-op: it records nothing and returns no recipients, so the reply is the same and
--   the administrators' inbox cannot be flooded. The requester's membership row is locked first, so
--   two requests at once serialise and the second sees the first's audit row.
-- Callers: TenancyRoutines.request_account_deletion; RequestMyAccountDeletion (POST /setup/me/deletion-request).
-- Reads: tenancy.audit_events, tenancy.memberships, tenancy.organizations, identity.users, and what
--   tenancy.effective_permissions reads.
-- Writes: on the first request only, through tenancy.record_change tenancy.change_log,
--   tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization.
-- Tests: tests/db/test_deletion_routines.py, tests/api/test_account_deletion.py.

CREATE OR REPLACE FUNCTION api.me_deletion_request(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_member tenancy.memberships;
  v_organization_name text;
  v_recipients jsonb;
  v_snapshot jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);

  -- Lock the requester's own membership first: two requests at once serialise here, so the
  -- second reads the first's audit row and the 24-hour check below makes it a no-op.
  SELECT m.* INTO v_member
  FROM tenancy.memberships AS m
  WHERE m.organization_id = p_organization_id AND m.user_id = p_actor_id
  FOR NO KEY UPDATE;

  SELECT o.name INTO v_organization_name
  FROM tenancy.organizations AS o
  WHERE o.id = p_organization_id;

  IF EXISTS (
    SELECT 1 FROM tenancy.audit_events AS a
    WHERE a.organization_id = p_organization_id
      AND a.actor_id = p_actor_id
      AND a.action = 'person.deletion_requested'
      AND a.occurred_at > p_now - interval '24 hours'
  ) THEN
    RETURN jsonb_build_object(
      'recorded', false,
      'requester_name', v_member.first_name || ' ' || v_member.last_name,
      'organization_name', v_organization_name,
      'recipients', '[]'::jsonb
    );
  END IF;

  SELECT coalesce(
           jsonb_agg(
             jsonb_build_object('email', u.email, 'first_name', m.first_name)
             ORDER BY m.last_name, m.first_name, m.user_id),
           '[]'::jsonb)
  INTO v_recipients
  FROM tenancy.memberships AS m
  JOIN identity.users AS u ON u.id = m.user_id
  WHERE m.organization_id = p_organization_id
    AND m.active
    AND m.user_id <> p_actor_id
    AND u.status = 'active'
    AND 'people.block' = ANY (tenancy.effective_permissions(p_organization_id, m.user_id));

  v_snapshot := jsonb_build_object('user_id', p_actor_id, 'requested_at', p_now);
  PERFORM tenancy.record_change(
    'people', p_actor_id, NULL, v_snapshot::json, v_snapshot::json,
    'Account deletion requested, ' || v_member.first_name || ' ' || v_member.last_name,
    'person.deletion_requested', p_actor_id::text, v_snapshot, v_snapshot, p_now
  );

  RETURN jsonb_build_object(
    'recorded', true,
    'requester_name', v_member.first_name || ' ' || v_member.last_name,
    'organization_name', v_organization_name,
    'recipients', v_recipients
  );
END;
$$;
