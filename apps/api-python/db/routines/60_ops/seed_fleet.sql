-- ops.seed_fleet(p_organization_id uuid, p_owner_id uuid, p_request_id text, p_company_ids uuid[], p_now timestamptz) RETURNS void
-- Purpose: build the demo fleet's history day by day, from 42 days before the business date to yesterday: each day's setup events, revenue and petty cash run through the business routines at that day's instant, so the change log, versions and dates read as if the organization had been used; ends with a dated target set starting today.
-- Callers: api.ops_seed_demo.
-- Reads: setup.fleet_vehicles. Writes: what ops.seed_fleet_setup, ops.seed_revenue_day, ops.seed_pettycash_day and api.setup_target_set_save write.
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py.
-- The caller adds it only to an organization with no vehicle. p_company_ids lists the companies in the order of the vehicle plan.

CREATE OR REPLACE FUNCTION ops.seed_fleet(
  p_organization_id uuid,
  p_owner_id uuid,
  p_request_id text,
  p_company_ids uuid[],
  p_now timestamptz
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  c_days CONSTANT integer := 42;
  v_today date;
  v_n integer;
  v_vehicle_id uuid;
BEGIN
  PERFORM tenancy.enter_organization_as_operator(p_organization_id);
  v_today := tenancy.business_date(p_organization_id, p_now);

  FOR v_n IN REVERSE c_days..1 LOOP
    PERFORM ops.seed_fleet_setup(
      p_organization_id, p_owner_id, p_request_id, p_company_ids, v_n, v_today - v_n,
      p_now - make_interval(days => v_n)
    );
    PERFORM ops.seed_revenue_day(
      p_organization_id, p_owner_id, p_request_id, v_n, v_today - v_n,
      p_now - make_interval(days => v_n)
    );
    PERFORM ops.seed_pettycash_day(
      p_organization_id, p_owner_id, p_request_id, v_n, v_today - v_n,
      p_now - make_interval(days => v_n)
    );
  END LOOP;

  PERFORM tenancy.enter_organization_as_operator(p_organization_id);
  SELECT f.id INTO v_vehicle_id
  FROM setup.fleet_vehicles AS f
  WHERE f.organization_id = p_organization_id AND f.registration = 'KDB 117P';
  PERFORM api.setup_target_set_save(
    p_owner_id, p_organization_id, p_request_id, v_vehicle_id, v_today,
    ARRAY[5800, 5800, 5800, 5800, 6300, 7300, 4800]::numeric[], p_now
  );
END;
$$;

REVOKE ALL ON FUNCTION ops.seed_fleet(uuid, uuid, text, uuid[], timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ops.seed_fleet(uuid, uuid, text, uuid[], timestamptz) TO xcode_api_executor;
