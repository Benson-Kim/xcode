-- tenancy.setting_word(p_key text) RETURNS text
-- Purpose: how a settings reason names a field: the fixed names of the settings sections, else "the " and the camelCase key in words; NULL for organizationId.
-- Callers: the settings writes (reason "Changed {setting} to {value}").
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.setting_word(p_key text)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  WITH camel AS (
    -- snake_case column names are accepted as well as the camelCase wire keys
    SELECT string_agg(
             CASE WHEN parts.ord = 1 THEN parts.part ELSE initcap(parts.part) END,
             '' ORDER BY parts.ord
           ) AS key
    FROM regexp_split_to_table(p_key, '_') WITH ORDINALITY AS parts (part, ord)
  )
  SELECT CASE camel.key
           WHEN 'organizationId' THEN NULL
           WHEN 'name' THEN 'the organization name'
           WHEN 'hour12' THEN 'the 12-hour clock'
           WHEN 'datePattern' THEN 'the date format'
           WHEN 'firstDayOfWeek' THEN 'the first day of the week'
           WHEN 'weekNumbering' THEN 'week numbering'
           WHEN 'useGrouping' THEN 'digit grouping'
           WHEN 'numberDecimals' THEN 'the decimal places'
           WHEN 'allowLocaleOverride' THEN 'personal locales'
           WHEN 'allowTimeZoneOverride' THEN 'personal time zones'
           WHEN 'allowHour12Override' THEN 'personal clock formats'
           WHEN 'allowThemeOverride' THEN 'personal themes'
           WHEN 'logoLight' THEN 'the light logo'
           WHEN 'logoLightUrl' THEN 'the light logo'
           WHEN 'logoDark' THEN 'the dark logo'
           WHEN 'logoDarkUrl' THEN 'the dark logo'
           WHEN 'primary' THEN 'the primary colour'
           WHEN 'primaryColor' THEN 'the primary colour'
           WHEN 'secondary' THEN 'the secondary colour'
           WHEN 'secondaryColor' THEN 'the secondary colour'
           WHEN 'accent' THEN 'the accent colour'
           WHEN 'accentColor' THEN 'the accent colour'
           WHEN 'passwordComplexity' THEN 'password complexity'
           WHEN 'pinLength' THEN 'the PIN length'
           WHEN 'lockoutThreshold' THEN 'the wrong PIN tries before a pause'
           WHEN 'lockoutMinutes' THEN 'the pause in minutes'
           WHEN 'allowPinSignIn' THEN 'PIN sign-in'
           WHEN 'logoAlt' THEN 'the logo text'
           WHEN 'lowDayThreshold' THEN 'the low-day threshold'
           WHEN 'gapAmberPercent' THEN 'the amber band'
           ELSE 'the ' || lower(regexp_replace(camel.key, '([a-z])([A-Z])', '\1 \2', 'g'))
         END
  FROM camel;
$$;

REVOKE ALL ON FUNCTION tenancy.setting_word(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.setting_word(text) TO xcode_api_executor;
