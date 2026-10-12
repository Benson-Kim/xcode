-- pettycash.status_word(p_status smallint, p_sent_back_note text) RETURNS text
-- Purpose: the wire word of an entry's state: waiting, sentBack (a waiting expense with a sent-back note), approved, rejected; NULL for cash and credit notes.
-- Callers: pettycash.entry_document, pettycash.saved.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_pettycash_helpers.py.

CREATE OR REPLACE FUNCTION pettycash.status_word(p_status smallint, p_sent_back_note text)
RETURNS text
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
           WHEN p_status = 1 AND p_sent_back_note IS NOT NULL THEN 'sentBack'
           WHEN p_status = 1 THEN 'waiting'
           WHEN p_status = 2 THEN 'approved'
           WHEN p_status = 4 THEN 'rejected'
         END;
$$;

REVOKE ALL ON FUNCTION pettycash.status_word(smallint, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.status_word(smallint, text) TO xcode_api_executor;
