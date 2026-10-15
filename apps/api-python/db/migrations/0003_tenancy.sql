-- Tenancy tables: organizations, memberships, organization settings, user_preferences, change_log, audit_events; session and contrast functions.

SET LOCAL lock_timeout = '10s';

-- Transaction-local session settings; NULL when unset, so every tenant policy matches nothing.
-- No SET search_path: every name is qualified, and the planner can inline them into policies.
CREATE FUNCTION tenancy.current_organization() RETURNS uuid
LANGUAGE sql STABLE
AS $$ SELECT nullif(pg_catalog.current_setting('xcode.organization_id', true), '')::pg_catalog.uuid $$;

CREATE FUNCTION tenancy.current_actor() RETURNS uuid
LANGUAGE sql STABLE
AS $$ SELECT nullif(pg_catalog.current_setting('xcode.actor_id', true), '')::pg_catalog.uuid $$;

CREATE FUNCTION tenancy.current_request() RETURNS text
LANGUAGE sql STABLE
AS $$ SELECT nullif(pg_catalog.current_setting('xcode.request_id', true), '') $$;

-- WCAG 2 contrast ratio of two #RRGGBB colours (sRGB linearisation, relative luminance),
-- truncated to two decimals so that ">= 4.5" holds exactly when the unrounded ratio does.
-- NULL when either argument is not #RRGGBB (the format CHECK reports that case).
CREATE FUNCTION tenancy.check_contrast(p_hex text, p_against text) RETURNS numeric
LANGUAGE sql IMMUTABLE STRICT PARALLEL SAFE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT trunc(((max(lum.l) + 0.05) / (min(lum.l) + 0.05))::numeric, 2)
  FROM (
    SELECT 0.2126 * rgb.c[1] + 0.7152 * rgb.c[2] + 0.0722 * rgb.c[3] AS l
    FROM (
      SELECT ARRAY(
        SELECT CASE
                 WHEN channel.v <= 0.04045 THEN channel.v / 12.92
                 ELSE power((channel.v + 0.055) / 1.055, 2.4)
               END
        FROM (
          SELECT ('x' || substr(h, 2 * k, 2))::bit(8)::integer / 255.0::double precision AS v, k
          FROM generate_series(1, 3) AS k
        ) AS channel
        ORDER BY channel.k
      ) AS c
      FROM unnest(ARRAY[p_hex, p_against]) AS h
    ) AS rgb
  ) AS lum
  WHERE p_hex ~ '^#[0-9a-fA-F]{6}$' AND p_against ~ '^#[0-9a-fA-F]{6}$'
$$;

