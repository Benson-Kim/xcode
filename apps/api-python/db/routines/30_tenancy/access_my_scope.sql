-- api.access_my_scope(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_now timestamptz) RETURNS jsonb
-- Purpose: the actor's own reach for "Your access": the all-companies flag, the companies they can see (by name) and the vehicles they can see, retired ones included (by registration); how far back they may change records in words and the earliest date that allows on today's business date (null for any date).
-- Callers: TenancyRoutines.my_scope; GetMyAccessScope (GET /setup/access/me).
-- Reads: setup.psv_companies, setup.fleet_vehicles, tenancy.memberships, and what tenancy.actor_scope, setup.visible_companies, setup.visible_vehicles, tenancy.business_date, tenancy.earliest_writable and tenancy.back_limit_words read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_access_routines.py, tests/api/test_access.py.

CREATE OR REPLACE FUNCTION api.access_my_scope(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  RETURN jsonb_build_object(
    'all_companies', (tenancy.actor_scope()).all_companies,
    'companies', (
      SELECT coalesce(jsonb_agg(jsonb_build_object('id', c.id, 'name', c.name) ORDER BY c.name, c.id), '[]'::jsonb)
      FROM setup.psv_companies AS c
      WHERE c.organization_id = p_organization_id
        AND c.id IN (SELECT visible.id FROM setup.visible_companies() AS visible (id))
    ),
    'vehicles', (
      SELECT coalesce(
               jsonb_agg(
                 jsonb_build_object('id', f.id, 'registration', f.registration, 'fleet_number', f.fleet_number, 'company_id', f.company_id)
                 ORDER BY f.registration, f.id),
               '[]'::jsonb)
      FROM setup.fleet_vehicles AS f
      WHERE f.organization_id = p_organization_id
        AND f.id IN (SELECT visible.id FROM setup.visible_vehicles() AS visible (id))
    ),
    'can_change', (
      SELECT tenancy.back_limit_words(m.back_limit_mode, m.back_limit_count, m.back_limit_from)
      FROM tenancy.memberships AS m
      WHERE m.organization_id = p_organization_id AND m.user_id = p_actor_id
    ),
    'earliest', tenancy.earliest_writable(
      p_organization_id, p_actor_id, tenancy.business_date(p_organization_id, p_now)
    )
  );
END;
$$;
