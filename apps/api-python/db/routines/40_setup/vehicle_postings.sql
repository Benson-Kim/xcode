-- setup.vehicle_postings(p_vehicle_id uuid, p_window daterange) RETURNS TABLE (item_id uuid, version_id uuid, day date, name text, kind smallint, amount numeric, bucket smallint)
-- Purpose: the scheduled postings of the vehicle in the window: every due day of every version that shares a cost or saving with it, while that version is in charge, at the vehicle's share; a cost reports its stored bucket or recurring charges (2), a saving none. Unordered.
-- Callers: setup.vehicle_net, api.setup_vehicle_report.
-- Reads: setup.recurring_allocations, setup.recurring_versions, and what setup.recurring_due_days reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_vehicle_routines.py.

CREATE OR REPLACE FUNCTION setup.vehicle_postings(p_vehicle_id uuid, p_window daterange)
RETURNS TABLE (
  item_id uuid,
  version_id uuid,
  day date,
  name text,
  kind smallint,
  amount numeric,
  bucket smallint
)
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT v.item_id,
         v.id,
         due.day,
         v.name,
         v.kind,
         a.amount,
         CASE WHEN v.kind = 1 THEN coalesce(v.bucket, 2::smallint) END
  FROM setup.recurring_allocations AS a
  JOIN setup.recurring_versions AS v
    ON v.organization_id = a.organization_id AND v.id = a.version_id
  CROSS JOIN LATERAL setup.recurring_due_days(v, lower(p_window), upper(p_window) - 1) AS due (day)
  WHERE a.organization_id = tenancy.current_organization()
    AND a.vehicle_id = p_vehicle_id
    AND NOT isempty(p_window);
$$;

REVOKE ALL ON FUNCTION setup.vehicle_postings(uuid, daterange) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.vehicle_postings(uuid, daterange) TO xcode_api_executor;
