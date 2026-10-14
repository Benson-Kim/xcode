-- expenses.describe(p_id uuid) RETURNS text
-- Purpose: the subject of a central expense's change-log reasons: "central expense on {registration} for {d MMM yyyy}: {item}, {currency} {total}", the total as #,##0 when whole, else #,##0.00.
-- Callers: expenses.log.
-- Reads: expenses.entries, setup.fleet_vehicles, setup.expense_items, and what tenancy.settings_document, tenancy.fmt_day and tenancy.fmt_money read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_expense_routines.py.

CREATE OR REPLACE FUNCTION expenses.describe(p_id uuid)
RETURNS text
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT 'central expense on ' || f.registration || ' for ' || tenancy.fmt_day(e.entry_date) || ': '
         || i.name || ', ' || (tenancy.settings_document('localization') ->> 'currency') || ' '
         || tenancy.fmt_money(e.total)
  FROM expenses.entries AS e
  JOIN setup.fleet_vehicles AS f ON f.organization_id = e.organization_id AND f.id = e.vehicle_id
  JOIN setup.expense_items AS i ON i.organization_id = e.organization_id AND i.id = e.expense_item_id
  WHERE e.organization_id = tenancy.current_organization() AND e.id = p_id;
$$;

REVOKE ALL ON FUNCTION expenses.describe(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION expenses.describe(uuid) TO xcode_api_executor;
