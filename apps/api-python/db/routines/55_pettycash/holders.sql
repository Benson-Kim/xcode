-- pettycash.holders() RETURNS TABLE (user_id uuid, name text, active boolean)
-- Purpose: every float of the organization: the members who keep one today (active) and anyone else with an entry not removed (not active), by name ignoring case (ordinal), then id.
-- Callers: pettycash.visible_holders, api.pettycash_options_get, api.pettycash_entry_create.
-- Reads: tenancy.memberships, pettycash.entries, and what pettycash.is_holder reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_pettycash_helpers.py.

CREATE OR REPLACE FUNCTION pettycash.holders()
RETURNS TABLE (user_id uuid, name text, active boolean)
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  RETURN QUERY
  SELECT h.user_id, h.name, h.active
  FROM (
    SELECT m.user_id,
           btrim(m.first_name || ' ' || m.last_name) AS name,
           pettycash.is_holder(m.user_id) AS active
    FROM tenancy.memberships AS m
    WHERE m.organization_id = tenancy.current_organization()
  ) AS h
  WHERE h.active
     OR EXISTS (
       SELECT 1
       FROM pettycash.entries AS e
       WHERE e.organization_id = tenancy.current_organization()
         AND e.holder_id = h.user_id
         AND e.removed_at IS NULL
     )
  ORDER BY upper(h.name) COLLATE "C", h.user_id;
END;
$$;

REVOKE ALL ON FUNCTION pettycash.holders() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.holders() TO xcode_api_executor;
