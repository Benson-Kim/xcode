-- pettycash.lock_float(p_holder_id uuid) RETURNS void
-- Purpose: hold a float for the rest of the transaction, so writes on one float run one after another and the float guard reads a balance no other write can change before the commit; FOR NO KEY UPDATE on the holder's membership, which does not block the change log's foreign-key checks.
-- Callers: api.pettycash_entry_create, api.pettycash_entry_update, api.pettycash_entry_approve, api.pettycash_entries_approve, api.pettycash_entry_send_back, api.pettycash_entry_reject, api.pettycash_entry_reopen, api.pettycash_entry_remove, api.pettycash_day_approve.
-- Reads: tenancy.memberships. Writes: nothing (a row lock).
-- Raises: none.
-- Tests: tests/db/test_pettycash_routines.py.

CREATE OR REPLACE FUNCTION pettycash.lock_float(p_holder_id uuid)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM 1
  FROM tenancy.memberships AS m
  WHERE m.organization_id = tenancy.current_organization() AND m.user_id = p_holder_id
  FOR NO KEY UPDATE;
END;
$$;

REVOKE ALL ON FUNCTION pettycash.lock_float(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.lock_float(uuid) TO xcode_api_executor;
