-- tenancy.check_person_grant(p_user_id uuid, p_role text, p_scope_mode text, p_company_ids uuid[], p_vehicle_ids uuid[], p_permissions text[], p_approval_limit numeric, p_email text, p_phone text) RETURNS tenancy.scope
-- Purpose: steps 10 to 15 of a person save, once for create (p_user_id NULL) and update: the data scope the editor may give (hidden holdings kept and pinning the kind of scope), no editing yourself, the Owner rules, catalogue permissions only (retired and hidden keys are unknown), the role and single permissions the editor holds (single permissions and approval limits need people.edit), and who may change sign-in details; returns the scope to store.
-- Callers: tenancy.save_person.
-- Reads: tenancy.memberships, identity.users, tenancy.permission_overrides, tenancy.permissions (the catalogue flag), setup.psv_companies, setup.fleet_vehicles, and what tenancy.person_reach, tenancy.person_scope, tenancy.scope_mode, tenancy.role_of, tenancy.role_permissions, tenancy.expand_permissions, tenancy.effective_permissions and tenancy.assigned_permissions read. Writes: nothing.
-- Raises: XC403 people_all_companies_needs_all, XC422 people_companies_unknown, XC422 people_vehicles_unknown, XC403 people_companies_outside_scope, XC403 people_vehicles_outside_scope, XC403 people_hidden_scope_kind, XC422 people_self_edit, XC403 people_owner_grant, XC403 people_owner_edit, XC422 people_permission_unknown, XC403 people_role_not_held, XC403 people_access_manage_needed, XC403 people_permission_not_held, XC403 people_sign_in_scope, XC403 people_sign_in_holdings.
-- Tests: tests/db/test_access_routines.py.

CREATE OR REPLACE FUNCTION tenancy.check_person_grant(
  p_user_id uuid,
  p_role text,
  p_scope_mode text,
  p_company_ids uuid[],
  p_vehicle_ids uuid[],
  p_permissions text[],
  p_approval_limit numeric,
  p_email text,
  p_phone text
)
RETURNS tenancy.scope
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.current_organization();
  v_actor_id uuid := tenancy.current_actor();
  v_reach tenancy.scope := tenancy.person_reach(tenancy.current_actor());
  v_held text[] := tenancy.effective_permissions(tenancy.current_organization(), tenancy.current_actor());
  v_actor_is_owner boolean := lower(coalesce(tenancy.role_of(tenancy.current_actor()), '')) = 'owner';
  v_target tenancy.scope := ROW(false, '{}'::uuid[], '{}'::uuid[])::tenancy.scope;
  v_target_mode text;
  v_target_role text;
  v_target_limit numeric;
  v_target_email text;
  v_target_phone text;
  v_current_granted text[] := '{}';
  v_current_denied text[] := '{}';
  v_companies uuid[] := coalesce(p_company_ids, '{}'::uuid[]);
  v_vehicles uuid[] := coalesce(p_vehicle_ids, '{}'::uuid[]);
  v_hidden_companies uuid[] := '{}';
  v_hidden_vehicles uuid[] := '{}';
  v_defaults text[] := tenancy.role_permissions(p_role);
  v_requested text[] := tenancy.expand_permissions(p_permissions);
  v_granted text[];
  v_denied text[];
