-- Deletion notices: the durable outbox of the emails that tell the administrators who can block members that a member asked to delete their account. One row per recipient is written with the request and sent after it commits; a send lost to a crash or a mail fault is retried by the sweep. The row keeps only identifiers: the address is read when the mail is sent.

SET LOCAL lock_timeout = '10s';

CREATE TABLE tenancy.deletion_notices (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL,
  requester_id uuid NOT NULL,
  recipient_id uuid NOT NULL,
  created_at timestamptz NOT NULL,
  state text NOT NULL DEFAULT 'pending',
  attempts integer NOT NULL DEFAULT 0,
  attempted_at timestamptz,
  sent_at timestamptz,
  CONSTRAINT pk_deletion_notices PRIMARY KEY (id),
  CONSTRAINT fk_deletion_notices_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id) ON DELETE CASCADE,
  CONSTRAINT fk_deletion_notices_requester FOREIGN KEY (organization_id, requester_id)
    REFERENCES tenancy.memberships (organization_id, user_id) ON DELETE CASCADE,
  CONSTRAINT fk_deletion_notices_recipient FOREIGN KEY (organization_id, recipient_id)
    REFERENCES tenancy.memberships (organization_id, user_id) ON DELETE CASCADE,
  CONSTRAINT ck_deletion_notices_state CHECK (state IN ('pending', 'sent', 'failed', 'dropped')),
  CONSTRAINT ck_deletion_notices_attempts CHECK (attempts >= 0),
  CONSTRAINT ck_deletion_notices_sent CHECK ((state = 'sent') = (sent_at IS NOT NULL))
);

-- The sweep that re-sends what a crash or a failed send left behind.
CREATE INDEX ix_deletion_notices_pending
  ON tenancy.deletion_notices (organization_id, created_at) WHERE state = 'pending';

CREATE INDEX ix_deletion_notices_requester ON tenancy.deletion_notices (organization_id, requester_id);

CREATE INDEX ix_deletion_notices_recipient ON tenancy.deletion_notices (organization_id, recipient_id);

ALTER TABLE tenancy.deletion_notices ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON tenancy.deletion_notices TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());

REVOKE ALL ON tenancy.deletion_notices FROM PUBLIC, xcode_api_executor;
GRANT SELECT, INSERT, UPDATE ON tenancy.deletion_notices TO xcode_api_executor;
