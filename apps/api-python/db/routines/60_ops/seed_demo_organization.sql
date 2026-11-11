-- ops.seed_demo_organization(p_at timestamptz) RETURNS uuid
-- Purpose: create the demo organization "Demo Fleet" (slug demo-fleet) flagged as demo, with its default localization, branding and security-policy rows and the seeded roles, created at p_at, and enter it as the operator; the one place an organization is created with the demo flag.
-- Callers: api.ops_seed_demo, api.ops_review_account_create.
-- Reads: what tenancy.seed_roles reads. Writes: tenancy.organizations, tenancy.organization_localizations, tenancy.organization_brandings, tenancy.organization_security_policies, tenancy.roles.
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py, tests/db/test_review_account.py.

CREATE OR REPLACE FUNCTION ops.seed_demo_organization(p_at timestamptz)
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := gen_random_uuid();
BEGIN
  PERFORM tenancy.enter_organization_as_operator(v_organization_id);
  INSERT INTO tenancy.organizations (id, slug, name, demo, created_at, updated_at)
  VALUES (v_organization_id, 'demo-fleet', 'Demo Fleet', true, p_at, p_at);
  INSERT INTO tenancy.organization_localizations (organization_id, created_at, updated_at)
  VALUES (v_organization_id, p_at, p_at);
  INSERT INTO tenancy.organization_brandings (organization_id, created_at, updated_at)
  VALUES (v_organization_id, p_at, p_at);
  INSERT INTO tenancy.organization_security_policies (organization_id, created_at, updated_at)
  VALUES (v_organization_id, p_at, p_at);
  PERFORM tenancy.seed_roles(v_organization_id);
  RETURN v_organization_id;
END;
$$;

REVOKE ALL ON FUNCTION ops.seed_demo_organization(timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ops.seed_demo_organization(timestamptz) TO xcode_api_executor;
