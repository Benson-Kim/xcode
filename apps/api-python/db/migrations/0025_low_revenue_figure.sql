-- Low revenue figure per vehicle (design notes decided 8 November 2026, prototype Web v2.34): each target set carries the amount below which a day with revenue needs a reason, every existing set gets KES 4,000, and the fleet-wide low-day threshold goes.

SET LOCAL lock_timeout = '10s';

-- Routines whose signature changes; `db routines` creates the new ones.
DROP FUNCTION IF EXISTS api.setup_target_set_save(uuid, uuid, text, uuid, date, numeric[], timestamptz);
DROP FUNCTION IF EXISTS api.setup_vehicle_create(
  uuid, uuid, text, uuid, text, text, date, numeric[], numeric, text, timestamptz
);

ALTER TABLE setup.vehicle_target_sets
  ADD COLUMN low_below numeric(14,2) NOT NULL DEFAULT 4000,
  ADD CONSTRAINT ck_vehicle_target_sets_low_below CHECK (low_below >= 0);

ALTER TABLE tenancy.organization_revenue_settings DROP COLUMN low_day_threshold;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM setup.vehicle_target_sets WHERE low_below <> 4000) THEN
    RAISE EXCEPTION 'a target set did not get the low revenue figure of KES 4,000';
  END IF;
END;
$$;
