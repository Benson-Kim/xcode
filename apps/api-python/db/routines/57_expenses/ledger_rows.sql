-- expenses.ledger_rows(p_vehicle_ids uuid[], p_from date, p_to date, p_today date, p_source text, p_q text, p_actor_id uuid, p_can_capture boolean, p_can_correct boolean, p_earliest date) RETURNS TABLE (id text, source text, entry_date date, vehicle_id uuid, registration text, expense_item_id uuid, item_name text, category_name text, bucket smallint, units numeric, unit_amount numeric, total numeric, note text, recorded_by_name text, holder_name text, schedule_id uuid, "group" jsonb, version bigint, can_edit boolean, can_remove boolean, main_category_name text, fleet_number text, source_order smallint, matched boolean)
-- Purpose: every row of the central-expenses ledger on the vehicles over p_from..p_to cut to the business date, each inside its vehicle's own days (setup.fleet_postings): central expenses not removed, approved petty-cash expenses not removed, and the scheduled cost runs (never savings); the row columns are the ledger row's keys (id is a scheduled run's "{item}:{yyyy-MM-dd}:{vehicle}"), source_order 1 central, 2 petty cash, 3 scheduled, and matched says whether the row matches p_source (a source word, NULL for all) and p_q (trimmed, NULL for none; a literal case-insensitive substring of the registration, the item or schedule name, the category, the note, and the recorder's name on a central row or the holder's on a petty-cash row). A central row can be changed and removed by a person with p_can_correct, or by p_actor_id with p_can_capture alone on their own row of the business date, never before p_earliest. Unordered; the ledger, its 409 current row and its export read it.
-- Callers: api.expenses_ledger_get, expenses.row_document, api.expenses_export_get.
-- Reads: setup.fleet_vehicles, tenancy.memberships, and what setup.fleet_postings reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_expense_routines.py.

CREATE OR REPLACE FUNCTION expenses.ledger_rows(
  p_vehicle_ids uuid[],
  p_from date,
  p_to date,
  p_today date,
  p_source text,
  p_q text,
  p_actor_id uuid,
  p_can_capture boolean,
  p_can_correct boolean,
  p_earliest date
)
RETURNS TABLE (
  id text,
  source text,
  entry_date date,
  vehicle_id uuid,
  registration text,
  expense_item_id uuid,
  item_name text,
  category_name text,
  bucket smallint,
  units numeric,
  unit_amount numeric,
  total numeric,
  note text,
  recorded_by_name text,
  holder_name text,
  schedule_id uuid,
  "group" jsonb,
  version bigint,
  can_edit boolean,
  can_remove boolean,
  main_category_name text,
  fleet_number text,
  source_order smallint,
  matched boolean
)
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
#variable_conflict use_column
DECLARE
  v_organization_id uuid := tenancy.current_organization();
  v_text text := tenancy.trim_text(p_q);
  v_pattern text;
  v_source smallint := CASE p_source WHEN 'central' THEN 1 WHEN 'pettycash' THEN 2 WHEN 'scheduled' THEN 3 END;
BEGIN
  v_pattern := '%' || replace(replace(replace(v_text, '\', '\\'), '%', '\%'), '_', '\_') || '%';
  RETURN QUERY
  WITH postings AS (
    SELECT p.*,
           f.registration AS reg,
           f.fleet_number AS fleet,
           CASE WHEN p.source <> 3 THEN coalesce(btrim(r.first_name || ' ' || r.last_name), '') END AS recorder,
           CASE WHEN p.source = 2 THEN coalesce(btrim(h.first_name || ' ' || h.last_name), '') END AS holder
    FROM setup.fleet_postings(p_vehicle_ids, p_from, p_to, p_today, '{1}') AS p
    JOIN setup.fleet_vehicles AS f ON f.organization_id = v_organization_id AND f.id = p.vehicle_id
    LEFT JOIN tenancy.memberships AS r ON r.organization_id = v_organization_id AND r.user_id = p.recorded_by
    LEFT JOIN tenancy.memberships AS h ON h.organization_id = v_organization_id AND h.user_id = p.holder_id
    WHERE p.kind = 1
  )
  SELECT CASE
           WHEN p.source = 3 THEN p.id::text || ':' || to_char(p.day, 'YYYY-MM-DD') || ':' || p.vehicle_id::text
           ELSE p.id::text
         END,
         CASE p.source WHEN 1 THEN 'central' WHEN 2 THEN 'pettycash' ELSE 'scheduled' END,
         p.day,
         p.vehicle_id,
         p.reg,
         p.expense_item_id,
         p.name,
         p.category_name,
         p.bucket,
         p.units,
         p.unit_amount,
         p.amount,
         p.note,
         p.recorder,
         p.holder,
         CASE WHEN p.source = 3 THEN p.id END,
         CASE
           WHEN p.group_size > 1 THEN jsonb_build_object(
             'id', p.group_id,
             'size', p.group_size,
             'total', p.group_total,
             'units', p.group_units,
             'unit_amount', p.group_unit_amount
           )
         END,
         CASE WHEN p.source = 1 THEN p.version END,
         p.source = 1 AND p.editable,
         p.source = 1 AND p.editable,
         p.main_category_name,
         p.fleet,
         p.source,
         (v_source IS NULL OR p.source = v_source)
           AND (
             v_text IS NULL
             OR p.reg ILIKE v_pattern
             OR p.name ILIKE v_pattern
             OR p.category_name ILIKE v_pattern
             OR p.note ILIKE v_pattern
             OR (p.source = 1 AND p.recorder ILIKE v_pattern)
             OR (p.source = 2 AND p.holder ILIKE v_pattern)
           )
  FROM (
    SELECT q.*,
           q.source = 1
             AND (p_can_correct OR (p_can_capture AND q.recorded_by = p_actor_id AND q.day = p_today))
             AND (p_earliest IS NULL OR q.day >= p_earliest) AS editable
    FROM postings AS q
  ) AS p;
END;
$$;

REVOKE ALL ON FUNCTION expenses.ledger_rows(uuid[], date, date, date, text, text, uuid, boolean, boolean, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION expenses.ledger_rows(uuid[], date, date, date, text, text, uuid, boolean, boolean, date) TO xcode_api_executor;
