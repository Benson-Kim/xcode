-- setup.expense_item_snapshot(p_id uuid) RETURNS json
-- Purpose: the change-log snapshot of an expense item, compact JSON with the .NET keys Id, CategoryId, Name, StoppedOn; the JSON null for an unknown item.
-- Callers: the expense item write routines.
-- Reads: setup.expense_items. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.expense_item_snapshot(p_id uuid)
RETURNS json
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT tenancy.compact_json(coalesce(
    (
      SELECT json_build_object(
               'Id', i.id,
               'CategoryId', i.category_id,
               'Name', i.name,
               'StoppedOn', i.stopped_on
             )
      FROM setup.expense_items AS i
      WHERE i.organization_id = tenancy.current_organization() AND i.id = p_id
    ),
    'null'::json
  ));
$$;

REVOKE ALL ON FUNCTION setup.expense_item_snapshot(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.expense_item_snapshot(uuid) TO xcode_api_executor;
