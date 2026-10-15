-- pettycash.check_expense(p_vehicle_id uuid, p_expense_item_id uuid, p_date date, p_check_vehicle boolean, p_check_item boolean) RETURNS void
-- Purpose: an expense's vehicle and item on its date, each only when asked (a change checks only what changed, so an old entry stays correctable): the vehicle visible to the actor, then in the fleet that day (joined, not left, not away); the item and its category in use that day. Each row is read `FOR SHARE`, so a retirement, an away period or a stop that commits meanwhile is waited for and then seen.
-- Callers: api.pettycash_entry_create, api.pettycash_entry_update.
-- Reads: setup.fleet_vehicles, setup.expense_items, setup.expense_categories, and what setup.vehicle_visible and setup.vehicle_active_on read. Writes: nothing.
-- Raises: XC422 pettycash_vehicle_scope, XC422 pettycash_vehicle_inactive, XC422 pettycash_item_inactive.
-- Tests: tests/db/test_pettycash_routines.py.

CREATE OR REPLACE FUNCTION pettycash.check_expense(
  p_vehicle_id uuid,
  p_expense_item_id uuid,
  p_date date,
  p_check_vehicle boolean,
  p_check_item boolean
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF p_check_vehicle THEN
    PERFORM 1
    FROM setup.fleet_vehicles AS f
    WHERE f.organization_id = tenancy.current_organization() AND f.id = p_vehicle_id
    FOR SHARE;
    IF NOT setup.vehicle_visible(p_vehicle_id) THEN
      PERFORM tenancy.refuse('pettycash_vehicle_scope', 'XC422');
    END IF;
    IF NOT setup.vehicle_active_on(p_vehicle_id, p_date) THEN
      PERFORM tenancy.refuse('pettycash_vehicle_inactive', 'XC422');
    END IF;
  END IF;
  IF p_check_item THEN
    PERFORM 1
    FROM setup.expense_items AS i
    JOIN setup.expense_categories AS c
      ON c.organization_id = i.organization_id AND c.id = i.category_id
    WHERE i.organization_id = tenancy.current_organization()
      AND i.id = p_expense_item_id
      AND (i.stopped_on IS NULL OR i.stopped_on > p_date)
      AND (c.stopped_on IS NULL OR c.stopped_on > p_date)
    FOR SHARE OF i, c;
    IF NOT FOUND THEN
      PERFORM tenancy.refuse('pettycash_item_inactive', 'XC422');
    END IF;
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION pettycash.check_expense(uuid, uuid, date, boolean, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.check_expense(uuid, uuid, date, boolean, boolean) TO xcode_api_executor;
