-- tenancy.settings_snapshot(p_section text) RETURNS json
-- Purpose: the change-log snapshot of a settings section of the current organization, compact camelCase JSON in the order the settings read serves it: organization {name, slug}; localization, branding, securityPolicy and revenue with organizationId (revenue figures without trailing zeros); businessDate a "yyyy-MM-dd" string or null; null when the section has no row.
-- Callers: api.organization_settings_set.
-- Reads: tenancy.organizations, tenancy.organization_localizations, tenancy.organization_brandings, tenancy.organization_security_policies, tenancy.organization_revenue_settings. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_organization_routines.py.

CREATE OR REPLACE FUNCTION tenancy.settings_snapshot(p_section text)
RETURNS json
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.current_organization();
  v_snapshot json;
BEGIN
  CASE p_section
    WHEN 'organization' THEN
      SELECT json_build_object('name', o.name, 'slug', o.slug)
      INTO v_snapshot
      FROM tenancy.organizations AS o
      WHERE o.id = v_organization_id;
    WHEN 'businessDate' THEN
      SELECT to_json(tenancy.fmt_iso(o.business_date))
      INTO v_snapshot
      FROM tenancy.organizations AS o
      WHERE o.id = v_organization_id;
    WHEN 'localization' THEN
      SELECT json_build_object(
               'organizationId', l.organization_id,
               'locale', l.locale,
               'timeZone', l.time_zone,
               'datePattern', l.date_pattern,
               'hour12', l.hour12,
               'firstDayOfWeek', l.first_day_of_week,
               'weekNumbering', l.week_numbering,
               'currency', l.currency,
               'useGrouping', l.use_grouping,
               'numberDecimals', l.number_decimals,
               'allowLocaleOverride', l.allow_locale_override,
               'allowTimeZoneOverride', l.allow_time_zone_override,
               'allowHour12Override', l.allow_hour12_override,
               'allowThemeOverride', l.allow_theme_override
             )
      INTO v_snapshot
      FROM tenancy.organization_localizations AS l
      WHERE l.organization_id = v_organization_id;
    WHEN 'branding' THEN
      SELECT json_build_object(
               'organizationId', b.organization_id,
               'displayName', b.display_name,
               'legalName', b.legal_name,
               'logoLight', b.logo_light_url,
               'logoDark', b.logo_dark_url,
               'logoAlt', b.logo_alt,
               'favicon', b.favicon_url,
               'primary', b.primary_color,
               'secondary', b.secondary_color,
               'accent', b.accent_color,
               'domain', b.domain,
               'supportEmail', b.support_email,
               'termsUrl', b.terms_url,
               'privacyUrl', b.privacy_url
             )
      INTO v_snapshot
      FROM tenancy.organization_brandings AS b
      WHERE b.organization_id = v_organization_id;
    WHEN 'securityPolicy' THEN
      SELECT json_build_object(
               'organizationId', s.organization_id,
               'passwordMinLength', s.password_min_length,
               'passwordComplexity', s.password_complexity,
               'passwordHistory', s.password_history,
               'pinLength', s.pin_length,
               'lockoutThreshold', s.lockout_threshold,
               'lockoutMinutes', s.lockout_minutes,
               'accessTokenMinutes', s.access_token_minutes,
               'refreshTokenDays', s.refresh_token_days,
               'idleUnlockSeconds', s.idle_unlock_seconds,
               'allowPinSignIn', s.allow_pin_sign_in
             )
      INTO v_snapshot
      FROM tenancy.organization_security_policies AS s
      WHERE s.organization_id = v_organization_id;
    WHEN 'revenue' THEN
      SELECT json_build_object(
               'organizationId', r.organization_id,
               'lowDayThreshold', trim_scale(r.low_day_threshold),
               'gapAmberPercent', trim_scale(r.gap_amber_percent)
             )
      INTO v_snapshot
      FROM tenancy.organization_revenue_settings AS r
      WHERE r.organization_id = v_organization_id;
    ELSE
      v_snapshot := NULL;
  END CASE;
  RETURN tenancy.compact_json(coalesce(v_snapshot, 'null'::json));
END;
$$;

REVOKE ALL ON FUNCTION tenancy.settings_snapshot(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.settings_snapshot(text) TO xcode_api_executor;
