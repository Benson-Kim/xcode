-- Setup tables: code tables, psv_companies, fleet_vehicles, vehicle targets, away periods and investments, recurring items, versions and allocations, expense catalogue; data-scope foreign keys.

SET LOCAL lock_timeout = '10s';

-- In ops, not public: the public schema stays empty. Only the exclusion constraint uses it.
CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA ops;

CREATE TABLE setup.recurring_kinds (
  code smallint NOT NULL,
  name text NOT NULL,
  label text NOT NULL,
  CONSTRAINT pk_recurring_kinds PRIMARY KEY (code),
  CONSTRAINT uq_recurring_kinds_name UNIQUE (name)
);

CREATE TABLE setup.recurrence_frequencies (
  code smallint NOT NULL,
  name text NOT NULL,
  label text NOT NULL,
  CONSTRAINT pk_recurrence_frequencies PRIMARY KEY (code),
  CONSTRAINT uq_recurrence_frequencies_name UNIQUE (name)
);

CREATE TABLE setup.expense_buckets (
  code smallint NOT NULL,
  name text NOT NULL,
  label text NOT NULL,
  CONSTRAINT pk_expense_buckets PRIMARY KEY (code),
  CONSTRAINT uq_expense_buckets_name UNIQUE (name)
);

INSERT INTO setup.recurring_kinds (code, name, label) VALUES
  (1, 'cost', 'Cost'),
  (2, 'savings', 'Savings');

INSERT INTO setup.recurrence_frequencies (code, name, label) VALUES
  (1, 'daily', 'Daily'),
  (2, 'weekly', 'Weekly'),
  (3, 'monthly', 'Monthly'),
  (4, 'yearly', 'Yearly');

INSERT INTO setup.expense_buckets (code, name, label) VALUES
  (1, 'repairs_and_maintenance', 'repairs and maintenance'),
  (2, 'recurring_charges', 'recurring charges'),
  (3, 'loan_repayments', 'loan repayments');

CREATE TABLE setup.psv_companies (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL,
  normalized_name text GENERATED ALWAYS AS (upper(name COLLATE "C")) STORED,
  archived_on date,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_psv_companies PRIMARY KEY (organization_id, id),
  CONSTRAINT fk_psv_companies_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT uq_psv_companies_normalized_name UNIQUE (organization_id, normalized_name),
  CONSTRAINT ck_psv_companies_name CHECK (char_length(name) BETWEEN 1 AND 160 AND name = btrim(name))
);

CREATE TABLE setup.fleet_vehicles (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  company_id uuid NOT NULL,
  registration text NOT NULL,
  joined_on date NOT NULL,
  left_on date,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_fleet_vehicles PRIMARY KEY (organization_id, id),
  CONSTRAINT fk_fleet_vehicles_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_fleet_vehicles_company FOREIGN KEY (organization_id, company_id)
    REFERENCES setup.psv_companies (organization_id, id),
  CONSTRAINT uq_fleet_vehicles_registration UNIQUE (organization_id, registration),
  CONSTRAINT ck_fleet_vehicles_registration CHECK (registration ~ '^K[A-Z]{2} [0-9]{3}[A-Z]$'),
  CONSTRAINT ck_fleet_vehicles_left_on CHECK (left_on IS NULL OR left_on >= joined_on)
);

CREATE INDEX ix_fleet_vehicles_company ON setup.fleet_vehicles (organization_id, company_id);

CREATE TABLE setup.vehicle_targets (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  vehicle_id uuid NOT NULL,
  revision integer NOT NULL,
  effective_from date NOT NULL,
  weekly_amount numeric(14,2) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_vehicle_targets PRIMARY KEY (organization_id, id),
  CONSTRAINT fk_vehicle_targets_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_vehicle_targets_vehicle FOREIGN KEY (organization_id, vehicle_id)
    REFERENCES setup.fleet_vehicles (organization_id, id),
  CONSTRAINT uq_vehicle_targets_revision UNIQUE (organization_id, vehicle_id, revision),
  CONSTRAINT ck_vehicle_targets_revision CHECK (revision >= 1),
  CONSTRAINT ck_vehicle_targets_weekly_amount CHECK (weekly_amount > 0)
);

