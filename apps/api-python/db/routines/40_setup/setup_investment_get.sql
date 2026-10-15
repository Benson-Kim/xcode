-- api.setup_investment_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_vehicle_id uuid, p_now timestamptz) RETURNS jsonb
-- Purpose: what went into a visible vehicle and what has come back: the entries by date then recording instant with the recorder's name, their total, the vehicle's net from its join date through the business date, and that net as a percentage of the total (rounded half away from zero; null when nothing went in).
-- Callers: SetupRoutines.get_investment; GetInvestment (GET /setup/vehicles/{id}/investment).
-- Reads: setup.fleet_vehicles, setup.vehicle_investments, tenancy.memberships, and what tenancy.business_date, setup.vehicle_visible and setup.vehicle_net read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 time_zone_invalid via tenancy.business_date, XC404 not_found.
-- Tests: tests/db/test_setup_investment_routines.py, tests/api/test_setup_investment.py.

CREATE OR REPLACE FUNCTION api.setup_investment_get(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_vehicle_id uuid,
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
  v_joined_on date;
  v_total numeric;
  v_returned numeric;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'reports.investment');
  v_today := tenancy.business_date(p_organization_id, p_now);
  SELECT f.joined_on INTO v_joined_on
  FROM setup.fleet_vehicles AS f
  WHERE f.organization_id = p_organization_id AND f.id = p_vehicle_id;
  IF NOT FOUND OR NOT setup.vehicle_visible(p_vehicle_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  SELECT coalesce(sum(e.amount), 0) INTO v_total
  FROM setup.vehicle_investments AS e
  WHERE e.organization_id = p_organization_id AND e.vehicle_id = p_vehicle_id;
  v_returned := setup.vehicle_net(p_vehicle_id, v_joined_on, v_today, v_today);
  RETURN jsonb_build_object(
    'vehicle_id', p_vehicle_id,
    'total_invested', v_total,
    'returned', v_returned,
    'percent_paid_off', CASE WHEN v_total = 0 THEN NULL ELSE round(v_returned / v_total * 100) END,
    'entries', (
      SELECT coalesce(
               jsonb_agg(
                 jsonb_build_object(
                   'id', e.id,
                   'invested_on', e.invested_on,
                   'description', e.description,
                   'amount', e.amount,
                   'recorded_by', coalesce(m.first_name || ' ' || m.last_name, ''),
                   'recorded_at', e.recorded_at
                 ) ORDER BY e.invested_on, e.recorded_at, e.id),
               '[]'::jsonb)
      FROM setup.vehicle_investments AS e
      LEFT JOIN tenancy.memberships AS m
        ON m.organization_id = e.organization_id AND m.user_id = e.recorded_by
      WHERE e.organization_id = p_organization_id AND e.vehicle_id = p_vehicle_id
    )
  );
END;
$$;
