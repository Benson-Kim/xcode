-- ops.seed_catalogue(p_organization_id uuid, p_owner_id uuid, p_request_id text, p_at timestamptz) RETURNS void
-- Purpose: add the demo expense catalogue as the Owner: three main categories (found by name when one exists), a category under each and 13 items in all, through the setup routines.
-- Callers: api.ops_seed_demo.
-- Reads: setup.expense_main_categories. Writes: what api.setup_expense_main_category_create, api.setup_expense_category_create and api.setup_expense_item_create write.
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py.
-- The caller adds it only to an organization with no expense category.

CREATE OR REPLACE FUNCTION ops.seed_catalogue(
  p_organization_id uuid,
  p_owner_id uuid,
  p_request_id text,
  p_at timestamptz
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_group record;
  v_main_id uuid;
  v_category_id uuid;
  v_item text;
BEGIN
  FOR v_group IN
    SELECT g.main_name, g.category_name, g.items
    FROM (
      VALUES
        (
          1, 'Repairs and maintenance', 'Garage and repairs',
          ARRAY['Garage labour', 'Spares', 'Tyres', 'Service and maintenance', 'Body work', 'Towing']
        ),
        (
          2, 'Recurring charges', 'Charges',
          ARRAY['Parking', 'City council', 'SACCO fee', 'Insurance', 'Licence', 'Inspection']
        ),
        (3, 'Loan repayments', 'Loans', ARRAY['Loan repayment'])
    ) AS g (ord, main_name, category_name, items)
    ORDER BY g.ord
  LOOP
    SELECT m.id INTO v_main_id
    FROM setup.expense_main_categories AS m
    WHERE m.organization_id = p_organization_id
      AND m.normalized_name = upper(v_group.main_name COLLATE "C");
    IF v_main_id IS NULL THEN
      v_main_id := (
        api.setup_expense_main_category_create(
          p_owner_id, p_organization_id, p_request_id, v_group.main_name, p_at
        )
      ).id;
    END IF;
    v_category_id := (
      api.setup_expense_category_create(
        p_owner_id, p_organization_id, p_request_id, v_group.category_name, v_main_id, p_at
      )
    ).id;
    FOREACH v_item IN ARRAY v_group.items LOOP
      PERFORM api.setup_expense_item_create(
        p_owner_id, p_organization_id, p_request_id, v_category_id, v_item, p_at
      );
    END LOOP;
  END LOOP;
END;
$$;

REVOKE ALL ON FUNCTION ops.seed_catalogue(uuid, uuid, text, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ops.seed_catalogue(uuid, uuid, text, timestamptz) TO xcode_api_executor;
