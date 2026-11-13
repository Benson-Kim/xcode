-- tenancy.save_role(p_role_id uuid, p_name text, p_permissions text[], p_expected_version bigint, p_now timestamptz) RETURNS jsonb
-- Purpose: create (p_role_id NULL) or change a custom role: a trimmed name of 1 to 100 characters, catalogue permissions each named once; on change a custom role of this organization at the version the actor saw, whose permissions the actor all holds; a name no built-in role has and no other role of the organization has, ignoring case; permissions, dependencies expanded, that the actor all holds. A change of name or permissions bumps the version, and the security version (their tokens carry its permissions) and membership version (an open person edit then conflicts) of everyone holding the role, and logs one roles change with before and after; no change answers the role as it is. Returns tenancy.role_document.
-- Callers: api.access_role_create, api.access_role_update (after tenancy.enter_organization with access.manage).
-- Reads: tenancy.roles, tenancy.role_grants, tenancy.role_defaults, tenancy.permissions, tenancy.person_roles, and what tenancy.effective_permissions and tenancy.role_permissions read. Writes: tenancy.roles, tenancy.role_grants, tenancy.memberships (version), identity.users (security_version, through identity.touch_version version), and through tenancy.record_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC422 role_name_invalid, XC422 role_permissions_invalid, XC422 role_permission_unknown, XC404 not_found, XC422 role_built_in, XC409 version_conflict, XC422 role_not_held, XC422 role_name_taken, XC422 role_permission_not_held.
-- Tests: tests/db/test_role_routines.py.
-- The role row is locked FOR UPDATE: a person save that gives this role takes KEY SHARE on it
-- before locking the person, so a holder added meanwhile either waits for this change or is
-- already counted among the holders whose tokens it ends.

