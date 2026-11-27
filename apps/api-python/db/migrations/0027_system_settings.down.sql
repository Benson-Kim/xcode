-- Reverse 0027: the system settings and the right `settings.edit` go, with every grant of it, and target sets need day targets above zero again; refused while a set of zero day targets exists.

SET LOCAL lock_timeout = '10s';

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM setup.vehicle_target_sets WHERE monday = 0) THEN
    RAISE EXCEPTION 'a target set holds zero day targets; give the vehicle day targets first';
  END IF;
END;
$$;

DROP FUNCTION IF EXISTS api.setup_settings_get(uuid, uuid, text);
DROP FUNCTION IF EXISTS api.setup_settings_set(uuid, uuid, text, text, boolean, timestamptz);
DROP FUNCTION IF EXISTS tenancy.setting_enabled(text);
DROP FUNCTION IF EXISTS tenancy.system_settings_document();

ALTER TABLE setup.vehicle_target_sets
  DROP CONSTRAINT ck_vehicle_target_sets_days,
  ADD CONSTRAINT ck_vehicle_target_sets_days CHECK (
    monday > 0 AND tuesday > 0 AND wednesday > 0 AND thursday > 0 AND friday > 0
    AND saturday > 0 AND sunday > 0
  );

DELETE FROM tenancy.role_grants WHERE permission = 'settings.edit';
DELETE FROM tenancy.permission_overrides WHERE permission = 'settings.edit';
DELETE FROM tenancy.role_defaults WHERE permission = 'settings.edit';
DELETE FROM tenancy.permission_dependencies
WHERE permission = 'settings.edit' OR needs = 'settings.edit';
DELETE FROM tenancy.permissions WHERE key = 'settings.edit';

DROP TABLE tenancy.organization_system_settings;
DROP TABLE tenancy.system_settings;
