-- pettycash.authorize_remove(p_entry pettycash.entries, p_permissions text[], p_reason text) RETURNS void
-- Purpose: who may delete an entry and whether a reason is needed: cash given or a credit note with pettycash.delete_cash and a reason; a rejected expense never (reopen it first); an approved expense with pettycash.delete_approved and a reason; a waiting expense on one's own float with pettycash.delete_own or pettycash.delete, on another with pettycash.delete, no reason needed. p_reason arrives trimmed, blank as NULL.
-- Callers: api.pettycash_entry_remove.
-- Reads: nothing. Writes: nothing.
-- Raises: XC403 pettycash_delete_cash_permission, XC422 pettycash_delete_rejected, XC403 pettycash_delete_approved_permission, XC403 pettycash_delete_own_permission, XC403 pettycash_delete_other_permission, XC422 reason_length.
-- Tests: tests/db/test_pettycash_helpers.py, tests/db/test_pettycash_routines.py.

CREATE OR REPLACE FUNCTION pettycash.authorize_remove(
  p_entry pettycash.entries,
  p_permissions text[],
  p_reason text
)
RETURNS void
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_needs_reason boolean;
BEGIN
  IF p_entry.kind <> 2 THEN
    IF NOT 'pettycash.delete_cash' = ANY (p_permissions) THEN
      PERFORM tenancy.refuse('pettycash_delete_cash_permission', 'XC403');
    END IF;
    v_needs_reason := true;
  ELSIF p_entry.status = 4 THEN
    PERFORM tenancy.refuse('pettycash_delete_rejected', 'XC422');
  ELSIF p_entry.status = 2 THEN
    IF NOT 'pettycash.delete_approved' = ANY (p_permissions) THEN
      PERFORM tenancy.refuse('pettycash_delete_approved_permission', 'XC403');
    END IF;
    v_needs_reason := true;
  ELSE
    IF p_entry.holder_id = tenancy.current_actor() THEN
      IF NOT p_permissions && ARRAY['pettycash.delete_own', 'pettycash.delete'] THEN
        PERFORM tenancy.refuse('pettycash_delete_own_permission', 'XC403');
      END IF;
    ELSIF NOT 'pettycash.delete' = ANY (p_permissions) THEN
      PERFORM tenancy.refuse('pettycash_delete_other_permission', 'XC403');
    END IF;
    v_needs_reason := false;
  END IF;
  IF v_needs_reason AND p_reason IS NULL THEN
    PERFORM tenancy.refuse('reason_length', 'XC422');
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION pettycash.authorize_remove(pettycash.entries, text[], text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.authorize_remove(pettycash.entries, text[], text) TO xcode_api_executor;
