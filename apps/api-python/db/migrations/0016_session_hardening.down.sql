-- Reverse 0016: drop the windows' start index, the sign-out stamp, the rotation time and the superseded refusal; `db routines` of the release before restores api.auth_resolve_session without the token's issue time and the bodies that read the new columns.

SET LOCAL lock_timeout = '10s';

DROP FUNCTION IF EXISTS api.auth_resolve_session(uuid, text, integer, timestamptz, timestamptz);

DROP INDEX IF EXISTS ops.ix_rate_limit_windows_window_start;

DELETE FROM identity.sign_in_attempts WHERE refusal = 'refresh_superseded';

ALTER TABLE identity.sign_in_attempts
  DROP CONSTRAINT ck_sign_in_attempts_refusal,
  ADD CONSTRAINT ck_sign_in_attempts_refusal CHECK (refusal IN (
    'unknown_number', 'inactive', 'no_pin', 'wrong_pin', 'paused_untrusted', 'untrusted_cap',
    'wrong_code', 'code_expired', 'token_unknown', 'token_replayed', 'token_expired',
    'device_untrusted', 'policy_pin_length', 'locked', 'reset_required', 'pin_rule',
    'verdict_void', 'invite_invalid', 'invite_expired', 'invite_used', 'invite_revoked'
  ));

ALTER TABLE identity.refresh_tokens
  DROP CONSTRAINT ck_refresh_tokens_rotated,
  DROP COLUMN rotated_at;

ALTER TABLE identity.trusted_devices DROP COLUMN signed_out_at;
