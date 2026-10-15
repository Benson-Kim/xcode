-- Sign-in of the design notes v2.33: forced reset, last sign-in, the wrong-PIN lock as a counter, hashed device tokens with name and use dates, the sign-in history words, the signIn change-log section, a 15-minute idle unlock.

SET LOCAL lock_timeout = '10s';

-- Routines whose signature or row type changes; `db routines` creates the new ones.
DROP FUNCTION IF EXISTS api.auth_account_lookup(text, text, text, timestamptz);
DROP FUNCTION IF EXISTS api.auth_verify_device(text, text, text, text, text, integer, timestamptz);
DROP FUNCTION IF EXISTS api.auth_verify_code(text, text, text, text, text, timestamptz);
DROP FUNCTION IF EXISTS api.auth_complete_pin(
  text, text, text, text, text, integer, text, text, integer, timestamptz
);
DROP FUNCTION IF EXISTS identity.device_trusted(uuid, text, timestamptz);
DROP FUNCTION IF EXISTS identity.trust_device(uuid, text, integer, timestamptz);
DROP FUNCTION IF EXISTS identity.code_caps(uuid, text, boolean, timestamptz);
DROP FUNCTION IF EXISTS identity.matching_code(uuid, text, text, text, timestamptz);
DROP FUNCTION IF EXISTS identity.issue_session(uuid, text, text, identity.policy, timestamptz);
DROP TYPE IF EXISTS api.account_state;
DROP TYPE IF EXISTS identity.code_check;

ALTER TABLE identity.users
  ADD COLUMN pin_reset_required boolean NOT NULL DEFAULT false,
  ADD COLUMN last_signed_in_at timestamptz;

-- The timed pause becomes the lock: a pause still running is a lock on every device, a lapsed
-- one is cleared, and both counters stop at five.
DO $$
DECLARE
  v_paused bigint;
  v_lapsed bigint;
  v_clamped bigint;
  v_locked_before bigint;
  v_locked_after bigint;
BEGIN
  SELECT count(*) INTO v_paused FROM identity.users WHERE paused_until > now();
  SELECT count(*) INTO v_lapsed FROM identity.users WHERE paused_until <= now();
  SELECT count(*) INTO v_locked_before
  FROM identity.users
  WHERE paused_until > now() OR (paused_until IS NULL AND failed_attempts >= 5);

  UPDATE identity.users
  SET failed_attempts = CASE
        WHEN paused_until > now() THEN 5
        WHEN paused_until IS NOT NULL THEN 0
        ELSE least(failed_attempts, 5)
      END,
      untrusted_failed_attempts = least(untrusted_failed_attempts, 5)
  WHERE paused_until IS NOT NULL OR failed_attempts > 5 OR untrusted_failed_attempts > 5;
  GET DIAGNOSTICS v_clamped = ROW_COUNT;

  SELECT count(*) INTO v_locked_after FROM identity.users WHERE failed_attempts = 5;
  RAISE NOTICE 'identity.users: % paused -> locked, % lapsed -> cleared, % rows changed',
    v_paused, v_lapsed, v_clamped;
  IF v_locked_after <> v_locked_before THEN
    RAISE EXCEPTION 'expected % accounts locked on every device, found %', v_locked_before, v_locked_after;
  END IF;
END
$$;

ALTER TABLE identity.users
  DROP COLUMN paused_until,
  DROP CONSTRAINT ck_users_failed_attempts,
  DROP CONSTRAINT ck_users_untrusted_failed_attempts,
  ADD CONSTRAINT ck_users_failed_attempts CHECK (failed_attempts BETWEEN 0 AND 5),
  ADD CONSTRAINT ck_users_untrusted_failed_attempts CHECK (untrusted_failed_attempts BETWEEN 0 AND 5);

ALTER TABLE identity.trusted_devices
  ADD COLUMN token_hash text,
  ADD COLUMN name text,
  ADD COLUMN trusted_at timestamptz,
  ADD COLUMN last_used_at timestamptz,
  ADD COLUMN remembered boolean NOT NULL DEFAULT true;

