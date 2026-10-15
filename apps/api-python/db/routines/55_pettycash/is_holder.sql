-- pettycash.is_holder(p_user_id uuid) RETURNS boolean
-- Purpose: whether the member keeps a petty-cash float today: an active membership whose permissions hold pettycash.spend.
-- Callers: pettycash.holders, api.pettycash_entry_create.
-- Reads: what tenancy.effective_permissions reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_pettycash_helpers.py.

CREATE OR REPLACE FUNCTION pettycash.is_holder(p_user_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT coalesce(
    'pettycash.spend' = ANY (tenancy.effective_permissions(tenancy.current_organization(), p_user_id)),
    false
  );
$$;

REVOKE ALL ON FUNCTION pettycash.is_holder(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.is_holder(uuid) TO xcode_api_executor;
