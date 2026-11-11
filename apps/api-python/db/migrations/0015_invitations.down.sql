-- Reverse 0015: drop the invitation routines, the invitations and the invitation words of the sign-in history; `db routines` of the release before restores the old people_create, people_update and person_document and the bodies that read invitations.

SET LOCAL lock_timeout = '10s';

DROP FUNCTION IF EXISTS api.auth_invite_redeem(text, text, text, text, text, timestamptz);
DROP FUNCTION IF EXISTS api.people_invite(uuid, uuid, text, uuid, text, text, timestamptz);
DROP FUNCTION IF EXISTS api.invite_delivery_start(text, timestamptz);
DROP FUNCTION IF EXISTS api.invite_delivery_result(text, boolean, timestamptz);
DROP FUNCTION IF EXISTS api.invite_claim_undelivered(timestamptz, integer, text[], text[]);
DROP FUNCTION IF EXISTS api.people_create(
  uuid, uuid, text, text, text, text, text, text, text, uuid[], uuid[], text[], numeric, text,
  integer, date, text, text, timestamptz
);
DROP FUNCTION IF EXISTS api.people_update(
  uuid, uuid, text, uuid, text, text, text, text, text, text, uuid[], uuid[], text[], numeric,
  text, integer, date, bigint, text, text, timestamptz
);
DROP FUNCTION IF EXISTS tenancy.person_document(uuid, tenancy.scope, timestamptz);
DROP FUNCTION IF EXISTS identity.usable_invitation(uuid, timestamptz);
DROP FUNCTION IF EXISTS identity.invitation_delivery(identity.invitations);
DROP FUNCTION IF EXISTS identity.invite(uuid, uuid, uuid, text, text, timestamptz);
DROP FUNCTION IF EXISTS identity.revoke_invitations(uuid, text, timestamptz);
DROP FUNCTION IF EXISTS identity.people_status(identity.users, boolean, timestamptz);
DROP FUNCTION IF EXISTS identity.invitation_status(uuid, timestamptz);
DROP FUNCTION IF EXISTS identity.invitation_org(text);
DROP FUNCTION IF EXISTS identity.invitation_tries();
DROP FUNCTION IF EXISTS identity.invitation_sends();
DROP FUNCTION IF EXISTS identity.store_code(uuid, text, text, text, timestamptz);

DELETE FROM identity.sign_in_attempts
WHERE operation = 'invite_redeem'
   OR refusal IN ('invite_invalid', 'invite_expired', 'invite_used', 'invite_revoked');

ALTER TABLE identity.sign_in_attempts
  DROP CONSTRAINT ck_sign_in_attempts_operation,
  DROP CONSTRAINT ck_sign_in_attempts_refusal,
  ADD CONSTRAINT ck_sign_in_attempts_operation CHECK (operation IN (
    'sign_in', 'verify_device', 'request_code', 'verify_code', 'complete_pin', 'refresh',
    'sign_out', 'revoke_device', 'start', 'pin', 'code', 'resend_code', 'forgot_pin', 'new_pin',
    'change_pin', 'remove_device'
  )),
  ADD CONSTRAINT ck_sign_in_attempts_refusal CHECK (refusal IN (
    'unknown_number', 'inactive', 'no_pin', 'wrong_pin', 'paused_untrusted', 'untrusted_cap',
    'wrong_code', 'code_expired', 'token_unknown', 'token_replayed', 'token_expired',
    'device_untrusted', 'policy_pin_length', 'locked', 'reset_required', 'pin_rule',
    'verdict_void'
  ));

DROP TABLE identity.invitations;
