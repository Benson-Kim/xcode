-- pettycash.visible_entry(p_entry_id uuid, p_view_all boolean, p_vehicles uuid[], p_lock boolean) RETURNS pettycash.entries
-- Purpose: an entry the current actor may see (pettycash.entry_visible), or XC404 not_found when it does not exist, is removed or is out of view; with p_lock its float is locked first (pettycash.lock_float; the holder never changes) and the row then read again FOR UPDATE NOWAIT, a row another save holds being pettycash_concurrent_save.
-- Callers: api.pettycash_entry_update, api.pettycash_entry_approve, api.pettycash_entries_approve, api.pettycash_entry_send_back, api.pettycash_entry_reject, api.pettycash_entry_reopen, api.pettycash_entry_remove.
-- Reads: pettycash.entries. Writes: nothing (row locks on the holder's membership and the entry).
-- Raises: XC409 pettycash_concurrent_save, XC404 not_found.
-- Tests: tests/db/test_pettycash_routines.py.

CREATE OR REPLACE FUNCTION pettycash.visible_entry(
  p_entry_id uuid,
  p_view_all boolean,
  p_vehicles uuid[],
  p_lock boolean
)
RETURNS pettycash.entries
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_holder uuid;
  v_entry pettycash.entries;
BEGIN
  IF p_lock THEN
    SELECT e.holder_id INTO v_holder
    FROM pettycash.entries AS e
    WHERE e.organization_id = tenancy.current_organization() AND e.id = p_entry_id;
    IF FOUND THEN
      PERFORM pettycash.lock_float(v_holder);
    END IF;
    BEGIN
      SELECT e.* INTO v_entry
      FROM pettycash.entries AS e
      WHERE e.organization_id = tenancy.current_organization() AND e.id = p_entry_id
      FOR UPDATE NOWAIT;
    EXCEPTION
      WHEN lock_not_available THEN
        PERFORM tenancy.refuse('pettycash_concurrent_save', 'XC409');
    END;
  ELSE
    SELECT e.* INTO v_entry
    FROM pettycash.entries AS e
    WHERE e.organization_id = tenancy.current_organization() AND e.id = p_entry_id;
  END IF;
  IF v_entry.id IS NULL OR NOT pettycash.entry_visible(v_entry, p_view_all, p_vehicles) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  RETURN v_entry;
END;
$$;

REVOKE ALL ON FUNCTION pettycash.visible_entry(uuid, boolean, uuid[], boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.visible_entry(uuid, boolean, uuid[], boolean) TO xcode_api_executor;
