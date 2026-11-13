-- Reverse 0022: drop the role and person delete routines, the custom role permissions, built_in and version, and take back the grants. A custom role would lose its permissions, so the reversal refuses while one exists; deleted people stay deleted and the change log keeps what they held.

SET LOCAL lock_timeout = '10s';

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM tenancy.roles WHERE NOT built_in) THEN
    RAISE EXCEPTION 'tenancy.roles holds custom roles; 0022 cannot be reversed';
  END IF;
  IF EXISTS (SELECT 1 FROM tenancy.change_log WHERE section = 'roles') THEN
    RAISE EXCEPTION 'tenancy.change_log holds role history; 0022 cannot be reversed';
  END IF;
END;
$$;

ALTER TABLE tenancy.change_log
  DROP CONSTRAINT ck_change_log_section,
  ADD CONSTRAINT ck_change_log_section CHECK (section IN (
    'companies', 'vehicles', 'investment', 'expenses', 'recurring', 'people', 'revenue',
    'organization', 'businessDate', 'localization', 'branding', 'securityPolicy', 'logo',
    'signIn', 'pettycash', 'centralexpenses', 'reports'
  ));

DROP FUNCTION IF EXISTS api.people_delete(uuid, uuid, text, uuid, timestamptz);
DROP FUNCTION IF EXISTS api.access_role_create(uuid, uuid, text, text, text[], timestamptz);
DROP FUNCTION IF EXISTS api.access_role_update(uuid, uuid, text, uuid, text, text[], bigint, timestamptz);
DROP FUNCTION IF EXISTS api.access_role_delete(uuid, uuid, text, uuid, timestamptz);
DROP FUNCTION IF EXISTS tenancy.save_role(uuid, text, text[], bigint, timestamptz);
DROP FUNCTION IF EXISTS tenancy.role_document(uuid);
DROP FUNCTION IF EXISTS tenancy.refuse_role_in_use(tenancy.roles);
DROP FUNCTION IF EXISTS tenancy.forget_contact_history(uuid, uuid);
DROP FUNCTION IF EXISTS tenancy.contactless_snapshot(text);

REVOKE DELETE ON tenancy.memberships, tenancy.person_roles, tenancy.user_preferences, identity.users
  FROM xcode_api_executor;
REVOKE UPDATE, DELETE ON tenancy.roles FROM xcode_api_executor;

DROP TABLE tenancy.role_grants;

ALTER TABLE tenancy.roles
  DROP CONSTRAINT ck_roles_version,
  DROP COLUMN version,
  DROP COLUMN built_in;
