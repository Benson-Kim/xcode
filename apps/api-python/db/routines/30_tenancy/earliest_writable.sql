-- tenancy.earliest_writable(p_organization_id uuid, p_user_id uuid, p_today date) RETURNS date
-- Purpose: the earliest date the member may add, change or delete records for, given today's business date: N days back is p_today - N; N months back is the same day N months earlier, or that month's last day when the day does not exist; the later of that and the fixed date; NULL when neither is set (any date).
-- Callers: tenancy.check_writable, tenancy.person_document, api.access_my_scope; the petty-cash and central-expense writes through tenancy.check_writable.
-- Reads: tenancy.memberships, and what tenancy.back_limit_earliest reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_back_limit.py.
-- Reads tenant rows under row-level security: the organization setting must already name p_organization_id.

CREATE OR REPLACE FUNCTION tenancy.earliest_writable(
  p_organization_id uuid,
  p_user_id uuid,
  p_today date
)
RETURNS date
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT tenancy.back_limit_earliest(
           m.back_limit_mode, m.back_limit_count, m.back_limit_from, p_today
         )
  FROM tenancy.memberships AS m
  WHERE m.organization_id = p_organization_id
    AND m.user_id = p_user_id;
$$;

REVOKE ALL ON FUNCTION tenancy.earliest_writable(uuid, uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.earliest_writable(uuid, uuid, date) TO xcode_api_executor;
