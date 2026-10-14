-- api.pettycash_options_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_date date, p_now timestamptz) RETURNS jsonb
-- Purpose: the choices of the entry form on p_date (default the business date) (PettyCashOptionsDto): for a person who may add or edit an expense, the vehicles they see that are in the fleet on the date (by registration, with their fleet number) and the expense items in use on the date (by category, then name); for a person who may add for another manager, give cash or record a credit note, the active holders; every other part an empty list.
-- Callers: PettyCashRoutines.options; GetPettyCashOptions (GET /setup/pettycash/options).
-- Reads: setup.fleet_vehicles, setup.psv_companies, setup.expense_items, setup.expense_categories, and what tenancy.business_date, tenancy.effective_permissions, setup.visible_vehicles, setup.vehicle_active_on and pettycash.holders read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 time_zone_invalid via tenancy.business_date, XC422 pettycash_future_date via pettycash.check_date, XC422 pettycash_too_old via pettycash.check_date.
-- Tests: tests/db/test_pettycash_routines.py, tests/api/test_petty_cash.py.

CREATE OR REPLACE FUNCTION api.pettycash_options_get(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_date date,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_permissions text[];
  v_today date;
  v_date date;
  v_expenses boolean;
  v_vehicles jsonb := '[]'::jsonb;
  v_items jsonb := '[]'::jsonb;
  v_holders jsonb := '[]'::jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY[
    'pettycash.spend', 'pettycash.spend_other', 'pettycash.edit_own', 'pettycash.edit',
    'pettycash.issue', 'pettycash.credit'
  ]);
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_date := coalesce(p_date, v_today);
  PERFORM pettycash.check_date(v_date, v_today);
  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  v_expenses := v_permissions
    && ARRAY['pettycash.spend', 'pettycash.spend_other', 'pettycash.edit_own', 'pettycash.edit'];

  IF v_expenses THEN
    SELECT coalesce(jsonb_agg(
             jsonb_build_object(
               'id', f.id,
               'company_id', f.company_id,
               'company_name', c.name,
               'registration', f.registration,
               'active', true,
               'fleet_number', f.fleet_number
             ) ORDER BY f.registration, f.id), '[]'::jsonb)
    INTO v_vehicles
    FROM setup.fleet_vehicles AS f
    JOIN setup.psv_companies AS c ON c.organization_id = f.organization_id AND c.id = f.company_id
    WHERE f.organization_id = p_organization_id
      AND f.id IN (SELECT visible.id FROM setup.visible_vehicles() AS visible (id))
      AND setup.vehicle_active_on(f.id, v_date);

    SELECT coalesce(jsonb_agg(
             jsonb_build_object(
               'id', i.id,
               'name', i.name,
               'category_id', c.id,
               'category_name', c.name,
               'bucket', c.bucket
             ) ORDER BY c.name, i.name, i.id), '[]'::jsonb)
    INTO v_items
    FROM setup.expense_items AS i
    JOIN setup.expense_categories AS c ON c.organization_id = i.organization_id AND c.id = i.category_id
    WHERE i.organization_id = p_organization_id
      AND (i.stopped_on IS NULL OR i.stopped_on > v_date)
      AND (c.stopped_on IS NULL OR c.stopped_on > v_date);
  END IF;

  IF v_permissions && ARRAY['pettycash.spend_other', 'pettycash.issue', 'pettycash.credit'] THEN
    SELECT coalesce(jsonb_agg(jsonb_build_object('id', h.user_id, 'name', h.name, 'active', h.active)
                              ORDER BY h.position), '[]'::jsonb)
    INTO v_holders
    FROM pettycash.holders() WITH ORDINALITY AS h (user_id, name, active, position)
    WHERE h.active;
  END IF;

  RETURN jsonb_build_object('vehicles', v_vehicles, 'items', v_items, 'holders', v_holders);
END;
$$;
