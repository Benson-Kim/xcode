-- pettycash.authorize_change(p_entry pettycash.entries, p_permissions text[]) RETURNS void
-- Purpose: who may edit an expense: only while it waits (an approved or rejected one is reopened first); on one's own float with pettycash.edit_own or pettycash.edit, on another with pettycash.edit. Cash and credit notes are refused by the caller before this.
-- Callers: api.pettycash_entry_update.
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 pettycash_change_decided, XC403 pettycash_change_own_permission, XC403 pettycash_change_other_permission.
-- Tests: tests/db/test_pettycash_helpers.py, tests/db/test_pettycash_routines.py.

CREATE OR REPLACE FUNCTION pettycash.authorize_change(p_entry pettycash.entries, p_permissions text[])
RETURNS void
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF p_entry.status IS DISTINCT FROM 1 THEN
    PERFORM tenancy.refuse('pettycash_change_decided', 'XC422');
  END IF;
  IF 'pettycash.edit' = ANY (p_permissions) THEN
    RETURN;
  END IF;
  IF p_entry.holder_id = tenancy.current_actor() THEN
    IF NOT 'pettycash.edit_own' = ANY (p_permissions) THEN
      PERFORM tenancy.refuse('pettycash_change_own_permission', 'XC403');
    END IF;
    RETURN;
  END IF;
  PERFORM tenancy.refuse('pettycash_change_other_permission', 'XC403');
END;
$$;

REVOKE ALL ON FUNCTION pettycash.authorize_change(pettycash.entries, text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.authorize_change(pettycash.entries, text[]) TO xcode_api_executor;
