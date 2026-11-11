-- Session hardening: the shared rate limiter's windows gain an index on their start, so each hit can sweep the windows of keys not seen for a day; a sign-out on a remembered device stamps the device row so the access tokens issued before it stop working; a rotated refresh token keeps the time of its rotation so a replay from the same device within 30 seconds is told it was superseded instead of ending the device's session; the sign-in history gains that refusal; api.auth_resolve_session gains the token's issue time.

SET LOCAL lock_timeout = '10s';

ALTER TABLE identity.trusted_devices ADD COLUMN signed_out_at timestamptz;

ALTER TABLE identity.refresh_tokens
  ADD COLUMN rotated_at timestamptz,
  ADD CONSTRAINT ck_refresh_tokens_rotated CHECK (rotated_at IS NULL OR revoked);

ALTER TABLE identity.sign_in_attempts
  DROP CONSTRAINT ck_sign_in_attempts_refusal,
  ADD CONSTRAINT ck_sign_in_attempts_refusal CHECK (refusal IN (
    'unknown_number', 'inactive', 'no_pin', 'wrong_pin', 'paused_untrusted', 'untrusted_cap',
    'wrong_code', 'code_expired', 'token_unknown', 'token_replayed', 'token_expired',
    'device_untrusted', 'policy_pin_length', 'locked', 'reset_required', 'pin_rule',
    'verdict_void', 'invite_invalid', 'invite_expired', 'invite_used', 'invite_revoked',
    'refresh_superseded'
  ));

DROP FUNCTION IF EXISTS api.auth_resolve_session(uuid, text, integer, timestamptz);

CREATE INDEX ix_rate_limit_windows_window_start ON ops.rate_limit_windows (window_start);