CREATE INDEX ix_vehicle_targets_in_force
  ON setup.vehicle_targets (organization_id, vehicle_id, effective_from DESC, revision DESC);

CREATE TABLE setup.vehicle_away_periods (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  vehicle_id uuid NOT NULL,
  left_on date NOT NULL,
  returned_on date NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_vehicle_away_periods PRIMARY KEY (organization_id, id),
  CONSTRAINT fk_vehicle_away_periods_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_vehicle_away_periods_vehicle FOREIGN KEY (organization_id, vehicle_id)
    REFERENCES setup.fleet_vehicles (organization_id, id),
  CONSTRAINT uq_vehicle_away_periods_left_on UNIQUE (organization_id, vehicle_id, left_on),
  CONSTRAINT ck_vehicle_away_periods_returned_on CHECK (returned_on > left_on),
  CONSTRAINT ex_vehicle_away_periods_overlap EXCLUDE USING gist (
    organization_id WITH =,
    vehicle_id WITH =,
    daterange(left_on, returned_on) WITH &&
  )
);

CREATE TABLE setup.vehicle_investments (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  vehicle_id uuid NOT NULL,
  invested_on date NOT NULL,
  description text NOT NULL,
  amount numeric(14,2) NOT NULL,
  recorded_by uuid NOT NULL,
  recorded_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_vehicle_investments PRIMARY KEY (organization_id, id),
  CONSTRAINT fk_vehicle_investments_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_vehicle_investments_vehicle FOREIGN KEY (organization_id, vehicle_id)
    REFERENCES setup.fleet_vehicles (organization_id, id),
  CONSTRAINT fk_vehicle_investments_recorded_by FOREIGN KEY (organization_id, recorded_by)
    REFERENCES tenancy.memberships (organization_id, user_id),
  CONSTRAINT ck_vehicle_investments_description CHECK (char_length(description) BETWEEN 1 AND 160),
  CONSTRAINT ck_vehicle_investments_amount CHECK (amount > 0)
);

CREATE INDEX ix_vehicle_investments_vehicle_day
  ON setup.vehicle_investments (organization_id, vehicle_id, invested_on);

CREATE TABLE setup.expense_categories (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL,
  normalized_name text GENERATED ALWAYS AS (upper(name COLLATE "C")) STORED,
  bucket smallint NOT NULL,
  stopped_on date,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_expense_categories PRIMARY KEY (organization_id, id),
  CONSTRAINT fk_expense_categories_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_expense_categories_bucket FOREIGN KEY (bucket) REFERENCES setup.expense_buckets (code),
  CONSTRAINT uq_expense_categories_normalized_name UNIQUE (organization_id, normalized_name),
  CONSTRAINT ck_expense_categories_name CHECK (
    char_length(name) BETWEEN 1 AND 100 AND name = btrim(name)
  )
);

CREATE TABLE setup.expense_items (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  category_id uuid NOT NULL,
  name text NOT NULL,
  normalized_name text GENERATED ALWAYS AS (upper(name COLLATE "C")) STORED,
  stopped_on date,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_expense_items PRIMARY KEY (organization_id, id),
  CONSTRAINT fk_expense_items_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_expense_items_category FOREIGN KEY (organization_id, category_id)
    REFERENCES setup.expense_categories (organization_id, id),
  CONSTRAINT uq_expense_items_normalized_name UNIQUE (organization_id, category_id, normalized_name),
  CONSTRAINT ck_expense_items_name CHECK (char_length(name) BETWEEN 1 AND 100 AND name = btrim(name))
);

CREATE TABLE setup.recurring_items (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  stopped_from date,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_recurring_items PRIMARY KEY (organization_id, id),
  CONSTRAINT fk_recurring_items_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id)
);

