-- api.setup_expense_main_category_list(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_page integer, p_page_size integer, p_now timestamptz) RETURNS jsonb
-- Purpose: one page of the main categories by name, each with how many categories and items sit under it, and how many categories have no main category; {total, items, categories_without_main}.
-- Callers: SetupRoutines.list_expense_main_categories; ListExpenseMainCategories (GET /setup/expense-main-categories).
-- Reads: setup.expense_main_categories, setup.expense_categories, setup.expense_items. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 page_out_of_range via tenancy.check_page.
-- Tests: tests/db/test_setup_main_category_routines.py, tests/api/test_setup_expenses.py.

CREATE OR REPLACE FUNCTION api.setup_expense_main_category_list(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_page integer,
  p_page_size integer,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['catalog.view', 'expenses.view', 'scheduled.view']);
  PERFORM tenancy.check_page(p_page, p_page_size);
  RETURN jsonb_build_object(
    'total', (
      SELECT count(*) FROM setup.expense_main_categories AS m
      WHERE m.organization_id = p_organization_id
    ),
    'items', (
      SELECT coalesce(jsonb_agg(page.document ORDER BY page.name, page.id), '[]'::jsonb)
      FROM (
        SELECT m.name, m.id,
               jsonb_build_object(
                 'id', m.id,
                 'name', m.name,
                 'category_count', (
                   SELECT count(*) FROM setup.expense_categories AS c
                   WHERE c.organization_id = m.organization_id AND c.main_category_id = m.id
                 ),
                 'item_count', (
                   SELECT count(*)
                   FROM setup.expense_categories AS c
                   JOIN setup.expense_items AS i
                     ON i.organization_id = c.organization_id AND i.category_id = c.id
                   WHERE c.organization_id = m.organization_id AND c.main_category_id = m.id
                 )
               ) AS document
        FROM setup.expense_main_categories AS m
        WHERE m.organization_id = p_organization_id
        ORDER BY m.name, m.id
        OFFSET (p_page - 1) * p_page_size
        LIMIT p_page_size
      ) AS page
    ),
    'categories_without_main', (
      SELECT count(*) FROM setup.expense_categories AS c
      WHERE c.organization_id = p_organization_id AND c.main_category_id IS NULL
    )
  );
END;
$$;
