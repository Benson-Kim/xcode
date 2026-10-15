-- ops.seed_revenue_day(p_organization_id uuid, p_owner_id uuid, p_request_id text, p_days_back integer, p_day date, p_at timestamptz) RETURNS void
-- Purpose: capture one demo day's revenue through api.revenue_capture for every vehicle in the fleet that day, by the demo clerk for the first company and the demo fleet manager for the second (the Owner when either is missing): an amount around the day's target, now and then no record at all, a no-earnings reason or a low day with a reason; and first correct, as the Owner, some of the previous day's amounts so the record reaches version 2.
-- Callers: ops.seed_fleet.
-- Reads: setup.fleet_vehicles, revenue.records, identity.users, tenancy.memberships, and what setup.day_target and setup.vehicle_active_on read. Writes: what api.revenue_capture writes.
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py.
-- Which day gets which entry follows from p_days_back and the vehicle's place in the plan, so a run always gives the same fleet.

CREATE OR REPLACE FUNCTION ops.seed_revenue_day(
  p_organization_id uuid,
  p_owner_id uuid,
  p_request_id text,
  p_days_back integer,
  p_day date,
  p_at timestamptz
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  c_reasons CONSTANT text[] := ARRAY['Garage', 'Arrest', 'No Crew', 'Other'];
  v_plan record;
  v_vehicle_id uuid;
  v_record revenue.records;
  v_clerk_id uuid;
  v_manager_id uuid;
  v_actor_id uuid;
  v_target numeric;
  v_amount numeric;
  v_reason text;
  v_note text;
  v_spread integer;
BEGIN
  PERFORM tenancy.enter_organization_as_operator(p_organization_id);
  SELECT m.user_id INTO v_clerk_id
  FROM tenancy.memberships AS m
  JOIN identity.users AS u ON u.id = m.user_id
  WHERE m.organization_id = p_organization_id AND m.active AND u.status = 'active'
    AND u.email = 'wanjiru.kamau@zurigenesis.co.ke';
  SELECT m.user_id INTO v_manager_id
  FROM tenancy.memberships AS m
  JOIN identity.users AS u ON u.id = m.user_id
  WHERE m.organization_id = p_organization_id AND m.active AND u.status = 'active'
    AND u.email = 'brian.mwangi@metrotrans.co.ke';

  FOR v_plan IN SELECT p.* FROM ops.seed_vehicle_plan() AS p ORDER BY p.idx LOOP
    PERFORM tenancy.enter_organization_as_operator(p_organization_id);
    SELECT f.id INTO v_vehicle_id
    FROM setup.fleet_vehicles AS f
    WHERE f.organization_id = p_organization_id AND f.registration = v_plan.registration;
    IF v_vehicle_id IS NULL THEN
      CONTINUE;
    END IF;

    SELECT r.* INTO v_record
    FROM revenue.records AS r
    WHERE r.organization_id = p_organization_id
      AND r.vehicle_id = v_vehicle_id
      AND r.business_date = p_day - 1;
    IF FOUND AND v_record.amount IS NOT NULL AND v_record.reason IS NULL
       AND (p_days_back + v_plan.idx) % 11 = 3 THEN
      PERFORM api.revenue_capture(
        p_owner_id, p_organization_id, p_request_id, v_vehicle_id, p_day - 1, v_record.amount + 250,
        NULL, NULL, v_record.version, NULL, p_at
      );
      PERFORM tenancy.enter_organization_as_operator(p_organization_id);
    END IF;

    IF NOT setup.vehicle_active_on(v_vehicle_id, p_day) THEN
      CONTINUE;
    END IF;
    IF (p_days_back + v_plan.idx * 5) % 13 = 4 THEN
      CONTINUE;
    END IF;

    v_actor_id := coalesce(CASE v_plan.company_index WHEN 1 THEN v_clerk_id ELSE v_manager_id END, p_owner_id);
    v_target := setup.day_target(v_vehicle_id, p_day);
    v_spread := (abs(hashtext(v_plan.registration || p_day::text)::bigint) % 36)::integer;
    v_reason := c_reasons[1 + (p_days_back + v_plan.idx) % 4];
    v_note := CASE WHEN v_reason = 'Other' THEN 'Waiting for the insurance assessor' END;

    IF (p_days_back * 3 + v_plan.idx) % 17 = 5 THEN
      v_amount := NULL;
    ELSIF (p_days_back + v_plan.idx * 2) % 23 = 7 THEN
      v_amount := 2500 + (v_spread % 10) * 100;
    ELSE
      v_amount := round(v_target * (90 + v_spread) / 100 / 50) * 50;
      v_reason := NULL;
      v_note := NULL;
    END IF;

    PERFORM api.revenue_capture(
      v_actor_id, p_organization_id, p_request_id, v_vehicle_id, p_day, v_amount, v_reason, v_note,
      NULL, NULL, p_at
    );
  END LOOP;
END;
$$;

REVOKE ALL ON FUNCTION ops.seed_revenue_day(uuid, uuid, text, integer, date, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ops.seed_revenue_day(uuid, uuid, text, integer, date, timestamptz)
  TO xcode_api_executor;
