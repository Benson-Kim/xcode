-- api.ops_seed_demo(p_operator text, p_request_id text, p_environment text, p_pins jsonb, p_now timestamptz) RETURNS jsonb
-- Purpose: in a development database, create the demo organization with its four logins, expense catalogue and six weeks of fleet history, adding only what is missing, so a second run changes nothing already there; a database holding any other organization is never seeded.
-- Callers: OpsRoutines.seed_demo; CLI seed-demo.
-- Reads: tenancy.organizations, setup.expense_categories, setup.fleet_vehicles, setup.psv_companies. Writes: ops.operator_actions, tenancy.organizations and its localization, branding and security-policy rows, tenancy.roles, and through ops.seed_demo_user, ops.seed_catalogue, ops.seed_companies and ops.seed_fleet the people, catalogue, companies, vehicles, targets, scheduled items, investments, revenue and petty-cash rows with their change log.
-- Raises: XC403 seed_development_only, XC409 organization_not_single, XC409 seed_exists.
-- Tests: tests/db/test_ops_routines.py.
-- p_pins maps a login's email to a PIN hash made by the CLI; it is set only on an account this run created, and a login missing from it has no PIN. Everything is written as the demo Owner through the business routines, at instants counted back from p_now, so the change log reads as if the organization had been used.

CREATE OR REPLACE FUNCTION api.ops_seed_demo(
  p_operator text,
  p_request_id text,
  p_environment text,
  p_pins jsonb,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organizations uuid[];
  v_organization_id uuid;
  v_created boolean := false;
  v_fleet boolean;
  v_at timestamptz;
  v_owner_id uuid;
  v_company_ids uuid[];
  v_clerk_company_id uuid;
  v_login record;
BEGIN
  PERFORM ops.record_operator_action(
    p_operator, 'seed-demo', 'demo-fleet', jsonb_build_object('request_id', p_request_id), p_now
  );

  IF p_environment IS DISTINCT FROM 'development' THEN
    PERFORM tenancy.refuse('seed_development_only', 'XC403');
  END IF;

  v_organizations := tenancy.organization_ids();
  IF cardinality(v_organizations) > 1 THEN
    PERFORM tenancy.refuse('organization_not_single', 'XC409');
  END IF;
  IF cardinality(v_organizations) = 1 THEN
    v_organization_id := v_organizations[1];
    PERFORM tenancy.enter_organization_as_operator(v_organization_id);
    IF (
      SELECT o.slug FROM tenancy.organizations AS o WHERE o.id = v_organization_id
    ) <> 'demo-fleet' THEN
      PERFORM tenancy.refuse('seed_exists', 'XC409');
    END IF;
  ELSE
    v_organization_id := gen_random_uuid();
    PERFORM tenancy.enter_organization_as_operator(v_organization_id);
    INSERT INTO tenancy.organizations (id, slug, name, created_at, updated_at)
    VALUES (
      v_organization_id, 'demo-fleet', 'Demo Fleet', p_now - make_interval(days => 43),
      p_now - make_interval(days => 43)
    );
    INSERT INTO tenancy.organization_localizations (organization_id, created_at, updated_at)
    VALUES (v_organization_id, p_now - make_interval(days => 43), p_now - make_interval(days => 43));
    INSERT INTO tenancy.organization_brandings (organization_id, created_at, updated_at)
    VALUES (v_organization_id, p_now - make_interval(days => 43), p_now - make_interval(days => 43));
    INSERT INTO tenancy.organization_security_policies (organization_id, created_at, updated_at)
    VALUES (v_organization_id, p_now - make_interval(days => 43), p_now - make_interval(days => 43));
    v_created := true;
  END IF;
  PERFORM tenancy.seed_roles(v_organization_id);

  v_fleet := NOT EXISTS (
    SELECT 1 FROM setup.fleet_vehicles AS f WHERE f.organization_id = v_organization_id
  );
  v_at := CASE WHEN v_fleet THEN p_now - make_interval(days => 42) ELSE p_now END;

  v_owner_id := ops.seed_demo_user(
    v_organization_id, NULL, p_request_id, 'antony.maina@shamayah.co.ke', '+254733520614', 'Owner',
    NULL, p_pins ->> 'antony.maina@shamayah.co.ke', v_at
  );

  IF NOT EXISTS (
    SELECT 1 FROM setup.expense_categories AS c WHERE c.organization_id = v_organization_id
  ) THEN
    PERFORM ops.seed_catalogue(v_organization_id, v_owner_id, p_request_id, v_at);
  END IF;
  IF v_fleet THEN
    v_company_ids := ops.seed_companies(v_organization_id, v_owner_id, p_request_id, v_at);
  END IF;

  SELECT c.id INTO v_clerk_company_id
  FROM setup.psv_companies AS c
  WHERE c.organization_id = v_organization_id
  ORDER BY c.normalized_name = 'ZURI GENESIS' DESC, c.name, c.id
  LIMIT 1;

  FOR v_login IN
    SELECT l.email, l.phone, l.role
    FROM (
      VALUES
        (2, 'peter.otieno@zurigenesis.co.ke', '+254722410355', 'Office admin'),
        (3, 'brian.mwangi@metrotrans.co.ke', '+254700111222', 'Fleet manager'),
        (4, 'wanjiru.kamau@zurigenesis.co.ke', '+254712345678', 'Revenue clerk')
    ) AS l (ord, email, phone, role)
    ORDER BY l.ord
  LOOP
    PERFORM ops.seed_demo_user(
      v_organization_id, v_owner_id, p_request_id, v_login.email, v_login.phone, v_login.role,
      CASE WHEN v_login.role = 'Revenue clerk' THEN v_clerk_company_id END,
      p_pins ->> v_login.email, v_at
    );
  END LOOP;

  IF v_fleet THEN
    PERFORM ops.seed_fleet(v_organization_id, v_owner_id, p_request_id, v_company_ids, p_now);
  END IF;

  RETURN jsonb_build_object('organization_id', v_organization_id, 'created', v_created);
END;
$$;
