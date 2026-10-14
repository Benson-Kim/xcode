-- api.report_catalog_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_now timestamptz) RETURNS jsonb
-- Purpose: the reports the actor may open (ReportsAccessDto): the business date, the first day of the week, the fleet report ids (investment only with reports.investment), the petty-cash report ids (only with pettycash.reports), the floats a petty-cash report can be cut to (every float with pettycash.view_all, else the actor's own; none without pettycash.reports) and whether the actor may export (reports.export).
-- Callers: ReportsRoutines.access; GetReportsAccess (GET /setup/reports).
-- Reads: what tenancy.business_date, tenancy.has_permission, tenancy.settings_document and pettycash.visible_holders read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_report_routines.py, tests/api/test_reports.py.

CREATE OR REPLACE FUNCTION api.report_catalog_get(
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
DECLARE
  v_today date;
  v_investment boolean;
  v_pettycash boolean;
  v_holders jsonb := '[]'::jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'reports.view');
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_investment := tenancy.has_permission('reports.investment');
  v_pettycash := tenancy.has_permission('pettycash.reports');
  IF v_pettycash THEN
    SELECT coalesce(
             jsonb_agg(
               jsonb_build_object('id', h.user_id, 'name', h.name, 'active', h.active)
               ORDER BY h.position),
             '[]'::jsonb
           )
    INTO v_holders
    FROM pettycash.visible_holders(tenancy.has_permission('pettycash.view_all'))
         WITH ORDINALITY AS h (user_id, name, active, position);
  END IF;
  RETURN jsonb_build_object(
    'business_date', v_today,
    'first_day_of_week', (tenancy.settings_document('localization') ->> 'first_day_of_week')::integer,
    'fleet', to_jsonb(
      ARRAY['net', 'target', 'moneyOut', 'gaps', 'savings']
      || CASE WHEN v_investment THEN ARRAY['investment'] ELSE '{}'::text[] END
    ),
    'petty_cash', CASE
                    WHEN v_pettycash THEN to_jsonb(
                      ARRAY['cashBook', 'managers', 'vehicles', 'items', 'waiting', 'sentBack', 'rejected']
                    )
                    ELSE '[]'::jsonb
                  END,
    'holders', v_holders,
    'can_export', tenancy.has_permission('reports.export')
  );
END;
$$;
