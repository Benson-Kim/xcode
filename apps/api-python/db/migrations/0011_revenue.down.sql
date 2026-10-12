-- Reverse of 0011_revenue.sql. A low day loses its reason and keeps its amount; Other saved without a note gets the note "Other"; the revenue settings are lost; the weekly targets come back as one revision per target set, each the week total of its set.

SET LOCAL lock_timeout = '10s';

DROP FUNCTION IF EXISTS api.revenue_capture(
  uuid, uuid, text, uuid, date, numeric, text, text, bigint, timestamptz, timestamptz
);
DROP FUNCTION IF EXISTS api.revenue_week_get(
  uuid, uuid, text, date, uuid, uuid, integer, integer, text, timestamptz
);
DROP FUNCTION IF EXISTS revenue.cell(revenue.vehicle_day, date, boolean, boolean, date);
DROP FUNCTION IF EXISTS revenue.vehicle_week(
  revenue.vehicle_day[], date, boolean, boolean, date, numeric, numeric
);
DROP FUNCTION IF EXISTS revenue.gap_band(numeric, numeric, numeric);
DROP FUNCTION IF EXISTS tenancy.check_revenue_settings(jsonb);

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

ALTER TABLE setup.vehicle_targets ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON setup.vehicle_targets TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
REVOKE ALL ON setup.vehicle_targets FROM xcode_api_executor;
GRANT SELECT ON setup.vehicle_targets TO xcode_api_executor;

INSERT INTO setup.vehicle_targets (
  organization_id, vehicle_id, revision, effective_from, weekly_amount, created_at
)
SELECT t.organization_id, t.vehicle_id,
       row_number() OVER (PARTITION BY t.organization_id, t.vehicle_id ORDER BY t.starts_on),
       t.starts_on,
       t.monday + t.tuesday + t.wednesday + t.thursday + t.friday + t.saturday + t.sunday,
       t.created_at
FROM setup.vehicle_target_sets AS t;

DROP TABLE tenancy.organization_revenue_settings;

UPDATE revenue.records SET reason = NULL, note = NULL WHERE amount IS NOT NULL AND reason IS NOT NULL;
UPDATE revenue.records SET note = 'Other' WHERE amount IS NULL AND reason = 4 AND note IS NULL;
ALTER TABLE revenue.records
  DROP CONSTRAINT ck_records_entry,
  ADD CONSTRAINT ck_records_entry CHECK (
    (amount IS NOT NULL AND reason IS NULL AND note IS NULL)
    OR (amount IS NULL AND reason IS NOT NULL AND ((reason = 4) = (note IS NOT NULL)))
  );
