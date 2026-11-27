-- setup.check_low_below(p_amount numeric) RETURNS numeric
-- Purpose: the low revenue figure of a target set, 0 or a positive amount with at most two decimal places up to 999999999999.99; revenue with an amount below it on a day needs a reason.
-- Callers: api.setup_vehicle_create, api.setup_target_set_save.
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 money_invalid via tenancy.check_money.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.check_low_below(p_amount numeric)
RETURNS numeric
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF p_amount IS DISTINCT FROM 0 THEN
    PERFORM tenancy.check_money(p_amount);
  END IF;
  RETURN p_amount;
END;
$$;

REVOKE ALL ON FUNCTION setup.check_low_below(numeric) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.check_low_below(numeric) TO xcode_api_executor;
