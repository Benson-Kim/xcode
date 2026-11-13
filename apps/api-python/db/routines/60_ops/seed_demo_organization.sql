-- ops.seed_demo_organization(p_at timestamptz) RETURNS uuid
-- Purpose: create the demo organization "Demo Fleet" flagged as demo, with slug demo-fleet, or the first free demo-fleet-2, demo-fleet-3 and so on when another organization holds it (a real one may choose that slug), with its default localization, branding and security-policy rows and the seeded roles, created at p_at, and enter it as the operator; the one place an organization is created with the demo flag.
-- Callers: api.ops_seed_demo, api.ops_review_account_create (each holds the demo-organization advisory lock first).
-- Reads: what tenancy.insert_organization_with_free_slug and tenancy.seed_roles read. Writes: tenancy.organizations (through tenancy.insert_organization_with_free_slug), tenancy.organization_localizations, tenancy.organization_brandings, tenancy.organization_security_policies, tenancy.roles.
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py, tests/db/test_review_account.py.
-- The slug search is tenancy.insert_organization_with_free_slug.

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
  PERFORM tenancy.insert_organization_with_free_slug(v_organization_id, 'demo-fleet', 'Demo Fleet', true, p_at);
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
