-- System settings (design notes Web v2.38): the catalogue of on/off settings with their defaults, Targets (on) the first; each organization's choices, where no row means the default; the right `settings.edit`, "Change settings", in its own Settings group and held by the Owner role only; and a target set may hold seven zero day targets, as a vehicle added while Targets is off starts with none.

SET LOCAL lock_timeout = '10s';

CREATE TABLE tenancy.system_settings (
  key text NOT NULL,
  label text NOT NULL,
  sort_order smallint NOT NULL,
  default_enabled boolean NOT NULL,
  CONSTRAINT pk_system_settings PRIMARY KEY (key),
  CONSTRAINT uq_system_settings_sort_order UNIQUE (sort_order)
);

INSERT INTO tenancy.system_settings (key, label, sort_order, default_enabled) VALUES
  ('targets', 'Targets', 1, true);

CREATE TABLE tenancy.organization_system_settings (
  organization_id uuid NOT NULL,
  key text NOT NULL,
  enabled boolean NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_organization_system_settings PRIMARY KEY (organization_id, key),
  CONSTRAINT fk_organization_system_settings_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_organization_system_settings_key FOREIGN KEY (key)
    REFERENCES tenancy.system_settings (key)
);

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON tenancy.organization_system_settings
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();

ALTER TABLE tenancy.organization_system_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON tenancy.organization_system_settings TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());

REVOKE ALL ON tenancy.system_settings, tenancy.organization_system_settings FROM xcode_api_executor;
GRANT SELECT ON tenancy.system_settings TO xcode_api_executor, xcode_readonly;
GRANT SELECT, INSERT, UPDATE ON tenancy.organization_system_settings TO xcode_api_executor;

INSERT INTO tenancy.permissions (key, group_name, label, group_order, item_order, catalogue, section)
VALUES ('settings.edit', 'Settings', 'Change settings', 13, 1, true, NULL);
INSERT INTO tenancy.role_defaults (role_name, permission) VALUES ('Owner', 'settings.edit');

-- All seven above zero (Targets on) or all seven zero (a vehicle added with Targets off).
ALTER TABLE setup.vehicle_target_sets
  DROP CONSTRAINT ck_vehicle_target_sets_days,
  ADD CONSTRAINT ck_vehicle_target_sets_days CHECK (
    (monday > 0 AND tuesday > 0 AND wednesday > 0 AND thursday > 0 AND friday > 0
      AND saturday > 0 AND sunday > 0)
    OR (monday = 0 AND tuesday = 0 AND wednesday = 0 AND thursday = 0 AND friday = 0
      AND saturday = 0 AND sunday = 0)
  );

DO $$
BEGIN
  IF (SELECT count(*) FROM tenancy.permissions WHERE catalogue) <> 60
     OR NOT EXISTS (
       SELECT 1 FROM tenancy.role_defaults WHERE role_name = 'Owner' AND permission = 'settings.edit'
     ) THEN
    RAISE EXCEPTION 'the catalogue does not hold 60 rights with settings.edit on the Owner';
  END IF;
END;
$$;
