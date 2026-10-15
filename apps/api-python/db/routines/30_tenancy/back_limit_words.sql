-- tenancy.back_limit_words(p_mode text, p_count integer, p_from date) RETURNS text
-- Purpose: how far back a person may change records, in the words of the people list ("Can change"): Any date; Today only; n day(s) back; n month(s) back; then ", not before d Month yyyy", or "Not before d Month yyyy" alone.
-- Callers: tenancy.person_document.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_back_limit.py.

CREATE OR REPLACE FUNCTION tenancy.back_limit_words(p_mode text, p_count integer, p_from date)
RETURNS text
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
           WHEN p_mode IN ('days', 'months') THEN
             CASE
               WHEN p_count = 0 THEN 'Today only'
               ELSE p_count::text || ' '
                    || CASE p_mode WHEN 'days' THEN 'day' ELSE 'month' END
                    || CASE WHEN p_count = 1 THEN '' ELSE 's' END || ' back'
             END
             || coalesce(', not before ' || to_char(p_from, 'FMDD FMMonth YYYY'), '')
           WHEN p_from IS NOT NULL THEN 'Not before ' || to_char(p_from, 'FMDD FMMonth YYYY')
           ELSE 'Any date'
         END;
$$;

REVOKE ALL ON FUNCTION tenancy.back_limit_words(text, integer, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.back_limit_words(text, integer, date) TO xcode_api_executor;
