-- pettycash.member_name(p_user_id uuid) RETURNS text
-- Purpose: a member's name as petty cash shows it, first and last name trimmed; NULL when the organization has no such member.
-- Callers: pettycash.holders, pettycash.describe, pettycash.entry_document, api.pettycash_dashboard_get.
-- Reads: tenancy.memberships. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_pettycash_helpers.py.

CREATE OR REPLACE FUNCTION pettycash.member_name(p_user_id uuid)
RETURNS text
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT btrim(m.first_name || ' ' || m.last_name)
  FROM tenancy.memberships AS m
  WHERE m.organization_id = tenancy.current_organization() AND m.user_id = p_user_id;
$$;

REVOKE ALL ON FUNCTION pettycash.member_name(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.member_name(uuid) TO xcode_api_executor;
