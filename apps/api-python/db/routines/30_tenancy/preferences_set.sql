-- api.preferences_set(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_locale text, p_time_zone text, p_hour12 boolean, p_theme_mode text, p_reduced_motion boolean, p_font_scale double precision, p_now timestamptz) RETURNS jsonb
-- Purpose: replace the actor's own preferences (NULL clears an override) after checking each value and that the organization allows every override given; no change log and no settings version; returns the saved row.
-- Callers: TenancyRoutines.save_preferences; UpdateUserPreferences (PUT /setup/preferences).
-- Reads: what tenancy.settings_document reads. Writes: tenancy.user_preferences.
-- Raises: XC403 not_member via tenancy.enter_organization, XC422 locale_invalid, XC422 preferences_accessibility, XC422 preferences_locale_not_allowed, XC422 preferences_time_zone_not_allowed, XC422 preferences_hour12_not_allowed, XC422 preferences_theme_not_allowed, XC422 time_zone_invalid via tenancy.check_time_zone.
-- Tests: tests/db/test_organization_routines.py, tests/api/test_preferences.py.

CREATE OR REPLACE FUNCTION api.preferences_set(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_locale text,
  p_time_zone text,
  p_hour12 boolean,
  p_theme_mode text,
  p_reduced_motion boolean,
  p_font_scale double precision,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_localization jsonb;
  v_saved tenancy.user_preferences;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  IF p_locale IS NOT NULL AND p_locale !~ '^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$' THEN
    PERFORM tenancy.refuse('locale_invalid', 'XC422');
  END IF;
  IF p_time_zone IS NOT NULL THEN
    PERFORM tenancy.check_time_zone(p_time_zone);
  END IF;
  -- NaN and the infinities fall outside 1..3 in PostgreSQL's float order.
  IF (p_theme_mode IS NOT NULL AND p_theme_mode NOT IN ('light', 'dark', 'system'))
     OR coalesce(p_font_scale NOT BETWEEN 1 AND 3, true) THEN
    PERFORM tenancy.refuse('preferences_accessibility', 'XC422');
  END IF;
  v_localization := tenancy.settings_document('localization');
  IF p_locale IS NOT NULL AND NOT (v_localization ->> 'allow_locale_override')::boolean THEN
    PERFORM tenancy.refuse('preferences_locale_not_allowed', 'XC422');
  END IF;
  IF p_time_zone IS NOT NULL AND NOT (v_localization ->> 'allow_time_zone_override')::boolean THEN
    PERFORM tenancy.refuse('preferences_time_zone_not_allowed', 'XC422');
  END IF;
  IF p_hour12 IS NOT NULL AND NOT (v_localization ->> 'allow_hour12_override')::boolean THEN
    PERFORM tenancy.refuse('preferences_hour12_not_allowed', 'XC422');
  END IF;
  IF p_theme_mode IS NOT NULL AND NOT (v_localization ->> 'allow_theme_override')::boolean THEN
    PERFORM tenancy.refuse('preferences_theme_not_allowed', 'XC422');
  END IF;

  INSERT INTO tenancy.user_preferences AS p (
    organization_id, user_id, locale, time_zone, hour12, theme_mode, reduced_motion, font_scale,
    created_at, updated_at
  )
  VALUES (
    p_organization_id, p_actor_id, p_locale, p_time_zone, p_hour12, p_theme_mode,
    coalesce(p_reduced_motion, false), p_font_scale, p_now, p_now
  )
  ON CONFLICT (organization_id, user_id) DO UPDATE
  SET locale = EXCLUDED.locale,
      time_zone = EXCLUDED.time_zone,
      hour12 = EXCLUDED.hour12,
      theme_mode = EXCLUDED.theme_mode,
      reduced_motion = EXCLUDED.reduced_motion,
      font_scale = EXCLUDED.font_scale,
      updated_at = p_now
  RETURNING p.* INTO v_saved;
  RETURN jsonb_build_object(
    'organization_id', v_saved.organization_id,
    'user_id', v_saved.user_id,
    'locale', v_saved.locale,
    'time_zone', v_saved.time_zone,
    'hour12', v_saved.hour12,
    'theme_mode', v_saved.theme_mode,
    'reduced_motion', v_saved.reduced_motion,
    'font_scale', v_saved.font_scale
  );
END;
$$;
