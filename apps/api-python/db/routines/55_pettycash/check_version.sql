-- pettycash.check_version(p_entry pettycash.entries, p_expected bigint, p_permissions text[], p_limit numeric, p_earliest date) RETURNS void
-- Purpose: the optimistic check of a write on an entry: a missing or different version is pettycash_entry_changed with the entry as it is now as current.
-- Callers: api.pettycash_entry_update, api.pettycash_entry_approve, api.pettycash_entries_approve, api.pettycash_entry_send_back, api.pettycash_entry_reject, api.pettycash_entry_reopen, api.pettycash_entry_remove.
-- Reads: what pettycash.entry_document reads. Writes: nothing.
-- Raises: XC409 pettycash_entry_changed.
-- Tests: tests/db/test_pettycash_routines.py.

CREATE OR REPLACE FUNCTION pettycash.check_version(
  p_entry pettycash.entries,
  p_expected bigint,
  p_permissions text[],
  p_limit numeric,
  p_earliest date
)
RETURNS void
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF p_expected IS DISTINCT FROM p_entry.version THEN
    PERFORM tenancy.refuse(
      'pettycash_entry_changed',
      'XC409',
      jsonb_build_object(
        'current', pettycash.entry_document(p_entry, p_permissions, p_limit, p_earliest)
      )
    );
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION pettycash.check_version(pettycash.entries, bigint, text[], numeric, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.check_version(pettycash.entries, bigint, text[], numeric, date) TO xcode_api_executor;
