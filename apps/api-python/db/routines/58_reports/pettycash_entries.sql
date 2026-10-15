-- reports.pettycash_entries(p_holder_ids uuid[], p_view_all boolean, p_vehicles uuid[]) RETURNS TABLE (id uuid, holder_id uuid, kind smallint, entry_date date, vehicle_id uuid, expense_item_id uuid, units numeric, unit_amount numeric, total numeric, payee text, note text, status smallint, sent_back_note text, reject_reason text, reopen_reason text, recorded_by uuid, reviewed_by uuid, holder_name text, registration text, company_name text, item_name text, category_name text, recorded_by_name text, reviewed_by_name text)
-- Purpose: the petty-cash entries the Petty cash page shows the current actor on the given floats (pettycash.entry_visible: not removed, their own float, or every float with pettycash.view_all on a vehicle they see), with the names the reports show: the holder, the registration, the company (only for a vehicle in the actor's scope), the item and its category, the recorder and the reviewer. Unordered.
-- Callers: reports.pettycash_cash_book, reports.pettycash_managers, reports.pettycash_vehicles, reports.pettycash_items, reports.pettycash_waiting, reports.pettycash_sent_back, reports.pettycash_rejected.
-- Reads: pettycash.entries, setup.fleet_vehicles, setup.psv_companies, setup.expense_items, setup.expense_categories, tenancy.memberships. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_report_routines.py.
-- The set form of pettycash.entry_visible and pettycash.member_name, which answer one entry and
-- one member each: called per row, they cost over a hundred thousand lookups on a year of ten
-- times the demo fleet.

CREATE OR REPLACE FUNCTION reports.pettycash_entries(
  p_holder_ids uuid[],
  p_view_all boolean,
  p_vehicles uuid[]
)
RETURNS TABLE (
  id uuid,
  holder_id uuid,
  kind smallint,
  entry_date date,
  vehicle_id uuid,
  expense_item_id uuid,
  units numeric,
  unit_amount numeric,
  total numeric,
  payee text,
  note text,
  status smallint,
  sent_back_note text,
  reject_reason text,
  reopen_reason text,
  recorded_by uuid,
  reviewed_by uuid,
  holder_name text,
  registration text,
  company_name text,
  item_name text,
  category_name text,
  recorded_by_name text,
  reviewed_by_name text
)
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  WITH seen AS MATERIALIZED (
    SELECT DISTINCT v.id FROM unnest(p_vehicles) AS v (id) WHERE v.id IS NOT NULL
  )
  SELECT e.id,
         e.holder_id,
         e.kind,
         e.entry_date,
         e.vehicle_id,
         e.expense_item_id,
         e.units::numeric,
         e.unit_amount::numeric,
         e.total::numeric,
         e.payee,
         e.note,
         e.status,
         e.sent_back_note,
         e.reject_reason,
         e.reopen_reason,
         e.recorded_by,
         e.reviewed_by,
         coalesce(btrim(h.first_name || ' ' || h.last_name), ''),
         f.registration,
         CASE WHEN s.id IS NOT NULL THEN c.name END,
         i.name,
         cat.name,
         coalesce(btrim(rb.first_name || ' ' || rb.last_name), ''),
         btrim(rv.first_name || ' ' || rv.last_name)
  FROM pettycash.entries AS e
  LEFT JOIN seen AS s ON s.id = e.vehicle_id
  LEFT JOIN setup.fleet_vehicles AS f ON f.organization_id = e.organization_id AND f.id = e.vehicle_id
  LEFT JOIN setup.psv_companies AS c ON c.organization_id = f.organization_id AND c.id = f.company_id
  LEFT JOIN setup.expense_items AS i ON i.organization_id = e.organization_id AND i.id = e.expense_item_id
  LEFT JOIN setup.expense_categories AS cat
    ON cat.organization_id = i.organization_id AND cat.id = i.category_id
  LEFT JOIN tenancy.memberships AS h ON h.organization_id = e.organization_id AND h.user_id = e.holder_id
  LEFT JOIN tenancy.memberships AS rb ON rb.organization_id = e.organization_id AND rb.user_id = e.recorded_by
  LEFT JOIN tenancy.memberships AS rv ON rv.organization_id = e.organization_id AND rv.user_id = e.reviewed_by
  WHERE e.organization_id = tenancy.current_organization()
    AND e.holder_id = ANY (p_holder_ids)
    AND e.removed_at IS NULL
    AND (
      e.holder_id = tenancy.current_actor()
      OR (p_view_all AND (e.vehicle_id IS NULL OR s.id IS NOT NULL))
    );
$$;

REVOKE ALL ON FUNCTION reports.pettycash_entries(uuid[], boolean, uuid[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.pettycash_entries(uuid[], boolean, uuid[]) TO xcode_api_executor;
