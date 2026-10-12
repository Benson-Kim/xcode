-- Identity tables: users, verification_codes, trusted_devices, refresh_tokens, sign_in_attempts; ops.touch_updated_at().

SET LOCAL lock_timeout = '10s';

-- Fills updated_at when an UPDATE left it unchanged; a routine that sets it (from p_now) wins.
CREATE FUNCTION ops.touch_updated_at() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF NEW.updated_at IS NOT DISTINCT FROM OLD.updated_at THEN
    NEW.updated_at := pg_catalog.now();
  END IF;
  RETURN NEW;
END
$$;

REVOKE ALL ON FUNCTION ops.touch_updated_at() FROM PUBLIC;

CREATE TABLE identity.users (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  email text NOT NULL,
  phone_number text NOT NULL,
  pin_hash text,
  status text NOT NULL DEFAULT 'active',
  security_version integer NOT NULL DEFAULT 0,
  failed_attempts integer NOT NULL DEFAULT 0,
  paused_until timestamptz,
  untrusted_failed_attempts integer NOT NULL DEFAULT 0,
  version bigint NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_users PRIMARY KEY (id),
  CONSTRAINT uq_users_email UNIQUE (email),
  CONSTRAINT uq_users_phone_number UNIQUE (phone_number),
  CONSTRAINT ck_users_email CHECK (char_length(email) <= 320 AND email = lower(email)),
  CONSTRAINT ck_users_phone_number CHECK (phone_number ~ '^\+254[17][0-9]{8}$'),
  CONSTRAINT ck_users_pin_hash CHECK (pin_hash ~ '^[A-Za-z0-9+/]+=*\.[A-Za-z0-9+/]+=*$'),
  CONSTRAINT ck_users_status CHECK (status IN ('active', 'removed')),
  CONSTRAINT ck_users_security_version CHECK (security_version >= 0),
  CONSTRAINT ck_users_failed_attempts CHECK (failed_attempts >= 0),
  CONSTRAINT ck_users_untrusted_failed_attempts CHECK (untrusted_failed_attempts >= 0)
);

CREATE TABLE identity.verification_codes (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  purpose text NOT NULL,
  device_id text NOT NULL,
  code_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  consumed boolean NOT NULL DEFAULT false,
  failed_attempts integer NOT NULL DEFAULT 0,
  CONSTRAINT pk_verification_codes PRIMARY KEY (id),
  CONSTRAINT fk_verification_codes_user FOREIGN KEY (user_id)
    REFERENCES identity.users (id) ON DELETE CASCADE,
  CONSTRAINT ck_verification_codes_purpose CHECK (purpose IN ('first_setup', 'new_device', 'pin_reset')),
  CONSTRAINT ck_verification_codes_device_id CHECK (char_length(device_id) BETWEEN 1 AND 128),
  CONSTRAINT ck_verification_codes_code_hash CHECK (code_hash ~ '^[0-9A-F]{64}$'),
  CONSTRAINT ck_verification_codes_failed_attempts CHECK (failed_attempts >= 0)
);

CREATE INDEX ix_verification_codes_user_purpose_created
  ON identity.verification_codes (user_id, purpose, created_at DESC);

CREATE TABLE identity.trusted_devices (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  device_id text NOT NULL,
  revoked boolean NOT NULL DEFAULT false,
  trust_expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_trusted_devices PRIMARY KEY (id),
  CONSTRAINT fk_trusted_devices_user FOREIGN KEY (user_id)
    REFERENCES identity.users (id) ON DELETE CASCADE,
  CONSTRAINT uq_trusted_devices_user_device UNIQUE (user_id, device_id),
  CONSTRAINT ck_trusted_devices_device_id CHECK (char_length(device_id) BETWEEN 1 AND 128)
);

CREATE TABLE identity.refresh_tokens (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  device_id text NOT NULL,
  token_hash text NOT NULL,
  expires_at timestamptz NOT NULL,
  revoked boolean NOT NULL DEFAULT false,
  version bigint NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_refresh_tokens PRIMARY KEY (id),
  CONSTRAINT fk_refresh_tokens_user FOREIGN KEY (user_id)
    REFERENCES identity.users (id) ON DELETE CASCADE,
  CONSTRAINT uq_refresh_tokens_token_hash UNIQUE (token_hash),
  CONSTRAINT ck_refresh_tokens_device_id CHECK (char_length(device_id) BETWEEN 1 AND 128),
  CONSTRAINT ck_refresh_tokens_token_hash CHECK (token_hash ~ '^[0-9A-F]{64}$')
);

CREATE INDEX ix_refresh_tokens_user_device ON identity.refresh_tokens (user_id, device_id);

CREATE TABLE identity.sign_in_attempts (
  id bigint GENERATED ALWAYS AS IDENTITY,
  occurred_at timestamptz NOT NULL,
  operation text NOT NULL,
  outcome text NOT NULL,
  refusal text,
  user_id uuid,
  phone_digest text NOT NULL,
  device_id text NOT NULL,
  request_id text,
  CONSTRAINT pk_sign_in_attempts PRIMARY KEY (id),
  CONSTRAINT fk_sign_in_attempts_user FOREIGN KEY (user_id) REFERENCES identity.users (id),
  CONSTRAINT ck_sign_in_attempts_operation CHECK (operation IN (
    'sign_in', 'verify_device', 'request_code', 'verify_code', 'complete_pin', 'refresh',
    'sign_out', 'revoke_device'
  )),
  CONSTRAINT ck_sign_in_attempts_outcome CHECK (outcome IN (
    'authenticated', 'verification_required', 'check_email', 'code_verified', 'paused',
    'refused', 'signed_out', 'device_revoked'
  )),
  CONSTRAINT ck_sign_in_attempts_refusal CHECK (refusal IN (
    'unknown_number', 'inactive', 'no_pin', 'wrong_pin', 'paused_untrusted', 'untrusted_cap',
    'wrong_code', 'code_expired', 'token_unknown', 'token_replayed', 'token_expired',
    'device_untrusted', 'policy_pin_length'
  )),
  CONSTRAINT ck_sign_in_attempts_device_id CHECK (char_length(device_id) <= 128),
  CONSTRAINT ck_sign_in_attempts_request_id CHECK (char_length(request_id) <= 128)
);

CREATE INDEX ix_sign_in_attempts_user_occurred ON identity.sign_in_attempts (user_id, occurred_at DESC);
CREATE INDEX ix_sign_in_attempts_phone_occurred
  ON identity.sign_in_attempts (phone_digest, occurred_at DESC);

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON identity.users
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();
CREATE TRIGGER touch_updated_at BEFORE UPDATE ON identity.trusted_devices
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();
CREATE TRIGGER touch_updated_at BEFORE UPDATE ON identity.refresh_tokens
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();

REVOKE ALL ON identity.users, identity.verification_codes, identity.trusted_devices,
  identity.refresh_tokens, identity.sign_in_attempts FROM xcode_api_executor;
GRANT SELECT, INSERT, UPDATE ON identity.users, identity.verification_codes,
  identity.trusted_devices, identity.refresh_tokens TO xcode_api_executor;
-- Audit trail: append-only by privilege.
GRANT SELECT, INSERT ON identity.sign_in_attempts TO xcode_api_executor;
REVOKE UPDATE, DELETE ON identity.sign_in_attempts FROM xcode_api_executor;
