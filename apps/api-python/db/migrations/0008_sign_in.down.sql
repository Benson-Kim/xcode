-- Reverse of 0008_sign_in.sql. A lock becomes a pause of 15 minutes from now; history and change-log rows written with the new words stay, under constraints restored as NOT VALID.

SET LOCAL lock_timeout = '10s';

DROP FUNCTION IF EXISTS api.auth_account_lookup(text, text, text, text, boolean, timestamptz);
DROP FUNCTION IF EXISTS api.auth_account_lookup_user(text, uuid, text, timestamptz);
DROP FUNCTION IF EXISTS api.auth_start(text, text, text, text, text, boolean, timestamptz);
DROP FUNCTION IF EXISTS api.auth_pin(
  text, text, text, text, boolean, text, text, text, boolean, timestamptz
);
DROP FUNCTION IF EXISTS api.auth_check_code(
  text, text, text, text, text, text, text, boolean, text, text, integer, timestamptz
);
DROP FUNCTION IF EXISTS api.auth_resend_code(text, text, text, text, text, boolean, timestamptz);
DROP FUNCTION IF EXISTS api.auth_change_pin(text, uuid, text, boolean, text, text, timestamptz);
DROP FUNCTION IF EXISTS api.auth_device_list(uuid, text, timestamptz);
DROP FUNCTION IF EXISTS api.auth_device_remove(text, uuid, uuid, timestamptz);
DROP FUNCTION IF EXISTS api.auth_verify_device(text, text, text, text, text, text, integer, timestamptz);
DROP FUNCTION IF EXISTS api.auth_verify_code(text, text, text, text, text, text, timestamptz);
DROP FUNCTION IF EXISTS api.auth_complete_pin(
  text, text, text, text, text, boolean, text, text, text, boolean, text, text, integer, timestamptz
);
DROP FUNCTION IF EXISTS identity.device_trusted(uuid, text, text, timestamptz);
DROP FUNCTION IF EXISTS identity.trust_device(uuid, text, text, text, boolean, integer, timestamptz);
DROP FUNCTION IF EXISTS identity.code_caps(uuid, boolean, boolean, timestamptz);
DROP FUNCTION IF EXISTS identity.matching_code(uuid, text, text, text, timestamptz);
DROP FUNCTION IF EXISTS identity.issue_session(uuid, text, text, identity.policy, boolean, timestamptz);
DROP FUNCTION IF EXISTS identity.device_live(identity.trusted_devices, timestamptz);
DROP FUNCTION IF EXISTS identity.locked_for(identity.users, boolean);
DROP FUNCTION IF EXISTS identity.count_wrong_pin(identity.users, boolean, timestamptz);
DROP FUNCTION IF EXISTS identity.sign_in_status(identity.users, boolean);
DROP FUNCTION IF EXISTS identity.remove_devices(uuid, timestamptz, uuid);
DROP TYPE IF EXISTS api.account_state;
DROP TYPE IF EXISTS identity.code_check;

ALTER TABLE tenancy.organization_security_policies
  ALTER COLUMN idle_unlock_seconds SET DEFAULT 300;

ALTER TABLE tenancy.change_log
  DROP CONSTRAINT ck_change_log_section,
  ADD CONSTRAINT ck_change_log_section CHECK (section IN (
    'companies', 'vehicles', 'investment', 'expenses', 'recurring', 'people', 'revenue',
    'organization', 'businessDate', 'localization', 'branding', 'securityPolicy', 'logo'
  )) NOT VALID;

DROP INDEX identity.ix_sign_in_attempts_unknown;
ALTER TABLE identity.sign_in_attempts
  DROP CONSTRAINT ck_sign_in_attempts_operation,
  DROP CONSTRAINT ck_sign_in_attempts_outcome,
  DROP CONSTRAINT ck_sign_in_attempts_refusal,
  ADD CONSTRAINT ck_sign_in_attempts_operation CHECK (operation IN (
    'sign_in', 'verify_device', 'request_code', 'verify_code', 'complete_pin', 'refresh',
    'sign_out', 'revoke_device'
  )) NOT VALID,
  ADD CONSTRAINT ck_sign_in_attempts_outcome CHECK (outcome IN (
    'authenticated', 'verification_required', 'check_email', 'code_verified', 'paused',
    'refused', 'signed_out', 'device_revoked'
  )) NOT VALID,
  ADD CONSTRAINT ck_sign_in_attempts_refusal CHECK (refusal IN (
    'unknown_number', 'inactive', 'no_pin', 'wrong_pin', 'paused_untrusted', 'untrusted_cap',
    'wrong_code', 'code_expired', 'token_unknown', 'token_replayed', 'token_expired',
    'device_untrusted', 'policy_pin_length'
  )) NOT VALID;

-- A device trusted with a token, or not remembered, was not trusted under the old model.
UPDATE identity.trusted_devices SET revoked = true WHERE token_hash IS NOT NULL OR NOT remembered;
DROP INDEX identity.uq_trusted_devices_token;
ALTER TABLE identity.trusted_devices
  DROP COLUMN token_hash,
  DROP COLUMN name,
  DROP COLUMN trusted_at,
  DROP COLUMN last_used_at,
  DROP COLUMN remembered;

ALTER TABLE identity.users
  DROP CONSTRAINT ck_users_failed_attempts,
  DROP CONSTRAINT ck_users_untrusted_failed_attempts,
  ADD CONSTRAINT ck_users_failed_attempts CHECK (failed_attempts >= 0),
  ADD CONSTRAINT ck_users_untrusted_failed_attempts CHECK (untrusted_failed_attempts >= 0),
  ADD COLUMN paused_until timestamptz;
UPDATE identity.users SET paused_until = now() + interval '15 minutes' WHERE failed_attempts >= 5;
ALTER TABLE identity.users
  DROP COLUMN pin_reset_required,
  DROP COLUMN last_signed_in_at;
