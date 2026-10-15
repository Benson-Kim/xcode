-- api.setup_recurring_runs(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_item_id uuid, p_now timestamptz) RETURNS jsonb
-- Purpose: a visible scheduled item's runs on the actor's vehicles, from the earliest start of its versions to the business date: {id, name (latest version), kind, start, total, run_count, runs}, runs being the last ten run dates, newest first, each {date, amount, shares [{vehicle_id, registration, amount, state, revenue}] by registration}. Amounts and the total count posted and saved shares only; state is posted, saved, skipped or held; revenue is the decided figure, the window so far for a held share, null without a revenue rule.
-- Callers: SetupRoutines.recurring_runs; GetSetupRecurringRuns (GET /setup/recurring/{id}/runs).
-- Reads: setup.recurring_items, setup.recurring_versions, setup.fleet_vehicles, setup.saving_runs, and what tenancy.business_date, setup.recurring_visible, setup.recurring_current_version, setup.visible_vehicles, setup.scheduled_runs and setup.saving_window_revenue read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 time_zone_invalid via tenancy.business_date, XC404 not_found.
-- Tests: tests/db/test_recurring_pause_routines.py, tests/api/test_recurring_pause.py.

CREATE OR REPLACE FUNCTION api.setup_recurring_runs(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_item_id uuid,
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
  v_current setup.recurring_versions;
  v_start date;
  v_result jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['scheduled.view', 'savings.view']);
  v_today := tenancy.business_date(p_organization_id, p_now);
  IF NOT EXISTS (
       SELECT 1 FROM setup.recurring_items AS i
       WHERE i.organization_id = p_organization_id AND i.id = p_item_id
     )
     OR NOT setup.recurring_visible(p_item_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  v_current := setup.recurring_current_version(p_item_id);
  SELECT min(v.start_on) INTO v_start
  FROM setup.recurring_versions AS v
  WHERE v.organization_id = p_organization_id AND v.item_id = p_item_id;

  WITH runs AS (
    SELECT r.run_on,
           r.vehicle_id,
           f.registration,
           r.amount,
           r.state,
           CASE
             WHEN s.state IS NOT NULL THEN s.revenue
             WHEN r.state = 3 THEN (
               SELECT w.revenue FROM setup.saving_window_revenue(r.vehicle_id, r.run_on, v.condition_days) AS w
             )
           END AS revenue
    FROM setup.scheduled_runs(
           ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id)), v_start, v_today, v_today,
           NULL, ARRAY[p_item_id]
         ) AS r
    JOIN setup.recurring_versions AS v ON v.organization_id = p_organization_id AND v.id = r.version_id
    JOIN setup.fleet_vehicles AS f ON f.organization_id = p_organization_id AND f.id = r.vehicle_id
    LEFT JOIN setup.saving_runs AS s
      ON s.organization_id = p_organization_id
     AND s.item_id = r.item_id
     AND s.run_on = r.run_on
     AND s.vehicle_id = r.vehicle_id
    WHERE r.item_id = p_item_id
  ),
  dates AS (
    SELECT runs.run_on, coalesce(sum(runs.amount) FILTER (WHERE runs.state IN (0, 1)), 0) AS amount
    FROM runs
    GROUP BY runs.run_on
  )
  SELECT jsonb_build_object(
           'id', p_item_id,
           'name', v_current.name,
           'kind', v_current.kind,
           'start', v_start,
           'total', coalesce((SELECT sum(d.amount) FROM dates AS d), 0),
           'run_count', (SELECT count(*) FROM dates),
           'runs', coalesce(
             (
               SELECT jsonb_agg(
                        jsonb_build_object(
                          'date', d.run_on,
                          'amount', d.amount,
                          'shares', (
                            SELECT jsonb_agg(
                                     jsonb_build_object(
                                       'vehicle_id', r.vehicle_id,
                                       'registration', r.registration,
                                       'amount', r.amount,
                                       'state', CASE r.state
                                                  WHEN 0 THEN 'posted'
                                                  WHEN 1 THEN 'saved'
                                                  WHEN 2 THEN 'skipped'
                                                  ELSE 'held'
                                                END,
                                       'revenue', r.revenue
                                     ) ORDER BY r.registration COLLATE "C", r.vehicle_id)
                            FROM runs AS r
                            WHERE r.run_on = d.run_on
                          )
                        ) ORDER BY d.run_on DESC)
               FROM (SELECT * FROM dates ORDER BY dates.run_on DESC LIMIT 10) AS d
             ),
             '[]'::jsonb
           )
         )
  INTO v_result;
  RETURN v_result;
END;
$$;
