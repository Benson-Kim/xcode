-- tenancy.person_snapshot(p_user_id uuid) RETURNS json
-- Purpose: the change-log snapshot of a person, compact JSON with the .NET keys FirstName, LastName, Email, PhoneNumber, Role, Active, ScopeMode, CompanyIds, VehicleIds, Permissions (ordinal order), ApprovalLimit, BackLimitMode, BackLimitCount, BackLimitFrom (yyyy-MM-dd), Name (the computed "First Last" the .NET record serialised last); ids sorted.
-- Callers: tenancy.save_person, api.people_set_active.
-- Reads: tenancy.memberships, identity.users, and what tenancy.role_of, tenancy.scope_mode, tenancy.person_scope and tenancy.assigned_permissions read. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_access_routines.py.

CREATE OR REPLACE FUNCTION tenancy.person_snapshot(p_user_id uuid)
RETURNS json
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.current_organization();
  v_scope tenancy.scope := tenancy.person_scope(p_user_id);
  v_snapshot json;
BEGIN
  SELECT json_build_object(
           'FirstName', m.first_name,
           'LastName', m.last_name,
           'Email', u.email,
           'PhoneNumber', u.phone_number,
           'Role', tenancy.role_of(m.user_id),
           'Active', m.active,
           'ScopeMode', tenancy.scope_mode(m.organization_id, m.user_id),
           'CompanyIds', to_json(v_scope.company_ids),
           'VehicleIds', to_json(v_scope.vehicle_ids),
           'Permissions', (
             SELECT coalesce(json_agg(granted.key ORDER BY granted.key COLLATE "C"), '[]'::json)
             FROM unnest(tenancy.assigned_permissions(m.organization_id, m.user_id)) AS granted (key)
           ),
           'ApprovalLimit', trim_scale(m.approval_limit),
           'BackLimitMode', m.back_limit_mode,
           'BackLimitCount', m.back_limit_count,
           'BackLimitFrom', to_char(m.back_limit_from, 'YYYY-MM-DD'),
           'Name', m.first_name || ' ' || m.last_name
         )
  INTO v_snapshot
  FROM tenancy.memberships AS m
  JOIN identity.users AS u ON u.id = m.user_id
  WHERE m.organization_id = v_organization_id AND m.user_id = p_user_id;
  RETURN tenancy.compact_json(coalesce(v_snapshot, 'null'::json));
END;
$$;

REVOKE ALL ON FUNCTION tenancy.person_snapshot(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.person_snapshot(uuid) TO xcode_api_executor;