BEGIN
  IF p_user_id IS NOT NULL THEN
    v_target := tenancy.person_scope(p_user_id);
    v_target_mode := tenancy.scope_mode(v_organization_id, p_user_id);
    v_target_role := tenancy.role_of(p_user_id);
    SELECT m.approval_limit, u.email, u.phone_number
    INTO v_target_limit, v_target_email, v_target_phone
    FROM tenancy.memberships AS m
    JOIN identity.users AS u ON u.id = m.user_id
    WHERE m.organization_id = v_organization_id AND m.user_id = p_user_id;
    SELECT coalesce(array_agg(o.permission ORDER BY o.permission) FILTER (WHERE o.granted), '{}'::text[]),
           coalesce(array_agg(o.permission ORDER BY o.permission) FILTER (WHERE NOT o.granted), '{}'::text[])
    INTO v_current_granted, v_current_denied
    FROM tenancy.permission_overrides AS o
    WHERE o.organization_id = v_organization_id AND o.user_id = p_user_id;
  END IF;

  -- The data scope: only an all-companies editor gives every company; chosen items must exist
  -- and lie within the editor's reach unless the person already holds them; holdings outside
  -- the editor's reach are kept and fix the kind of scope.
  IF p_scope_mode = 'all' AND NOT v_reach.all_companies THEN
    PERFORM tenancy.refuse('people_all_companies_needs_all', 'XC403');
  END IF;
  IF p_scope_mode = 'companies' AND EXISTS (
    SELECT 1
    FROM unnest(v_companies) AS chosen (id)
    WHERE NOT EXISTS (
      SELECT 1 FROM setup.psv_companies AS c
      WHERE c.organization_id = v_organization_id AND c.id = chosen.id
    )
  ) THEN
    PERFORM tenancy.refuse('people_companies_unknown', 'XC422');
  END IF;
  IF p_scope_mode = 'vehicles' AND EXISTS (
    SELECT 1
    FROM unnest(v_vehicles) AS chosen (id)
    WHERE NOT EXISTS (
      SELECT 1 FROM setup.fleet_vehicles AS f
      WHERE f.organization_id = v_organization_id AND f.id = chosen.id
    )
  ) THEN
    PERFORM tenancy.refuse('people_vehicles_unknown', 'XC422');
  END IF;
  IF NOT v_reach.all_companies THEN
    IF p_scope_mode = 'companies' AND EXISTS (
      SELECT 1
      FROM unnest(v_companies) AS chosen (id)
      WHERE NOT chosen.id = ANY (v_reach.company_ids)
        AND NOT chosen.id = ANY (v_target.company_ids)
    ) THEN
      PERFORM tenancy.refuse('people_companies_outside_scope', 'XC403');
    END IF;
    IF p_scope_mode = 'vehicles' AND EXISTS (
      SELECT 1
      FROM unnest(v_vehicles) AS chosen (id)
      WHERE NOT chosen.id = ANY (v_reach.vehicle_ids)
        AND NOT chosen.id = ANY (v_target.vehicle_ids)
    ) THEN
      PERFORM tenancy.refuse('people_vehicles_outside_scope', 'XC403');
    END IF;
    v_hidden_companies := ARRAY(
      SELECT held.id FROM unnest(v_target.company_ids) AS held (id)
      WHERE NOT held.id = ANY (v_reach.company_ids)
    );
    v_hidden_vehicles := ARRAY(
      SELECT held.id FROM unnest(v_target.vehicle_ids) AS held (id)
      WHERE NOT held.id = ANY (v_reach.vehicle_ids)
    );
    IF cardinality(v_hidden_companies) + cardinality(v_hidden_vehicles) > 0
       AND p_scope_mode IS DISTINCT FROM v_target_mode THEN
      PERFORM tenancy.refuse('people_hidden_scope_kind', 'XC403');
    END IF;
  END IF;
  v_companies := CASE
                   WHEN p_scope_mode = 'companies' THEN ARRAY(
                     SELECT DISTINCT kept.id FROM unnest(v_companies || v_hidden_companies) AS kept (id)
                     ORDER BY kept.id)
                   ELSE '{}'::uuid[]
                 END;
  v_vehicles := CASE
                  WHEN p_scope_mode = 'vehicles' THEN ARRAY(
                    SELECT DISTINCT kept.id FROM unnest(v_vehicles || v_hidden_vehicles) AS kept (id)
                    ORDER BY kept.id)
                  ELSE '{}'::uuid[]
                END;

  IF p_user_id = v_actor_id THEN
    PERFORM tenancy.refuse('people_self_edit', 'XC422');
  END IF;

  -- Only an Owner gives the Owner role, and only an Owner changes an Owner.
  IF NOT v_actor_is_owner AND lower(p_role) = 'owner'
     AND lower(coalesce(v_target_role, '')) <> 'owner' THEN
    PERFORM tenancy.refuse('people_owner_grant', 'XC403');
  END IF;
  IF NOT v_actor_is_owner AND lower(coalesce(v_target_role, '')) = 'owner' THEN
    PERFORM tenancy.refuse('people_owner_edit', 'XC403');
  END IF;

  IF EXISTS (
    SELECT 1
    FROM unnest(p_permissions) AS requested (key)
    WHERE NOT EXISTS (
      SELECT 1 FROM tenancy.permissions AS p WHERE p.key = requested.key AND p.catalogue
    )
  ) THEN
    PERFORM tenancy.refuse('people_permission_unknown', 'XC422');
  END IF;

  -- A non-Owner gives a role only when holding all its defaults; a change to the single
  -- permissions or the approval limit needs people.edit and permissions the editor holds.
  v_granted := ARRAY(
    SELECT k.key FROM unnest(v_requested) AS k (key) WHERE NOT k.key = ANY (v_defaults) ORDER BY k.key
  );
  v_denied := ARRAY(
    SELECT k.key FROM unnest(v_defaults) AS k (key) WHERE NOT k.key = ANY (v_requested) ORDER BY k.key
  );
  IF NOT v_actor_is_owner THEN
    IF lower(p_role) IS DISTINCT FROM lower(v_target_role) AND NOT v_defaults <@ v_held THEN
      PERFORM tenancy.refuse('people_role_not_held', 'XC403');
    END IF;
    IF v_granted <> v_current_granted
       OR v_denied <> v_current_denied
       OR p_approval_limit IS DISTINCT FROM v_target_limit THEN
      IF NOT 'people.edit' = ANY (v_held) THEN
        PERFORM tenancy.refuse('people_access_manage_needed', 'XC403');
      END IF;
      IF NOT v_granted <@ v_held THEN
        PERFORM tenancy.refuse('people_permission_not_held', 'XC403');
      END IF;
    END IF;
  END IF;

  -- Someone else's email or mobile number: an Owner, or an editor who sees the person's whole
  -- scope and holds everything they hold (an update already needs people.edit, which covers
  -- the approval limit).
  IF p_user_id IS NOT NULL AND NOT v_actor_is_owner
     AND (p_email IS DISTINCT FROM v_target_email OR p_phone IS DISTINCT FROM v_target_phone) THEN
    IF NOT v_reach.all_companies
       AND (v_target.all_companies
            OR NOT v_target.company_ids <@ v_reach.company_ids
            OR NOT v_target.vehicle_ids <@ v_reach.vehicle_ids) THEN
      PERFORM tenancy.refuse('people_sign_in_scope', 'XC403');
    END IF;
    IF NOT tenancy.assigned_permissions(v_organization_id, p_user_id) <@ v_held THEN
      PERFORM tenancy.refuse('people_sign_in_holdings', 'XC403');
    END IF;
  END IF;

  RETURN ROW(p_scope_mode = 'all', v_companies, v_vehicles)::tenancy.scope;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.check_person_grant(
  uuid, text, text, uuid[], uuid[], text[], numeric, text, text
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.check_person_grant(
  uuid, text, text, uuid[], uuid[], text[], numeric, text, text
) TO xcode_api_executor;
