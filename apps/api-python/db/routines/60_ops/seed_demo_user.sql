-- ops.seed_demo_user(p_organization_id uuid, p_owner_id uuid, p_request_id text, p_email text, p_phone text, p_role text, p_company_id uuid, p_pin_hash text, p_at timestamptz) RETURNS uuid
-- Purpose: make sure one demo login exists and is active in the organization, adding only what is missing: the Owner (p_owner_id NULL) by plain rows, everyone else through api.people_create as that Owner; the PIN hash is set only on an account this call created, and a removed account is revived with its sessions ended.
-- Callers: api.ops_seed_demo.
-- Reads: identity.users, tenancy.memberships, tenancy.roles, tenancy.person_roles, tenancy.data_scopes, tenancy.data_scope_companies. Writes: identity.users, identity.trusted_devices, identity.refresh_tokens, tenancy.memberships, tenancy.person_roles, tenancy.data_scopes, and what api.people_create writes.
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py.
-- The organization setting must already name p_organization_id. A revenue clerk (p_company_id given) is scoped to that company; every other login sees all companies.

CREATE OR REPLACE FUNCTION ops.seed_demo_user(
  p_organization_id uuid,
  p_owner_id uuid,
  p_request_id text,
  p_email text,
  p_phone text,
  p_role text,
  p_company_id uuid,
  p_pin_hash text,
  p_at timestamptz
)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_parts text[] := array_remove(string_to_array(split_part(p_email, '@', 1), '.'), '');
  v_first_name text := initcap(coalesce(v_parts[1], 'New'));
  v_last_name text := initcap(coalesce(v_parts[2], 'Member'));
  v_user identity.users;
  v_created boolean := false;
BEGIN
  SELECT u.* INTO v_user FROM identity.users AS u WHERE u.email = p_email;

  IF v_user.id IS NULL THEN
    v_created := true;
    IF p_owner_id IS NULL THEN
      INSERT INTO identity.users (email, phone_number, status, created_at, updated_at)
      VALUES (p_email, p_phone, 'active', p_at, p_at)
      RETURNING * INTO v_user;
    ELSE
      PERFORM api.people_create(
        p_owner_id, p_organization_id, p_request_id, v_first_name, v_last_name, p_email, p_phone,
        p_role,
        CASE WHEN p_company_id IS NULL THEN 'all' ELSE 'companies' END,
        CASE WHEN p_company_id IS NULL THEN '{}'::uuid[] ELSE ARRAY[p_company_id] END,
        '{}'::uuid[], tenancy.role_permissions(p_role), NULL, NULL, NULL, NULL, p_at
      );
      SELECT u.* INTO v_user FROM identity.users AS u WHERE u.email = p_email;
    END IF;
  ELSIF v_user.status <> 'active' THEN
    UPDATE identity.users
    SET status = 'active', security_version = security_version + 1
    WHERE id = v_user.id;
    PERFORM identity.revoke_devices(v_user.id);
    PERFORM identity.revoke_tokens(v_user.id);
    PERFORM identity.touch_version(v_user.id);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM tenancy.memberships AS m
    WHERE m.organization_id = p_organization_id AND m.user_id = v_user.id
  ) THEN
    INSERT INTO tenancy.memberships (
      organization_id, user_id, first_name, last_name, active, created_at, updated_at
    )
    VALUES (p_organization_id, v_user.id, v_first_name, v_last_name, true, p_at, p_at);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM tenancy.person_roles AS pr
    WHERE pr.organization_id = p_organization_id AND pr.user_id = v_user.id
  ) THEN
    INSERT INTO tenancy.person_roles (organization_id, user_id, role_id, updated_at)
    SELECT p_organization_id, v_user.id, r.id, p_at
    FROM tenancy.roles AS r
    WHERE r.organization_id = p_organization_id AND lower(r.name) = lower(p_role);
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM tenancy.data_scopes AS s
    WHERE s.organization_id = p_organization_id AND s.user_id = v_user.id
  ) AND NOT EXISTS (
    SELECT 1 FROM tenancy.data_scope_companies AS s
    WHERE s.organization_id = p_organization_id AND s.user_id = v_user.id
  ) AND NOT EXISTS (
    SELECT 1 FROM tenancy.data_scope_vehicles AS s
    WHERE s.organization_id = p_organization_id AND s.user_id = v_user.id
  ) THEN
    IF p_company_id IS NULL THEN
      INSERT INTO tenancy.data_scopes (organization_id, user_id, all_companies, updated_at)
      VALUES (p_organization_id, v_user.id, true, p_at);
    END IF;
  END IF;

  IF v_created AND p_pin_hash IS NOT NULL THEN
    UPDATE identity.users SET pin_hash = p_pin_hash WHERE id = v_user.id;
    PERFORM identity.touch_version(v_user.id);
  END IF;

  RETURN v_user.id;
END;
$$;

REVOKE ALL ON FUNCTION ops.seed_demo_user(uuid, uuid, text, text, text, text, uuid, text, timestamptz)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ops.seed_demo_user(uuid, uuid, text, text, text, text, uuid, text, timestamptz)
  TO xcode_api_executor;
