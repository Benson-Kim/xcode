-- Sign-in notices: the durable outbox of the emails that tell a person their sign-in email or mobile number was changed. tenancy.save_person writes them with the change: one to the old address and one to the new when the email changes, one to the current address when only the number does. They are sent after commit; a send lost to a crash or a mail fault is retried by the sweep. The address is kept only while the notice is pending.

SET LOCAL lock_timeout = '10s';

CREATE TABLE tenancy.sign_in_notices (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  user_id uuid NOT NULL,
  actor_id uuid,
  kind text NOT NULL,
  address text,
  created_at timestamptz NOT NULL,
  state text NOT NULL DEFAULT 'pending',
  attempts integer NOT NULL DEFAULT 0,
  attempted_at timestamptz,
  sent_at timestamptz,
  CONSTRAINT pk_sign_in_notices PRIMARY KEY (id),
  CONSTRAINT fk_sign_in_notices_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id) ON DELETE CASCADE,
  CONSTRAINT fk_sign_in_notices_user FOREIGN KEY (organization_id, user_id)
    REFERENCES tenancy.memberships (organization_id, user_id) ON DELETE CASCADE,
  CONSTRAINT fk_sign_in_notices_actor FOREIGN KEY (organization_id, actor_id)
    REFERENCES tenancy.memberships (organization_id, user_id) ON DELETE SET NULL (actor_id),
  CONSTRAINT ck_sign_in_notices_kind CHECK (kind IN ('old', 'new', 'current')),
  CONSTRAINT ck_sign_in_notices_state CHECK (state IN ('pending', 'sent', 'failed', 'dropped')),
  CONSTRAINT ck_sign_in_notices_address CHECK ((state = 'pending') = (address IS NOT NULL)),
  CONSTRAINT ck_sign_in_notices_attempts CHECK (attempts >= 0),
  CONSTRAINT ck_sign_in_notices_sent CHECK ((state = 'sent') = (sent_at IS NOT NULL))
);

-- The sweep that re-sends what a crash or a failed send left behind.
CREATE INDEX ix_sign_in_notices_pending
  ON tenancy.sign_in_notices (organization_id, created_at) WHERE state = 'pending';

CREATE INDEX ix_sign_in_notices_user ON tenancy.sign_in_notices (organization_id, user_id);

CREATE INDEX ix_sign_in_notices_actor ON tenancy.sign_in_notices (organization_id, actor_id);

ALTER TABLE tenancy.sign_in_notices ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON tenancy.sign_in_notices TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());

REVOKE ALL ON tenancy.sign_in_notices FROM PUBLIC, xcode_api_executor;
GRANT SELECT, INSERT, UPDATE ON tenancy.sign_in_notices TO xcode_api_executor;
