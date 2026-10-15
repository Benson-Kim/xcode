-- api.organization_settings_set(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_section text, p_value jsonb, p_reason text, p_expected_version bigint, p_now timestamptz) RETURNS api.write_result
-- Purpose: save one settings section (organization, localization, branding, securityPolicy, businessDate, revenue): checked and normalised, merged onto the stored section where the section merges, validated, and logged once with an automatic reason; unchanged (nothing written, no version) when it equals what is stored.
-- Callers: TenancyRoutines.save_settings; UpdateOrganizationSettings (PUT /setup/organization/settings/{section}).
-- Reads: tenancy.organizations, and what tenancy.settings_document and tenancy.settings_snapshot read. Writes: tenancy.organizations (name, slug, business date), tenancy.organization_localizations, tenancy.organization_brandings, tenancy.organization_security_policies, tenancy.organization_revenue_settings, and through tenancy.record_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 reason_length via tenancy.check_typed_reason, XC404 not_found, XC422 settings_not_object, XC422 settings_wrong_type, XC422 organization_name_slug, XC409 version_conflict, XC409 organization_slug_taken, XC422 business_date_invalid, XC422 business_date_future, XC422 settings_business_date_future_zone, XC422 time_zone_invalid via tenancy.calendar_date, XC422 locale_invalid via tenancy.check_localization, XC422 time_zone_invalid via tenancy.check_localization, XC422 format_settings_invalid via tenancy.check_localization, XC422 brand_names_required via tenancy.check_branding, XC422 brand_colour_format via tenancy.check_branding, XC422 brand_contrast via tenancy.check_branding, XC422 brand_url_https via tenancy.check_branding, XC422 brand_domain_invalid via tenancy.check_branding, XC422 brand_support_email_invalid via tenancy.check_branding, XC422 security_policy_pin_sign_in via tenancy.check_security_policy, XC422 security_policy_invalid via tenancy.check_security_policy, XC422 revenue_settings_invalid via tenancy.check_revenue_settings.
-- Tests: tests/db/test_organization_routines.py, tests/api/test_organization_settings.py.
-- The organization row is locked first: a section save reads, merges and writes, so two saves of
-- one organization queue instead of overwriting each other's fields. Values arrive under the
-- document keys (use_grouping; the legacy use_groupping counts when use_grouping is absent).
-- The revenue section logs in the change-log section organization: revenue rows there are a
-- vehicle's records and always carry the vehicle. Its reason shows the threshold as money
-- ({CUR} {amount}); the logged snapshots keep the numbers.

