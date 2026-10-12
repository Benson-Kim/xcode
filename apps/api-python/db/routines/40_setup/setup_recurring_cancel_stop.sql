-- api.setup_recurring_cancel_stop(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_item_id uuid, p_now timestamptz) RETURNS api.write_result
-- Purpose: cancel a stop dated after the business date on a scheduled item whose every current share the actor can reach; a stop already in effect is final, and an item that is not stopped answers unchanged.
-- Callers: SetupRoutines.cancel_recurring_stop; CancelRecurringStop (POST /setup/recurring/{id}/restore).
-- Reads: setup.recurring_items, setup.recurring_allocations, and what tenancy.business_date, setup.recurring_visible, setup.recurring_current_version, setup.visible_vehicles and setup.recurring_snapshot read. Writes: setup.recurring_items, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 time_zone_invalid via tenancy.business_date, XC404 not_found (also for an item of a kind the actor cannot view), XC403 permission_missing via tenancy.require_permission (the edit right of the item's kind), XC403 permission_missing, XC422 recurring_stop_in_effect.
-- Tests: tests/db/test_setup_recurring_routines.py, tests/api/test_setup_recurring.py.

CREATE OR REPLACE FUNCTION api.setup_recurring_cancel_stop(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_item_id uuid,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_today date;
  v_item setup.recurring_items;
  v_current setup.recurring_versions;
  v_before json;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['scheduled.edit', 'savings.edit']);
  v_today := tenancy.business_date(p_organization_id, p_now);
  SELECT i.* INTO v_item
  FROM setup.recurring_items AS i
  WHERE i.organization_id = p_organization_id AND i.id = p_item_id
  FOR UPDATE;
  IF NOT FOUND OR NOT setup.recurring_visible(p_item_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  v_current := setup.recurring_current_version(p_item_id);
  PERFORM tenancy.require_permission(setup.recurring_kind_right(v_current.kind, 'edit'));
  IF EXISTS (
    SELECT 1 FROM setup.recurring_allocations AS a
    WHERE a.organization_id = p_organization_id
      AND a.version_id = v_current.id
      AND a.vehicle_id NOT IN (SELECT visible.id FROM setup.visible_vehicles() AS visible (id))
  ) THEN
    PERFORM tenancy.refuse('permission_missing', 'XC403');
  END IF;
  IF v_item.stopped_from IS NULL THEN
    RETURN setup.unchanged_result(p_item_id);
  END IF;
  IF v_item.stopped_from <= v_today THEN
    PERFORM tenancy.refuse('recurring_stop_in_effect', 'XC422');
  END IF;

  v_before := setup.recurring_snapshot(p_item_id);
  UPDATE setup.recurring_items
  SET stopped_from = NULL, updated_at = p_now
  WHERE organization_id = p_organization_id AND id = p_item_id;
  v_version := setup.record_setup_change(
    'recurring', p_item_id, NULL, v_before, setup.recurring_snapshot(p_item_id),
    setup.recurring_change_reason(v_current.kind, v_current.name), p_now
  );
  RETURN ROW(p_item_id, v_version, 'updated')::api.write_result;
END;
$$;
