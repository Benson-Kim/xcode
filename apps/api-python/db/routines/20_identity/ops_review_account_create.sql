-- api.ops_review_account_create(p_operator text, p_request_id text, p_email text, p_phone text, p_pin_hash text, p_code_hash text, p_now timestamptz) RETURNS jsonb
-- Purpose: create or renew the App Review login in the database's single organization, which must be flagged as demo: an Owner added by the demo Owner with no invitation, whose PIN hash and fixed new-device code digest replace any earlier ones; a renewal also ends every session and device and clears the wrong-PIN counters.
-- Callers: OpsRoutines.create_review_account; CLI review-account create.
-- Reads: identity.users, identity.review_accounts, tenancy.organizations, tenancy.memberships, tenancy.roles, tenancy.person_roles. Writes: ops.operator_actions, identity.review_accounts, identity.users, identity.trusted_devices, identity.refresh_tokens, and what ops.seed_demo_user writes.
-- Raises: XC422 people_email_invalid, XC422 people_phone_invalid, XC409 organization_not_single, XC403 review_demo_only, XC409 people_contact_taken, XC409 review_phone_differs.
-- Tests: tests/db/test_review_account.py, tests/api/test_cli.py.
-- The email names the login: one that belongs to a person who is not a review login is refused, and a renewal must give the phone the login already has. identity.matching_code accepts the code only after the PIN was right on the device.

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
  v_organizations uuid[];
  v_organization_id uuid;
  v_owner_id uuid;
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

  v_organizations := tenancy.organization_ids();
  IF cardinality(v_organizations) > 1 THEN
    PERFORM tenancy.refuse('organization_not_single', 'XC409');
  END IF;
  v_organization_id := v_organizations[1];
  IF v_organization_id IS NULL THEN
    PERFORM tenancy.refuse('review_demo_only', 'XC403');
  END IF;
  PERFORM tenancy.enter_organization_as_operator(v_organization_id);
  IF NOT (SELECT o.demo FROM tenancy.organizations AS o WHERE o.id = v_organization_id) THEN
    PERFORM tenancy.refuse('review_demo_only', 'XC403');
  END IF;

  SELECT pr.user_id INTO v_owner_id
  FROM tenancy.person_roles AS pr
  JOIN tenancy.roles AS r ON r.id = pr.role_id
  JOIN tenancy.memberships AS m
    ON m.organization_id = pr.organization_id AND m.user_id = pr.user_id AND m.active
  JOIN identity.users AS u ON u.id = pr.user_id AND u.status = 'active'
  WHERE pr.organization_id = v_organization_id
    AND r.name = 'Owner'
    AND NOT EXISTS (SELECT 1 FROM identity.review_accounts AS ra WHERE ra.user_id = pr.user_id)
  ORDER BY m.created_at, pr.user_id
  LIMIT 1;
  IF v_owner_id IS NULL THEN
    PERFORM tenancy.refuse('review_demo_only', 'XC403');
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
  END IF;

  v_user_id := ops.seed_demo_user(
    v_organization_id, v_owner_id, p_request_id, v_email, v_phone, 'Owner', NULL, p_pin_hash, p_now
  );

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
    'user_id', v_user_id, 'organization_id', v_organization_id, 'created_user', v_created
  );
END;
$$;
