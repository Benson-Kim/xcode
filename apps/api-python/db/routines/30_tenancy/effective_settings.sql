-- tenancy.effective_settings(p_user_id uuid) RETURNS jsonb
-- Purpose: what a member's screens use: the formats (locale, time zone and clock from the person when the organization allows it, everything else from the organization, direction from the locale), the branding, the security policy clamped into its bounds, and the theme (the person's or system when allowed, else light), reduced motion and font scale; the stored sections are validated on every read.
-- Callers: api.organization_settings_get (effective), api.organization_appearance_get.
-- Reads: tenancy.user_preferences, and what tenancy.settings_document reads. Writes: nothing.
-- Raises: XC422 locale_invalid via tenancy.check_localization, XC422 time_zone_invalid via tenancy.check_localization, XC422 format_settings_invalid via tenancy.check_localization, XC422 brand_names_required via tenancy.check_branding, XC422 brand_colour_format via tenancy.check_branding, XC422 brand_contrast via tenancy.check_branding, XC422 brand_url_https via tenancy.check_branding, XC422 brand_domain_invalid via tenancy.check_branding, XC422 brand_support_email_invalid via tenancy.check_branding, XC422 time_zone_invalid via tenancy.check_time_zone.
-- Tests: tests/db/test_organization_routines.py.

CREATE OR REPLACE FUNCTION tenancy.effective_settings(p_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_localization jsonb := tenancy.settings_document('localization');
  v_branding jsonb := tenancy.settings_document('branding');
  v_policy jsonb := tenancy.settings_document('securityPolicy');
  v_preference tenancy.user_preferences;
  v_locale text;
BEGIN
  PERFORM tenancy.check_localization(v_localization);
  PERFORM tenancy.check_branding(v_branding);
  SELECT p.* INTO v_preference
  FROM tenancy.user_preferences AS p
  WHERE p.organization_id = tenancy.current_organization() AND p.user_id = p_user_id;
  IF v_preference.time_zone IS NOT NULL THEN
    PERFORM tenancy.check_time_zone(v_preference.time_zone);
  END IF;

  v_locale := CASE
                WHEN (v_localization ->> 'allow_locale_override')::boolean AND v_preference.locale IS NOT NULL
                  THEN v_preference.locale
                ELSE v_localization ->> 'locale'
              END;
  RETURN jsonb_build_object(
    'formats', jsonb_build_object(
      'locale', v_locale,
      'time_zone', CASE
                     WHEN (v_localization ->> 'allow_time_zone_override')::boolean
                          AND v_preference.time_zone IS NOT NULL THEN v_preference.time_zone
                     ELSE v_localization ->> 'time_zone'
                   END,
      'date_pattern', v_localization -> 'date_pattern',
      'hour12', CASE
                  WHEN (v_localization ->> 'allow_hour12_override')::boolean
                       AND v_preference.hour12 IS NOT NULL THEN to_jsonb(v_preference.hour12)
                  ELSE v_localization -> 'hour12'
                END,
      'first_day_of_week', v_localization -> 'first_day_of_week',
      'week_numbering', v_localization -> 'week_numbering',
      'currency', v_localization -> 'currency',
      'use_grouping', v_localization -> 'use_grouping',
      'number_decimals', v_localization -> 'number_decimals',
      'direction', CASE
                     WHEN lower(split_part(v_locale, '-', 1)) IN ('ar', 'fa', 'he', 'ur') THEN 'rtl'
                     ELSE 'ltr'
                   END
    ),
    'branding', v_branding,
    'security_policy', jsonb_build_object(
      'organization_id', v_policy -> 'organization_id',
      'password_min_length', greatest(12, least(128, (v_policy ->> 'password_min_length')::integer)),
      'password_complexity', v_policy -> 'password_complexity',
      'password_history', greatest(0, least(24, (v_policy ->> 'password_history')::integer)),
      'pin_length', greatest(4, least(8, (v_policy ->> 'pin_length')::integer)),
      'lockout_threshold', greatest(3, least(10, (v_policy ->> 'lockout_threshold')::integer)),
      'lockout_minutes', greatest(1, least(60, (v_policy ->> 'lockout_minutes')::integer)),
      'access_token_minutes', greatest(1, least(15, (v_policy ->> 'access_token_minutes')::integer)),
      'refresh_token_days', greatest(1, least(90, (v_policy ->> 'refresh_token_days')::integer)),
      'idle_unlock_seconds', greatest(30, least(3600, (v_policy ->> 'idle_unlock_seconds')::integer)),
      'allow_pin_sign_in', v_policy -> 'allow_pin_sign_in'
    ),
    'theme_mode', CASE
                    WHEN (v_localization ->> 'allow_theme_override')::boolean
                      THEN coalesce(v_preference.theme_mode, 'system')
                    ELSE 'light'
                  END,
    'reduced_motion', coalesce(v_preference.reduced_motion, false),
    'font_scale', coalesce(v_preference.font_scale, 1)
  );
END;
$$;

REVOKE ALL ON FUNCTION tenancy.effective_settings(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.effective_settings(uuid) TO xcode_api_executor;
