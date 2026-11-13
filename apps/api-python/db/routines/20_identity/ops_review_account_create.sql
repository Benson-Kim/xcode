-- api.ops_review_account_create(p_operator text, p_request_id text, p_email text, p_phone text, p_pin_hash text, p_code_hash text, p_now timestamptz) RETURNS jsonb
-- Purpose: create or renew the App Review login, an Owner of the database's one demo organization, whose PIN hash and fixed new-device code digest replace any earlier ones; a renewal also ends every session and device and clears the wrong-PIN counters. When no demo organization exists, it is created beside any real one (ops.seed_demo_organization) with the login as its first Owner and the made-up catalogue, companies and six weeks of fleet history of the demo seed, written as that login.
-- Callers: OpsRoutines.create_review_account; CLI review-account create.
-- Reads: identity.users, identity.review_accounts, tenancy.memberships, tenancy.roles, tenancy.person_roles, and what tenancy.organization_ids_where_demo reads. Writes: ops.operator_actions, identity.review_accounts, identity.users, identity.trusted_devices, identity.refresh_tokens, and what ops.seed_demo_organization, ops.seed_demo_user, ops.seed_catalogue, ops.seed_companies and ops.seed_fleet write.
-- Raises: XC422 people_email_invalid, XC422 people_phone_invalid, XC409 organization_not_single, XC409 people_contact_taken, XC409 review_phone_differs.
-- Tests: tests/db/test_review_account.py, tests/api/test_cli.py.
-- Two runs at once make one demo organization: the demo-organization advisory transaction lock, which api.ops_seed_demo also takes, is held before the demo organization is looked for, so a later run waits and then uses the one the first created.
-- The email names the login: an email or phone that belongs to a person who is not a review login is refused, and a renewal must give the phone the login already has. A login added to an existing demo organization is added by its first Owner who is not a review login, else by its first Owner. identity.matching_code accepts the code only after the PIN was right on the device.

CREATE OR REPLACE FUNCTION api.ops_review_account_create(
  p_operator text,
  p_request_id text,
  p_email text,
  p_phone text,
  p_pin_hash text,
  p_code_hash text,
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
  v_demo uuid[];
  v_organization_id uuid;
  v_created_organization boolean;
  v_at timestamptz := p_now;
  v_owner_id uuid;
  v_company_ids uuid[];
  v_user identity.users;
  v_created boolean;
  v_user_id uuid;
BEGIN
  PERFORM ops.record_operator_action(
    p_operator, 'review-account', v_email, jsonb_build_object('request_id', p_request_id), p_now
  );

  IF identity.normalize_email(v_email) IS NULL THEN
    PERFORM tenancy.refuse('people_email_invalid', 'XC422');
  END IF;
  IF v_phone IS NULL THEN
    PERFORM tenancy.refuse('people_phone_invalid', 'XC422');
  END IF;

  PERFORM pg_advisory_xact_lock(hashtext('demo-organization'));
  v_demo := tenancy.organization_ids_where_demo(true);
  IF cardinality(v_demo) > 1 THEN
    PERFORM tenancy.refuse('organization_not_single', 'XC409');
  END IF;

  SELECT u.* INTO v_user FROM identity.users AS u WHERE u.email = v_email FOR UPDATE;
  v_created := v_user.id IS NULL;
  IF NOT v_created THEN
    IF NOT EXISTS (SELECT 1 FROM identity.review_accounts AS ra WHERE ra.user_id = v_user.id) THEN
      PERFORM tenancy.refuse('people_contact_taken', 'XC409');
    END IF;
    IF v_user.phone_number <> v_phone THEN
      PERFORM tenancy.refuse('review_phone_differs', 'XC409');
    END IF;
  ELSIF EXISTS (SELECT 1 FROM identity.users AS u WHERE u.phone_number = v_phone) THEN
    PERFORM tenancy.refuse('people_contact_taken', 'XC409');
  END IF;

  v_created_organization := cardinality(v_demo) = 0;
  IF v_created_organization THEN
    v_at := p_now - make_interval(days => 42);
    v_organization_id := ops.seed_demo_organization(p_now - make_interval(days => 43));
  ELSE
    v_organization_id := v_demo[1];
    PERFORM tenancy.enter_organization_as_operator(v_organization_id);
    SELECT pr.user_id INTO v_owner_id
    FROM tenancy.person_roles AS pr
    JOIN tenancy.roles AS r ON r.id = pr.role_id
    JOIN tenancy.memberships AS m
      ON m.organization_id = pr.organization_id AND m.user_id = pr.user_id AND m.active
    JOIN identity.users AS u ON u.id = pr.user_id AND u.status = 'active'
    WHERE pr.organization_id = v_organization_id
      AND r.name = 'Owner'
      AND pr.user_id IS DISTINCT FROM v_user.id
    ORDER BY EXISTS (SELECT 1 FROM identity.review_accounts AS ra WHERE ra.user_id = pr.user_id),
             m.created_at, pr.user_id
    LIMIT 1;
  END IF;

  v_user_id := ops.seed_demo_user(
    v_organization_id, v_owner_id, p_request_id, v_email, v_phone, 'Owner', NULL, p_pin_hash, v_at
  );

  IF v_created_organization THEN
    PERFORM ops.seed_catalogue(v_organization_id, v_user_id, p_request_id, v_at);
    v_company_ids := ops.seed_companies(v_organization_id, v_user_id, p_request_id, v_at);
    PERFORM ops.seed_fleet(v_organization_id, v_user_id, p_request_id, v_company_ids, p_now);
  END IF;

  IF NOT v_created THEN
    UPDATE identity.users
    SET pin_hash = p_pin_hash, failed_attempts = 0, untrusted_failed_attempts = 0,
        pin_reset_required = false, security_version = security_version + 1
    WHERE id = v_user_id;
    PERFORM identity.revoke_devices(v_user_id);
    PERFORM identity.revoke_tokens(v_user_id);
    PERFORM identity.touch_version(v_user_id);
  END IF;

  INSERT INTO identity.review_accounts (user_id, code_hash, created_at, updated_at)
  VALUES (v_user_id, p_code_hash, p_now, p_now)
  ON CONFLICT (user_id) DO UPDATE
  SET code_hash = EXCLUDED.code_hash, updated_at = EXCLUDED.updated_at;

  RETURN jsonb_build_object(
    'user_id', v_user_id,
    'organization_id', v_organization_id,
    'created_user', v_created,
    'created_organization', v_created_organization
  );
END;
$$;
