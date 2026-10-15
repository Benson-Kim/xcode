-- tenancy.fmt_money(p_amount numeric) RETURNS text
-- Purpose: an amount as .NET formatted it in reasons: #,##0 when whole, else #,##0.00, invariant culture.
-- Callers: the reasons of vehicle, investment and revenue writes.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.fmt_money(p_amount numeric)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
           WHEN p_amount = trunc(p_amount) THEN to_char(p_amount, 'FM999,999,999,999,990')
           ELSE to_char(p_amount, 'FM999,999,999,999,990.00')
         END;
$$;

REVOKE ALL ON FUNCTION tenancy.fmt_money(numeric) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.fmt_money(numeric) TO xcode_api_executor;
