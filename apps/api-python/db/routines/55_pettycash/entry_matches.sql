-- pettycash.entry_matches(p_holder_id uuid, p_from date, p_to date, p_kinds smallint[], p_statuses text[], p_q text, p_view_all boolean, p_vehicles uuid[]) RETURNS SETOF pettycash.entries
-- Purpose: the entries the Petty cash page lists for the current actor (pettycash.entry_visible with p_view_all and the actor's visible vehicles), of one float when p_holder_id is given, dated p_from..p_to (either end open), of the kind codes and status words asked (empty or null = all), whose note, payee, holder name, registration or item name holds p_q literally, ignoring case (the LIKE wildcards escaped); unordered, so the list and the export order or page them themselves.
-- Callers: api.pettycash_entry_list, api.pettycash_export_get.
-- Reads: pettycash.entries, tenancy.memberships, setup.fleet_vehicles, setup.expense_items, and what pettycash.entry_visible and pettycash.status_word read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_pettycash_routines.py, tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION pettycash.entry_matches(
  p_holder_id uuid,
  p_from date,
  p_to date,
  p_kinds smallint[],
  p_statuses text[],
  p_q text,
  p_view_all boolean,
  p_vehicles uuid[]
)
RETURNS SETOF pettycash.entries
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_text text := tenancy.trim_text(p_q);
  v_pattern text;
BEGIN
  v_pattern := '%' || replace(replace(replace(v_text, '\', '\\'), '%', '\%'), '_', '\_') || '%';
  RETURN QUERY
  SELECT e.*
  FROM pettycash.entries AS e
  JOIN tenancy.memberships AS h ON h.organization_id = e.organization_id AND h.user_id = e.holder_id
  LEFT JOIN setup.fleet_vehicles AS f ON f.organization_id = e.organization_id AND f.id = e.vehicle_id
  LEFT JOIN setup.expense_items AS i ON i.organization_id = e.organization_id AND i.id = e.expense_item_id
  WHERE e.organization_id = tenancy.current_organization()
    AND pettycash.entry_visible(e, p_view_all, p_vehicles)
    AND (p_holder_id IS NULL OR e.holder_id = p_holder_id)
    AND (p_from IS NULL OR e.entry_date >= p_from)
    AND (p_to IS NULL OR e.entry_date <= p_to)
    AND (coalesce(cardinality(p_kinds), 0) = 0 OR e.kind = ANY (p_kinds))
    AND (coalesce(cardinality(p_statuses), 0) = 0
         OR pettycash.status_word(e.status, e.sent_back_note) = ANY (p_statuses))
    AND (v_text IS NULL
         OR e.note ILIKE v_pattern
         OR e.payee ILIKE v_pattern
         OR btrim(h.first_name || ' ' || h.last_name) ILIKE v_pattern
         OR f.registration ILIKE v_pattern
         OR i.name ILIKE v_pattern);
END;
$$;

REVOKE ALL ON FUNCTION pettycash.entry_matches(uuid, date, date, smallint[], text[], text, boolean, uuid[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.entry_matches(uuid, date, date, smallint[], text[], text, boolean, uuid[])
  TO xcode_api_executor;
