-- Custom roles and person delete. tenancy.roles gains built_in, true exactly for the four catalogue role names (generated, so no insert can get it wrong), and version, the concurrency token of a role edit. tenancy.role_grants holds a custom role's permissions, dependencies expanded; a built-in role keeps reading tenancy.role_defaults. The service role may rename, re-grant and delete roles (api.access_role_update, api.access_role_delete) and may delete a membership, its role row, its preferences and an account that belongs nowhere else (api.people_delete), which the foreign keys stop while anything refers to them. tenancy.forget_contact_history, owned by the migration owner because the service role may only add history rows, clears the email and mobile number from the people and sign-in history of a person deleted from the current organization (names stay); it touches nothing while the person still has a membership there, and calls only built-ins and tenancy.contactless_snapshot. The change log gains the roles section.

SET LOCAL lock_timeout = '10s';

ALTER TABLE tenancy.roles
  ADD COLUMN built_in boolean GENERATED ALWAYS AS (
    lower(name) IN ('owner', 'office admin', 'fleet manager', 'revenue clerk')
  ) STORED,
  ADD COLUMN version bigint NOT NULL DEFAULT 1,
  ADD CONSTRAINT ck_roles_version CHECK (version >= 1);

CREATE TABLE tenancy.role_grants (
  organization_id uuid NOT NULL,
  role_id uuid NOT NULL,
  permission text NOT NULL,
  CONSTRAINT pk_role_grants PRIMARY KEY (organization_id, role_id, permission),
  CONSTRAINT fk_role_grants_organization FOREIGN KEY (organization_id)
    REFERENCES tenancy.organizations (id),
  CONSTRAINT fk_role_grants_role FOREIGN KEY (organization_id, role_id)
    REFERENCES tenancy.roles (organization_id, id),
  CONSTRAINT fk_role_grants_permission FOREIGN KEY (permission)
    REFERENCES tenancy.permissions (key)
);

ALTER TABLE tenancy.role_grants ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant_isolation ON tenancy.role_grants TO xcode_api_executor
  USING (organization_id = tenancy.current_organization())
  WITH CHECK (organization_id = tenancy.current_organization());

REVOKE ALL ON tenancy.role_grants FROM xcode_api_executor;
GRANT SELECT, INSERT, DELETE ON tenancy.role_grants TO xcode_api_executor;
GRANT UPDATE, DELETE ON tenancy.roles TO xcode_api_executor;
GRANT DELETE ON tenancy.memberships, tenancy.person_roles, tenancy.user_preferences, identity.users
  TO xcode_api_executor;

CREATE FUNCTION tenancy.contactless_snapshot(p_snapshot text)
RETURNS text
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
    WHEN p_snapshot IS NULL OR json_typeof(p_snapshot::json) <> 'object' THEN p_snapshot
    ELSE (
      SELECT '{' || coalesce(string_agg(
               to_json(e.key)::text || ':' || CASE
                 WHEN e.key IN ('Email', 'PhoneNumber', 'email', 'phone_number') THEN 'null'
                 ELSE e.value::text
               END,
               ',' ORDER BY e.ord), '') || '}'
      FROM json_each(p_snapshot::json) WITH ORDINALITY AS e (key, value, ord)
    )
  END;
$$;

REVOKE ALL ON FUNCTION tenancy.contactless_snapshot(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.contactless_snapshot(text) TO xcode_api_executor;

CREATE FUNCTION tenancy.forget_contact_history(p_organization_id uuid, p_user_id uuid)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  IF p_organization_id IS NULL
     OR p_organization_id IS DISTINCT FROM tenancy.current_organization()
     OR EXISTS (
       SELECT 1 FROM tenancy.memberships AS m
       WHERE m.organization_id = p_organization_id AND m.user_id = p_user_id
     ) THEN
    RETURN;
  END IF;
  UPDATE tenancy.change_log AS c
  SET before = tenancy.contactless_snapshot(c.before),
      after = tenancy.contactless_snapshot(c.after)
  WHERE c.organization_id = p_organization_id
    AND c.entity_id = p_user_id
    AND c.section IN ('people', 'signIn');
  UPDATE tenancy.audit_events AS a
  SET before = tenancy.contactless_snapshot(a.before::text)::jsonb,
      after = tenancy.contactless_snapshot(a.after::text)::jsonb
  WHERE a.organization_id = p_organization_id
    AND a.entity = p_user_id::text;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.forget_contact_history(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.forget_contact_history(uuid, uuid) TO xcode_api_executor;

ALTER TABLE tenancy.change_log
  DROP CONSTRAINT ck_change_log_section,
  ADD CONSTRAINT ck_change_log_section CHECK (section IN (
    'companies', 'vehicles', 'investment', 'expenses', 'recurring', 'people', 'revenue',
    'organization', 'businessDate', 'localization', 'branding', 'securityPolicy', 'logo',
    'signIn', 'pettycash', 'centralexpenses', 'reports', 'roles'
  ));
