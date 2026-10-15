-- api.ops_provision_user(p_operator text, p_request_id text, p_email text, p_phone text, p_role text, p_first_name text, p_last_name text, p_organization_name text, p_now timestamptz) RETURNS jsonb
-- Purpose: create or re-activate a person in the database's single organization (created with defaults and seeded roles when none exists); a changed or revived existing account loses every session and device.
-- Callers: OpsRoutines.provision_user; CLI provision-user.
-- Reads: identity.users, tenancy.organizations, tenancy.memberships, tenancy.roles, tenancy.person_roles. Writes: ops.operator_actions, tenancy.organizations and its localization, branding and security-policy rows, tenancy.roles, identity.users, tenancy.memberships, tenancy.person_roles, tenancy.data_scopes, identity.trusted_devices, identity.refresh_tokens.
-- Raises: XC422 people_email_invalid, XC422 people_phone_invalid, XC422 people_role_unknown, XC422 people_names_required, XC422 organization_name_slug, XC409 organization_not_single, XC409 people_contact_taken.
-- Tests: tests/db/test_ops_routines.py, tests/api/test_cli.py.

CREATE OR REPLACE FUNCTION api.ops_provision_user(
  p_operator text,
  p_request_id text,
  p_email text,
  p_phone text,
  p_role text,
  p_first_name text,
  p_last_name text,
  p_organization_name text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_email text := lower(tenancy.trim_text(p_email));
  v_phone text := identity.normalize_phone(p_phone);
  v_role text := tenancy.trim_text(p_role);
  v_first_name text := tenancy.trim_text(p_first_name);
  v_last_name text := tenancy.trim_text(p_last_name);
  v_organization_name text := tenancy.trim_text(p_organization_name);
  v_organizations uuid[];
  v_organization_id uuid;
  v_created_organization boolean := false;
  v_user_id uuid;
  v_user identity.users;
  v_created_user boolean := false;
  v_was_active boolean := true;
  v_phone_changed boolean := false;
  v_membership tenancy.memberships;
  v_membership_revived boolean := false;
  v_local_parts text[];
  v_current_role_id uuid;
  v_current_role text;
  v_role_id uuid;
  v_role_changed boolean := false;
BEGIN
  PERFORM ops.record_operator_action(
    p_operator, 'provision-user', v_email, jsonb_build_object('request_id', p_request_id), p_now
  );

  IF identity.normalize_email(v_email) IS NULL THEN
    PERFORM tenancy.refuse('people_email_invalid', 'XC422');
  END IF;
  IF v_phone IS NULL THEN
    PERFORM tenancy.refuse('people_phone_invalid', 'XC422');
  END IF;
  -- A catalogue role name in any case, stored as the catalogue spells it (as .NET).
  IF v_role IS NOT NULL THEN
    v_role := (
      SELECT catalogue.name
      FROM unnest(ARRAY['Owner', 'Office admin', 'Fleet manager', 'Revenue clerk']) AS catalogue (name)
      WHERE lower(catalogue.name) = lower(v_role)
    );
    IF v_role IS NULL THEN
      PERFORM tenancy.refuse('people_role_unknown', 'XC422');
    END IF;
  END IF;
  IF char_length(v_first_name) > 100 OR char_length(v_last_name) > 100 THEN
    PERFORM tenancy.refuse('people_names_required', 'XC422');
  END IF;
  IF char_length(v_organization_name) > 200 THEN
    PERFORM tenancy.refuse('organization_name_slug', 'XC422');
  END IF;

  -- One organization per database: reuse it, or create it with the default settings rows.
  v_organizations := tenancy.organization_ids();
  IF cardinality(v_organizations) > 1 THEN
    PERFORM tenancy.refuse('organization_not_single', 'XC409');
  END IF;
  IF cardinality(v_organizations) = 1 THEN
    v_organization_id := v_organizations[1];
    PERFORM tenancy.enter_organization_as_operator(v_organization_id);
  ELSE
    v_organization_id := gen_random_uuid();
    PERFORM tenancy.enter_organization_as_operator(v_organization_id);
    INSERT INTO tenancy.organizations (id, slug, name, created_at, updated_at)
    VALUES (v_organization_id, 'my-fleet', coalesce(v_organization_name, 'My fleet'), p_now, p_now);
    INSERT INTO tenancy.organization_localizations (organization_id, created_at, updated_at)
    VALUES (v_organization_id, p_now, p_now);
    INSERT INTO tenancy.organization_brandings (organization_id, created_at, updated_at)
    VALUES (v_organization_id, p_now, p_now);
    INSERT INTO tenancy.organization_security_policies (organization_id, created_at, updated_at)
    VALUES (v_organization_id, p_now, p_now);
    v_created_organization := true;
  END IF;
  PERFORM tenancy.seed_roles(v_organization_id);

  IF EXISTS (
    SELECT 1 FROM identity.users AS u WHERE u.phone_number = v_phone AND u.email <> v_email
  ) THEN
    PERFORM tenancy.refuse('people_contact_taken', 'XC409');
  END IF;

  -- The account: created active with no PIN, or re-activated with the given number (PIN kept).
  SELECT u.id INTO v_user_id FROM identity.users AS u WHERE u.email = v_email;
  IF v_user_id IS NULL THEN
    INSERT INTO identity.users (email, phone_number, status, created_at, updated_at)
    VALUES (v_email, v_phone, 'active', p_now, p_now)
    RETURNING * INTO v_user;
    v_created_user := true;
  ELSE
    v_user := identity.lock_user(v_user_id);
    v_was_active := v_user.status = 'active';
    v_phone_changed := v_user.phone_number <> v_phone;
    IF v_phone_changed OR NOT v_was_active THEN
      UPDATE identity.users SET phone_number = v_phone, status = 'active' WHERE id = v_user.id;
    END IF;
  END IF;

  -- The membership: names from the options, else from the email's first.last local part.
  SELECT m.* INTO v_membership
  FROM tenancy.memberships AS m
  WHERE m.organization_id = v_organization_id AND m.user_id = v_user.id;
  IF v_membership.user_id IS NULL THEN
    v_local_parts := array_remove(string_to_array(split_part(v_email, '@', 1), '.'), '');
    INSERT INTO tenancy.memberships (organization_id, user_id, first_name, last_name, active, created_at, updated_at)
    VALUES (
      v_organization_id,
      v_user.id,
      coalesce(v_first_name, left(upper(left(v_local_parts[1], 1)) || substr(v_local_parts[1], 2), 100), 'New'),
      coalesce(v_last_name, left(upper(left(v_local_parts[2], 1)) || substr(v_local_parts[2], 2), 100), 'Member'),
      true,
      p_now,
      p_now
    );
    v_membership_revived := NOT v_created_user;
  ELSIF NOT v_membership.active
        OR coalesce(v_first_name, v_membership.first_name) <> v_membership.first_name
        OR coalesce(v_last_name, v_membership.last_name) <> v_membership.last_name THEN
    v_membership_revived := NOT v_membership.active;
    UPDATE tenancy.memberships
    SET active = true,
        first_name = coalesce(v_first_name, first_name),
        last_name = coalesce(v_last_name, last_name),
        version = version + 1
    WHERE organization_id = v_organization_id AND user_id = v_user.id;
  END IF;

  -- The role: the option, else the existing link, else Owner.
  SELECT pr.role_id, r.name INTO v_current_role_id, v_current_role
  FROM tenancy.person_roles AS pr
  JOIN tenancy.roles AS r ON r.organization_id = pr.organization_id AND r.id = pr.role_id
  WHERE pr.organization_id = v_organization_id AND pr.user_id = v_user.id;
  v_role := coalesce(v_role, v_current_role, 'Owner');
  SELECT r.id INTO v_role_id
  FROM tenancy.roles AS r
  WHERE r.organization_id = v_organization_id AND lower(r.name) = lower(v_role);
  IF v_current_role_id IS NULL THEN
    INSERT INTO tenancy.person_roles (organization_id, user_id, role_id, updated_at)
    VALUES (v_organization_id, v_user.id, v_role_id, p_now);
    v_role_changed := NOT v_created_user;
  ELSIF v_current_role_id <> v_role_id THEN
    UPDATE tenancy.person_roles SET role_id = v_role_id, updated_at = p_now
    WHERE organization_id = v_organization_id AND user_id = v_user.id;
    v_role_changed := true;
  END IF;

  -- A changed or revived existing account: every access token, refresh token and device ends.
  IF NOT v_created_user
     AND (v_phone_changed OR NOT v_was_active OR v_membership_revived OR v_role_changed) THEN
    UPDATE identity.users SET security_version = security_version + 1 WHERE id = v_user.id;
    PERFORM identity.revoke_devices(v_user.id);
    PERFORM identity.revoke_tokens(v_user.id);
    PERFORM identity.touch_version(v_user.id);
  END IF;

  IF v_role IN ('Owner', 'Office admin') THEN
    INSERT INTO tenancy.data_scopes (organization_id, user_id, all_companies, updated_at)
    VALUES (v_organization_id, v_user.id, true, p_now)
    ON CONFLICT (organization_id, user_id) DO NOTHING;
  END IF;

  RETURN jsonb_build_object(
    'user_id', v_user.id,
    'organization_id', v_organization_id,
    'created_user', v_created_user,
    'created_organization', v_created_organization,
    'reactivated', NOT v_created_user AND (NOT v_was_active OR v_membership_revived)
  );
END;
$$;
