-- tenancy.check_money(p_amount numeric, p_code text DEFAULT 'money_invalid') RETURNS numeric
-- Purpose: accept a positive amount with at most two decimal places up to 999999999999.99 and return it; nothing is rounded.
-- Callers: every routine that takes an amount (setup, revenue, petty cash).
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 money_invalid.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.check_money(p_amount numeric, p_code text DEFAULT 'money_invalid')
RETURNS numeric
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  -- round(v, 2) = v rather than scale(v) <= 2: 1.500 is accepted, as .NET's Round(v, 2) == v.
  IF p_amount IS NULL OR p_amount <= 0 OR p_amount > 999999999999.99
     OR round(p_amount, 2) <> p_amount THEN
    IF p_code IS NULL OR p_code = 'money_invalid' THEN
      PERFORM tenancy.refuse('money_invalid', 'XC422');
    ELSE
      PERFORM tenancy.refuse(p_code, 'XC422');
    END IF;
  END IF;
  RETURN p_amount;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.check_money(numeric, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.check_money(numeric, text) TO xcode_api_executor;
