-- Reverse 0025: the fleet-wide low-day threshold comes back at KES 4,000 and the target sets lose their low revenue figure; `db routines` of the release before restores the routines without it.

SET LOCAL lock_timeout = '10s';

DROP FUNCTION IF EXISTS api.setup_target_set_save(
  uuid, uuid, text, uuid, date, numeric[], numeric, timestamptz
);
DROP FUNCTION IF EXISTS api.setup_vehicle_create(
  uuid, uuid, text, uuid, text, text, date, numeric[], numeric, numeric, text, timestamptz
);
DROP FUNCTION IF EXISTS setup.low_below_on(uuid, date);

ALTER TABLE tenancy.organization_revenue_settings
  ADD COLUMN low_day_threshold numeric(14,2) NOT NULL DEFAULT 4000,
  ADD CONSTRAINT ck_revenue_settings_low_day_threshold CHECK (low_day_threshold >= 0);

ALTER TABLE setup.vehicle_target_sets DROP COLUMN low_below;
