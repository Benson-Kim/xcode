-- Reverse of 0002_identity.sql.

SET LOCAL lock_timeout = '10s';

DROP TABLE identity.sign_in_attempts;
DROP TABLE identity.refresh_tokens;
DROP TABLE identity.trusted_devices;
DROP TABLE identity.verification_codes;
DROP TABLE identity.users;
DROP FUNCTION ops.touch_updated_at();
