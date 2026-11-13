-- setup.refuse_in_use(p_record text, p_name text, p_table text) RETURNS void
-- Purpose: refuse a setup delete that a foreign key blocked: XC409 in_use with the DETAIL {name, use}, where use is the record kind and what refers to it, read from p_table (the referencing table as schema.table, from the foreign key violation); a table this list does not know answers <kind>_other, so a reference added later still refuses with a sentence.
-- Callers: api.setup_expense_main_category_delete, api.setup_expense_category_delete, api.setup_expense_item_delete, api.setup_vehicle_delete, api.setup_company_delete.
-- Reads: nothing. Writes: nothing.
-- Raises: XC409 in_use.
-- Tests: tests/db/test_setup_delete_routines.py.

CREATE OR REPLACE FUNCTION setup.refuse_in_use(p_record text, p_name text, p_table text)
RETURNS void
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_use text;
BEGIN
  v_use := CASE p_record || ':' || p_table
    WHEN 'main_category:setup.expense_categories' THEN 'categories'
    WHEN 'category:setup.expense_items' THEN 'items'
    WHEN 'item:expenses.entries' THEN 'expenses'
    WHEN 'item:pettycash.entries' THEN 'pettycash'
    WHEN 'item:setup.recurring_versions' THEN 'schedules'
    WHEN 'vehicle:revenue.records' THEN 'revenue'
    WHEN 'vehicle:pettycash.entries' THEN 'pettycash'
    WHEN 'vehicle:expenses.entries' THEN 'expenses'
    WHEN 'vehicle:setup.vehicle_investments' THEN 'investments'
    WHEN 'vehicle:setup.vehicle_away_periods' THEN 'away'
    WHEN 'vehicle:setup.recurring_allocations' THEN 'schedules'
    WHEN 'vehicle:setup.saving_runs' THEN 'savings'
    WHEN 'vehicle:setup.saving_opening_amounts' THEN 'savings'
    WHEN 'vehicle:tenancy.data_scope_vehicles' THEN 'scope'
    WHEN 'company:setup.fleet_vehicles' THEN 'vehicles'
    WHEN 'company:tenancy.data_scope_companies' THEN 'scope'
    ELSE 'other'
  END;
  PERFORM tenancy.refuse(
    'in_use', 'XC409', jsonb_build_object('name', p_name, 'use', p_record || '_' || v_use)
  );
END;
$$;

REVOKE ALL ON FUNCTION setup.refuse_in_use(text, text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.refuse_in_use(text, text, text) TO xcode_api_executor;
