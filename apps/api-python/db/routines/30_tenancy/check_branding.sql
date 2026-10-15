-- tenancy.check_branding(p_document jsonb) RETURNS void
-- Purpose: validate a branding document (document keys, values already strings or null): the names and logo text non-blank within their lengths, each colour a six-digit hex colour with WCAG AA contrast (4.5:1) against #FFFFFF and #F6F3EC, https URLs of at most 2048 characters (the scheme in any letter case), a host name as .NET's Uri.CheckHostName accepts it (letters in either case, digits, hyphens inside a label, underscores, non-ASCII letters, one or more labels, an optional trailing dot, at most 253 characters), a support email.
-- Callers: api.organization_settings_set (the merged section), tenancy.effective_settings (the stored section, on every read).
-- Reads: nothing (tenancy.check_contrast is pure). Writes: nothing.
-- Raises: XC422 brand_names_required, XC422 brand_colour_format, XC422 brand_contrast, XC422 brand_url_https, XC422 brand_domain_invalid, XC422 brand_support_email_invalid.
-- Tests: tests/db/test_organization_routines.py.

CREATE OR REPLACE FUNCTION tenancy.check_branding(p_document jsonb)
RETURNS void
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_colour text;
  v_url text;
BEGIN
  IF tenancy.trim_text(p_document ->> 'display_name') IS NULL
     OR char_length(p_document ->> 'display_name') > 100
     OR tenancy.trim_text(p_document ->> 'legal_name') IS NULL
     OR char_length(p_document ->> 'legal_name') > 200
     OR tenancy.trim_text(p_document ->> 'logo_alt') IS NULL
     OR char_length(p_document ->> 'logo_alt') > 200 THEN
    PERFORM tenancy.refuse('brand_names_required', 'XC422');
  END IF;
  FOREACH v_colour IN ARRAY ARRAY[
    p_document ->> 'primary', p_document ->> 'secondary', p_document ->> 'accent'
  ] LOOP
    IF coalesce(v_colour !~ '^#[0-9a-fA-F]{6}$', true) THEN
      PERFORM tenancy.refuse('brand_colour_format', 'XC422');
    END IF;
    IF tenancy.check_contrast(v_colour, '#FFFFFF') < 4.5
       OR tenancy.check_contrast(v_colour, '#F6F3EC') < 4.5 THEN
      PERFORM tenancy.refuse('brand_contrast', 'XC422');
    END IF;
  END LOOP;
  FOREACH v_url IN ARRAY ARRAY[
    p_document ->> 'logo_light', p_document ->> 'logo_dark', p_document ->> 'favicon',
    p_document ->> 'terms_url', p_document ->> 'privacy_url'
  ] LOOP
    IF v_url IS NOT NULL
       AND (char_length(v_url) > 2048 OR v_url !~* '^https://[^/?#[:space:]]+([/?#][^[:space:]]*)?$') THEN
      PERFORM tenancy.refuse('brand_url_https', 'XC422');
    END IF;
  END LOOP;
  IF p_document ->> 'domain' IS NOT NULL
     AND (char_length(p_document ->> 'domain') > 253
          OR (p_document ->> 'domain')
             !~ '^[A-Za-z0-9_\u00a1-\uffff][A-Za-z0-9_\u00a1-\uffff-]*(\.[A-Za-z0-9_\u00a1-\uffff][A-Za-z0-9_\u00a1-\uffff-]*)*\.?$') THEN
    PERFORM tenancy.refuse('brand_domain_invalid', 'XC422');
  END IF;
  IF p_document ->> 'support_email' IS NOT NULL
     AND (char_length(p_document ->> 'support_email') > 320
          OR (p_document ->> 'support_email') !~ '^[^@[:space:]]+@[^@[:space:]]+$') THEN
    PERFORM tenancy.refuse('brand_support_email_invalid', 'XC422');
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.check_branding(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.check_branding(jsonb) TO xcode_api_executor;
