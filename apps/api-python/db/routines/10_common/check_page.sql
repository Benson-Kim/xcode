-- tenancy.check_page(p_page integer, p_page_size integer) RETURNS void
-- Purpose: refuse a page outside 1..100000 or a page size outside 1..100; nothing is clamped.
-- Callers: every list routine.
-- Reads: nothing. Writes: nothing.
-- Raises: XC422 page_out_of_range.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.check_page(p_page integer, p_page_size integer)
RETURNS void
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF p_page IS NULL OR p_page NOT BETWEEN 1 AND 100000
     OR p_page_size IS NULL OR p_page_size NOT BETWEEN 1 AND 100 THEN
    PERFORM tenancy.refuse('page_out_of_range', 'XC422');
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.check_page(integer, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.check_page(integer, integer) TO xcode_api_executor;
