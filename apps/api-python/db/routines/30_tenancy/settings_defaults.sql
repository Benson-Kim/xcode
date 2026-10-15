-- tenancy.settings_defaults(p_section text) RETURNS jsonb
-- Purpose: the default values of a settings section (localization, branding, securityPolicy, revenue) under the document keys, for an organization that has no row for it yet; NULL for any other section.
-- Callers: tenancy.settings_document.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_organization_routines.py (equal to the column defaults of the four tables).

CREATE OR REPLACE FUNCTION tenancy.settings_defaults(p_section text)
RETURNS jsonb
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE p_section
           WHEN 'localization' THEN jsonb_build_object(
             'locale', 'en-GB',
             'time_zone', 'Africa/Nairobi',
             'date_pattern', 'medium',
             'hour12', false,
             'first_day_of_week', 1,
             'week_numbering', 'iso8601',
             'currency', 'KES',
             'use_grouping', true,
             'number_decimals', 2,
             'allow_locale_override', true,
             'allow_time_zone_override', false,
             'allow_hour12_override', true,
             'allow_theme_override', true
           )
           WHEN 'branding' THEN jsonb_build_object(
             'display_name', 'XCODE',
             'legal_name', 'XCODE',
             'logo_light', NULL,
             'logo_dark', NULL,
             'logo_alt', 'XCODE',
             'favicon', NULL,
             'primary', '#1D5FD6',
             'secondary', '#14213D',
             'accent', '#1E6B3A',
             'domain', NULL,
             'support_email', NULL,
             'terms_url', NULL,
             'privacy_url', NULL
           )
           WHEN 'securityPolicy' THEN jsonb_build_object(
             'password_min_length', 12,
             'password_complexity', true,
             'password_history', 5,
             'pin_length', 4,
             'lockout_threshold', 5,
             'lockout_minutes', 15,
             'access_token_minutes', 10,
             'refresh_token_days', 30,
             'idle_unlock_seconds', 900,
             'allow_pin_sign_in', true
           )
           WHEN 'revenue' THEN jsonb_build_object(
             'low_day_threshold', 4000,
             'gap_amber_percent', 10
           )
         END;
$$;

REVOKE ALL ON FUNCTION tenancy.settings_defaults(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.settings_defaults(text) TO xcode_api_executor;
