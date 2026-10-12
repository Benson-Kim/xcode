-- setup.expense_main_category_snapshot(p_id uuid) RETURNS json
-- Purpose: the change-log snapshot of a main category, compact JSON with the keys Id, Name; the JSON null for an unknown main category.
-- Callers: the main category write routines.
-- Reads: setup.expense_main_categories. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.expense_main_category_snapshot(p_id uuid)
RETURNS json
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT tenancy.compact_json(coalesce(
    (
      SELECT json_build_object('Id', m.id, 'Name', m.name)
      FROM setup.expense_main_categories AS m
      WHERE m.organization_id = tenancy.current_organization() AND m.id = p_id
    ),
    'null'::json
  ));
$$;

REVOKE ALL ON FUNCTION setup.expense_main_category_snapshot(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.expense_main_category_snapshot(uuid) TO xcode_api_executor;