CREATE TABLE setup.recurring_versions (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  item_id uuid NOT NULL,
  revision integer NOT NULL,
  effective_from date NOT NULL,
  name text NOT NULL,
  kind smallint NOT NULL,
  amount numeric(14,2) NOT NULL,
  frequency smallint NOT NULL,
  day smallint,
  last_day boolean NOT NULL,
  month smallint,
  start_on date NOT NULL,
  end_on date,
  expense_item_id uuid,
  bucket smallint,
  note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_recurring_versions PRIMARY KEY (organization_id, id),
  CONSTRAINT fk_recurring_versions_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_recurring_versions_item FOREIGN KEY (organization_id, item_id)
    REFERENCES setup.recurring_items (organization_id, id),
  CONSTRAINT fk_recurring_versions_kind FOREIGN KEY (kind) REFERENCES setup.recurring_kinds (code),
  CONSTRAINT fk_recurring_versions_frequency FOREIGN KEY (frequency)
    REFERENCES setup.recurrence_frequencies (code),
  CONSTRAINT fk_recurring_versions_expense_item FOREIGN KEY (organization_id, expense_item_id)
    REFERENCES setup.expense_items (organization_id, id) MATCH SIMPLE,
  CONSTRAINT fk_recurring_versions_bucket FOREIGN KEY (bucket) REFERENCES setup.expense_buckets (code),
  CONSTRAINT uq_recurring_versions_revision UNIQUE (organization_id, item_id, revision),
  CONSTRAINT ck_recurring_versions_revision CHECK (revision >= 1),
  CONSTRAINT ck_recurring_versions_name CHECK (char_length(name) BETWEEN 1 AND 160),
  CONSTRAINT ck_recurring_versions_amount CHECK (amount > 0),
  CONSTRAINT ck_recurring_versions_end_on CHECK (end_on IS NULL OR end_on >= start_on),
  CONSTRAINT ck_recurring_versions_note CHECK (char_length(note) <= 200),
  CONSTRAINT ck_recurring_versions_schedule CHECK (
    (frequency = 2 AND day IS NOT NULL AND day BETWEEN 0 AND 6 AND NOT last_day AND month IS NULL)
    OR (
      frequency IN (3, 4)
      AND ((day IS NOT NULL AND day BETWEEN 1 AND 28 AND NOT last_day) OR (day IS NULL AND last_day))
      AND ((frequency = 4) = (month IS NOT NULL))
      AND (month IS NULL OR month BETWEEN 1 AND 12)
    )
    OR (frequency = 1 AND day IS NULL AND NOT last_day AND month IS NULL)
  ),
  CONSTRAINT ck_recurring_versions_kind CHECK (
    (kind = 2 AND expense_item_id IS NULL AND bucket IS NULL) OR kind = 1
  )
);

CREATE INDEX ix_recurring_versions_expense_item
  ON setup.recurring_versions (organization_id, expense_item_id);

CREATE TABLE setup.recurring_allocations (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  version_id uuid NOT NULL,
  vehicle_id uuid NOT NULL,
  amount numeric(14,2) NOT NULL,
  CONSTRAINT pk_recurring_allocations PRIMARY KEY (organization_id, id),
  CONSTRAINT fk_recurring_allocations_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_recurring_allocations_version FOREIGN KEY (organization_id, version_id)
    REFERENCES setup.recurring_versions (organization_id, id),
  CONSTRAINT fk_recurring_allocations_vehicle FOREIGN KEY (organization_id, vehicle_id)
    REFERENCES setup.fleet_vehicles (organization_id, id),
  CONSTRAINT uq_recurring_allocations_vehicle UNIQUE (organization_id, version_id, vehicle_id),
  CONSTRAINT ck_recurring_allocations_amount CHECK (amount > 0)
);

CREATE INDEX ix_recurring_allocations_vehicle ON setup.recurring_allocations (organization_id, vehicle_id);

ALTER TABLE tenancy.data_scope_companies
  ADD CONSTRAINT fk_data_scope_companies_company FOREIGN KEY (organization_id, company_id)
    REFERENCES setup.psv_companies (organization_id, id);
ALTER TABLE tenancy.data_scope_vehicles
  ADD CONSTRAINT fk_data_scope_vehicles_vehicle FOREIGN KEY (organization_id, vehicle_id)
    REFERENCES setup.fleet_vehicles (organization_id, id);

CREATE FUNCTION setup.forbid_registration_change() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  RAISE EXCEPTION USING
    ERRCODE = 'XC422',
    MESSAGE = 'registration_immutable',
    DETAIL = json_build_object('registration', OLD.registration)::text;
END
$$;

CREATE TRIGGER forbid_registration_change BEFORE UPDATE ON setup.fleet_vehicles
  FOR EACH ROW WHEN (NEW.registration IS DISTINCT FROM OLD.registration)
  EXECUTE FUNCTION setup.forbid_registration_change();

