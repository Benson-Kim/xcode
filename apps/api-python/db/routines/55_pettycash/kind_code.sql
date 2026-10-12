-- pettycash.kind_code(p_word text) RETURNS smallint
-- Purpose: the code of a kind's wire word (cash, expense, credit), compared exactly after trimming; NULL for anything else.
-- Callers: api.pettycash_entry_create, api.pettycash_entry_update, api.pettycash_entry_list.
-- Reads: pettycash.kinds. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_pettycash_helpers.py.

CREATE OR REPLACE FUNCTION pettycash.kind_code(p_word text)
RETURNS smallint
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT k.code FROM pettycash.kinds AS k WHERE k.name = tenancy.trim_text(p_word);
$$;

REVOKE ALL ON FUNCTION pettycash.kind_code(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.kind_code(text) TO xcode_api_executor;
