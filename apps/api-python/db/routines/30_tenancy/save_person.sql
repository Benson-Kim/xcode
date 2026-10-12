-- tenancy.save_person(p_user_id uuid, p_first_name text, p_last_name text, p_email text, p_phone text, p_role text, p_scope_mode text, p_company_ids uuid[], p_vehicle_ids uuid[], p_permissions text[], p_approval_limit numeric, p_back_limit_mode text, p_back_limit_count integer, p_back_limit_from date, p_expected_version bigint, p_now timestamptz) RETURNS api.write_result
-- Purpose: create (p_user_id NULL) or update a person in the sixteen-step order of the people contract: input shape, role, how far back they may change records (no mode: 7 days on create, unchanged on update; a fixed date not after the business date), the visible person and their version, the grant rules of tenancy.check_person_grant, contact uniqueness; then the user, membership, role, scope and override rows, the session side effects of an update, and one change-log entry.
-- Callers: api.people_create (after tenancy.enter_organization with people.add), api.people_update (with people.edit).
-- Reads: identity.users, tenancy.organizations and tenancy.organization_localizations (the business date), tenancy.memberships, tenancy.roles, tenancy.person_roles, tenancy.role_defaults, tenancy.permission_overrides, tenancy.data_scopes, tenancy.data_scope_companies, tenancy.data_scope_vehicles. Writes: identity.users, identity.trusted_devices, identity.refresh_tokens, tenancy.memberships, tenancy.roles, tenancy.person_roles, tenancy.permission_overrides, tenancy.data_scopes, tenancy.data_scope_companies, tenancy.data_scope_vehicles, tenancy.audit_events, and through tenancy.record_change tenancy.change_log and tenancy.organizations.settings_version.
-- Raises: XC422 people_names_required, XC422 people_email_invalid, XC422 people_phone_invalid, XC422 people_scope_mode, XC422 people_scope_empty, XC422 people_scope_duplicate, XC422 people_permissions_invalid, XC422 people_role_unknown, XC422 people_back_limit_invalid, XC422 people_back_limit_date_future, XC422 time_zone_invalid via tenancy.business_date, XC404 not_found, XC422 people_version_required, XC409 version_conflict, XC403 people_back_limit_not_held, XC422 people_contact_taken, XC403 people_all_companies_needs_all via tenancy.check_person_grant, XC422 people_companies_unknown via tenancy.check_person_grant, XC422 people_vehicles_unknown via tenancy.check_person_grant, XC403 people_companies_outside_scope via tenancy.check_person_grant, XC403 people_vehicles_outside_scope via tenancy.check_person_grant, XC403 people_hidden_scope_kind via tenancy.check_person_grant, XC422 people_self_edit via tenancy.check_person_grant, XC403 people_owner_grant via tenancy.check_person_grant, XC403 people_owner_edit via tenancy.check_person_grant, XC422 people_permission_unknown via tenancy.check_person_grant, XC403 people_role_not_held via tenancy.check_person_grant, XC403 people_access_manage_needed via tenancy.check_person_grant, XC403 people_permission_not_held via tenancy.check_person_grant, XC403 people_sign_in_scope via tenancy.check_person_grant, XC403 people_sign_in_holdings via tenancy.check_person_grant.
-- Tests: tests/db/test_access_routines.py.
-- The grant rules run between the version check and the contact check (steps 10 to 15), so the
-- refusals keep the contract's order; people_contact_taken is also the unique-index backstop.

