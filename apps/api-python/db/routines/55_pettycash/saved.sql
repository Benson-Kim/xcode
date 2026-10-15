-- pettycash.saved(p_entry_id uuid, p_outcome text) RETURNS jsonb
-- Purpose: the answer of an entry write (PettyCashSaved plus the outcome): {id, version, status (word), balance (the float to date, after the write), outcome}.
-- Callers: every petty-cash write on one entry.
-- Reads: pettycash.entries, and what pettycash.balance reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_pettycash_routines.py.

CREATE OR REPLACE FUNCTION pettycash.saved(p_entry_id uuid, p_outcome text)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_entry pettycash.entries;
BEGIN
  SELECT e.* INTO v_entry
  FROM pettycash.entries AS e
  WHERE e.organization_id = tenancy.current_organization() AND e.id = p_entry_id;
  RETURN jsonb_build_object(
    'id', v_entry.id,
    'version', v_entry.version,
    'status', pettycash.status_word(v_entry.status, v_entry.sent_back_note),
    'balance', pettycash.balance(v_entry.holder_id),
    'outcome', p_outcome
  );
END;
$$;

REVOKE ALL ON FUNCTION pettycash.saved(uuid, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.saved(uuid, text) TO xcode_api_executor;
