-- Central expenses, scheduled-item pauses, the saving model, petty-cash shared purchases, the centralexpenses and reports change-log sections.

SET LOCAL lock_timeout = '10s';

-- Routines whose signature changes or that leave; `db routines` creates the new ones.
DROP FUNCTION IF EXISTS setup.vehicle_postings(uuid, daterange);
DROP FUNCTION IF EXISTS pettycash.vehicle_postings(uuid, daterange);
DROP FUNCTION IF EXISTS setup.save_recurring(
  uuid, text, integer, numeric, integer, integer, boolean, date, date, jsonb, uuid, text, integer, text, timestamptz
);
DROP FUNCTION IF EXISTS api.setup_recurring_create(
  uuid, uuid, text, text, integer, numeric, integer, integer, boolean, date, date, jsonb, uuid, text, integer, text,
  timestamptz
);
DROP FUNCTION IF EXISTS api.setup_recurring_revise(
  uuid, uuid, text, uuid, text, integer, numeric, integer, integer, boolean, date, date, jsonb, uuid, text, integer,
  text, timestamptz
);
DROP FUNCTION IF EXISTS api.pettycash_entry_create(
  uuid, uuid, text, uuid, text, date, numeric, uuid, uuid, uuid, numeric, text, text, boolean, timestamptz
);

-- A purchase recorded for one vehicle or split across several: one row per vehicle, sharing the group.
CREATE TABLE expenses.entries (
  organization_id uuid NOT NULL,
  id uuid NOT NULL,
  entry_date date NOT NULL,
  vehicle_id uuid NOT NULL,
  expense_item_id uuid NOT NULL,
  units numeric(12,3) NOT NULL,
  unit_amount numeric(14,2) NOT NULL,
  total numeric(14,2) GENERATED ALWAYS AS (round(units * unit_amount, 2)) STORED,
  note text,
  group_id uuid NOT NULL,
  group_size integer NOT NULL,
  group_total numeric(14,2) NOT NULL,
  group_units numeric(12,3) NOT NULL,
  group_unit_amount numeric(14,2) NOT NULL,
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
  CONSTRAINT fk_entries_vehicle FOREIGN KEY (organization_id, vehicle_id)
    REFERENCES setup.fleet_vehicles (organization_id, id),
  CONSTRAINT fk_entries_expense_item FOREIGN KEY (organization_id, expense_item_id)
    REFERENCES setup.expense_items (organization_id, id),
  CONSTRAINT fk_entries_recorded_by FOREIGN KEY (organization_id, recorded_by)
    REFERENCES tenancy.memberships (organization_id, user_id),
  CONSTRAINT fk_entries_updated_by FOREIGN KEY (organization_id, updated_by)
    REFERENCES tenancy.memberships (organization_id, user_id),
  CONSTRAINT fk_entries_removed_by FOREIGN KEY (organization_id, removed_by)
    REFERENCES tenancy.memberships (organization_id, user_id),
  CONSTRAINT uq_entries_group_vehicle UNIQUE (organization_id, group_id, vehicle_id),
  CONSTRAINT ck_entries_units CHECK (units > 0 AND units <= 999999999.999),
  CONSTRAINT ck_entries_total CHECK (total <> 0),
  CONSTRAINT ck_entries_note CHECK (char_length(note) BETWEEN 1 AND 80 AND note = btrim(note)),
  CONSTRAINT ck_entries_group_size CHECK (group_size BETWEEN 1 AND 50),
  CONSTRAINT ck_entries_group_total CHECK (group_total <> 0),
  CONSTRAINT ck_entries_group_units CHECK (group_units > 0 AND group_units <= 999999999.999),
  CONSTRAINT ck_entries_group_unit_amount CHECK (group_unit_amount <> 0),
  CONSTRAINT ck_entries_group CHECK (
    group_size > 1
    OR (group_total = total AND group_units = units AND group_unit_amount = unit_amount)
  ),
  CONSTRAINT ck_entries_removal CHECK (
    (removed_at IS NULL) = (removed_by IS NULL)
    AND (removed_at IS NULL) = (removal_reason IS NULL)
  ),
  CONSTRAINT ck_entries_removal_reason CHECK (char_length(removal_reason) BETWEEN 1 AND 500),
  CONSTRAINT ck_entries_version CHECK (version >= 1)
);

