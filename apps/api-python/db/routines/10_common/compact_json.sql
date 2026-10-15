-- tenancy.compact_json(p_value json) RETURNS json
-- Purpose: the same JSON with no white space between tokens and every key in its original order, the form the change-log snapshots are stored in.
-- Callers: the snapshot builders (tenancy.person_snapshot, tenancy.settings_snapshot, tenancy.logo_snapshot) and tenancy.redact_person_snapshot.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_access_routines.py, tests/db/test_organization_routines.py.
-- json (not jsonb) keeps key order and the text exactly as built; json_build_object and json_agg
-- put spaces around separators, so every snapshot passes through here before it is stored.

CREATE OR REPLACE FUNCTION tenancy.compact_json(p_value json)
RETURNS json
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_text text;
BEGIN
  IF p_value IS NULL THEN
    RETURN NULL;
  END IF;
  CASE json_typeof(p_value)
    WHEN 'object' THEN
      SELECT '{' || coalesce(
               string_agg(to_json(e.key)::text || ':' || tenancy.compact_json(e.value)::text, ','
                          ORDER BY e.ord),
               '') || '}'
      INTO v_text
      FROM json_each(p_value) WITH ORDINALITY AS e (key, value, ord);
    WHEN 'array' THEN
      SELECT '[' || coalesce(string_agg(tenancy.compact_json(a.value)::text, ',' ORDER BY a.ord), '')
             || ']'
      INTO v_text
      FROM json_array_elements(p_value) WITH ORDINALITY AS a (value, ord);
    ELSE
      v_text := btrim(p_value::text);
  END CASE;
  RETURN v_text::json;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.compact_json(json) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.compact_json(json) TO xcode_api_executor;
