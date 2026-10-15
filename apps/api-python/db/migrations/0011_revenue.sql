-- Revenue of the design notes v2.29 to v2.31: a day below the low-day threshold keeps its amount with a reason, the note on Other becomes optional, the organization settings of the threshold and of the gap's amber band, and the weekly targets leave now that every reader uses the target sets.

SET LOCAL lock_timeout = '10s';

-- Routines whose signature changes; `db routines` creates the new ones.
DROP FUNCTION IF EXISTS api.revenue_capture(
  uuid, uuid, text, uuid, date, numeric, text, text, bigint, timestamptz
);
DROP FUNCTION IF EXISTS api.revenue_week_get(
  uuid, uuid, text, date, uuid, uuid, integer, integer, timestamptz
);
DROP FUNCTION IF EXISTS revenue.cell(revenue.vehicle_day, date, boolean, boolean);
DROP FUNCTION IF EXISTS revenue.vehicle_week(revenue.vehicle_day[], date, boolean, boolean);

-- An amount, an amount with a reason (a low day) or a reason alone (no revenue); the note goes
-- only with Other and is optional (IS NOT DISTINCT FROM: a NULL reason must fail, not pass). That
-- a reason goes with an amount only below the threshold is the capture routine's rule, as the
-- threshold is a setting.
ALTER TABLE revenue.records
  DROP CONSTRAINT ck_records_entry,
  ADD CONSTRAINT ck_records_entry CHECK (
    (amount IS NOT NULL OR reason IS NOT NULL) AND (note IS NULL OR reason IS NOT DISTINCT FROM 4)
  );

-- No row reads as the defaults, so creating an organization is unchanged.
CREATE TABLE tenancy.organization_revenue_settings (
  organization_id uuid NOT NULL,
  low_day_threshold numeric(14,2) NOT NULL DEFAULT 4000,
  gap_amber_percent numeric(5,2) NOT NULL DEFAULT 10,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_revenue_settings PRIMARY KEY (organization_id),
  CONSTRAINT fk_revenue_settings_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT ck_revenue_settings_low_day_threshold CHECK (low_day_threshold >= 0),
  CONSTRAINT ck_revenue_settings_gap_amber_percent CHECK (gap_amber_percent BETWEEN 0 AND 100)
);

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON tenancy.organization_revenue_settings
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();

ALTER TABLE tenancy.organization_revenue_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenancy.organization_revenue_settings TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());

REVOKE ALL ON tenancy.organization_revenue_settings FROM xcode_api_executor;
GRANT SELECT, INSERT, UPDATE ON tenancy.organization_revenue_settings TO xcode_api_executor;

-- Read by nothing since 0010 made the target sets from it.
DROP TABLE setup.vehicle_targets;
