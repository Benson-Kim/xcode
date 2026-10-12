-- pettycash.entry_visible(p_entry pettycash.entries, p_view_all boolean, p_vehicles uuid[]) RETURNS boolean
-- Purpose: whether the current actor may see the entry: not removed, and on their own float, or with pettycash.view_all on an entry with no vehicle or a vehicle among p_vehicles (the actor's visible vehicles).
-- Callers: pettycash.tallies, pettycash.visible_entry, and the petty-cash lists.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_pettycash_helpers.py.

CREATE OR REPLACE FUNCTION pettycash.entry_visible(
  p_entry pettycash.entries,
  p_view_all boolean,
  p_vehicles uuid[]
)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT p_entry.removed_at IS NULL
     AND (
       p_entry.holder_id = tenancy.current_actor()
       OR (p_view_all AND (p_entry.vehicle_id IS NULL OR p_entry.vehicle_id = ANY (p_vehicles)))
     );
$$;

REVOKE ALL ON FUNCTION pettycash.entry_visible(pettycash.entries, boolean, uuid[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.entry_visible(pettycash.entries, boolean, uuid[]) TO xcode_api_executor;
