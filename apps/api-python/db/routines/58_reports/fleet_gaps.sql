-- reports.fleet_gaps(p_from date, p_to date, p_company_id uuid, p_today date) RETURNS jsonb
-- Purpose: the Capture gaps table: one row per missing revenue day of the visible vehicles in the period (in the fleet, before the business date, without a record), by day then registration: date, vehicle, company and what is missing ("Revenue not captured"); headline Missing days (the rows), figure Vehicles with gaps.
-- Callers: reports.build.
-- Reads: what reports.vehicles and reports.vehicle_figures read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.fleet_gaps(p_from date, p_to date, p_company_id uuid, p_today date)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_ids uuid[] := ARRAY(SELECT v.vehicle_id FROM reports.vehicles(p_company_id) AS v);
  v_rows jsonb;
  v_days numeric;
  v_vehicles numeric;
BEGIN
  WITH lines AS (
    SELECT d.day, v.vehicle_id, v.registration, v.company_name
    FROM reports.vehicle_figures(v_ids, p_from, p_to, p_today) AS f
    JOIN reports.vehicles(p_company_id) AS v ON v.vehicle_id = f.vehicle_id
    CROSS JOIN unnest(f.missing_days) AS d (day)
  )
  SELECT coalesce(
           jsonb_agg(
             jsonb_build_array(l.day, l.registration, l.company_name, 'Revenue not captured')
             ORDER BY l.day, l.registration COLLATE "C", l.vehicle_id),
           '[]'::jsonb
         ),
         count(*),
         count(DISTINCT l.vehicle_id)
  INTO v_rows, v_days, v_vehicles
  FROM lines AS l;

  RETURN reports.build_table(
    'fleet',
    'gaps',
    'Capture gaps',
    p_from,
    p_to,
    p_today,
    reports.figure('Missing days', v_days, 'count'),
    jsonb_build_array(reports.figure('Vehicles with gaps', v_vehicles, 'count')),
    jsonb_build_array(
      reports.heading('date', 'Date', 'date', false),
      reports.heading('vehicle', 'Vehicle', 'vehicle', false),
      reports.heading('company', 'Company', 'text', false),
      reports.heading('missing', 'What is missing', 'text', false)
    ),
    v_rows
  );
END;
$$;

REVOKE ALL ON FUNCTION reports.fleet_gaps(date, date, uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.fleet_gaps(date, date, uuid, date) TO xcode_api_executor;
