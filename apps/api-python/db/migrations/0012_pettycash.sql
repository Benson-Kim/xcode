-- Petty cash: kind and status code tables, the entries table, the pettycash change-log section.

SET LOCAL lock_timeout = '10s';

CREATE TABLE pettycash.kinds (
  code smallint NOT NULL,
  name text NOT NULL,
  label text NOT NULL,
  CONSTRAINT pk_kinds PRIMARY KEY (code),
  CONSTRAINT uq_kinds_name UNIQUE (name)
);

INSERT INTO pettycash.kinds (code, name, label) VALUES
  (1, 'cash', 'Cash given'),
  (2, 'expense', 'Expense'),
  (3, 'credit', 'Credit note');

-- 3 was the .NET SentBack status; sent back is a reason on a waiting expense here.
CREATE TABLE pettycash.statuses (
  code smallint NOT NULL,
  name text NOT NULL,
  label text NOT NULL,
  CONSTRAINT pk_statuses PRIMARY KEY (code),
  CONSTRAINT uq_statuses_name UNIQUE (name)
);

INSERT INTO pettycash.statuses (code, name, label) VALUES
  (1, 'waiting', 'Waiting'),
  (2, 'approved', 'Approved'),
  (4, 'rejected', 'Rejected');

CREATE TABLE pettycash.entries (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  holder_id uuid NOT NULL,
  kind smallint NOT NULL,
  entry_date date NOT NULL,
  vehicle_id uuid,
  expense_item_id uuid,
  units numeric(12,3) NOT NULL DEFAULT 1,
  unit_amount numeric(14,2) NOT NULL,
  total numeric(14,2) GENERATED ALWAYS AS (round(units * unit_amount, 2)) STORED,
  payee text,
  note text,
  reimbursable boolean NOT NULL DEFAULT false,
  status smallint,
  sent_back_note text,
  reject_reason text,
  reopen_reason text,
  reviewed_by uuid,
  reviewed_at timestamptz,
  recorded_by uuid NOT NULL,
  recorded_at timestamptz NOT NULL,
  updated_by uuid NOT NULL,
  updated_at timestamptz NOT NULL,
  removed_by uuid,
  removed_at timestamptz,
  removal_reason text,
  version bigint NOT NULL DEFAULT 1,
  CONSTRAINT pk_entries PRIMARY KEY (organization_id, id),
  CONSTRAINT fk_entries_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_entries_holder FOREIGN KEY (organization_id, holder_id)
    REFERENCES tenancy.memberships (organization_id, user_id),
  CONSTRAINT fk_entries_kind FOREIGN KEY (kind) REFERENCES pettycash.kinds (code),
  CONSTRAINT fk_entries_status FOREIGN KEY (status) REFERENCES pettycash.statuses (code),
  CONSTRAINT fk_entries_vehicle FOREIGN KEY (organization_id, vehicle_id)
    REFERENCES setup.fleet_vehicles (organization_id, id),
  CONSTRAINT fk_entries_expense_item FOREIGN KEY (organization_id, expense_item_id)
    REFERENCES setup.expense_items (organization_id, id),
  CONSTRAINT fk_entries_reviewed_by FOREIGN KEY (organization_id, reviewed_by)
    REFERENCES tenancy.memberships (organization_id, user_id),
  CONSTRAINT fk_entries_recorded_by FOREIGN KEY (organization_id, recorded_by)
    REFERENCES tenancy.memberships (organization_id, user_id),
  CONSTRAINT fk_entries_updated_by FOREIGN KEY (organization_id, updated_by)
    REFERENCES tenancy.memberships (organization_id, user_id),
  CONSTRAINT fk_entries_removed_by FOREIGN KEY (organization_id, removed_by)
    REFERENCES tenancy.memberships (organization_id, user_id),
  CONSTRAINT ck_entries_units CHECK (units > 0 AND units <= 999999999.999),
  CONSTRAINT ck_entries_total CHECK (total <> 0),
  CONSTRAINT ck_entries_payee CHECK (char_length(payee) BETWEEN 1 AND 80),
  CONSTRAINT ck_entries_note CHECK (char_length(note) BETWEEN 1 AND 80),
  CONSTRAINT ck_entries_sent_back_note CHECK (char_length(sent_back_note) BETWEEN 1 AND 200),
  CONSTRAINT ck_entries_reject_reason CHECK (char_length(reject_reason) BETWEEN 1 AND 200),
  CONSTRAINT ck_entries_reopen_reason CHECK (char_length(reopen_reason) BETWEEN 1 AND 200),
  CONSTRAINT ck_entries_removal_reason CHECK (char_length(removal_reason) BETWEEN 1 AND 500),
  CONSTRAINT ck_entries_version CHECK (version >= 1),
  CONSTRAINT ck_entries_kind_shape CHECK (
    (kind = 1 AND status IS NULL AND units = 1 AND vehicle_id IS NULL AND expense_item_id IS NULL
      AND payee IS NULL AND NOT reimbursable)
    OR (kind = 2 AND status IS NOT NULL AND vehicle_id IS NOT NULL AND expense_item_id IS NOT NULL
      AND payee IS NULL AND NOT reimbursable)
    OR (kind = 3 AND status IS NULL AND units = 1 AND vehicle_id IS NULL AND expense_item_id IS NULL)
  ),
  CONSTRAINT ck_entries_review CHECK (
    (sent_back_note IS NULL OR status = 1)
    AND ((reject_reason IS NOT NULL) = (status IS NOT DISTINCT FROM 4))
    AND (reopen_reason IS NULL OR kind = 2)
    AND ((reviewed_by IS NULL) = (reviewed_at IS NULL))
    AND ((reviewed_by IS NOT NULL) = (status IS NOT DISTINCT FROM 2 OR status IS NOT DISTINCT FROM 4
      OR sent_back_note IS NOT NULL))
  ),
  CONSTRAINT ck_entries_removal CHECK (
    ((removed_at IS NULL) = (removed_by IS NULL))
    AND (removal_reason IS NULL OR removed_at IS NOT NULL)
  )
);

