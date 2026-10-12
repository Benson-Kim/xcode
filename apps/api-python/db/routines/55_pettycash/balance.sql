-- pettycash.balance(p_holder_id uuid) RETURNS numeric
-- Purpose: a float's balance to date over all its entries not removed, seen or not: cash given less credit notes less expenses that are not rejected.
-- Callers: pettycash.guard_float, pettycash.saved.
-- Reads: pettycash.entries. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_pettycash_helpers.py.

CREATE OR REPLACE FUNCTION pettycash.balance(p_holder_id uuid)
RETURNS numeric
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  RETURN coalesce(
    (
      SELECT sum(pettycash.effect(e.kind, e.status, e.total))
      FROM pettycash.entries AS e
      WHERE e.organization_id = tenancy.current_organization()
        AND e.holder_id = p_holder_id
        AND e.removed_at IS NULL
    ),
    0
  );
END;
$$;

REVOKE ALL ON FUNCTION pettycash.balance(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.balance(uuid) TO xcode_api_executor;