CREATE OR REPLACE FUNCTION api.organization_settings_set(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_section text,
  p_value jsonb,
  p_reason text,
  p_expected_version bigint,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_reason text;
  v_organization tenancy.organizations;
  v_value jsonb := p_value;
  v_name text;
  v_slug text;
  v_date date;
  v_patch jsonb;
  v_wrong_type boolean;
  v_stored jsonb;
  v_merged jsonb;
  v_exists boolean;
  v_before json;
  v_after json;
  v_automatic text;
  v_currency text;
  v_final text;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'organization.manage');
  v_reason := tenancy.check_typed_reason(p_reason);
  IF p_section IS NULL
     OR p_section NOT IN (
       'organization', 'localization', 'branding', 'securityPolicy', 'businessDate', 'revenue'
     ) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  SELECT o.* INTO v_organization
  FROM tenancy.organizations AS o
  WHERE o.id = p_organization_id
  FOR UPDATE;

  IF p_section = 'organization' THEN
    IF jsonb_typeof(v_value) IS DISTINCT FROM 'object' THEN
      PERFORM tenancy.refuse('settings_not_object', 'XC422');
    END IF;
    IF coalesce(jsonb_typeof(v_value -> 'name'), 'null') NOT IN ('string', 'null')
       OR coalesce(jsonb_typeof(v_value -> 'slug'), 'null') NOT IN ('string', 'null') THEN
      PERFORM tenancy.refuse('settings_wrong_type', 'XC422');
    END IF;
    v_name := tenancy.trim_text(v_value ->> 'name');
    v_slug := lower(tenancy.trim_text(v_value ->> 'slug'));
    IF v_name IS NULL OR char_length(v_name) > 200
       OR v_slug IS NULL OR char_length(v_slug) > 100
       OR v_slug !~ '^[a-z0-9]+(-[a-z0-9]+)*$' THEN
      PERFORM tenancy.refuse('organization_name_slug', 'XC422');
    END IF;
    IF v_name = v_organization.name AND v_slug = v_organization.slug THEN
      RETURN ROW(p_organization_id, v_organization.settings_version, 'unchanged')::api.write_result;
    END IF;
    IF p_expected_version IS NOT NULL AND p_expected_version <> v_organization.settings_version THEN
      PERFORM tenancy.refuse('version_conflict', 'XC409');
    END IF;
    v_before := tenancy.settings_snapshot('organization');
    -- Other organizations' slugs are invisible under row-level security; the unique index decides.
    BEGIN
      UPDATE tenancy.organizations
      SET name = v_name, slug = v_slug, updated_at = p_now
      WHERE id = p_organization_id;
    EXCEPTION
      WHEN unique_violation THEN
        PERFORM tenancy.refuse('organization_slug_taken', 'XC409');
    END;
    v_after := tenancy.settings_snapshot('organization');
    v_automatic := tenancy.settings_reason(p_section, v_before, v_after);

  ELSIF p_section = 'businessDate' THEN
    IF v_value IS NULL OR jsonb_typeof(v_value) = 'null' THEN
      v_date := NULL;
    ELSIF jsonb_typeof(v_value) = 'string' AND (v_value #>> '{}') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' THEN
      BEGIN
        v_date := (v_value #>> '{}')::date;
      EXCEPTION
        WHEN invalid_datetime_format OR datetime_field_overflow THEN
          PERFORM tenancy.refuse('business_date_invalid', 'XC422');
      END;
      IF v_date = DATE '0001-01-01' THEN
        PERFORM tenancy.refuse('business_date_invalid', 'XC422');
      END IF;
    ELSE
      PERFORM tenancy.refuse('business_date_invalid', 'XC422');
    END IF;
    IF v_date > tenancy.calendar_date(p_organization_id, p_now) THEN
      PERFORM tenancy.refuse('business_date_future', 'XC422');
    END IF;
    IF v_date IS NOT DISTINCT FROM v_organization.business_date THEN
      RETURN ROW(p_organization_id, v_organization.settings_version, 'unchanged')::api.write_result;
    END IF;
    IF p_expected_version IS NOT NULL AND p_expected_version <> v_organization.settings_version THEN
      PERFORM tenancy.refuse('version_conflict', 'XC409');
    END IF;
    v_before := tenancy.settings_snapshot('businessDate');
    UPDATE tenancy.organizations
    SET business_date = v_date, updated_at = p_now
    WHERE id = p_organization_id;
    v_after := tenancy.settings_snapshot('businessDate');
    v_automatic := CASE
                     WHEN v_date IS NULL THEN 'Returned the business date to the calendar'
                     ELSE 'Set the business date to ' || tenancy.fmt_iso(v_date)
                   END;

  ELSE
    IF jsonb_typeof(v_value) IS DISTINCT FROM 'object' THEN
      PERFORM tenancy.refuse('settings_not_object', 'XC422');
    END IF;
    IF p_section = 'localization' AND v_value ? 'use_groupping' THEN
      IF NOT v_value ? 'use_grouping' THEN
        v_value := v_value || jsonb_build_object('use_grouping', v_value -> 'use_groupping');
      END IF;
      v_value := v_value - 'use_groupping';
    END IF;
    -- Only the section's own keys count; each must carry a value of its kind.
    SELECT coalesce(jsonb_object_agg(f.key, v_value -> f.key), '{}'::jsonb),
           coalesce(bool_or(NOT CASE jsonb_typeof(v_value -> f.key)
                                  WHEN 'null' THEN f.nullable
                                  WHEN 'string' THEN f.kind = 'string'
                                  WHEN 'boolean' THEN f.kind = 'boolean'
                                  WHEN 'number' THEN f.kind = 'decimal'
                                    OR (f.kind = 'integer'
                                        AND (v_value ->> f.key) ~ '^-?[0-9]+$'
                                        AND abs((v_value ->> f.key)::numeric) <= 2147483647)
                                  ELSE false
                                END), false)
    INTO v_patch, v_wrong_type
    FROM (VALUES
      ('localization', 'locale', 'string', false),
      ('localization', 'time_zone', 'string', false),
      ('localization', 'date_pattern', 'string', false),
      ('localization', 'hour12', 'boolean', false),
      ('localization', 'first_day_of_week', 'integer', false),
      ('localization', 'week_numbering', 'string', false),
      ('localization', 'currency', 'string', false),
      ('localization', 'use_grouping', 'boolean', false),
      ('localization', 'number_decimals', 'integer', false),
      ('localization', 'allow_locale_override', 'boolean', false),
      ('localization', 'allow_time_zone_override', 'boolean', false),
      ('localization', 'allow_hour12_override', 'boolean', false),
      ('localization', 'allow_theme_override', 'boolean', false),
      ('branding', 'display_name', 'string', false),
      ('branding', 'legal_name', 'string', false),
      ('branding', 'logo_light', 'string', true),
      ('branding', 'logo_dark', 'string', true),
      ('branding', 'logo_alt', 'string', false),
      ('branding', 'favicon', 'string', true),
      ('branding', 'primary', 'string', false),
      ('branding', 'secondary', 'string', false),
      ('branding', 'accent', 'string', false),
      ('branding', 'domain', 'string', true),
      ('branding', 'support_email', 'string', true),
      ('branding', 'terms_url', 'string', true),
      ('branding', 'privacy_url', 'string', true),
      ('securityPolicy', 'password_min_length', 'integer', false),
      ('securityPolicy', 'password_complexity', 'boolean', false),
      ('securityPolicy', 'password_history', 'integer', false),
      ('securityPolicy', 'pin_length', 'integer', false),
      ('securityPolicy', 'lockout_threshold', 'integer', false),
      ('securityPolicy', 'lockout_minutes', 'integer', false),
      ('securityPolicy', 'access_token_minutes', 'integer', false),
      ('securityPolicy', 'refresh_token_days', 'integer', false),
      ('securityPolicy', 'idle_unlock_seconds', 'integer', false),
      ('securityPolicy', 'allow_pin_sign_in', 'boolean', false),
      ('revenue', 'low_day_threshold', 'decimal', false),
      ('revenue', 'gap_amber_percent', 'decimal', false)
    ) AS f (section, key, kind, nullable)
    WHERE f.section = p_section AND v_value ? f.key;
    IF v_wrong_type THEN
      PERFORM tenancy.refuse('settings_wrong_type', 'XC422');
    END IF;

    v_stored := tenancy.settings_document(p_section);
    v_merged := v_stored || v_patch;
    v_exists := CASE p_section
                  WHEN 'localization' THEN EXISTS (
                    SELECT 1 FROM tenancy.organization_localizations AS l
                    WHERE l.organization_id = p_organization_id)
                  WHEN 'branding' THEN EXISTS (
                    SELECT 1 FROM tenancy.organization_brandings AS b
                    WHERE b.organization_id = p_organization_id)
                  WHEN 'revenue' THEN EXISTS (
                    SELECT 1 FROM tenancy.organization_revenue_settings AS r
                    WHERE r.organization_id = p_organization_id)
                  ELSE EXISTS (
                    SELECT 1 FROM tenancy.organization_security_policies AS s
                    WHERE s.organization_id = p_organization_id)
                END;
    IF p_section = 'localization' THEN
      PERFORM tenancy.check_localization(v_merged);
      IF v_merged <> v_stored
         AND v_organization.business_date > (p_now AT TIME ZONE (v_merged ->> 'time_zone'))::date THEN
        PERFORM tenancy.refuse('settings_business_date_future_zone', 'XC422');
      END IF;
    ELSIF p_section = 'branding' THEN
      PERFORM tenancy.check_branding(v_merged);
    ELSIF p_section = 'revenue' THEN
      PERFORM tenancy.check_revenue_settings(v_merged);
    ELSE
      PERFORM tenancy.check_security_policy(v_merged);
    END IF;
    IF v_exists AND v_merged = v_stored THEN
      RETURN ROW(p_organization_id, v_organization.settings_version, 'unchanged')::api.write_result;
    END IF;
    IF p_expected_version IS NOT NULL AND p_expected_version <> v_organization.settings_version THEN
      PERFORM tenancy.refuse('version_conflict', 'XC409');
    END IF;

    v_before := tenancy.settings_snapshot(p_section);
    IF p_section = 'localization' THEN
      INSERT INTO tenancy.organization_localizations AS l (
        organization_id, locale, time_zone, date_pattern, hour12, first_day_of_week,
        week_numbering, currency, use_grouping, number_decimals, allow_locale_override,
        allow_time_zone_override, allow_hour12_override, allow_theme_override, created_at, updated_at
      )
      VALUES (
        p_organization_id,
        v_merged ->> 'locale',
        v_merged ->> 'time_zone',
        v_merged ->> 'date_pattern',
        (v_merged ->> 'hour12')::boolean,
        (v_merged ->> 'first_day_of_week')::smallint,
        v_merged ->> 'week_numbering',
        v_merged ->> 'currency',
        (v_merged ->> 'use_grouping')::boolean,
        (v_merged ->> 'number_decimals')::smallint,
        (v_merged ->> 'allow_locale_override')::boolean,
        (v_merged ->> 'allow_time_zone_override')::boolean,
        (v_merged ->> 'allow_hour12_override')::boolean,
        (v_merged ->> 'allow_theme_override')::boolean,
        p_now,
        p_now
      )
      ON CONFLICT (organization_id) DO UPDATE
      SET locale = EXCLUDED.locale,
          time_zone = EXCLUDED.time_zone,
          date_pattern = EXCLUDED.date_pattern,
          hour12 = EXCLUDED.hour12,
          first_day_of_week = EXCLUDED.first_day_of_week,
          week_numbering = EXCLUDED.week_numbering,
          currency = EXCLUDED.currency,
          use_grouping = EXCLUDED.use_grouping,
          number_decimals = EXCLUDED.number_decimals,
          allow_locale_override = EXCLUDED.allow_locale_override,
          allow_time_zone_override = EXCLUDED.allow_time_zone_override,
          allow_hour12_override = EXCLUDED.allow_hour12_override,
          allow_theme_override = EXCLUDED.allow_theme_override,
          updated_at = p_now;
    ELSIF p_section = 'branding' THEN
      INSERT INTO tenancy.organization_brandings AS b (
        organization_id, display_name, legal_name, logo_alt, primary_color, secondary_color,
        accent_color, logo_light_url, logo_dark_url, favicon_url, terms_url, privacy_url, domain,
        support_email, created_at, updated_at
      )
      VALUES (
        p_organization_id,
        v_merged ->> 'display_name',
        v_merged ->> 'legal_name',
        v_merged ->> 'logo_alt',
        v_merged ->> 'primary',
        v_merged ->> 'secondary',
        v_merged ->> 'accent',
        v_merged ->> 'logo_light',
        v_merged ->> 'logo_dark',
        v_merged ->> 'favicon',
        v_merged ->> 'terms_url',
        v_merged ->> 'privacy_url',
        v_merged ->> 'domain',
        v_merged ->> 'support_email',
        p_now,
        p_now
      )
      ON CONFLICT (organization_id) DO UPDATE
      SET display_name = EXCLUDED.display_name,
          legal_name = EXCLUDED.legal_name,
          logo_alt = EXCLUDED.logo_alt,
          primary_color = EXCLUDED.primary_color,
          secondary_color = EXCLUDED.secondary_color,
          accent_color = EXCLUDED.accent_color,
          logo_light_url = EXCLUDED.logo_light_url,
          logo_dark_url = EXCLUDED.logo_dark_url,
          favicon_url = EXCLUDED.favicon_url,
          terms_url = EXCLUDED.terms_url,
          privacy_url = EXCLUDED.privacy_url,
          domain = EXCLUDED.domain,
          support_email = EXCLUDED.support_email,
          updated_at = p_now;
    ELSIF p_section = 'revenue' THEN
      INSERT INTO tenancy.organization_revenue_settings AS r (
        organization_id, low_day_threshold, gap_amber_percent, created_at, updated_at
      )
      VALUES (
        p_organization_id,
        (v_merged ->> 'low_day_threshold')::numeric,
        (v_merged ->> 'gap_amber_percent')::numeric,
        p_now,
        p_now
      )
      ON CONFLICT (organization_id) DO UPDATE
      SET low_day_threshold = EXCLUDED.low_day_threshold,
          gap_amber_percent = EXCLUDED.gap_amber_percent,
          updated_at = p_now;
    ELSE
      INSERT INTO tenancy.organization_security_policies AS s (
        organization_id, password_min_length, password_complexity, password_history, pin_length,
        lockout_threshold, lockout_minutes, access_token_minutes, refresh_token_days,
        idle_unlock_seconds, allow_pin_sign_in, created_at, updated_at
      )
      VALUES (
        p_organization_id,
        (v_merged ->> 'password_min_length')::smallint,
        (v_merged ->> 'password_complexity')::boolean,
        (v_merged ->> 'password_history')::smallint,
        (v_merged ->> 'pin_length')::smallint,
        (v_merged ->> 'lockout_threshold')::smallint,
        (v_merged ->> 'lockout_minutes')::smallint,
        (v_merged ->> 'access_token_minutes')::smallint,
        (v_merged ->> 'refresh_token_days')::smallint,
        (v_merged ->> 'idle_unlock_seconds')::integer,
        (v_merged ->> 'allow_pin_sign_in')::boolean,
        p_now,
        p_now
      )
      ON CONFLICT (organization_id) DO UPDATE
      SET password_min_length = EXCLUDED.password_min_length,
          password_complexity = EXCLUDED.password_complexity,
          password_history = EXCLUDED.password_history,
          pin_length = EXCLUDED.pin_length,
          lockout_threshold = EXCLUDED.lockout_threshold,
          lockout_minutes = EXCLUDED.lockout_minutes,
          access_token_minutes = EXCLUDED.access_token_minutes,
          refresh_token_days = EXCLUDED.refresh_token_days,
          idle_unlock_seconds = EXCLUDED.idle_unlock_seconds,
          allow_pin_sign_in = EXCLUDED.allow_pin_sign_in,
          updated_at = p_now;
    END IF;
    v_after := tenancy.settings_snapshot(p_section);
    IF p_section = 'revenue' THEN
      v_currency := tenancy.settings_document('localization') ->> 'currency';
      v_automatic := tenancy.settings_reason(
        p_section,
        CASE
          WHEN json_typeof(v_before) = 'object' THEN
            json_build_object(
              'lowDayThreshold',
              v_currency || ' ' || tenancy.fmt_money((v_before ->> 'lowDayThreshold')::numeric),
              'gapAmberPercent', v_before -> 'gapAmberPercent'
            )
          ELSE v_before
        END,
        json_build_object(
          'lowDayThreshold',
          v_currency || ' ' || tenancy.fmt_money((v_after ->> 'lowDayThreshold')::numeric),
          'gapAmberPercent', v_after -> 'gapAmberPercent'
        )
      );
    ELSE
      v_automatic := tenancy.settings_reason(p_section, v_before, v_after);
    END IF;
  END IF;

  v_final := tenancy.compose_reason(v_automatic, v_reason);
  v_version := tenancy.record_change(
    CASE WHEN p_section = 'revenue' THEN 'organization' ELSE p_section END,
    p_organization_id, NULL, v_before, v_after, v_final,
    'organization.settings.updated', p_section, v_before::jsonb,
    jsonb_build_object('value', v_after::jsonb, 'reason', v_final), p_now
  );
  RETURN ROW(p_organization_id, v_version, 'updated')::api.write_result;
END;
$$;
