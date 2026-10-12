-- tenancy.setting_value(p_key text, p_value jsonb) RETURNS text
-- Purpose: how a settings reason shows a value: on/off, none, the weekday name for firstDayOfWeek, "{n} per cent" for gapAmberPercent, strings as is, anything else as JSON text.
-- Callers: the settings writes (reason "Changed {setting} to {value}").
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_tenancy_helpers.py.

CREATE OR REPLACE FUNCTION tenancy.setting_value(p_key text, p_value jsonb)
RETURNS text
LANGUAGE sql
IMMUTABLE
PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
           WHEN p_value IS NULL OR jsonb_typeof(p_value) = 'null' THEN 'none'
           WHEN jsonb_typeof(p_value) = 'boolean' THEN
             CASE WHEN (p_value #>> '{}')::boolean THEN 'on' ELSE 'off' END
           WHEN p_key IN ('firstDayOfWeek', 'first_day_of_week')
                AND jsonb_typeof(p_value) = 'number'
                AND (p_value #>> '{}') ~ '^[0-6]$' THEN
             (ARRAY['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'])
               [(p_value #>> '{}')::integer + 1]
           WHEN p_key IN ('gapAmberPercent', 'gap_amber_percent')
                AND jsonb_typeof(p_value) = 'number' THEN
             (p_value #>> '{}') || ' per cent'
           WHEN jsonb_typeof(p_value) = 'string' THEN p_value #>> '{}'
           ELSE p_value::text
         END;
$$;

REVOKE ALL ON FUNCTION tenancy.setting_value(text, jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.setting_value(text, jsonb) TO xcode_api_executor;
