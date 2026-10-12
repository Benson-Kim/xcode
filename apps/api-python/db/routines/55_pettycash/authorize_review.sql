-- pettycash.authorize_review(p_entry pettycash.entries, p_limit numeric) RETURNS void
-- Purpose: who may decide an entry (approve, send back, reject): only an expense; never on one's own float, never an entry one recorded, never above one's approval limit (NULL is no limit). The status is checked by the caller, after the version.
-- Callers: api.pettycash_entry_approve, api.pettycash_entries_approve, api.pettycash_entry_send_back, api.pettycash_entry_reject.
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 pettycash_cash_not_reviewed, XC422 pettycash_credit_not_reviewed, XC403 pettycash_own_float_review, XC403 pettycash_own_entry_review, XC403 pettycash_above_limit.
-- Tests: tests/db/test_pettycash_helpers.py, tests/db/test_pettycash_routines.py.

CREATE OR REPLACE FUNCTION pettycash.authorize_review(p_entry pettycash.entries, p_limit numeric)
RETURNS void
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF p_entry.kind = 1 THEN
    PERFORM tenancy.refuse('pettycash_cash_not_reviewed', 'XC422');
  END IF;
  IF p_entry.kind = 3 THEN
    PERFORM tenancy.refuse('pettycash_credit_not_reviewed', 'XC422');
  END IF;
  IF p_entry.holder_id = tenancy.current_actor() THEN
    PERFORM tenancy.refuse('pettycash_own_float_review', 'XC403');
  END IF;
  IF p_entry.recorded_by = tenancy.current_actor() THEN
    PERFORM tenancy.refuse('pettycash_own_entry_review', 'XC403');
  END IF;
  IF p_limit IS NOT NULL AND abs(p_entry.total) > p_limit THEN
    PERFORM tenancy.refuse('pettycash_above_limit', 'XC403');
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION pettycash.authorize_review(pettycash.entries, numeric) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.authorize_review(pettycash.entries, numeric) TO xcode_api_executor;
