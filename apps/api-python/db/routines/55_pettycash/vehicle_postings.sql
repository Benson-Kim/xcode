-- pettycash.vehicle_postings(p_vehicle_id uuid, p_window daterange) RETURNS TABLE (item_id uuid, version_id uuid, day date, name text, kind smallint, amount numeric, bucket smallint)
-- Purpose: the petty-cash postings of the vehicle in the window (the report window: the vehicle's own days, none after the business date): one cost per approved, non-removed expense on the vehicle dated in it, with the entry id as item and version, the item's name, the total and the bucket of the item's category (charges when the category has none, as a scheduled cost). Unordered.
-- Callers: setup.vehicle_net, api.setup_vehicle_report.
-- Reads: pettycash.entries, setup.expense_items, setup.expense_categories. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_pettycash_routines.py.

CREATE OR REPLACE FUNCTION pettycash.vehicle_postings(p_vehicle_id uuid, p_window daterange)
RETURNS TABLE (
  item_id uuid,
  version_id uuid,
  day date,
  name text,
  kind smallint,
  amount numeric,
  bucket smallint
)
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT e.id, e.id, e.entry_date, i.name, 1::smallint, e.total, coalesce(c.bucket, 2::smallint)
  FROM pettycash.entries AS e
  JOIN setup.expense_items AS i ON i.organization_id = e.organization_id AND i.id = e.expense_item_id
  JOIN setup.expense_categories AS c ON c.organization_id = i.organization_id AND c.id = i.category_id
  WHERE e.organization_id = tenancy.current_organization()
    AND e.vehicle_id = p_vehicle_id
    AND e.kind = 2
    AND e.status = 2
    AND e.removed_at IS NULL
    AND p_window @> e.entry_date;
$$;

REVOKE ALL ON FUNCTION pettycash.vehicle_postings(uuid, daterange) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.vehicle_postings(uuid, daterange) TO xcode_api_executor;
