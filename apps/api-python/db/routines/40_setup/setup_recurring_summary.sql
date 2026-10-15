-- api.setup_recurring_summary(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_now timestamptz) RETURNS jsonb
-- Purpose: the month holding the business date on the actor's vehicles: {from_date, to_date, costs_due, saved, savings_balance, running_costs, paused_costs, running_savings, paused_savings}. costs_due is every cost run of the month, those after today on vehicles in the fleet those days (join and leave only) and not paused; saved the saving runs set aside this month to today; savings_balance every saving's balance today, openings included; the counts are the visible items of each kind not stopped or ended, running or paused. Cost figures are null without scheduled.view, saving figures without savings.view.
-- Callers: SetupRoutines.recurring_summary; GetSetupRecurringSummary (GET /setup/recurring/summary).
-- Reads: setup.recurring_items, setup.recurring_pauses, setup.recurring_versions, and what tenancy.business_date, tenancy.has_permission, setup.visible_vehicles, setup.recurring_visible, setup.recurring_current_version, setup.scheduled_runs and setup.saving_balance read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_recurring_pause_routines.py, tests/api/test_recurring_pause.py.

CREATE OR REPLACE FUNCTION api.setup_recurring_summary(
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
  v_from date;
  v_to date;
  v_costs boolean;
  v_savings boolean;
  v_vehicles uuid[];
  v_costs_due numeric;
  v_saved numeric;
  v_balance numeric;
  v_running_costs integer;
  v_paused_costs integer;
  v_running_savings integer;
  v_paused_savings integer;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['scheduled.view', 'savings.view']);
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_from := date_trunc('month', v_today)::date;
  v_to := (v_from + interval '1 month' - interval '1 day')::date;
  v_costs := tenancy.has_permission('scheduled.view');
  v_savings := tenancy.has_permission('savings.view');
  v_vehicles := ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id));

  IF v_costs THEN
    SELECT coalesce(sum(r.amount), 0) INTO v_costs_due
    FROM setup.scheduled_runs(v_vehicles, v_from, v_to, v_to) AS r
    WHERE r.kind = 1;
  END IF;
  IF v_savings THEN
    SELECT coalesce(sum(r.amount), 0) INTO v_saved
    FROM setup.scheduled_runs(v_vehicles, v_from, v_today, v_today) AS r
    WHERE r.kind = 2 AND r.state = 1;
  END IF;

  WITH items AS (
    SELECT i.id,
           (setup.recurring_current_version(i.id)).kind AS kind,
           (setup.recurring_current_version(i.id)).end_on AS end_on,
           i.stopped_from,
           EXISTS (
             SELECT 1 FROM setup.recurring_pauses AS p
             WHERE p.organization_id = i.organization_id AND p.item_id = i.id AND p.paused_through IS NULL
           ) AS paused
    FROM setup.recurring_items AS i
    WHERE i.organization_id = p_organization_id AND setup.recurring_visible(i.id)
  )
  SELECT count(*) FILTER (WHERE it.kind = 1 AND it.live AND NOT it.paused),
         count(*) FILTER (WHERE it.kind = 1 AND it.live AND it.paused),
         count(*) FILTER (WHERE it.kind = 2 AND it.live AND NOT it.paused),
         count(*) FILTER (WHERE it.kind = 2 AND it.live AND it.paused),
         CASE
           WHEN v_savings THEN coalesce(
             sum(setup.saving_balance(it.id, v_vehicles, v_today, v_today)) FILTER (WHERE it.kind = 2), 0
           )
         END
  INTO v_running_costs, v_paused_costs, v_running_savings, v_paused_savings, v_balance
  FROM (
    SELECT items.*,
           (items.stopped_from IS NULL OR items.stopped_from > v_today)
             AND (items.end_on IS NULL OR items.end_on >= v_today) AS live
    FROM items
  ) AS it;

  RETURN jsonb_build_object(
    'from_date', v_from,
    'to_date', v_to,
    'costs_due', v_costs_due,
    'saved', v_saved,
    'savings_balance', v_balance,
    'running_costs', CASE WHEN v_costs THEN v_running_costs END,
    'paused_costs', CASE WHEN v_costs THEN v_paused_costs END,
    'running_savings', CASE WHEN v_savings THEN v_running_savings END,
    'paused_savings', CASE WHEN v_savings THEN v_paused_savings END
  );
END;
$$;
