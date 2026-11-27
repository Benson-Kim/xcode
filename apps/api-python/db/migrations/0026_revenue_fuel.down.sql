-- Reverse 0026: records lose the fuel answer and the revenue settings the fuel question amount; the routines with fuel go, and `db routines` of the release before restores the ones without it.

SET LOCAL lock_timeout = '10s';

DROP FUNCTION IF EXISTS api.revenue_capture(
  uuid, uuid, text, uuid, date, numeric, text, text, boolean, boolean, bigint, timestamptz,
  timestamptz
);
DROP FUNCTION IF EXISTS revenue.capture_entry(
  uuid, uuid, uuid, date, numeric, text, text, boolean, boolean, bigint, timestamptz, timestamptz
);
DROP FUNCTION IF EXISTS revenue.capture_row(
  uuid, uuid, text[], numeric, date, date, uuid, date, numeric, text, text, boolean, boolean, bigint,
  timestamptz, timestamptz, boolean
);
DROP TYPE IF EXISTS revenue.vehicle_day CASCADE;

ALTER TABLE revenue.records DROP COLUMN fuel;
ALTER TABLE tenancy.organization_revenue_settings DROP COLUMN fuel_question_from;