CREATE INDEX ix_entries_holder_date ON pettycash.entries (organization_id, holder_id, entry_date);
CREATE INDEX ix_entries_status_date ON pettycash.entries (organization_id, status, entry_date)
  WHERE removed_at IS NULL;
CREATE INDEX ix_entries_vehicle_date ON pettycash.entries (organization_id, vehicle_id, entry_date)
  WHERE removed_at IS NULL;
CREATE INDEX ix_entries_expense_item ON pettycash.entries (organization_id, expense_item_id);

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON pettycash.entries
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();

ALTER TABLE pettycash.entries ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON pettycash.entries TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());

REVOKE ALL ON pettycash.kinds, pettycash.statuses, pettycash.entries FROM xcode_api_executor;
GRANT SELECT ON pettycash.kinds, pettycash.statuses TO xcode_api_executor, xcode_readonly;
GRANT SELECT, INSERT, UPDATE ON pettycash.entries TO xcode_api_executor;

ALTER TABLE tenancy.change_log
  DROP CONSTRAINT ck_change_log_section,
  ADD CONSTRAINT ck_change_log_section CHECK (section IN (
    'companies', 'vehicles', 'investment', 'expenses', 'recurring', 'people', 'revenue',
    'organization', 'businessDate', 'localization', 'branding', 'securityPolicy', 'logo',
    'signIn', 'pettycash'
  )),
  DROP CONSTRAINT ck_change_log_vehicle,
  ADD CONSTRAINT ck_change_log_vehicle CHECK (
    section = 'pettycash'
    OR (section IN ('vehicles', 'investment', 'revenue')) = (vehicle_id IS NOT NULL)
  );
