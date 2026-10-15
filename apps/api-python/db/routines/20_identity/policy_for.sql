-- identity.policy_for(p_user_id uuid) RETURNS identity.policy
-- Purpose: the security policy (clamped into its bounds; defaults when no row) and the token claims of the user's single active membership; NULL when there is no active membership or no role, so no token is ever issued.
-- Callers: api.auth_account_lookup, api.auth_sign_in, api.auth_verify_device, api.auth_complete_pin, api.auth_refresh.
-- Reads: tenancy.memberships, tenancy.person_roles, tenancy.roles, tenancy.organization_security_policies, and what tenancy.effective_permissions reads. Writes: nothing (sets the transaction-local organization setting to the membership's organization).
-- Raises: none.
-- Tests: tests/db/test_identity_helpers.py.

CREATE OR REPLACE FUNCTION identity.policy_for(p_user_id uuid)
RETURNS identity.policy
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := identity.active_organization(p_user_id);
  v_first_name text;
  v_last_name text;
  v_role_name text;
  v_pin_length integer;
  v_lockout_threshold integer;
  v_lockout_minutes integer;
  v_access_token_minutes integer;
  v_refresh_token_days integer;
BEGIN
  IF v_organization_id IS NULL THEN
    RETURN NULL;
  END IF;
  -- The membership's rows are tenant rows: read them under that organization's setting.
  PERFORM set_config('xcode.organization_id', v_organization_id::text, true);

  SELECT m.first_name, m.last_name INTO v_first_name, v_last_name
  FROM tenancy.memberships AS m
  WHERE m.organization_id = v_organization_id AND m.user_id = p_user_id AND m.active;
  IF NOT FOUND THEN
    RETURN NULL;
  END IF;

  SELECT r.name INTO v_role_name
  FROM tenancy.person_roles AS pr
  JOIN tenancy.roles AS r ON r.organization_id = pr.organization_id AND r.id = pr.role_id
  WHERE pr.organization_id = v_organization_id AND pr.user_id = p_user_id;
  IF v_role_name IS NULL THEN
    RETURN NULL;
  END IF;

  SELECT s.pin_length, s.lockout_threshold, s.lockout_minutes, s.access_token_minutes,
         s.refresh_token_days
  INTO v_pin_length, v_lockout_threshold, v_lockout_minutes, v_access_token_minutes,
       v_refresh_token_days
  FROM tenancy.organization_security_policies AS s
  WHERE s.organization_id = v_organization_id;

  RETURN ROW(
    v_organization_id,
    least(greatest(coalesce(v_pin_length, 4), 4), 8),
    least(greatest(coalesce(v_lockout_threshold, 5), 3), 10),
    least(greatest(coalesce(v_lockout_minutes, 15), 1), 60),
    least(greatest(coalesce(v_access_token_minutes, 10), 1), 15),
    least(greatest(coalesce(v_refresh_token_days, 30), 1), 90),
    v_role_name,
    v_first_name,
    v_last_name,
    tenancy.effective_permissions(v_organization_id, p_user_id)
  )::identity.policy;
END;
$$;

REVOKE ALL ON FUNCTION identity.policy_for(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.policy_for(uuid) TO xcode_api_executor;
