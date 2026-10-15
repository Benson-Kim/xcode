-- api.organization_settings_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_now timestamptz) RETURNS jsonb
-- Purpose: the organization settings screen: the organization (with the held business date and settings version), the stored localization, branding, security policy and revenue settings (defaults for a missing row), the effective business date, today's calendar date in the organization zone, and the actor's effective settings.
-- Callers: TenancyRoutines.organization_settings; GetOrganizationSettings (GET /setup/organization/settings).
-- Reads: tenancy.organizations, and what tenancy.settings_document, tenancy.business_date, tenancy.calendar_date and tenancy.effective_settings read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 time_zone_invalid via tenancy.calendar_date, XC422 locale_invalid via tenancy.effective_settings, XC422 format_settings_invalid via tenancy.effective_settings, XC422 brand_names_required via tenancy.effective_settings, XC422 brand_colour_format via tenancy.effective_settings, XC422 brand_contrast via tenancy.effective_settings, XC422 brand_url_https via tenancy.effective_settings, XC422 brand_domain_invalid via tenancy.effective_settings, XC422 brand_support_email_invalid via tenancy.effective_settings.
-- Tests: tests/db/test_organization_routines.py, tests/api/test_organization_settings.py.

CREATE OR REPLACE FUNCTION api.organization_settings_get(
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
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'organization.manage');
  SELECT o.* INTO v_organization FROM tenancy.organizations AS o WHERE o.id = p_organization_id;
  RETURN jsonb_build_object(
    'organization', jsonb_build_object(
      'id', v_organization.id,
      'slug', v_organization.slug,
      'name', v_organization.name,
      'business_date', v_organization.business_date,
      'settings_version', v_organization.settings_version
    ),
    'localization', tenancy.settings_document('localization'),
    'branding', tenancy.settings_document('branding'),
    'security_policy', tenancy.settings_document('securityPolicy'),
    'effective_business_date', coalesce(
      v_organization.business_date, tenancy.calendar_date(p_organization_id, p_now)
    ),
    'calendar_date', tenancy.calendar_date(p_organization_id, p_now),
    'effective', tenancy.effective_settings(p_actor_id),
    'revenue', tenancy.settings_document('revenue')
  );
END;
$$;
