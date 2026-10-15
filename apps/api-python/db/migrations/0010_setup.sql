-- Setup of the design notes v2.29 to v2.32: dated target sets of seven day figures (the weekly targets split into them), the fleet number and optional initial investment on vehicles, and main categories above expense categories (one per bucket in use).

SET LOCAL lock_timeout = '10s';

-- Routines whose signature changes; `db routines` creates the new ones.
DROP FUNCTION IF EXISTS api.setup_vehicle_create(
  uuid, uuid, text, uuid, text, date, numeric, text, timestamptz
);
DROP FUNCTION IF EXISTS api.setup_vehicle_update(
  uuid, uuid, text, uuid, uuid, text, date, numeric, text, timestamptz
);
DROP FUNCTION IF EXISTS api.setup_expense_category_create(uuid, uuid, text, text, integer, timestamptz);
DROP FUNCTION IF EXISTS api.setup_expense_category_update(
  uuid, uuid, text, uuid, text, integer, timestamptz
);

-- A fleet number is required on every save; vehicles saved before it existed have none until
-- their next save. Nulls are distinct, so they never clash.
ALTER TABLE setup.fleet_vehicles
  ADD COLUMN fleet_number text,
  ADD COLUMN normalized_fleet_number text GENERATED ALWAYS AS (upper(fleet_number COLLATE "C")) STORED,
  ADD COLUMN initial_investment numeric(14,2),
  ADD CONSTRAINT ck_fleet_vehicles_fleet_number CHECK (
    char_length(fleet_number) BETWEEN 1 AND 20 AND fleet_number = btrim(fleet_number)
  ),
  ADD CONSTRAINT ck_fleet_vehicles_initial_investment CHECK (initial_investment > 0),
  ADD CONSTRAINT uq_fleet_vehicles_fleet_number UNIQUE (organization_id, company_id, normalized_fleet_number);

-- A start date and seven day figures, Monday to Sunday; a set applies until the next starts.
-- created_by is null only for the sets this migration makes from the weekly targets.
CREATE TABLE setup.vehicle_target_sets (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  vehicle_id uuid NOT NULL,
  starts_on date NOT NULL,
  monday numeric(14,2) NOT NULL,
  tuesday numeric(14,2) NOT NULL,
  wednesday numeric(14,2) NOT NULL,
  thursday numeric(14,2) NOT NULL,
  friday numeric(14,2) NOT NULL,
  saturday numeric(14,2) NOT NULL,
  sunday numeric(14,2) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by uuid,
  CONSTRAINT pk_vehicle_target_sets PRIMARY KEY (organization_id, id),
  CONSTRAINT fk_vehicle_target_sets_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_vehicle_target_sets_vehicle FOREIGN KEY (organization_id, vehicle_id)
    REFERENCES setup.fleet_vehicles (organization_id, id),
  CONSTRAINT fk_vehicle_target_sets_created_by FOREIGN KEY (organization_id, created_by)
    REFERENCES tenancy.memberships (organization_id, user_id),
  CONSTRAINT uq_vehicle_target_sets_start UNIQUE (organization_id, vehicle_id, starts_on),
  CONSTRAINT ck_vehicle_target_sets_days CHECK (
    monday > 0 AND tuesday > 0 AND wednesday > 0 AND thursday > 0 AND friday > 0
    AND saturday > 0 AND sunday > 0
  )
);

CREATE TABLE setup.expense_main_categories (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  name text NOT NULL,
  normalized_name text GENERATED ALWAYS AS (upper(name COLLATE "C")) STORED,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_expense_main_categories PRIMARY KEY (organization_id, id),
  CONSTRAINT fk_expense_main_categories_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT uq_expense_main_categories_normalized_name UNIQUE (organization_id, normalized_name),
  CONSTRAINT ck_expense_main_categories_name CHECK (
    char_length(name) BETWEEN 1 AND 100 AND name = btrim(name)
  )
);

-- A category has a main category or none; the bucket is kept for the vehicle report and
-- written by nothing.
ALTER TABLE setup.expense_categories
  ADD COLUMN main_category_id uuid,
  ALTER COLUMN bucket DROP NOT NULL,
  ADD CONSTRAINT fk_expense_categories_main_category FOREIGN KEY (organization_id, main_category_id)
    REFERENCES setup.expense_main_categories (organization_id, id);

CREATE INDEX ix_expense_categories_main_category
  ON setup.expense_categories (organization_id, main_category_id);

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON setup.expense_main_categories
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();

ALTER TABLE setup.vehicle_target_sets ENABLE ROW LEVEL SECURITY;
ALTER TABLE setup.expense_main_categories ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON setup.vehicle_target_sets TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON setup.expense_main_categories TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());