-- Every existing row was trusted by its device id (v2.11); it was last used when its newest
-- refresh token was issued.
DO $$
DECLARE
  v_devices bigint;
  v_filled bigint;
BEGIN
  SELECT count(*) INTO v_devices FROM identity.trusted_devices;
  UPDATE identity.trusted_devices AS d
  SET trusted_at = d.created_at,
      last_used_at = coalesce(
        (SELECT max(t.created_at)
         FROM identity.refresh_tokens AS t
         WHERE t.user_id = d.user_id AND t.device_id = d.device_id),
        d.updated_at
      );
  GET DIAGNOSTICS v_filled = ROW_COUNT;
  RAISE NOTICE 'identity.trusted_devices: % rows given trusted_at and last_used_at', v_filled;
  IF v_filled <> v_devices
     OR EXISTS (
       SELECT 1 FROM identity.trusted_devices WHERE trusted_at IS NULL OR last_used_at IS NULL
     ) THEN
    RAISE EXCEPTION 'expected % trusted devices with both dates, filled %', v_devices, v_filled;
  END IF;
END
$$;

ALTER TABLE identity.trusted_devices
  ALTER COLUMN trusted_at SET NOT NULL,
  ALTER COLUMN last_used_at SET NOT NULL,
  ADD CONSTRAINT ck_trusted_devices_token_hash CHECK (token_hash ~ '^[0-9A-F]{64}$'),
  ADD CONSTRAINT ck_trusted_devices_name CHECK (name ~ '^[A-Za-z0-9][A-Za-z0-9 .()+-]{0,59}$'),
  ADD CONSTRAINT ck_trusted_devices_remembered CHECK (remembered OR token_hash IS NULL);

CREATE UNIQUE INDEX uq_trusted_devices_token
  ON identity.trusted_devices (token_hash) WHERE token_hash IS NOT NULL;

ALTER TABLE identity.sign_in_attempts
  DROP CONSTRAINT ck_sign_in_attempts_operation,
  DROP CONSTRAINT ck_sign_in_attempts_outcome,
  DROP CONSTRAINT ck_sign_in_attempts_refusal,
  ADD CONSTRAINT ck_sign_in_attempts_operation CHECK (operation IN (
    'sign_in', 'verify_device', 'request_code', 'verify_code', 'complete_pin', 'refresh',
    'sign_out', 'revoke_device', 'start', 'pin', 'code', 'resend_code', 'forgot_pin', 'new_pin',
    'change_pin', 'remove_device'
  )),
  ADD CONSTRAINT ck_sign_in_attempts_outcome CHECK (outcome IN (
    'authenticated', 'verification_required', 'check_email', 'code_verified', 'paused',
    'refused', 'signed_out', 'device_revoked', 'pin_required', 'pin_locked', 'blocked',
    'code_resent', 'pin_changed'
  )),
  ADD CONSTRAINT ck_sign_in_attempts_refusal CHECK (refusal IN (
    'unknown_number', 'inactive', 'no_pin', 'wrong_pin', 'paused_untrusted', 'untrusted_cap',
    'wrong_code', 'code_expired', 'token_unknown', 'token_replayed', 'token_expired',
    'device_untrusted', 'policy_pin_length', 'locked', 'reset_required', 'pin_rule',
    'verdict_void'
  ));

-- The tries an unknown number has made: the simulated account of the number step.
CREATE INDEX ix_sign_in_attempts_unknown
  ON identity.sign_in_attempts (phone_digest, occurred_at DESC) WHERE user_id IS NULL;

ALTER TABLE tenancy.change_log
  DROP CONSTRAINT ck_change_log_section,
  ADD CONSTRAINT ck_change_log_section CHECK (section IN (
    'companies', 'vehicles', 'investment', 'expenses', 'recurring', 'people', 'revenue',
    'organization', 'businessDate', 'localization', 'branding', 'securityPolicy', 'logo',
    'signIn'
  ));

-- New organizations ask for the PIN again after 15 minutes idle; saved policies keep theirs.
ALTER TABLE tenancy.organization_security_policies
  ALTER COLUMN idle_unlock_seconds SET DEFAULT 900;
