-- tenancy.settings_reason(p_section text, p_before json, p_after json) RETURNS text
-- Purpose: the automatic reason of a settings save: "Changed " and "{setting} to {value}" for each top-level key of p_after whose value differs from p_before (every key when p_before is not an object; organizationId never), joined as a, b and c; "Changed the {section} settings" when no key differs.
-- Callers: api.organization_settings_set.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_organization_routines.py.

CREATE OR REPLACE FUNCTION tenancy.settings_reason(p_section text, p_before json, p_after json)
RETURNS text
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT coalesce(
    'Changed ' || tenancy.join_words(
      ARRAY(
        SELECT tenancy.setting_word(e.key) || ' to ' || tenancy.setting_value(e.key, e.value::jsonb)
        FROM json_each(p_after) WITH ORDINALITY AS e (key, value, ord)
        WHERE e.key <> 'organizationId'
          AND (json_typeof(p_before) IS DISTINCT FROM 'object'
               OR (p_before -> e.key)::jsonb IS DISTINCT FROM e.value::jsonb)
        ORDER BY e.ord
      )
    ),
    'Changed the ' || p_section || ' settings'
  );
$$;

REVOKE ALL ON FUNCTION tenancy.settings_reason(text, json, json) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.settings_reason(text, json, json) TO xcode_api_executor;
