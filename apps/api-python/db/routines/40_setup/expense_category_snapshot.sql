-- setup.expense_category_snapshot(p_id uuid) RETURNS json
-- Purpose: the change-log snapshot of an expense category, compact JSON with the keys Id, Name, MainCategoryId, StoppedOn; the JSON null for an unknown category.
-- Callers: the expense category write routines.
-- Reads: setup.expense_categories. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.expense_category_snapshot(p_id uuid)
RETURNS json
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT tenancy.compact_json(coalesce(
    (
      SELECT json_build_object(
               'Id', c.id,
               'Name', c.name,
               'MainCategoryId', c.main_category_id,
               'StoppedOn', c.stopped_on
             )
      FROM setup.expense_categories AS c
      WHERE c.organization_id = tenancy.current_organization() AND c.id = p_id
    ),
    'null'::json
  ));
$$;

REVOKE ALL ON FUNCTION setup.expense_category_snapshot(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.expense_category_snapshot(uuid) TO xcode_api_executor;