REVOKE ALL ON FUNCTION tenancy.current_organization(), tenancy.current_actor(),
  tenancy.current_request(), tenancy.check_contrast(text, text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.current_organization(), tenancy.current_actor(),
  tenancy.current_request(), tenancy.check_contrast(text, text) TO xcode_api_executor;

CREATE TABLE tenancy.organizations (
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  slug text NOT NULL,
  name text NOT NULL,
  business_date date,
  settings_version bigint NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_organizations PRIMARY KEY (id),
  CONSTRAINT uq_organizations_slug UNIQUE (slug),
  CONSTRAINT ck_organizations_slug CHECK (
    slug ~ '^[a-z0-9]+(-[a-z0-9]+)*$' AND char_length(slug) <= 100
  ),
  CONSTRAINT ck_organizations_name CHECK (char_length(name) BETWEEN 1 AND 200)
);

CREATE TABLE tenancy.memberships (
  organization_id uuid NOT NULL,
  user_id uuid NOT NULL,
  first_name text NOT NULL,
  last_name text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  approval_limit numeric(14,2),
  version bigint NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_memberships PRIMARY KEY (organization_id, user_id),
  CONSTRAINT fk_memberships_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_memberships_user FOREIGN KEY (user_id) REFERENCES identity.users (id),
  CONSTRAINT ck_memberships_first_name CHECK (char_length(first_name) BETWEEN 1 AND 100),
  CONSTRAINT ck_memberships_last_name CHECK (char_length(last_name) BETWEEN 1 AND 100),
  CONSTRAINT ck_memberships_approval_limit CHECK (approval_limit >= 0)
);

CREATE UNIQUE INDEX uq_memberships_active_user ON tenancy.memberships (user_id) WHERE active;
CREATE INDEX ix_memberships_people_order
  ON tenancy.memberships (organization_id, last_name, first_name, user_id);

CREATE TABLE tenancy.organization_localizations (
  organization_id uuid NOT NULL,
  locale text NOT NULL DEFAULT 'en-GB',
  time_zone text NOT NULL DEFAULT 'Africa/Nairobi',
  date_pattern text NOT NULL DEFAULT 'medium',
  hour12 boolean NOT NULL DEFAULT false,
  first_day_of_week smallint NOT NULL DEFAULT 1,
  week_numbering text NOT NULL DEFAULT 'iso8601',
  currency text NOT NULL DEFAULT 'KES',
  use_grouping boolean NOT NULL DEFAULT true,
  number_decimals smallint NOT NULL DEFAULT 2,
  allow_locale_override boolean NOT NULL DEFAULT true,
  allow_time_zone_override boolean NOT NULL DEFAULT false,
  allow_hour12_override boolean NOT NULL DEFAULT true,
  allow_theme_override boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_localizations PRIMARY KEY (organization_id),
  CONSTRAINT fk_localizations_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT ck_localizations_locale CHECK (locale ~ '^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$'),
  CONSTRAINT ck_localizations_date_pattern CHECK (date_pattern IN ('short', 'medium', 'long')),
  CONSTRAINT ck_localizations_first_day_of_week CHECK (first_day_of_week BETWEEN 0 AND 6),
  CONSTRAINT ck_localizations_week_numbering CHECK (week_numbering IN ('iso8601', 'local')),
  CONSTRAINT ck_localizations_currency CHECK (currency ~ '^[A-Z]{3}$'),
  CONSTRAINT ck_localizations_number_decimals CHECK (number_decimals BETWEEN 0 AND 2)
);

CREATE TABLE tenancy.organization_brandings (
  organization_id uuid NOT NULL,
  display_name text NOT NULL DEFAULT 'XCODE',
  legal_name text NOT NULL DEFAULT 'XCODE',
  logo_alt text NOT NULL DEFAULT 'XCODE',
  primary_color text NOT NULL DEFAULT '#1D5FD6',
  secondary_color text NOT NULL DEFAULT '#14213D',
  accent_color text NOT NULL DEFAULT '#1E6B3A',
  logo_light_url text,
  logo_dark_url text,
  favicon_url text,
  terms_url text,
  privacy_url text,
  domain text,
  support_email text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_brandings PRIMARY KEY (organization_id),
  CONSTRAINT fk_brandings_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT ck_brandings_display_name CHECK (char_length(display_name) BETWEEN 1 AND 100),
  CONSTRAINT ck_brandings_legal_name CHECK (char_length(legal_name) BETWEEN 1 AND 200),
  CONSTRAINT ck_brandings_logo_alt CHECK (char_length(logo_alt) BETWEEN 1 AND 200),
  CONSTRAINT ck_brandings_primary_color CHECK (primary_color ~ '^#[0-9a-fA-F]{6}$'),
  CONSTRAINT ck_brandings_secondary_color CHECK (secondary_color ~ '^#[0-9a-fA-F]{6}$'),
  CONSTRAINT ck_brandings_accent_color CHECK (accent_color ~ '^#[0-9a-fA-F]{6}$'),
  CONSTRAINT ck_brandings_contrast CHECK (
    tenancy.check_contrast(primary_color, '#FFFFFF') >= 4.5
    AND tenancy.check_contrast(primary_color, '#F6F3EC') >= 4.5
    AND tenancy.check_contrast(secondary_color, '#FFFFFF') >= 4.5
    AND tenancy.check_contrast(secondary_color, '#F6F3EC') >= 4.5
    AND tenancy.check_contrast(accent_color, '#FFFFFF') >= 4.5
    AND tenancy.check_contrast(accent_color, '#F6F3EC') >= 4.5
  ),
  CONSTRAINT ck_brandings_logo_light_url CHECK (
    logo_light_url ~ '^https://' AND char_length(logo_light_url) <= 2048
  ),
  CONSTRAINT ck_brandings_logo_dark_url CHECK (
    logo_dark_url ~ '^https://' AND char_length(logo_dark_url) <= 2048
  ),
  CONSTRAINT ck_brandings_favicon_url CHECK (
    favicon_url ~ '^https://' AND char_length(favicon_url) <= 2048
  ),
  CONSTRAINT ck_brandings_terms_url CHECK (
    terms_url ~ '^https://' AND char_length(terms_url) <= 2048
  ),
  CONSTRAINT ck_brandings_privacy_url CHECK (
    privacy_url ~ '^https://' AND char_length(privacy_url) <= 2048
  ),
  CONSTRAINT ck_brandings_domain CHECK (
    char_length(domain) <= 253
    AND domain ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'
  ),
  CONSTRAINT ck_brandings_support_email CHECK (
    char_length(support_email) <= 320 AND strpos(support_email, '@') > 0
  )
);

CREATE TABLE tenancy.organization_logos (
  organization_id uuid NOT NULL,
  content_type text NOT NULL,
  data bytea NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_logos PRIMARY KEY (organization_id),
  CONSTRAINT fk_logos_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT ck_logos_content_type CHECK (content_type IN ('image/png', 'image/jpeg', 'image/webp')),
  CONSTRAINT ck_logos_size CHECK (octet_length(data) BETWEEN 1 AND 262144),
  CONSTRAINT ck_logos_signature CHECK (
    (content_type = 'image/png' AND substring(data FROM 1 FOR 8) = '\x89504e470d0a1a0a'::bytea)
    OR (content_type = 'image/jpeg' AND substring(data FROM 1 FOR 3) = '\xffd8ff'::bytea)
    OR (
      content_type = 'image/webp'
      AND substring(data FROM 1 FOR 4) = '\x52494646'::bytea
      AND substring(data FROM 9 FOR 4) = '\x57454250'::bytea
    )
  )
);

CREATE TABLE tenancy.organization_security_policies (
  organization_id uuid NOT NULL,
  password_min_length smallint NOT NULL DEFAULT 12,
  password_complexity boolean NOT NULL DEFAULT true,
  password_history smallint NOT NULL DEFAULT 5,
  pin_length smallint NOT NULL DEFAULT 4,
  lockout_threshold smallint NOT NULL DEFAULT 5,
  lockout_minutes smallint NOT NULL DEFAULT 15,
  access_token_minutes smallint NOT NULL DEFAULT 10,
  refresh_token_days smallint NOT NULL DEFAULT 30,
  idle_unlock_seconds integer NOT NULL DEFAULT 300,
  allow_pin_sign_in boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_security_policies PRIMARY KEY (organization_id),
  CONSTRAINT fk_security_policies_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT ck_security_policies_password_min_length CHECK (password_min_length BETWEEN 12 AND 128),
  CONSTRAINT ck_security_policies_password_history CHECK (password_history BETWEEN 0 AND 24),
  CONSTRAINT ck_security_policies_pin_length CHECK (pin_length BETWEEN 4 AND 8),
  CONSTRAINT ck_security_policies_lockout_threshold CHECK (lockout_threshold BETWEEN 3 AND 10),
  CONSTRAINT ck_security_policies_lockout_minutes CHECK (lockout_minutes BETWEEN 1 AND 60),
  CONSTRAINT ck_security_policies_access_token_minutes CHECK (access_token_minutes BETWEEN 1 AND 15),
  CONSTRAINT ck_security_policies_refresh_token_days CHECK (refresh_token_days BETWEEN 1 AND 90),
  CONSTRAINT ck_security_policies_idle_unlock_seconds CHECK (idle_unlock_seconds BETWEEN 30 AND 3600),
  CONSTRAINT ck_security_policies_allow_pin_sign_in CHECK (allow_pin_sign_in)
);

CREATE TABLE tenancy.user_preferences (
  organization_id uuid NOT NULL,
  user_id uuid NOT NULL,
  locale text,
  time_zone text,
  hour12 boolean,
  theme_mode text,
  reduced_motion boolean NOT NULL DEFAULT false,
  font_scale double precision NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT pk_user_preferences PRIMARY KEY (organization_id, user_id),
  CONSTRAINT fk_user_preferences_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_user_preferences_membership FOREIGN KEY (organization_id, user_id)
    REFERENCES tenancy.memberships (organization_id, user_id),
  CONSTRAINT ck_user_preferences_locale CHECK (locale ~ '^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$'),
  CONSTRAINT ck_user_preferences_theme_mode CHECK (theme_mode IN ('light', 'dark', 'system')),
  CONSTRAINT ck_user_preferences_font_scale CHECK (font_scale BETWEEN 1 AND 3)
);

CREATE TABLE tenancy.change_log (
  organization_id uuid NOT NULL,
  version bigint NOT NULL,
  id uuid NOT NULL DEFAULT gen_random_uuid(),
  section text NOT NULL,
  entity_id uuid NOT NULL,
  vehicle_id uuid,
  actor_id uuid NOT NULL,
  reason text NOT NULL,
  occurred_at timestamptz NOT NULL,
  effective_from timestamptz,
  before text,
  after text,
  request_id text NOT NULL,
  CONSTRAINT pk_change_log PRIMARY KEY (organization_id, version),
  CONSTRAINT uq_change_log_id UNIQUE (organization_id, id),
  CONSTRAINT fk_change_log_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_change_log_actor FOREIGN KEY (organization_id, actor_id)
    REFERENCES tenancy.memberships (organization_id, user_id),
  CONSTRAINT ck_change_log_version CHECK (version >= 1),
  CONSTRAINT ck_change_log_section CHECK (section IN (
    'companies', 'vehicles', 'investment', 'expenses', 'recurring', 'people', 'revenue',
    'organization', 'businessDate', 'localization', 'branding', 'securityPolicy', 'logo'
  )),
  CONSTRAINT ck_change_log_vehicle CHECK (
    (section IN ('vehicles', 'investment', 'revenue')) = (vehicle_id IS NOT NULL)
  ),
  CONSTRAINT ck_change_log_reason CHECK (char_length(reason) BETWEEN 1 AND 500),
  CONSTRAINT ck_change_log_request_id CHECK (char_length(request_id) <= 128)
);

CREATE INDEX ix_change_log_occurred ON tenancy.change_log (organization_id, occurred_at);
CREATE INDEX ix_change_log_section_vehicle ON tenancy.change_log (organization_id, section, vehicle_id);
CREATE INDEX ix_change_log_actor ON tenancy.change_log (organization_id, actor_id);

CREATE TABLE tenancy.audit_events (
  organization_id uuid NOT NULL,
  id bigint GENERATED ALWAYS AS IDENTITY,
  actor_id uuid NOT NULL,
  action text NOT NULL,
  entity text NOT NULL,
  before jsonb,
  after jsonb,
  occurred_at timestamptz NOT NULL,
  request_id text NOT NULL,
  CONSTRAINT pk_audit_events PRIMARY KEY (organization_id, id),
  CONSTRAINT fk_audit_events_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_audit_events_actor FOREIGN KEY (organization_id, actor_id)
    REFERENCES tenancy.memberships (organization_id, user_id),
  CONSTRAINT ck_audit_events_action CHECK (char_length(action) <= 100),
  CONSTRAINT ck_audit_events_entity CHECK (char_length(entity) <= 200),
  CONSTRAINT ck_audit_events_request_id CHECK (char_length(request_id) <= 128)
);

CREATE INDEX ix_audit_events_occurred ON tenancy.audit_events (organization_id, occurred_at);

CREATE TRIGGER touch_updated_at BEFORE UPDATE ON tenancy.organizations
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();
CREATE TRIGGER touch_updated_at BEFORE UPDATE ON tenancy.memberships
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();
CREATE TRIGGER touch_updated_at BEFORE UPDATE ON tenancy.organization_localizations
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();
CREATE TRIGGER touch_updated_at BEFORE UPDATE ON tenancy.organization_brandings
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();
CREATE TRIGGER touch_updated_at BEFORE UPDATE ON tenancy.organization_logos
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();
CREATE TRIGGER touch_updated_at BEFORE UPDATE ON tenancy.organization_security_policies
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();
CREATE TRIGGER touch_updated_at BEFORE UPDATE ON tenancy.user_preferences
  FOR EACH ROW EXECUTE FUNCTION ops.touch_updated_at();

ALTER TABLE tenancy.organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenancy.memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenancy.organization_localizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenancy.organization_brandings ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenancy.organization_logos ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenancy.organization_security_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenancy.user_preferences ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenancy.change_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenancy.audit_events ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON tenancy.organizations TO xcode_api_executor
  USING (id = tenancy.current_organization())
  WITH CHECK (id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON tenancy.memberships TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON tenancy.organization_localizations TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON tenancy.organization_brandings TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON tenancy.organization_logos TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON tenancy.organization_security_policies TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON tenancy.user_preferences TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON tenancy.change_log TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());
CREATE POLICY tenant_isolation ON tenancy.audit_events TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());

REVOKE ALL ON tenancy.organizations, tenancy.memberships, tenancy.organization_localizations,
  tenancy.organization_brandings, tenancy.organization_logos,
  tenancy.organization_security_policies, tenancy.user_preferences, tenancy.change_log,
  tenancy.audit_events FROM xcode_api_executor;
GRANT SELECT, INSERT, UPDATE ON tenancy.organizations, tenancy.memberships,
  tenancy.organization_localizations, tenancy.organization_brandings,
  tenancy.organization_security_policies, tenancy.user_preferences TO xcode_api_executor;
GRANT SELECT, INSERT, UPDATE, DELETE ON tenancy.organization_logos TO xcode_api_executor;
-- Audit trails: append-only by privilege.
GRANT SELECT, INSERT ON tenancy.change_log, tenancy.audit_events TO xcode_api_executor;
REVOKE UPDATE, DELETE ON tenancy.change_log, tenancy.audit_events FROM xcode_api_executor;
