-- api.preferences_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_now timestamptz) RETURNS jsonb
-- Purpose: the actor's own preferences (defaults when none are stored), with locale, time zone, clock and theme served as NULL whenever the organization does not allow that override, the four allow flags, and the organization's locale, time zone and clock.
-- Callers: TenancyRoutines.preferences; GetUserPreferences (GET /setup/preferences).
-- Reads: tenancy.user_preferences, and what tenancy.settings_document reads. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization.
-- Tests: tests/db/test_organization_routines.py, tests/api/test_preferences.py.

CREATE OR REPLACE FUNCTION api.preferences_get(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_localization jsonb;
  v_preference tenancy.user_preferences;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  v_localization := tenancy.settings_document('localization');
  SELECT p.* INTO v_preference
  FROM tenancy.user_preferences AS p
  WHERE p.organization_id = p_organization_id AND p.user_id = p_actor_id;
  RETURN jsonb_build_object(
    'organization_id', p_organization_id,
    'user_id', p_actor_id,
    'locale', CASE WHEN (v_localization ->> 'allow_locale_override')::boolean THEN v_preference.locale END,
    'time_zone', CASE
                   WHEN (v_localization ->> 'allow_time_zone_override')::boolean THEN v_preference.time_zone
                 END,
    'hour12', CASE WHEN (v_localization ->> 'allow_hour12_override')::boolean THEN v_preference.hour12 END,
    'theme_mode', CASE
                    WHEN (v_localization ->> 'allow_theme_override')::boolean THEN v_preference.theme_mode
                  END,
    'reduced_motion', coalesce(v_preference.reduced_motion, false),
    'font_scale', coalesce(v_preference.font_scale, 1),
    'allow_locale_override', v_localization -> 'allow_locale_override',
    'allow_time_zone_override', v_localization -> 'allow_time_zone_override',
    'allow_hour12_override', v_localization -> 'allow_hour12_override',
    'allow_theme_override', v_localization -> 'allow_theme_override',
    'organization', jsonb_build_object(
      'locale', v_localization -> 'locale',
      'time_zone', v_localization -> 'time_zone',
      'hour12', v_localization -> 'hour12'
    )
  );
END;
$$;
