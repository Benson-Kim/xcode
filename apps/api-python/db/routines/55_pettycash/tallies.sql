-- pettycash.tallies(p_holder_ids uuid[], p_from date, p_to date, p_view_all boolean, p_vehicles uuid[]) RETURNS TABLE (holder_id uuid, kind smallint, status smallint, sent_back boolean, window_position smallint, total numeric, entries integer, latest date)
-- Purpose: the sums behind the figures and the float rows: the entries of the floats the actor may see (pettycash.entry_visible), grouped by float, kind, status, sent back or not, and position against the days p_from..p_to (0 before, 1 within, 2 after), with their total, count and latest date.
-- Callers: api.pettycash_overview_get, api.pettycash_dashboard_get.
-- Reads: pettycash.entries. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_pettycash_helpers.py.

CREATE OR REPLACE FUNCTION pettycash.tallies(
  p_holder_ids uuid[],
  p_from date,
  p_to date,
  p_view_all boolean,
  p_vehicles uuid[]
)
RETURNS TABLE (
  holder_id uuid,
  kind smallint,
  status smallint,
  sent_back boolean,
  window_position smallint,
  total numeric,
  entries integer,
  latest date
)
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT e.holder_id,
         e.kind,
         e.status,
         e.sent_back_note IS NOT NULL,
         (CASE WHEN e.entry_date < p_from THEN 0 WHEN e.entry_date <= p_to THEN 1 ELSE 2 END)::smallint,
         sum(e.total),
         count(*)::integer,
         max(e.entry_date)
  FROM pettycash.entries AS e
  WHERE e.organization_id = tenancy.current_organization()
    AND e.holder_id = ANY (p_holder_ids)
    AND pettycash.entry_visible(e, p_view_all, p_vehicles)
  GROUP BY 1, 2, 3, 4, 5;
$$;

REVOKE ALL ON FUNCTION pettycash.tallies(uuid[], date, date, boolean, uuid[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.tallies(uuid[], date, date, boolean, uuid[]) TO xcode_api_executor;
