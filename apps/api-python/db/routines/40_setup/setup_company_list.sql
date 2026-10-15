-- api.setup_company_list(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_page integer, p_page_size integer, p_now timestamptz) RETURNS jsonb
-- Purpose: one page of the companies the actor can see, by name then id, each with the count of their visible vehicles in the fleet on the business date, whether it is in use and its archive date; {total, items}.
-- Callers: SetupRoutines.list_companies; ListCompanies (GET /setup/companies).
-- Reads: setup.psv_companies, setup.fleet_vehicles, and what tenancy.business_date, setup.visible_companies and setup.visible_vehicles read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 page_out_of_range via tenancy.check_page, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_setup_company_routines.py, tests/api/test_setup_companies.py.

CREATE OR REPLACE FUNCTION api.setup_company_list(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_page integer,
  p_page_size integer,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_today date;
  v_companies uuid[];
  v_vehicles uuid[];
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'companies.view');
  PERFORM tenancy.check_page(p_page, p_page_size);
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_companies := ARRAY(SELECT visible.id FROM setup.visible_companies() AS visible (id));
  v_vehicles := ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id));
  RETURN jsonb_build_object(
    'total', cardinality(v_companies),
    'items', (
      SELECT coalesce(jsonb_agg(page.document ORDER BY page.name, page.id), '[]'::jsonb)
      FROM (
        SELECT c.name, c.id,
               jsonb_build_object(
                 'id', c.id,
                 'name', c.name,
                 'vehicle_count', (
                   SELECT count(*)
                   FROM setup.fleet_vehicles AS f
                   WHERE f.organization_id = c.organization_id
                     AND f.company_id = c.id
                     AND f.id = ANY (v_vehicles)
                     AND f.joined_on <= v_today
                     AND (f.left_on IS NULL OR f.left_on > v_today)
                 ),
                 'active', c.archived_on IS NULL OR c.archived_on > v_today,
                 'archived_on', c.archived_on
               ) AS document
        FROM setup.psv_companies AS c
        WHERE c.organization_id = p_organization_id AND c.id = ANY (v_companies)
        ORDER BY c.name, c.id
        OFFSET (p_page - 1) * p_page_size
        LIMIT p_page_size
      ) AS page
    )
  );
END;
$$;
