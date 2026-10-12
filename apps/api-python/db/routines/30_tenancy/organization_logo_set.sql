-- api.organization_logo_set(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_content_type text, p_data bytea, p_reason text, p_now timestamptz) RETURNS api.write_result
-- Purpose: store the organization's logo (PNG, JPEG or WebP, 1 byte to 256 KiB, bytes carrying the signature of the declared type), replacing any earlier one, and log its shape.
-- Callers: TenancyRoutines.save_logo; UpdateOrganizationLogo (PUT /setup/organization/logo; the service decodes the data URL first).
-- Reads: tenancy.organizations, tenancy.organization_logos. Writes: tenancy.organization_logos, and through tenancy.record_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 reason_length via tenancy.check_typed_reason, XC422 logo_type, XC422 logo_too_large, XC422 logo_signature.
-- Tests: tests/db/test_organization_routines.py, tests/api/test_organization_settings.py.

CREATE OR REPLACE FUNCTION api.organization_logo_set(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_content_type text,
  p_data bytea,
  p_reason text,
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
  v_before json;
  v_after json;
  v_final text;
  v_version bigint;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'organization.manage');
  v_reason := tenancy.check_typed_reason(p_reason);
  IF p_content_type IS NULL OR p_content_type NOT IN ('image/png', 'image/jpeg', 'image/webp') THEN
    PERFORM tenancy.refuse('logo_type', 'XC422');
  END IF;
  IF p_data IS NULL OR octet_length(p_data) NOT BETWEEN 1 AND 262144 THEN
    PERFORM tenancy.refuse('logo_too_large', 'XC422');
  END IF;
  IF NOT (CASE p_content_type
            WHEN 'image/png' THEN substring(p_data FROM 1 FOR 8) = '\x89504e470d0a1a0a'::bytea
            WHEN 'image/jpeg' THEN substring(p_data FROM 1 FOR 3) = '\xffd8ff'::bytea
            ELSE substring(p_data FROM 1 FOR 4) = '\x52494646'::bytea
                 AND substring(p_data FROM 9 FOR 4) = '\x57454250'::bytea
          END) THEN
    PERFORM tenancy.refuse('logo_signature', 'XC422');
  END IF;

  PERFORM 1 FROM tenancy.organizations AS o WHERE o.id = p_organization_id FOR UPDATE;
  v_before := tenancy.logo_snapshot();
  INSERT INTO tenancy.organization_logos (organization_id, content_type, data, updated_at)
  VALUES (p_organization_id, p_content_type, p_data, p_now)
  ON CONFLICT (organization_id) DO UPDATE
  SET content_type = EXCLUDED.content_type, data = EXCLUDED.data, updated_at = p_now;
  v_after := tenancy.logo_snapshot();
  v_final := tenancy.compose_reason('Uploaded a new logo', v_reason);
  v_version := tenancy.record_change(
    'logo', p_organization_id, NULL, v_before, v_after, v_final,
    'organization.settings.updated', 'logo', v_before::jsonb,
    jsonb_build_object('value', v_after::jsonb, 'reason', v_final), p_now
  );
  RETURN ROW(p_organization_id, v_version, 'updated')::api.write_result;
END;
$$;
