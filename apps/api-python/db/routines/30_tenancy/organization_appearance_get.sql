-- api.organization_appearance_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_now timestamptz) RETURNS jsonb
-- Purpose: what every member's screens need: the organization name, settings version and business date, the branding colours, names and logo (a data URL or NULL), the actor's effective formats, theme, motion and font scale, and the wrong-PIN policy (clamped) the phone enforces offline.
-- Callers: TenancyRoutines.appearance; GetAppearance (GET /setup/appearance).
-- Reads: tenancy.organizations, tenancy.organization_logos, and what tenancy.business_date and tenancy.effective_settings read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC422 time_zone_invalid via tenancy.business_date, XC422 locale_invalid via tenancy.effective_settings, XC422 format_settings_invalid via tenancy.effective_settings, XC422 brand_names_required via tenancy.effective_settings, XC422 brand_colour_format via tenancy.effective_settings, XC422 brand_contrast via tenancy.effective_settings, XC422 brand_url_https via tenancy.effective_settings, XC422 brand_domain_invalid via tenancy.effective_settings, XC422 brand_support_email_invalid via tenancy.effective_settings.
-- Tests: tests/db/test_organization_routines.py, tests/api/test_appearance.py.

CREATE OR REPLACE FUNCTION api.organization_appearance_get(
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
  v_organization tenancy.organizations;
  v_effective jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  SELECT o.* INTO v_organization FROM tenancy.organizations AS o WHERE o.id = p_organization_id;
  v_effective := tenancy.effective_settings(p_actor_id);
  RETURN jsonb_build_object(
    'organization_name', v_organization.name,
    'settings_version', v_organization.settings_version,
    'business_date', tenancy.business_date(p_organization_id, p_now),
    'branding', jsonb_build_object(
      'display_name', v_effective -> 'branding' -> 'display_name',
      'logo_alt', v_effective -> 'branding' -> 'logo_alt',
      'primary', v_effective -> 'branding' -> 'primary',
      'secondary', v_effective -> 'branding' -> 'secondary',
      'accent', v_effective -> 'branding' -> 'accent',
      'logo', (
        SELECT 'data:' || g.content_type || ';base64,' || translate(encode(g.data, 'base64'), E'\n', '')
        FROM tenancy.organization_logos AS g
        WHERE g.organization_id = p_organization_id
      )
    ),
    'formats', v_effective -> 'formats',
    'theme_mode', v_effective -> 'theme_mode',
    'reduced_motion', v_effective -> 'reduced_motion',
    'font_scale', v_effective -> 'font_scale',
    'lockout_threshold', identity.pin_tries(),
    'lockout_minutes', v_effective -> 'security_policy' -> 'lockout_minutes',
    'idle_unlock_seconds', v_effective -> 'security_policy' -> 'idle_unlock_seconds'
  );
END;
$$;