-- A version's shares number 1 to 500 and add up exactly to its amount, checked at commit.
CREATE FUNCTION setup.check_allocation_sum() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_version_id uuid;
  v_amount numeric;
  v_allocated numeric;
  v_vehicles integer;
BEGIN
  IF TG_TABLE_NAME = 'recurring_versions' THEN
    v_version_id := NEW.id;
  ELSE
    v_version_id := NEW.version_id;
  END IF;
  SELECT v.amount INTO v_amount
  FROM setup.recurring_versions v
  WHERE v.organization_id = NEW.organization_id AND v.id = v_version_id;
  SELECT coalesce(sum(a.amount), 0), count(*) INTO v_allocated, v_vehicles
  FROM setup.recurring_allocations a
  WHERE a.organization_id = NEW.organization_id AND a.version_id = v_version_id;
  IF v_vehicles NOT BETWEEN 1 AND 500 OR v_allocated IS DISTINCT FROM v_amount THEN
    RAISE EXCEPTION USING
      ERRCODE = 'XC422',
      MESSAGE = 'allocation_sum_mismatch',
      DETAIL = json_build_object(
        'version_id', v_version_id,
        'amount', v_amount,
        'allocated', v_allocated,
        'vehicles', v_vehicles
      )::text;
  END IF;
  RETURN NULL;
END
$$;

CREATE CONSTRAINT TRIGGER check_allocation_sum
  AFTER INSERT OR UPDATE OF amount ON setup.recurring_versions
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION setup.check_allocation_sum();
CREATE CONSTRAINT TRIGGER check_allocation_sum
  AFTER INSERT OR UPDATE ON setup.recurring_allocations
  DEFERRABLE INITIALLY DEFERRED
  FOR EACH ROW EXECUTE FUNCTION setup.check_allocation_sum();

REVOKE ALL ON FUNCTION setup.forbid_registration_change(), setup.check_allocation_sum() FROM PUBLIC;

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON setup.psv_companies
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();
CREATE TRIGGER touch_updated_at BEFORE UPDATE ON setup.fleet_vehicles
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();
CREATE TRIGGER touch_updated_at BEFORE UPDATE ON setup.vehicle_investments
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();
CREATE TRIGGER touch_updated_at BEFORE UPDATE ON setup.expense_categories
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();
CREATE TRIGGER touch_updated_at BEFORE UPDATE ON setup.expense_items
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();
CREATE TRIGGER touch_updated_at BEFORE UPDATE ON setup.recurring_items
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();

ALTER TABLE setup.psv_companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup.fleet_vehicles ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup.vehicle_targets ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup.vehicle_away_periods ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup.vehicle_investments ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup.expense_categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup.expense_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup.recurring_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup.recurring_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup.recurring_allocations ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON setup.psv_companies TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON setup.fleet_vehicles TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON setup.vehicle_targets TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON setup.vehicle_away_periods TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON setup.vehicle_investments TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON setup.expense_categories TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON setup.expense_items TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON setup.recurring_items TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON setup.recurring_versions TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON setup.recurring_allocations TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());

REVOKE ALL ON setup.recurring_kinds, setup.recurrence_frequencies, setup.expense_buckets,
  setup.psv_companies, setup.fleet_vehicles, setup.vehicle_targets, setup.vehicle_away_periods,
  setup.vehicle_investments, setup.expense_categories, setup.expense_items, setup.recurring_items,
  setup.recurring_versions, setup.recurring_allocations FROM xcode_api_executor;
GRANT SELECT ON setup.recurring_kinds, setup.recurrence_frequencies, setup.expense_buckets
  TO xcode_api_executor, xcode_readonly;
GRANT USAGE ON SCHEMA setup TO xcode_readonly;
GRANT SELECT, INSERT, UPDATE ON setup.psv_companies, setup.fleet_vehicles,
  setup.expense_categories, setup.expense_items, setup.recurring_items TO xcode_api_executor;
GRANT SELECT, INSERT ON setup.vehicle_targets, setup.vehicle_away_periods,
  setup.recurring_versions, setup.recurring_allocations TO xcode_api_executor;
GRANT SELECT, INSERT, UPDATE, DELETE ON setup.vehicle_investments TO xcode_api_executor;
