-- setup.saving_balance(p_item_id uuid, p_vehicle_ids uuid[], p_as_of date, p_today date) RETURNS numeric
-- Purpose: a saving's balance on the vehicles as at a date: the opening amounts of those vehicles once the opening date is reached, plus the runs saved after the opening date (every saved run when there is no opening) up to the earlier of p_as_of and p_today. Zero when nothing counts.
-- Callers: api.setup_recurring_list, api.setup_recurring_summary, reports.fleet_savings.
-- Reads: setup.saving_openings, setup.saving_opening_amounts, setup.recurring_versions, and what setup.scheduled_runs reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py, tests/db/test_recurring_pause_routines.py.

CREATE OR REPLACE FUNCTION setup.saving_balance(
  p_item_id uuid,
  p_vehicle_ids uuid[],
  p_as_of date,
  p_today date
)
RETURNS numeric
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.current_organization();
  v_opened_on date;
  v_first date;
  v_opening numeric := 0;
  v_saved numeric := 0;
BEGIN
  SELECT o.opened_on INTO v_opened_on
  FROM setup.saving_openings AS o
  WHERE o.organization_id = v_organization_id AND o.item_id = p_item_id;
  IF v_opened_on IS NOT NULL AND v_opened_on <= p_as_of THEN
    SELECT coalesce(sum(a.amount), 0) INTO v_opening
    FROM setup.saving_opening_amounts AS a
    WHERE a.organization_id = v_organization_id
      AND a.item_id = p_item_id
      AND a.vehicle_id = ANY (p_vehicle_ids);
  END IF;
  SELECT min(v.start_on) INTO v_first
  FROM setup.recurring_versions AS v
  WHERE v.organization_id = v_organization_id AND v.item_id = p_item_id;
  IF v_opened_on IS NOT NULL THEN
    v_first := greatest(v_first, v_opened_on + 1);
  END IF;
  SELECT coalesce(sum(r.amount), 0) INTO v_saved
  FROM setup.scheduled_runs(
    p_vehicle_ids, v_first, least(p_as_of, p_today), p_today, '{2}', ARRAY[p_item_id]
  ) AS r
  WHERE r.item_id = p_item_id AND r.state = 1;
  RETURN v_opening + v_saved;
END;
$$;

REVOKE ALL ON FUNCTION setup.saving_balance(uuid, uuid[], date, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.saving_balance(uuid, uuid[], date, date) TO xcode_api_executor;
