-- pettycash.describe(p_entry pettycash.entries) RETURNS text
-- Purpose: the subject of an entry's change-log reasons: an expense is "{holder}'s petty cash spending on {registration, or "a vehicle"} for {d MMM yyyy}"; a credit note "{holder}'s petty cash credit note paying {payee}", without a payee "..., {note}", without either "{holder}'s petty cash credit note"; cash "petty cash given to {holder}", or "taken back from" when negative; an unknown holder reads "someone".
-- Callers: api.pettycash_entry_create, api.pettycash_entry_update, api.pettycash_entry_approve, api.pettycash_entries_approve, api.pettycash_entry_send_back, api.pettycash_entry_reject, api.pettycash_entry_reopen, api.pettycash_entry_remove, api.pettycash_day_approve.
-- Reads: setup.fleet_vehicles, and what pettycash.member_name and tenancy.fmt_day read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_pettycash_helpers.py.

CREATE OR REPLACE FUNCTION pettycash.describe(p_entry pettycash.entries)
RETURNS text
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_holder text := coalesce(pettycash.member_name(p_entry.holder_id), 'someone');
  v_registration text;
BEGIN
  IF p_entry.kind = 2 THEN
    SELECT f.registration INTO v_registration
    FROM setup.fleet_vehicles AS f
    WHERE f.organization_id = p_entry.organization_id AND f.id = p_entry.vehicle_id;
    RETURN v_holder || '''s petty cash spending on ' || coalesce(v_registration, 'a vehicle')
      || ' for ' || tenancy.fmt_day(p_entry.entry_date);
  END IF;
  IF p_entry.kind = 3 THEN
    IF p_entry.payee IS NOT NULL THEN
      RETURN v_holder || '''s petty cash credit note paying ' || p_entry.payee;
    END IF;
    IF p_entry.note IS NOT NULL THEN
      RETURN v_holder || '''s petty cash credit note, ' || p_entry.note;
    END IF;
    RETURN v_holder || '''s petty cash credit note';
  END IF;
  IF p_entry.total < 0 THEN
    RETURN 'petty cash taken back from ' || v_holder;
  END IF;
  RETURN 'petty cash given to ' || v_holder;
END;
$$;

REVOKE ALL ON FUNCTION pettycash.describe(pettycash.entries) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.describe(pettycash.entries) TO xcode_api_executor;
