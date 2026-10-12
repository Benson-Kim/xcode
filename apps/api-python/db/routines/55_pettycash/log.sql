-- pettycash.log(p_entry_id uuid, p_before json, p_verb text, p_typed text, p_action text, p_now timestamptz) RETURNS void
-- Purpose: log one write on an entry, read after the write: a change-log row in section pettycash (the entry's vehicle, the snapshot before and after, the reason "{p_verb} {subject}" with the typed reason after it, within 500 characters) and the audit row pettycash.<p_action> with the same snapshots.
-- Callers: every petty-cash write.
-- Reads: pettycash.entries, and what pettycash.entry_snapshot and pettycash.describe read. Writes: what tenancy.record_change writes.
-- Raises: none.
-- Tests: tests/db/test_pettycash_routines.py.

CREATE OR REPLACE FUNCTION pettycash.log(
  p_entry_id uuid,
  p_before json,
  p_verb text,
  p_typed text,
  p_action text,
  p_now timestamptz
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_entry pettycash.entries;
  v_after json;
BEGIN
  SELECT e.* INTO v_entry
  FROM pettycash.entries AS e
  WHERE e.organization_id = tenancy.current_organization() AND e.id = p_entry_id;
  v_after := pettycash.entry_snapshot(v_entry);
  PERFORM tenancy.record_change(
    'pettycash',
    v_entry.id,
    v_entry.vehicle_id,
    p_before,
    v_after,
    tenancy.compose_reason(p_verb || ' ' || pettycash.describe(v_entry), p_typed),
    'pettycash.' || p_action,
    v_entry.id::text,
    p_before::jsonb,
    v_after::jsonb,
    p_now
  );
END;
$$;

REVOKE ALL ON FUNCTION pettycash.log(uuid, json, text, text, text, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.log(uuid, json, text, text, text, timestamptz) TO xcode_api_executor;
