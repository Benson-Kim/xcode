-- identity.invitation_delivery(p_invitation identity.invitations) RETURNS jsonb
-- Purpose: what the invitation email needs, in snake_case: invitation_id, email, first_name, organization_name, inviter_name (NULL when the inviter has no membership there), support_email (NULL when unset), expires_at and the organization's time_zone.
-- Callers: api.invite_delivery_start, api.invite_claim_undelivered.
-- Reads: identity.users, tenancy.memberships, tenancy.organizations, tenancy.organization_brandings, tenancy.organization_localizations. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_invitations.py.

CREATE OR REPLACE FUNCTION identity.invitation_delivery(p_invitation identity.invitations)
RETURNS jsonb
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT jsonb_build_object(
    'invitation_id', p_invitation.id,
    'email', u.email,
    'first_name', m.first_name,
    'organization_name', o.name,
    'inviter_name', (
      SELECT im.first_name || ' ' || im.last_name
      FROM tenancy.memberships AS im
      WHERE im.organization_id = p_invitation.organization_id AND im.user_id = p_invitation.invited_by
    ),
    'support_email', b.support_email,
    'expires_at', p_invitation.expires_at,
    'time_zone', coalesce(l.time_zone, 'Africa/Nairobi')
  )
  FROM identity.users AS u
  JOIN tenancy.memberships AS m
    ON m.organization_id = p_invitation.organization_id AND m.user_id = u.id
  JOIN tenancy.organizations AS o ON o.id = p_invitation.organization_id
  LEFT JOIN tenancy.organization_brandings AS b ON b.organization_id = o.id
  LEFT JOIN tenancy.organization_localizations AS l ON l.organization_id = o.id
  WHERE u.id = p_invitation.user_id;
$$;

REVOKE ALL ON FUNCTION identity.invitation_delivery(identity.invitations) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.invitation_delivery(identity.invitations) TO xcode_api_executor;