CREATE OR REPLACE FUNCTION tenancy.save_person(
  p_user_id uuid,
  p_first_name text,
  p_last_name text,
  p_email text,
  p_phone text,
  p_role text,
  p_scope_mode text,
  p_company_ids uuid[],
  p_vehicle_ids uuid[],
  p_permissions text[],
  p_approval_limit numeric,
  p_back_limit_mode text,
  p_back_limit_count integer,
  p_back_limit_from date,
  p_expected_version bigint,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.current_organization();
  v_first_name text := tenancy.trim_text(p_first_name);
  v_last_name text := tenancy.trim_text(p_last_name);
  v_email text := identity.normalize_email(p_email);
  v_phone text := identity.normalize_phone(p_phone);
  v_companies uuid[] := CASE WHEN p_scope_mode = 'companies' THEN coalesce(p_company_ids, '{}') ELSE '{}' END;
  v_vehicles uuid[] := CASE WHEN p_scope_mode = 'vehicles' THEN coalesce(p_vehicle_ids, '{}') ELSE '{}' END;
  v_role text;
  v_limit_mode text := p_back_limit_mode;
  v_limit_count integer := p_back_limit_count;
  v_limit_from date := p_back_limit_from;
  v_member tenancy.memberships;
  v_user identity.users;
  v_scope tenancy.scope;
  v_old_scope tenancy.scope;
  v_old_mode text;
  v_old_role text;
  v_old_granted text[] := '{}';
  v_old_denied text[] := '{}';
  v_requested text[];
  v_defaults text[];
  v_granted text[];
  v_denied text[];
  v_user_id uuid := p_user_id;
  v_changes text[] := '{}';
  v_contact_changed boolean := false;
  v_before json;
  v_after json;
  v_today date;
  v_editor_earliest date;
BEGIN
  -- Steps 1 to 8: the shape of the request.
  IF v_first_name IS NULL OR v_last_name IS NULL
     OR char_length(v_first_name) > 100 OR char_length(v_last_name) > 100 THEN
    PERFORM tenancy.refuse('people_names_required', 'XC422');
  END IF;
  IF v_email IS NULL THEN
    PERFORM tenancy.refuse('people_email_invalid', 'XC422');
  END IF;
  IF v_phone IS NULL THEN
    PERFORM tenancy.refuse('people_phone_invalid', 'XC422');
  END IF;
  IF p_scope_mode IS NULL OR p_scope_mode NOT IN ('all', 'companies', 'vehicles') THEN
    PERFORM tenancy.refuse('people_scope_mode', 'XC422');
  END IF;
  IF (p_scope_mode = 'companies' AND cardinality(v_companies) = 0)
     OR (p_scope_mode = 'vehicles' AND cardinality(v_vehicles) = 0) THEN
    PERFORM tenancy.refuse('people_scope_empty', 'XC422');
  END IF;
  IF (SELECT count(DISTINCT c.id) FROM unnest(v_companies) AS c (id)) <> cardinality(v_companies)
     OR (SELECT count(DISTINCT v.id) FROM unnest(v_vehicles) AS v (id)) <> cardinality(v_vehicles) THEN
    PERFORM tenancy.refuse('people_scope_duplicate', 'XC422');
  END IF;
  IF p_permissions IS NULL
     OR cardinality(p_permissions) = 0
     OR array_position(p_permissions, NULL) IS NOT NULL
     OR (SELECT count(DISTINCT k.key) FROM unnest(p_permissions) AS k (key)) <> cardinality(p_permissions)
     OR p_approval_limit < 0
     OR p_approval_limit > 999999999999.99
     OR p_approval_limit <> round(p_approval_limit, 2) THEN
    PERFORM tenancy.refuse('people_permissions_invalid', 'XC422');
  END IF;
  SELECT DISTINCT d.role_name INTO v_role
  FROM tenancy.role_defaults AS d
  WHERE lower(d.role_name) = lower(p_role);
  IF v_role IS NULL THEN
    PERFORM tenancy.refuse('people_role_unknown', 'XC422');
  END IF;
  -- How far back they may change records: no mode keeps the stored limit (7 days for a new
  -- person); a count only with days or months, in range; a fixed date not after today.
  IF v_limit_mode IS NULL THEN
    IF v_limit_count IS NOT NULL OR v_limit_from IS NOT NULL THEN
      PERFORM tenancy.refuse('people_back_limit_invalid', 'XC422');
    END IF;
    IF p_user_id IS NULL THEN
      v_limit_mode := 'days';
      v_limit_count := 7;
    END IF;
  ELSIF v_limit_mode NOT IN ('none', 'days', 'months')
     OR (v_limit_mode = 'none') <> (v_limit_count IS NULL)
     OR (v_limit_mode = 'days' AND v_limit_count NOT BETWEEN 0 AND 3650)
     OR (v_limit_mode = 'months' AND v_limit_count NOT BETWEEN 0 AND 120) THEN
    PERFORM tenancy.refuse('people_back_limit_invalid', 'XC422');
  ELSIF v_limit_from > tenancy.business_date(v_organization_id, p_now) THEN
    PERFORM tenancy.refuse('people_back_limit_date_future', 'XC422');
  END IF;

  -- Step 9: an update needs a person the editor can see, loaded at the version they edit.
  IF p_user_id IS NOT NULL THEN
    IF NOT tenancy.person_in_view(p_user_id) THEN
      PERFORM tenancy.refuse('not_found', 'XC404');
    END IF;
    -- NO KEY: a sign-in routine holding this user's row writes a change-log row whose actor
    -- key check needs KEY SHARE on this membership; FOR UPDATE would deadlock with it.
    SELECT m.* INTO v_member
    FROM tenancy.memberships AS m
    WHERE m.organization_id = v_organization_id AND m.user_id = p_user_id
    FOR NO KEY UPDATE;
    v_user := identity.lock_user(p_user_id);
    IF p_expected_version IS NULL THEN
      PERFORM tenancy.refuse('people_version_required', 'XC422');
    END IF;
    IF p_expected_version <> v_member.version THEN
      PERFORM tenancy.refuse('version_conflict', 'XC409');
    END IF;
    v_old_scope := tenancy.person_scope(p_user_id);
    v_old_mode := tenancy.scope_mode(v_organization_id, p_user_id);
    v_old_role := tenancy.role_of(p_user_id);
    SELECT coalesce(array_agg(o.permission ORDER BY o.permission) FILTER (WHERE o.granted), '{}'::text[]),
           coalesce(array_agg(o.permission ORDER BY o.permission) FILTER (WHERE NOT o.granted), '{}'::text[])
    INTO v_old_granted, v_old_denied
    FROM tenancy.permission_overrides AS o
    WHERE o.organization_id = v_organization_id AND o.user_id = p_user_id;
  END IF;

  -- Steps 10 to 15.
  v_scope := tenancy.check_person_grant(
    p_user_id, v_role, p_scope_mode, v_companies, v_vehicles, p_permissions, p_approval_limit,
    v_email, v_phone
  );

  -- A non-Owner gives no one more room to change past records than they have themselves,
  -- on create and when the limit changes (otherwise a second account would lift their own).
  IF v_limit_mode IS NOT NULL
     AND lower(coalesce(tenancy.role_of(tenancy.current_actor()), '')) <> 'owner'
     AND (p_user_id IS NULL
          OR v_limit_mode <> v_member.back_limit_mode
          OR v_limit_count IS DISTINCT FROM v_member.back_limit_count::integer
          OR v_limit_from IS DISTINCT FROM v_member.back_limit_from) THEN
    v_today := tenancy.business_date(v_organization_id, p_now);
    v_editor_earliest := tenancy.earliest_writable(
      v_organization_id, tenancy.current_actor(), v_today
    );
    IF v_editor_earliest IS NOT NULL
       AND coalesce(
             tenancy.back_limit_earliest(v_limit_mode, v_limit_count, v_limit_from, v_today)
               < v_editor_earliest,
             true
           ) THEN
      PERFORM tenancy.refuse('people_back_limit_not_held', 'XC403');
    END IF;
  END IF;

  -- Step 16.
  IF EXISTS (
    SELECT 1 FROM identity.users AS u
    WHERE (u.email = v_email OR u.phone_number = v_phone)
      AND u.id IS DISTINCT FROM p_user_id
  ) THEN
    PERFORM tenancy.refuse('people_contact_taken', 'XC422');
  END IF;

  v_requested := tenancy.expand_permissions(p_permissions);
  v_defaults := tenancy.role_permissions(v_role);
  v_granted := ARRAY(
    SELECT k.key FROM unnest(v_requested) AS k (key) WHERE NOT k.key = ANY (v_defaults) ORDER BY k.key
  );
  v_denied := ARRAY(
    SELECT k.key FROM unnest(v_defaults) AS k (key) WHERE NOT k.key = ANY (v_requested) ORDER BY k.key
  );

  IF p_user_id IS NULL THEN
    BEGIN
      INSERT INTO identity.users (email, phone_number, status, created_at, updated_at)
      VALUES (v_email, v_phone, 'active', p_now, p_now)
      RETURNING id INTO v_user_id;
    EXCEPTION
      WHEN unique_violation THEN
        PERFORM tenancy.refuse('people_contact_taken', 'XC422');
    END;
    INSERT INTO tenancy.memberships (
      organization_id, user_id, first_name, last_name, active, approval_limit, back_limit_mode,
      back_limit_count, back_limit_from, version, created_at, updated_at
    )
    VALUES (
      v_organization_id, v_user_id, v_first_name, v_last_name, true, p_approval_limit,
      v_limit_mode, v_limit_count, v_limit_from, 1, p_now, p_now
    );
    PERFORM tenancy.seed_roles(v_organization_id);
    INSERT INTO tenancy.person_roles (organization_id, user_id, role_id, updated_at)
    SELECT v_organization_id, v_user_id, r.id, p_now
    FROM tenancy.roles AS r
    WHERE r.organization_id = v_organization_id AND lower(r.name) = lower(v_role);
  ELSE
    IF v_first_name <> v_member.first_name OR v_last_name <> v_member.last_name THEN
      v_changes := v_changes || 'name'::text;
    END IF;
    IF v_email <> v_user.email OR v_phone <> v_user.phone_number THEN
      v_changes := v_changes || 'sign-in details'::text;
      v_contact_changed := true;
    END IF;
    IF lower(v_role) <> lower(coalesce(v_old_role, '')) THEN
      v_changes := v_changes || 'role'::text;
    END IF;
    IF v_granted <> v_old_granted OR v_denied <> v_old_denied THEN
      v_changes := v_changes || 'single permissions'::text;
    END IF;
    IF p_scope_mode <> v_old_mode
       OR v_scope.company_ids <> v_old_scope.company_ids
       OR v_scope.vehicle_ids <> v_old_scope.vehicle_ids THEN
      v_changes := v_changes || 'data scope'::text;
    END IF;
    IF p_approval_limit IS DISTINCT FROM v_member.approval_limit THEN
      v_changes := v_changes || 'approval limit'::text;
    END IF;
    IF v_limit_mode IS NULL THEN
      v_limit_mode := v_member.back_limit_mode;
      v_limit_count := v_member.back_limit_count;
      v_limit_from := v_member.back_limit_from;
    ELSIF v_limit_mode <> v_member.back_limit_mode
       OR v_limit_count IS DISTINCT FROM v_member.back_limit_count::integer
       OR v_limit_from IS DISTINCT FROM v_member.back_limit_from THEN
      v_changes := v_changes || 'how far back they can change records'::text;
    END IF;
    IF cardinality(v_changes) = 0 THEN
      RETURN ROW(p_user_id, v_member.version, 'unchanged')::api.write_result;
    END IF;

    v_before := tenancy.person_snapshot(p_user_id);
    -- A new email or number ends every session and device (the PIN is kept); a new name, role or
    -- set of single permissions changes what the token carries, so its security version moves.
    IF v_contact_changed THEN
      BEGIN
        UPDATE identity.users
        SET email = v_email,
            phone_number = v_phone,
            security_version = security_version + 1,
            updated_at = p_now
        WHERE id = p_user_id;
      EXCEPTION
        WHEN unique_violation THEN
          PERFORM tenancy.refuse('people_contact_taken', 'XC422');
      END;
      PERFORM identity.revoke_devices(p_user_id);
      PERFORM identity.revoke_tokens(p_user_id);
      PERFORM identity.touch_version(p_user_id);
    ELSIF ARRAY['name', 'role', 'single permissions'] && v_changes THEN
      UPDATE identity.users
      SET security_version = security_version + 1, updated_at = p_now
      WHERE id = p_user_id;
      PERFORM identity.touch_version(p_user_id);
    END IF;
    UPDATE tenancy.memberships
    SET first_name = v_first_name,
        last_name = v_last_name,
        approval_limit = p_approval_limit,
        back_limit_mode = v_limit_mode,
        back_limit_count = v_limit_count,
        back_limit_from = v_limit_from,
        version = version + 1,
        updated_at = p_now
    WHERE organization_id = v_organization_id
      AND user_id = p_user_id
      AND version = p_expected_version;
    UPDATE tenancy.person_roles AS pr
    SET role_id = r.id, updated_at = p_now
    FROM tenancy.roles AS r
    WHERE pr.organization_id = v_organization_id
      AND pr.user_id = p_user_id
      AND r.organization_id = v_organization_id
      AND lower(r.name) = lower(v_role)
      AND pr.role_id <> r.id;
  END IF;

  -- The person's access rows are replaced whole: scope rows for the chosen mode and an
  -- override for each difference from the role's defaults.
  DELETE FROM tenancy.permission_overrides
  WHERE organization_id = v_organization_id AND user_id = v_user_id;
  INSERT INTO tenancy.permission_overrides (organization_id, user_id, permission, granted)
  SELECT v_organization_id, v_user_id, k.key, true FROM unnest(v_granted) AS k (key)
  UNION ALL
  SELECT v_organization_id, v_user_id, k.key, false FROM unnest(v_denied) AS k (key);
  DELETE FROM tenancy.data_scope_companies
  WHERE organization_id = v_organization_id AND user_id = v_user_id;
  DELETE FROM tenancy.data_scope_vehicles
  WHERE organization_id = v_organization_id AND user_id = v_user_id;
  DELETE FROM tenancy.data_scopes
  WHERE organization_id = v_organization_id AND user_id = v_user_id;
  IF v_scope.all_companies THEN
    INSERT INTO tenancy.data_scopes (organization_id, user_id, all_companies, updated_at)
    VALUES (v_organization_id, v_user_id, true, p_now);
  END IF;
  INSERT INTO tenancy.data_scope_companies (organization_id, user_id, company_id)
  SELECT v_organization_id, v_user_id, c.id FROM unnest(v_scope.company_ids) AS c (id);
  INSERT INTO tenancy.data_scope_vehicles (organization_id, user_id, vehicle_id)
  SELECT v_organization_id, v_user_id, v.id FROM unnest(v_scope.vehicle_ids) AS v (id);

  v_after := tenancy.person_snapshot(v_user_id);
  IF p_user_id IS NULL THEN
    PERFORM tenancy.record_change(
      'people', v_user_id, NULL, 'null'::json, v_after,
      'Added ' || v_first_name || ' ' || v_last_name || ' as ' || v_role,
      'person.created', v_user_id::text, NULL, v_after::jsonb, p_now
    );
    RETURN ROW(v_user_id, 1, 'created')::api.write_result;
  END IF;

  IF v_contact_changed THEN
    INSERT INTO tenancy.audit_events (
      organization_id, actor_id, action, entity, before, after, occurred_at, request_id
    )
    VALUES (
      v_organization_id, tenancy.current_actor(), 'person.sign_in_details_changed', p_user_id::text,
      jsonb_build_object('email', v_user.email, 'phone_number', v_user.phone_number),
      jsonb_build_object('email', v_email, 'phone_number', v_phone),
      p_now, tenancy.current_request()
    );
  END IF;
  PERFORM tenancy.record_change(
    'people', p_user_id, NULL, v_before, v_after,
    'Changed ' || tenancy.join_words(v_changes) || ' for ' || v_first_name || ' ' || v_last_name,
    'person.updated', p_user_id::text, v_before::jsonb, v_after::jsonb, p_now
  );
  RETURN ROW(p_user_id, v_member.version + 1, 'updated')::api.write_result;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.save_person(
  uuid, text, text, text, text, text, text, uuid[], uuid[], text[], numeric, text, integer, date,
  bigint, timestamptz
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.save_person(
  uuid, text, text, text, text, text, text, uuid[], uuid[], text[], numeric, text, integer, date,
  bigint, timestamptz
) TO xcode_api_executor;
