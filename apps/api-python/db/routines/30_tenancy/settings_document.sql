-- tenancy.settings_document(p_section text) RETURNS jsonb
-- Purpose: the current organization's localization, branding, securityPolicy or revenue section as the settings read serves it (document keys, organization_id included), or its defaults when no row exists; NULL for any other section.
-- Callers: api.organization_settings_get, api.organization_settings_set (the merge base), tenancy.effective_settings, api.preferences_get, api.preferences_set, api.history_list (the organization zone).
-- Reads: tenancy.organization_localizations, tenancy.organization_brandings, tenancy.organization_security_policies, tenancy.organization_revenue_settings. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_organization_routines.py.
-- Branding columns carry the reserved-word-free names (primary_color, logo_light_url); the
-- document keeps the wire names (primary, logo_light), mapped here and in the section save.

CREATE OR REPLACE FUNCTION tenancy.settings_document(p_section text)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.current_organization();
  v_document jsonb;
BEGIN
  CASE p_section
    WHEN 'localization' THEN
      SELECT jsonb_build_object(
               'organization_id', l.organization_id,
               'locale', l.locale,
               'time_zone', l.time_zone,
               'date_pattern', l.date_pattern,
               'hour12', l.hour12,
               'first_day_of_week', l.first_day_of_week,
               'week_numbering', l.week_numbering,
               'currency', l.currency,
               'use_grouping', l.use_grouping,
               'number_decimals', l.number_decimals,
               'allow_locale_override', l.allow_locale_override,
               'allow_time_zone_override', l.allow_time_zone_override,
               'allow_hour12_override', l.allow_hour12_override,
               'allow_theme_override', l.allow_theme_override
             )
      INTO v_document
      FROM tenancy.organization_localizations AS l
      WHERE l.organization_id = v_organization_id;
    WHEN 'branding' THEN
      SELECT jsonb_build_object(
               'organization_id', b.organization_id,
               'display_name', b.display_name,
               'legal_name', b.legal_name,
               'logo_light', b.logo_light_url,
               'logo_dark', b.logo_dark_url,
               'logo_alt', b.logo_alt,
               'favicon', b.favicon_url,
               'primary', b.primary_color,
               'secondary', b.secondary_color,
               'accent', b.accent_color,
               'domain', b.domain,
               'support_email', b.support_email,
               'terms_url', b.terms_url,
               'privacy_url', b.privacy_url
             )
      INTO v_document
      FROM tenancy.organization_brandings AS b
      WHERE b.organization_id = v_organization_id;
    WHEN 'securityPolicy' THEN
      SELECT jsonb_build_object(
               'organization_id', s.organization_id,
               'password_min_length', s.password_min_length,
               'password_complexity', s.password_complexity,
               'password_history', s.password_history,
               'pin_length', s.pin_length,
               'lockout_threshold', s.lockout_threshold,
               'lockout_minutes', s.lockout_minutes,
               'access_token_minutes', s.access_token_minutes,
               'refresh_token_days', s.refresh_token_days,
               'idle_unlock_seconds', s.idle_unlock_seconds,
               'allow_pin_sign_in', s.allow_pin_sign_in
             )
      INTO v_document
      FROM tenancy.organization_security_policies AS s
      WHERE s.organization_id = v_organization_id;
    WHEN 'revenue' THEN
      SELECT jsonb_build_object(
               'organization_id', r.organization_id,
               'low_day_threshold', r.low_day_threshold,
               'gap_amber_percent', r.gap_amber_percent
             )
      INTO v_document
      FROM tenancy.organization_revenue_settings AS r
      WHERE r.organization_id = v_organization_id;
    ELSE
      RETURN NULL;
  END CASE;
  RETURN coalesce(
    v_document,
    jsonb_build_object('organization_id', v_organization_id) || tenancy.settings_defaults(p_section)
  );
END;
$$;

REVOKE ALL ON FUNCTION tenancy.settings_document(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.settings_document(text) TO xcode_api_executor;