CREATE INDEX ix_entries_date ON expenses.entries (organization_id, entry_date)
  WHERE removed_at IS NULL;
CREATE INDEX ix_entries_vehicle_date ON expenses.entries (organization_id, vehicle_id, entry_date)
  WHERE removed_at IS NULL;
CREATE INDEX ix_entries_expense_item ON expenses.entries (organization_id, expense_item_id);

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON expenses.entries
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();

CREATE TABLE setup.recurring_pauses (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  item_id uuid NOT NULL,
  paused_from date NOT NULL,
  paused_through date,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_recurring_pauses PRIMARY KEY (organization_id, id),
  CONSTRAINT fk_recurring_pauses_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_recurring_pauses_item FOREIGN KEY (organization_id, item_id)
    REFERENCES setup.recurring_items (organization_id, id),
  CONSTRAINT ck_recurring_pauses_through CHECK (paused_through >= paused_from - 1)
);

-- Created before the exclusion so that a second open pause is refused under this name.
CREATE UNIQUE INDEX uq_recurring_pauses_open ON setup.recurring_pauses (organization_id, item_id)
  WHERE paused_through IS NULL;

-- A same-day resume leaves an empty range, which overlaps nothing.
ALTER TABLE setup.recurring_pauses
  ADD CONSTRAINT ex_recurring_pauses_overlap EXCLUDE USING gist (
    organization_id WITH =,
    item_id WITH =,
    daterange(paused_from, paused_through + 1, '[)') WITH &&
  );

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON setup.recurring_pauses
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();

-- Only a saving carries a revenue rule.
ALTER TABLE setup.recurring_versions
  ADD COLUMN condition_min numeric(14,2),
  ADD COLUMN condition_days smallint,
  ADD CONSTRAINT ck_recurring_versions_condition_min CHECK (condition_min > 0),
  ADD CONSTRAINT ck_recurring_versions_condition_days CHECK (condition_days IN (1, 7, 30)),
  ADD CONSTRAINT ck_recurring_versions_condition CHECK (
    (condition_min IS NULL) = (condition_days IS NULL)
    AND (condition_min IS NULL OR kind = 2)
  );

CREATE TABLE setup.saving_run_states (
  code smallint NOT NULL,
  name text NOT NULL,
  label text NOT NULL,
  CONSTRAINT pk_saving_run_states PRIMARY KEY (code),
  CONSTRAINT uq_saving_run_states_name UNIQUE (name)
);

INSERT INTO setup.saving_run_states (code, name, label) VALUES
  (1, 'saved', 'Saved'),
  (2, 'skipped', 'Skipped');

CREATE TABLE setup.saving_openings (
  organization_id uuid NOT NULL,
  item_id uuid NOT NULL,
  opened_on date NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_saving_openings PRIMARY KEY (organization_id, item_id),
  CONSTRAINT fk_saving_openings_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_saving_openings_item FOREIGN KEY (organization_id, item_id)
    REFERENCES setup.recurring_items (organization_id, id)
);

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON setup.saving_openings
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();

CREATE TABLE setup.saving_opening_amounts (
  organization_id uuid NOT NULL,
  item_id uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  amount numeric(14,2) NOT NULL,
  CONSTRAINT pk_saving_opening_amounts PRIMARY KEY (organization_id, item_id, vehicle_id),
  CONSTRAINT fk_saving_opening_amounts_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_saving_opening_amounts_opening FOREIGN KEY (organization_id, item_id)
    REFERENCES setup.saving_openings (organization_id, item_id)
    ON UPDATE CASCADE ON DELETE CASCADE,
  CONSTRAINT fk_saving_opening_amounts_vehicle FOREIGN KEY (organization_id, vehicle_id)
    REFERENCES setup.fleet_vehicles (organization_id, id),
  CONSTRAINT ck_saving_opening_amounts_amount CHECK (amount > 0)
);

