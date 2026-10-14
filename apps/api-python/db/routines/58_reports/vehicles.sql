-- reports.vehicles(p_company_id uuid) RETURNS TABLE (vehicle_id uuid, registration text, fleet_number text, company_name text, joined_on date)
-- Purpose: the vehicles the current actor sees (setup.visible_vehicles), of one company when given, by registration ordinally then id: the rows every fleet report is cut to.
-- Callers: reports.fleet_net, reports.fleet_target, reports.fleet_gaps, reports.fleet_money_out, reports.fleet_savings, reports.fleet_investment.
-- Reads: setup.fleet_vehicles, setup.psv_companies, and what setup.visible_vehicles reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.vehicles(p_company_id uuid)
RETURNS TABLE (vehicle_id uuid, registration text, fleet_number text, company_name text, joined_on date)
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT f.id, f.registration, f.fleet_number, c.name, f.joined_on
  FROM setup.fleet_vehicles AS f
  JOIN setup.psv_companies AS c ON c.organization_id = f.organization_id AND c.id = f.company_id
  WHERE f.organization_id = tenancy.current_organization()
    AND f.id IN (SELECT setup.visible_vehicles())
    AND (p_company_id IS NULL OR f.company_id = p_company_id)
  ORDER BY f.registration COLLATE "C", f.id;
$$;

REVOKE ALL ON FUNCTION reports.vehicles(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.vehicles(uuid) TO xcode_api_executor;
