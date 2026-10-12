-- tenancy.compose_reason(p_automatic text, p_typed text) RETURNS text
-- Purpose: the change-log reason: the automatic text, then ". Reason: <typed>." within 500 characters.
-- Callers: every logged write that accepts a typed reason.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.compose_reason(p_automatic text, p_typed text)
RETURNS text
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_suffix text;
  v_automatic text := p_automatic;
  v_room integer;
  v_result text;
BEGIN
  IF p_typed IS NULL OR p_typed = '' THEN
    RETURN CASE WHEN char_length(p_automatic) > 500 THEN left(p_automatic, 497) || '...' ELSE p_automatic END;
  END IF;
  v_suffix := '. Reason: ' || p_typed
    || CASE WHEN right(p_typed, 1) IN ('.', '!', '?') THEN '' ELSE '.' END;
  IF char_length(v_automatic) + char_length(v_suffix) > 500 THEN
    -- The automatic part gives way first, but keeps at least 100 characters.
    v_room := greatest(500 - char_length(v_suffix), 100);
    IF char_length(v_automatic) > v_room THEN
      v_automatic := left(v_automatic, v_room - 3) || '...';
    END IF;
  END IF;
  v_result := v_automatic || v_suffix;
  IF char_length(v_result) > 500 THEN
    v_result := left(v_result, 497) || '...';
  END IF;
  RETURN v_result;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.compose_reason(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.compose_reason(text, text) TO xcode_api_executor;
