-- tenancy.person_document(p_user_id uuid, p_viewer tenancy.scope) RETURNS jsonb
-- Purpose: the person document the people routines return: the membership, sign-in details, role, scope mode, the companies and vehicles inside the viewer's reach with counts of the rest, the assigned catalogue permissions (kept for inactive people), approval limit, has_pin, version, the people status and last sign-in, how far back they may change records (back_limit and its words can_change), one access chip per catalogue module they reach ({name, held, total}), whether they hold every right, and sign_in null (api.people_get fills it).
-- Callers: api.people_list, api.people_get.
-- Reads: tenancy.memberships, identity.users, tenancy.permissions, and what tenancy.role_of, tenancy.scope_mode, tenancy.person_scope, tenancy.assigned_permissions and tenancy.back_limit_words read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_access_routines.py.

CREATE OR REPLACE FUNCTION tenancy.person_document(p_user_id uuid, p_viewer tenancy.scope)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.current_organization();
  v_scope tenancy.scope := tenancy.person_scope(p_user_id);
  v_companies uuid[];
  v_vehicles uuid[];
  v_held text[] := tenancy.assigned_permissions(tenancy.current_organization(), p_user_id);
  v_modules jsonb;
  v_held_count integer;
  v_document jsonb;
BEGIN
  IF p_viewer.all_companies THEN
    v_companies := v_scope.company_ids;
    v_vehicles := v_scope.vehicle_ids;
  ELSE
    v_companies := ARRAY(
      SELECT held.id FROM unnest(v_scope.company_ids) AS held (id)
      WHERE held.id = ANY (p_viewer.company_ids) ORDER BY held.id
    );
    v_vehicles := ARRAY(
      SELECT held.id FROM unnest(v_scope.vehicle_ids) AS held (id)
      WHERE held.id = ANY (p_viewer.vehicle_ids) ORDER BY held.id
    );
  END IF;

  SELECT coalesce(
           jsonb_agg(
             jsonb_build_object('name', modules.name, 'held', modules.held, 'total', modules.total)
             ORDER BY modules.group_order
           ) FILTER (WHERE modules.held > 0),
           '[]'::jsonb
         ),
         coalesce(sum(modules.held), 0)
  INTO v_modules, v_held_count
  FROM (
    SELECT p.group_order,
           min(p.group_name) AS name,
           count(*) FILTER (WHERE p.key = ANY (v_held))::integer AS held,
           count(*)::integer AS total
    FROM tenancy.permissions AS p
    WHERE p.catalogue
    GROUP BY p.group_order
  ) AS modules;

  SELECT jsonb_build_object(
           'id', m.user_id,
           'first_name', m.first_name,
           'last_name', m.last_name,
           'email', u.email,
           'phone_number', u.phone_number,
           'role', tenancy.role_of(m.user_id),
           'active', m.active,
           'scope_mode', tenancy.scope_mode(m.organization_id, m.user_id),
           'company_ids', to_jsonb(v_companies),
           'vehicle_ids', to_jsonb(v_vehicles),
           'permissions', (
             SELECT coalesce(jsonb_agg(p.key ORDER BY p.group_order, p.item_order), '[]'::jsonb)
             FROM tenancy.permissions AS p
             WHERE p.catalogue AND p.key = ANY (v_held)
           ),
           'approval_limit', m.approval_limit,
           'has_pin', u.pin_hash IS NOT NULL,
           'version', m.version,
           'other_companies', cardinality(v_scope.company_ids) - cardinality(v_companies),
           'other_vehicles', cardinality(v_scope.vehicle_ids) - cardinality(v_vehicles),
           'status', identity.sign_in_status(u, m.active),
           'last_signed_in_at', u.last_signed_in_at,
           'back_limit', jsonb_build_object(
             'mode', m.back_limit_mode,
             'count', m.back_limit_count,
             'from_date', m.back_limit_from
           ),
           'can_change', tenancy.back_limit_words(
             m.back_limit_mode, m.back_limit_count, m.back_limit_from
           ),
           'modules', v_modules,
           'everything', v_held_count = (SELECT count(*) FROM tenancy.permissions WHERE catalogue),
           'sign_in', NULL
         )
  INTO v_document
  FROM tenancy.memberships AS m
  JOIN identity.users AS u ON u.id = m.user_id
  WHERE m.organization_id = v_organization_id AND m.user_id = p_user_id;
  RETURN v_document;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.person_document(uuid, tenancy.scope) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.person_document(uuid, tenancy.scope) TO xcode_api_executor;
