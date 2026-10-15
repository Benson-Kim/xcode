-- Revenue tables: no_earnings_reasons code table and records.

SET LOCAL lock_timeout = '10s';

CREATE TABLE revenue.no_earnings_reasons (
  code smallint NOT NULL,
  name text NOT NULL,
  label text NOT NULL,
  CONSTRAINT pk_no_earnings_reasons PRIMARY KEY (code),
  CONSTRAINT uq_no_earnings_reasons_name UNIQUE (name)
);

INSERT INTO revenue.no_earnings_reasons (code, name, label) VALUES
  (1, 'garage', 'Garage'),
  (2, 'arrest', 'Arrest'),
  (3, 'no_crew', 'No Crew'),
  (4, 'other', 'Other');

CREATE TABLE revenue.records (
  organization_id uuid NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  vehicle_id uuid NOT NULL,
  business_date date NOT NULL,
  amount numeric(14,2),
  reason smallint,
  note text,
  captured_at timestamptz NOT NULL,
  captured_by uuid NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by uuid NOT NULL,
  corrected_after_date boolean NOT NULL DEFAULT false,
  version bigint NOT NULL DEFAULT 1,
  CONSTRAINT pk_records PRIMARY KEY (organization_id, id),
  CONSTRAINT fk_records_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_records_vehicle FOREIGN KEY (organization_id, vehicle_id)
    REFERENCES setup.fleet_vehicles (organization_id, id),
  CONSTRAINT fk_records_reason FOREIGN KEY (reason) REFERENCES revenue.no_earnings_reasons (code),
  CONSTRAINT fk_records_captured_by FOREIGN KEY (organization_id, captured_by)
    REFERENCES tenancy.memberships (organization_id, user_id),
  CONSTRAINT fk_records_updated_by FOREIGN KEY (organization_id, updated_by)
    REFERENCES tenancy.memberships (organization_id, user_id),
  CONSTRAINT uq_records_vehicle_day UNIQUE (organization_id, vehicle_id, business_date),
  CONSTRAINT ck_records_amount CHECK (amount > 0),
  CONSTRAINT ck_records_note CHECK (char_length(note) BETWEEN 1 AND 80),
  CONSTRAINT ck_records_entry CHECK (
    (amount IS NOT NULL AND reason IS NULL AND note IS NULL)
    OR (amount IS NULL AND reason IS NOT NULL AND ((reason = 4) = (note IS NOT NULL)))
  )
);

CREATE INDEX ix_records_business_date ON revenue.records (organization_id, business_date);

CREATE FUNCTION revenue.forbid_date_change() RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  RAISE EXCEPTION USING
    ERRCODE = 'XC422',
    MESSAGE = 'business_date_immutable',
    DETAIL = json_build_object('date', OLD.business_date)::text;
END
$$;

REVOKE ALL ON FUNCTION revenue.forbid_date_change() FROM PUBLIC;

CREATE TRIGGER forbid_date_change BEFORE UPDATE ON revenue.records
  FOR EACH ROW WHEN (NEW.business_date IS DISTINCT FROM OLD.business_date)
  EXECUTE FUNCTION revenue.forbid_date_change();
CREATE TRIGGER touch_updated_at BEFORE UPDATE ON revenue.records
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();

ALTER TABLE revenue.records ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON revenue.records TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());

REVOKE ALL ON revenue.no_earnings_reasons, revenue.records FROM xcode_api_executor;
GRANT SELECT ON revenue.no_earnings_reasons TO xcode_api_executor, xcode_readonly;
GRANT USAGE ON SCHEMA revenue TO xcode_readonly;
GRANT SELECT, INSERT, UPDATE ON revenue.records TO xcode_api_executor;
