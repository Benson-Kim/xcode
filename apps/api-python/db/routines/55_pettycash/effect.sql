-- pettycash.effect(p_kind smallint, p_status smallint, p_total numeric) RETURNS numeric
-- Purpose: what an entry does to its float: cash given adds its total, a credit note and an expense take theirs away, a rejected expense nothing (the manager carries it).
-- Callers: pettycash.balance, api.pettycash_entry_create, api.pettycash_entry_remove.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_pettycash_helpers.py.

CREATE OR REPLACE FUNCTION pettycash.effect(p_kind smallint, p_status smallint, p_total numeric)
RETURNS numeric
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
           WHEN p_kind = 1 THEN p_total
           WHEN p_status IS NOT DISTINCT FROM 4 THEN 0
           ELSE -p_total
         END;
$$;

REVOKE ALL ON FUNCTION pettycash.effect(smallint, smallint, numeric) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.effect(smallint, smallint, numeric) TO xcode_api_executor;