-- Decided runs of savings with a revenue rule; final once written.
CREATE TABLE setup.saving_runs (
  organization_id uuid NOT NULL,
  item_id uuid NOT NULL,
  run_on date NOT NULL,
  vehicle_id uuid NOT NULL,
  version_id uuid NOT NULL,
  amount numeric(14,2) NOT NULL,
  state smallint NOT NULL,
  revenue numeric(14,2) NOT NULL,
  decided_at timestamptz NOT NULL,
  CONSTRAINT pk_saving_runs PRIMARY KEY (organization_id, item_id, run_on, vehicle_id),
  CONSTRAINT fk_saving_runs_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_saving_runs_item FOREIGN KEY (organization_id, item_id)
    REFERENCES setup.recurring_items (organization_id, id),
  CONSTRAINT fk_saving_runs_vehicle FOREIGN KEY (organization_id, vehicle_id)
    REFERENCES setup.fleet_vehicles (organization_id, id),
  CONSTRAINT fk_saving_runs_version FOREIGN KEY (organization_id, version_id)
    REFERENCES setup.recurring_versions (organization_id, id),
  CONSTRAINT fk_saving_runs_state FOREIGN KEY (state) REFERENCES setup.saving_run_states (code),
  CONSTRAINT ck_saving_runs_amount CHECK (amount > 0)
);

CREATE INDEX ix_saving_runs_vehicle_run_on ON setup.saving_runs (organization_id, vehicle_id, run_on);

-- A petty-cash expense bought for several vehicles: one entry per vehicle, the purchase as bought.
ALTER TABLE pettycash.entries
  ADD COLUMN group_id uuid,
  ADD COLUMN group_total numeric(14,2),
  ADD COLUMN group_units numeric(12,3),
  ADD COLUMN group_unit_amount numeric(14,2),
  ADD CONSTRAINT uq_entries_group_vehicle UNIQUE (organization_id, group_id, vehicle_id),
  ADD CONSTRAINT ck_entries_group_total CHECK (group_total <> 0),
  ADD CONSTRAINT ck_entries_group_units CHECK (group_units > 0 AND group_units <= 999999999.999),
  ADD CONSTRAINT ck_entries_group_unit_amount CHECK (group_unit_amount <> 0),
  ADD CONSTRAINT ck_entries_group CHECK (
    (group_id IS NULL AND group_total IS NULL AND group_units IS NULL AND group_unit_amount IS NULL)
    OR (group_id IS NOT NULL AND group_total IS NOT NULL AND group_units IS NOT NULL
      AND group_unit_amount IS NOT NULL AND kind = 2)
  );

ALTER TABLE expenses.entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup.recurring_pauses ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup.saving_openings ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup.saving_opening_amounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup.saving_runs ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON expenses.entries TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON setup.recurring_pauses TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON setup.saving_openings TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON setup.saving_opening_amounts TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON setup.saving_runs TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());

REVOKE ALL ON expenses.entries, setup.recurring_pauses, setup.saving_run_states, setup.saving_openings,
  setup.saving_opening_amounts, setup.saving_runs FROM xcode_api_executor;
GRANT SELECT ON setup.saving_run_states TO xcode_api_executor, xcode_readonly;
GRANT SELECT, INSERT, UPDATE ON expenses.entries, setup.recurring_pauses TO xcode_api_executor;
GRANT SELECT, INSERT, UPDATE, DELETE ON setup.saving_openings, setup.saving_opening_amounts
  TO xcode_api_executor;
GRANT SELECT, INSERT ON setup.saving_runs TO xcode_api_executor;

ALTER TABLE tenancy.change_log
  DROP CONSTRAINT ck_change_log_section,
  ADD CONSTRAINT ck_change_log_section CHECK (section IN (
    'companies', 'vehicles', 'investment', 'expenses', 'recurring', 'people', 'revenue',
    'organization', 'businessDate', 'localization', 'branding', 'securityPolicy', 'logo',
    'signIn', 'pettycash', 'centralexpenses', 'reports'
  )),
  DROP CONSTRAINT ck_change_log_vehicle,
  ADD CONSTRAINT ck_change_log_vehicle CHECK (
    section = 'pettycash'
    OR (section IN ('vehicles', 'investment', 'revenue', 'centralexpenses')) = (vehicle_id IS NOT NULL)
  );