CREATE OR REPLACE FUNCTION tenancy.save_role(
  p_role_id uuid,
  p_name text,
  p_permissions text[],
  p_expected_version bigint,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.current_organization();
  v_name text := tenancy.trim_text(p_name);
  v_role tenancy.roles;
  v_role_id uuid := p_role_id;
  v_held text[];
  v_requested text[];
  v_current text[] := '{}';
  v_changes text[] := '{}';
  v_before json;
  v_after json;
BEGIN
  IF v_name IS NULL OR char_length(v_name) > 100 THEN
    PERFORM tenancy.refuse('role_name_invalid', 'XC422');
  END IF;
  IF p_permissions IS NULL
     OR cardinality(p_permissions) = 0
     OR array_position(p_permissions, NULL) IS NOT NULL
     OR (SELECT count(DISTINCT k.key) FROM unnest(p_permissions) AS k (key)) <> cardinality(p_permissions) THEN
    PERFORM tenancy.refuse('role_permissions_invalid', 'XC422');
  END IF;
  -- The catalogue only: organization.manage and the retired keys are not in it.
  IF EXISTS (
    SELECT 1
    FROM unnest(p_permissions) AS requested (key)
    WHERE NOT EXISTS (
      SELECT 1 FROM tenancy.permissions AS p WHERE p.key = requested.key AND p.catalogue
    )
  ) THEN
    PERFORM tenancy.refuse('role_permission_unknown', 'XC422');
  END IF;

  v_held := tenancy.effective_permissions(v_organization_id, tenancy.current_actor());
  IF p_role_id IS NOT NULL THEN
    SELECT r.* INTO v_role
    FROM tenancy.roles AS r
    WHERE r.organization_id = v_organization_id AND r.id = p_role_id
    FOR UPDATE;
    IF NOT FOUND THEN
      PERFORM tenancy.refuse('not_found', 'XC404');
    END IF;
    IF v_role.built_in THEN
      PERFORM tenancy.refuse('role_built_in', 'XC422');
    END IF;
    IF p_expected_version IS NULL OR p_expected_version <> v_role.version THEN
      PERFORM tenancy.refuse('version_conflict', 'XC409');
    END IF;
    v_current := tenancy.role_permissions(v_role.name);
    IF NOT v_current <@ v_held THEN
      PERFORM tenancy.refuse('role_not_held', 'XC422');
    END IF;
  END IF;

  IF EXISTS (SELECT 1 FROM tenancy.role_defaults AS d WHERE lower(d.role_name) = lower(v_name))
     OR EXISTS (
       SELECT 1 FROM tenancy.roles AS r
       WHERE r.organization_id = v_organization_id
         AND lower(r.name) = lower(v_name)
         AND r.id IS DISTINCT FROM p_role_id
     ) THEN
    PERFORM tenancy.refuse('role_name_taken', 'XC422');
  END IF;
  v_requested := tenancy.expand_permissions(p_permissions);
  IF NOT v_requested <@ v_held THEN
    PERFORM tenancy.refuse('role_permission_not_held', 'XC422');
  END IF;

  IF p_role_id IS NULL THEN
    BEGIN
      INSERT INTO tenancy.roles (organization_id, name, version, created_at)
      VALUES (v_organization_id, v_name, 1, p_now)
      RETURNING id INTO v_role_id;
    EXCEPTION
      WHEN unique_violation THEN
        PERFORM tenancy.refuse('role_name_taken', 'XC422');
    END;
  ELSE
    IF v_name <> v_role.name THEN
      v_changes := v_changes || 'name'::text;
    END IF;
    IF v_requested <> v_current THEN
      v_changes := v_changes || 'permissions'::text;
    END IF;
    IF cardinality(v_changes) = 0 THEN
      RETURN tenancy.role_document(p_role_id);
    END IF;
    v_before := tenancy.compact_json(json_build_object('Name', v_role.name, 'Permissions', v_current));
    BEGIN
      UPDATE tenancy.roles
      SET name = v_name, version = version + 1
      WHERE organization_id = v_organization_id AND id = p_role_id;
    EXCEPTION
      WHEN unique_violation THEN
        PERFORM tenancy.refuse('role_name_taken', 'XC422');
    END;
    DELETE FROM tenancy.role_grants
    WHERE organization_id = v_organization_id AND role_id = p_role_id;
    -- Holders' memberships, then their accounts, each in id order: the order tenancy.save_person
    -- takes them in. NO KEY, as there: a sign-in routine needs KEY SHARE on the membership. The
    -- membership version moves so a person edit opened before this change conflicts, rather than
    -- saving grants or denials against the role's old permissions.
    PERFORM 1
    FROM tenancy.memberships AS m
    WHERE m.organization_id = v_organization_id
      AND m.user_id IN (
        SELECT pr.user_id FROM tenancy.person_roles AS pr
        WHERE pr.organization_id = v_organization_id AND pr.role_id = p_role_id
      )
    ORDER BY m.user_id
    FOR NO KEY UPDATE;
    UPDATE tenancy.memberships AS m
    SET version = m.version + 1, updated_at = p_now
    WHERE m.organization_id = v_organization_id
      AND m.user_id IN (
        SELECT pr.user_id FROM tenancy.person_roles AS pr
        WHERE pr.organization_id = v_organization_id AND pr.role_id = p_role_id
      );
    PERFORM 1
    FROM identity.users AS u
    WHERE u.id IN (
      SELECT pr.user_id FROM tenancy.person_roles AS pr
      WHERE pr.organization_id = v_organization_id AND pr.role_id = p_role_id
    )
    ORDER BY u.id
    FOR UPDATE;
    UPDATE identity.users AS u
    SET security_version = u.security_version + 1, updated_at = p_now
    WHERE u.id IN (
      SELECT pr.user_id FROM tenancy.person_roles AS pr
      WHERE pr.organization_id = v_organization_id AND pr.role_id = p_role_id
    );
    PERFORM identity.touch_version(pr.user_id)
    FROM tenancy.person_roles AS pr
    WHERE pr.organization_id = v_organization_id AND pr.role_id = p_role_id;
  END IF;
  INSERT INTO tenancy.role_grants (organization_id, role_id, permission)
  SELECT v_organization_id, v_role_id, k.key FROM unnest(v_requested) AS k (key);

  v_after := tenancy.compact_json(json_build_object('Name', v_name, 'Permissions', v_requested));
  IF p_role_id IS NULL THEN
    PERFORM tenancy.record_change(
      'roles', v_role_id, NULL, 'null'::json, v_after, 'Added role ' || v_name,
      'role.created', v_role_id::text, NULL, v_after::jsonb, p_now
    );
  ELSE
    PERFORM tenancy.record_change(
      'roles', p_role_id, NULL, v_before, v_after,
      'Changed ' || tenancy.join_words(v_changes) || ' of role ' || v_name,
      'role.updated', p_role_id::text, v_before::jsonb, v_after::jsonb, p_now
    );
  END IF;
  RETURN tenancy.role_document(v_role_id);
END;
$$;

REVOKE ALL ON FUNCTION tenancy.save_role(uuid, text, text[], bigint, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.save_role(uuid, text, text[], bigint, timestamptz)
  TO xcode_api_executor;
