-- Fuel on revenue (design notes Web v2.36 and v2.37): a record with an amount may say the vehicle was fueled (true), not fueled (false) or nothing (NULL), and the revenue settings hold the amount from which the fuel question is asked, KES 10,000.

SET LOCAL lock_timeout = '10s';

-- Routines whose signature changes; `db routines` creates the new ones.
DROP FUNCTION IF EXISTS api.revenue_capture(
  uuid, uuid, text, uuid, date, numeric, text, text, bigint, timestamptz, timestamptz
);
DROP FUNCTION IF EXISTS revenue.capture_entry(
  uuid, uuid, uuid, date, numeric, text, text, bigint, timestamptz, timestamptz
);
DROP FUNCTION IF EXISTS revenue.capture_row(
  uuid, uuid, text[], numeric, date, date, uuid, date, numeric, text, text, bigint, timestamptz,
  timestamptz, boolean
);
-- revenue.vehicle_day gains the day's low revenue figure (0025) and fuel answer: the type goes
-- with the routines that take it (revenue.vehicle_days, revenue.cell, revenue.vehicle_week), and
-- `db routines` creates them again.
DROP TYPE IF EXISTS revenue.vehicle_day CASCADE;

ALTER TABLE revenue.records
  ADD COLUMN fuel boolean,
  ADD CONSTRAINT ck_records_fuel CHECK (fuel IS NULL OR amount IS NOT NULL);

ALTER TABLE tenancy.organization_revenue_settings
  ADD COLUMN fuel_question_from numeric(14,2) NOT NULL DEFAULT 10000,
  ADD CONSTRAINT ck_revenue_settings_fuel_question_from CHECK (fuel_question_from > 0);
