-- tenancy.join_words(p_parts text[]) RETURNS text
-- Purpose: join parts as "a", "a and b", "a, b and c"; NULL parts are skipped and no parts give NULL.
-- Callers: the reasons of settings, scheduled items and people writes.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.join_words(p_parts text[])
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
           WHEN cardinality(cleaned.parts) = 0 THEN NULL
           WHEN cardinality(cleaned.parts) = 1 THEN cleaned.parts[1]
           ELSE array_to_string(cleaned.parts[1:cardinality(cleaned.parts) - 1], ', ')
                || ' and ' || cleaned.parts[cardinality(cleaned.parts)]
         END
  FROM (SELECT coalesce(array_remove(p_parts, NULL), '{}'::text[]) AS parts) AS cleaned;
$$;

REVOKE ALL ON FUNCTION tenancy.join_words(text[]) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.join_words(text[]) TO xcode_api_executor;
