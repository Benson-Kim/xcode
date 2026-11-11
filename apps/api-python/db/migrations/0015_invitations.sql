-- Invitations: the emailed link and code that let a person added without a PIN choose one, the sign-in history words of redeeming it, the people_create and people_update signatures that gain the invitation hashes, and person_document, which gains the clock.

SET LOCAL lock_timeout = '10s';

CREATE TABLE identity.invitations (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  user_id uuid NOT NULL,
  invited_by uuid,
  token_hash text NOT NULL,
  code_hash text NOT NULL,
  created_at timestamptz NOT NULL,
  expires_at timestamptz NOT NULL,
  failed_attempts integer NOT NULL DEFAULT 0,
  accepted_at timestamptz,
  revoked_at timestamptz,
  revoke_reason text,
  delivery_state text NOT NULL DEFAULT 'pending',
  delivery_attempts integer NOT NULL DEFAULT 0,
  attempted_at timestamptz,
  sent_at timestamptz,
  CONSTRAINT pk_invitations PRIMARY KEY (id),
  CONSTRAINT fk_invitations_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id) ON DELETE CASCADE,
  CONSTRAINT fk_invitations_user FOREIGN KEY (user_id)
    REFERENCES identity.users (id) ON DELETE CASCADE,
  CONSTRAINT fk_invitations_membership FOREIGN KEY (organization_id, user_id)
    REFERENCES tenancy.memberships (organization_id, user_id) ON DELETE CASCADE,
  CONSTRAINT fk_invitations_invited_by FOREIGN KEY (invited_by)
    REFERENCES identity.users (id) ON DELETE SET NULL,
  CONSTRAINT ck_invitations_token_hash CHECK (token_hash ~ '^[0-9A-F]{64}$'),
  CONSTRAINT ck_invitations_code_hash CHECK (code_hash ~ '^[0-9A-F]{64}$'),
  CONSTRAINT ck_invitations_lifetime CHECK (expires_at > created_at),
  CONSTRAINT ck_invitations_failed_attempts CHECK (failed_attempts >= 0),
  CONSTRAINT ck_invitations_delivery_attempts CHECK (delivery_attempts >= 0),
  CONSTRAINT ck_invitations_revoke_reason CHECK (revoke_reason IN (
    'replaced', 'blocked', 'removed', 'email_changed'
  )),
  CONSTRAINT ck_invitations_revoked CHECK ((revoked_at IS NULL) = (revoke_reason IS NULL)),
  CONSTRAINT ck_invitations_one_end CHECK (accepted_at IS NULL OR revoked_at IS NULL),
  CONSTRAINT ck_invitations_delivery_state CHECK (delivery_state IN ('pending', 'sent', 'failed')),
  CONSTRAINT ck_invitations_sent CHECK ((delivery_state = 'sent') = (sent_at IS NOT NULL))
);

-- One live invitation per person; a new one first revokes the old as 'replaced'.
CREATE UNIQUE INDEX uq_invitations_live
  ON identity.invitations (user_id) WHERE accepted_at IS NULL AND revoked_at IS NULL;

CREATE UNIQUE INDEX uq_invitations_token ON identity.invitations (token_hash);

-- The sweep that mails what a crash or a failed send left behind.
CREATE INDEX ix_invitations_undelivered
  ON identity.invitations (created_at)
  WHERE delivery_state = 'pending' AND accepted_at IS NULL AND revoked_at IS NULL;

CREATE INDEX ix_invitations_organization ON identity.invitations (organization_id);

CREATE INDEX ix_invitations_invited_by ON identity.invitations (invited_by) WHERE invited_by IS NOT NULL;

ALTER TABLE identity.invitations ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON identity.invitations TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());

REVOKE ALL ON identity.invitations FROM PUBLIC, xcode_api_executor;
GRANT SELECT, INSERT, UPDATE ON identity.invitations TO xcode_api_executor;

ALTER TABLE identity.sign_in_attempts
  DROP CONSTRAINT ck_sign_in_attempts_operation,
  DROP CONSTRAINT ck_sign_in_attempts_refusal,
  ADD CONSTRAINT ck_sign_in_attempts_operation CHECK (operation IN (
    'sign_in', 'verify_device', 'request_code', 'verify_code', 'complete_pin', 'refresh',
    'sign_out', 'revoke_device', 'start', 'pin', 'code', 'resend_code', 'forgot_pin', 'new_pin',
    'change_pin', 'remove_device', 'invite_redeem'
  )),
  ADD CONSTRAINT ck_sign_in_attempts_refusal CHECK (refusal IN (
    'unknown_number', 'inactive', 'no_pin', 'wrong_pin', 'paused_untrusted', 'untrusted_cap',
    'wrong_code', 'code_expired', 'token_unknown', 'token_replayed', 'token_expired',
    'device_untrusted', 'policy_pin_length', 'locked', 'reset_required', 'pin_rule',
    'verdict_void', 'invite_invalid', 'invite_expired', 'invite_used', 'invite_revoked'
  ));

DROP FUNCTION IF EXISTS tenancy.person_document(uuid, tenancy.scope);
DROP FUNCTION IF EXISTS api.people_create(
  uuid, uuid, text, text, text, text, text, text, text, uuid[], uuid[], text[], numeric, text,
  integer, date, timestamptz
);
DROP FUNCTION IF EXISTS api.people_update(
  uuid, uuid, text, uuid, text, text, text, text, text, text, uuid[], uuid[], text[], numeric,
  text, integer, date, bigint, timestamptz
);
