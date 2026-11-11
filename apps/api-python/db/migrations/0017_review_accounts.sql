-- App Review access: an organization gains a demo flag, set only by api.ops_seed_demo, so only the seeded demo organization ever carries it; identity.review_accounts keeps the keyed digest of the fixed new-device code of each App Review login, written only by api.ops_review_account_create and read by identity.matching_code.

SET LOCAL lock_timeout = '10s';

ALTER TABLE tenancy.organizations ADD COLUMN demo boolean NOT NULL DEFAULT false;

CREATE TABLE identity.review_accounts (
  user_id uuid NOT NULL,
  code_hash text NOT NULL,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT pk_review_accounts PRIMARY KEY (user_id),
  CONSTRAINT fk_review_accounts_user FOREIGN KEY (user_id) REFERENCES identity.users (id) ON DELETE CASCADE,
  CONSTRAINT ck_review_accounts_code_hash CHECK (code_hash ~ '^[0-9A-F]{64}$')
);

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON identity.review_accounts
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();

REVOKE ALL ON identity.review_accounts FROM PUBLIC, xcode_api_executor;
GRANT SELECT, INSERT, UPDATE ON identity.review_accounts TO xcode_api_executor;
