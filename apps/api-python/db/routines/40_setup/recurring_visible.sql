-- setup.recurring_visible(p_item_id uuid) RETURNS boolean
-- Purpose: whether the current actor can see the scheduled item: they hold the view right of its current kind (scheduled.view for a cost, savings.view for a saving), and have an all-companies scope or any of its versions shares the cost with a vehicle they can see.
-- Callers: setup.save_recurring, api.setup_recurring_stop, api.setup_recurring_cancel_stop.
-- Reads: setup.recurring_versions, setup.recurring_allocations, and what tenancy.has_permission, setup.recurring_current_version, tenancy.actor_scope and setup.visible_vehicles read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_recurring_routines.py.

CREATE OR REPLACE FUNCTION setup.recurring_visible(p_item_id uuid)
RETURNS boolean
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF NOT tenancy.has_permission(
    setup.recurring_kind_right((setup.recurring_current_version(p_item_id)).kind, 'view')
  ) THEN
    RETURN false;
  END IF;
  IF (tenancy.actor_scope()).all_companies THEN
    RETURN true;
  END IF;
  RETURN EXISTS (
    SELECT 1
    FROM setup.recurring_versions AS v
    JOIN setup.recurring_allocations AS a
      ON a.organization_id = v.organization_id AND a.version_id = v.id
    WHERE v.organization_id = tenancy.current_organization()
      AND v.item_id = p_item_id
      AND a.vehicle_id IN (SELECT visible.id FROM setup.visible_vehicles() AS visible (id))
  );
END;
$$;

REVOKE ALL ON FUNCTION setup.recurring_visible(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.recurring_visible(uuid) TO xcode_api_executor;
