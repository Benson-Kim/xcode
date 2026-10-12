-- setup.check_day_targets(p_days numeric[]) RETURNS numeric[]
-- Purpose: seven day targets, Monday to Sunday, each a positive amount with at most two decimal places.
-- Callers: api.setup_vehicle_create, api.setup_target_set_save.
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 target_days_required, XC422 money_invalid via tenancy.check_money.
-- Tests: tests/db/test_setup_helpers.py.

CREATE OR REPLACE FUNCTION setup.check_day_targets(p_days numeric[])
RETURNS numeric[]
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_day numeric;
BEGIN
  IF p_days IS NULL OR array_ndims(p_days) <> 1 OR cardinality(p_days) <> 7
     OR array_position(p_days, NULL) IS NOT NULL THEN
    PERFORM tenancy.refuse('target_days_required', 'XC422');
  END IF;
  FOREACH v_day IN ARRAY p_days LOOP
    PERFORM tenancy.check_money(v_day);
  END LOOP;
  RETURN p_days;
END;
$$;

REVOKE ALL ON FUNCTION setup.check_day_targets(numeric[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.check_day_targets(numeric[]) TO xcode_api_executor;