REVOKE ALL ON setup.vehicle_target_sets, setup.expense_main_categories FROM xcode_api_executor;
-- A set that has not started may be replaced or removed; the routines keep started sets fixed.
GRANT SELECT, INSERT, UPDATE, DELETE ON setup.vehicle_target_sets TO xcode_api_executor;
GRANT SELECT, INSERT, UPDATE ON setup.expense_main_categories TO xcode_api_executor;
-- The weekly targets stay for reading until the revenue migration drops them.
REVOKE INSERT ON setup.vehicle_targets FROM xcode_api_executor;

-- Each weekly target becomes a set from its date (the highest revision of a date wins):
-- Monday to Saturday a seventh rounded to the cent, Sunday the rest, so the week total is
-- unchanged. A tie at half a cent cannot happen (the cents of a seventh never end in a half),
-- so round() equals half-even rounding. A target too small to give seven positive figures is
-- left for the owner to enter.
CREATE TEMPORARY TABLE setup_target_split ON COMMIT DROP AS
SELECT t.organization_id, t.vehicle_id, t.effective_from, t.weekly_amount, t.created_at,
       round(t.weekly_amount / 7, 2) AS day_amount
FROM (
  SELECT DISTINCT ON (organization_id, vehicle_id, effective_from)
         organization_id, vehicle_id, effective_from, weekly_amount, created_at
  FROM setup.vehicle_targets
  ORDER BY organization_id, vehicle_id, effective_from, revision DESC
) AS t;

INSERT INTO setup.vehicle_target_sets (
  organization_id, vehicle_id, starts_on, monday, tuesday, wednesday, thursday, friday,
  saturday, sunday, created_at, created_by
)
SELECT s.organization_id, s.vehicle_id, s.effective_from, s.day_amount, s.day_amount,
       s.day_amount, s.day_amount, s.day_amount, s.day_amount,
       s.weekly_amount - 6 * s.day_amount, s.created_at, NULL
FROM setup_target_split AS s
WHERE s.day_amount > 0 AND s.weekly_amount - 6 * s.day_amount > 0;

-- One main category for each bucket an organization's categories use, as ordinary records.
INSERT INTO setup.expense_main_categories (organization_id, name, created_at, updated_at)
SELECT DISTINCT c.organization_id,
       CASE c.bucket
         WHEN 1 THEN 'Repairs and maintenance'
         WHEN 2 THEN 'Recurring charges'
         WHEN 3 THEN 'Loan repayments'
       END,
       now(), now()
FROM setup.expense_categories AS c
WHERE c.bucket IS NOT NULL;

UPDATE setup.expense_categories AS c
SET main_category_id = m.id
FROM setup.expense_main_categories AS m
WHERE m.organization_id = c.organization_id
  AND m.name = CASE c.bucket
                 WHEN 1 THEN 'Repairs and maintenance'
                 WHEN 2 THEN 'Recurring charges'
                 WHEN 3 THEN 'Loan repayments'
               END;

DO $$
DECLARE
  v_targets integer;
  v_sets integer;
  v_left integer;
  v_unsplit integer;
  v_categories integer;
  v_grouped integer;
  v_mains integer;
BEGIN
  SELECT count(*) INTO v_targets FROM setup_target_split;
  SELECT count(*) INTO v_sets FROM setup.vehicle_target_sets;
  SELECT count(*) INTO v_left
  FROM setup_target_split
  WHERE NOT (day_amount > 0 AND weekly_amount - 6 * day_amount > 0);
  SELECT count(*) INTO v_unsplit
  FROM setup_target_split AS s
  JOIN setup.vehicle_target_sets AS v
    ON v.organization_id = s.organization_id AND v.vehicle_id = s.vehicle_id
   AND v.starts_on = s.effective_from
  WHERE v.monday + v.tuesday + v.wednesday + v.thursday + v.friday + v.saturday + v.sunday
        <> s.weekly_amount;
  IF v_sets <> v_targets - v_left OR v_unsplit <> 0 THEN
    RAISE EXCEPTION 'target sets: % made from % dated weekly targets (% too small to split), % with another week total',
      v_sets, v_targets, v_left, v_unsplit;
  END IF;
  SELECT count(*), count(main_category_id) INTO v_categories, v_grouped
  FROM setup.expense_categories;
  SELECT count(*) INTO v_mains FROM setup.expense_main_categories;
  IF v_grouped <> v_categories THEN
    RAISE EXCEPTION 'main categories: % of % categories grouped', v_grouped, v_categories;
  END IF;
  RAISE NOTICE 'setup.vehicle_target_sets: % sets from % dated weekly targets; % too small to split, left for the owner; setup.expense_main_categories: % made for % categories',
    v_sets, v_targets, v_left, v_mains, v_categories;
END;
$$;
