-- api.setup_expense_category_list(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_page integer, p_page_size integer, p_now timestamptz) RETURNS jsonb
-- Purpose: one page of the organization's expense categories by name then id, each with its bucket (as stored, null for categories made since main categories), whether it is in use on the business date, its stop date, its items by name then id, and its main category (null for none); {total, items}.
-- Callers: SetupRoutines.list_expense_categories; ListExpenseCategories (GET /setup/expense-categories).
-- Reads: setup.expense_categories, setup.expense_items, setup.expense_main_categories, and what tenancy.business_date reads. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 page_out_of_range via tenancy.check_page, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_setup_expense_routines.py, tests/api/test_setup_expenses.py.

CREATE OR REPLACE FUNCTION api.setup_expense_category_list(
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
DECLARE
  v_today date;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['catalog.view', 'expenses.view', 'scheduled.view']);
  PERFORM tenancy.check_page(p_page, p_page_size);
  v_today := tenancy.business_date(p_organization_id, p_now);
  RETURN jsonb_build_object(
    'total', (
      SELECT count(*) FROM setup.expense_categories AS c WHERE c.organization_id = p_organization_id
    ),
    'items', (
      SELECT coalesce(jsonb_agg(page.document ORDER BY page.name, page.id), '[]'::jsonb)
      FROM (
        SELECT c.name, c.id,
               jsonb_build_object(
                 'id', c.id,
                 'name', c.name,
                 'bucket', c.bucket,
                 'active', c.stopped_on IS NULL OR c.stopped_on > v_today,
                 'stopped_on', c.stopped_on,
                 'items', (
                   SELECT coalesce(
                            jsonb_agg(
                              jsonb_build_object(
                                'id', i.id,
                                'category_id', i.category_id,
                                'name', i.name,
                                'active', i.stopped_on IS NULL OR i.stopped_on > v_today,
                                'stopped_on', i.stopped_on
                              ) ORDER BY i.name, i.id),
                            '[]'::jsonb)
                   FROM setup.expense_items AS i
                   WHERE i.organization_id = c.organization_id AND i.category_id = c.id
                 ),
                 'main_category_id', c.main_category_id,
                 'main_category_name', (
                   SELECT m.name FROM setup.expense_main_categories AS m
                   WHERE m.organization_id = c.organization_id AND m.id = c.main_category_id
                 )
               ) AS document
        FROM setup.expense_categories AS c
        WHERE c.organization_id = p_organization_id
        ORDER BY c.name, c.id
        OFFSET (p_page - 1) * p_page_size
        LIMIT p_page_size
      ) AS page
    )
  );
END;
$$;
