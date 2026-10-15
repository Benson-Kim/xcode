-- revenue.round_half_even(p_value numeric, p_scale integer) RETURNS numeric
-- Purpose: banker's rounding (.NET decimal.Round's default) to p_scale decimals: an exact half goes to the even neighbour; every other value rounds as round() does.
-- Callers: none since the figures became sums of day targets in cents; kept with its tests.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.

-- plpgsql keeps its expressions across the calls of one query; a SQL body with FROM cannot be
-- inlined and is executed afresh on every call, five times slower over a week grid.

CREATE OR REPLACE FUNCTION revenue.round_half_even(p_value numeric, p_scale integer)
RETURNS numeric
LANGUAGE plpgsql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_scaled numeric := p_value * power(10::numeric, p_scale);
BEGIN
  IF abs(v_scaled - trunc(v_scaled)) = 0.5 AND mod(trunc(v_scaled), 2) = 0 THEN
    RETURN round(trunc(v_scaled) / power(10::numeric, p_scale), p_scale);
  END IF;
  RETURN round(p_value, p_scale);
END;
$$;

REVOKE ALL ON FUNCTION revenue.round_half_even(numeric, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION revenue.round_half_even(numeric, integer) TO xcode_api_executor;
