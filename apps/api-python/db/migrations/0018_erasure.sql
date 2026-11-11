-- Erasure: an account can be erased after its person asked for deletion and was blocked. identity.users gains erased_at; email and phone_number become optional, and each is cleared exactly when the account is erased, which also keeps it removed with no PIN. tenancy.erase_person_history rewrites the people and sign-in history of an erased person in the current organization: names become "Former member" and the email and mobile number are cleared. It is owned by the migration owner because the service role may only add history rows; it touches nothing for an account that is not erased or an organization other than the current one, and calls only built-ins and this file's helpers. identity.erase_review_login deletes the App Review sign-in code of an erased account (credential material the service role may not delete). tenancy.belongs_elsewhere tells whether a member of the current organization also belongs to another one, which row-level security hides from the service role; an account shared by two organizations is never erased.

SET LOCAL lock_timeout = '10s';

ALTER TABLE identity.users
  ADD COLUMN erased_at timestamptz,
  ALTER COLUMN email DROP NOT NULL,
  ALTER COLUMN phone_number DROP NOT NULL,
  ADD CONSTRAINT ck_users_erased_email CHECK ((erased_at IS NULL) = (email IS NOT NULL)),
  ADD CONSTRAINT ck_users_erased_phone_number CHECK ((erased_at IS NULL) = (phone_number IS NOT NULL)),
  ADD CONSTRAINT ck_users_erased_removed CHECK (
    erased_at IS NULL OR (status = 'removed' AND pin_hash IS NULL)
  );

CREATE FUNCTION tenancy.erased_snapshot(p_snapshot text)
RETURNS text
LANGUAGE sql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT CASE
    WHEN p_snapshot IS NULL OR json_typeof(p_snapshot::json) <> 'object' THEN p_snapshot
    ELSE (
      SELECT '{' || coalesce(string_agg(
               to_json(e.key)::text || ':' || CASE
                 WHEN e.key IN ('FirstName', 'first_name') THEN '"Former"'
                 WHEN e.key IN ('LastName', 'last_name') THEN '"member"'
                 WHEN e.key IN ('Name', 'requester_name') THEN '"Former member"'
                 WHEN e.key IN ('Email', 'PhoneNumber', 'email', 'phone_number') THEN 'null'
                 ELSE e.value::text
               END,
               ',' ORDER BY e.ord), '') || '}'
      FROM json_each(p_snapshot::json) WITH ORDINALITY AS e (key, value, ord)
    )
  END;
$$;

REVOKE ALL ON FUNCTION tenancy.erased_snapshot(text) FROM PUBLIC;

CREATE FUNCTION tenancy.erase_person_history(p_organization_id uuid, p_user_id uuid)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_name text;
BEGIN
  IF p_organization_id IS NULL
     OR p_organization_id IS DISTINCT FROM tenancy.current_organization()
     OR NOT EXISTS (
       SELECT 1 FROM identity.users AS u WHERE u.id = p_user_id AND u.erased_at IS NOT NULL
     ) THEN
    RETURN;
  END IF;
  SELECT m.first_name || ' ' || m.last_name INTO v_name
  FROM tenancy.memberships AS m
  WHERE m.organization_id = p_organization_id AND m.user_id = p_user_id;

  UPDATE tenancy.change_log AS c
  SET before = tenancy.erased_snapshot(c.before),
      after = tenancy.erased_snapshot(c.after),
      reason = CASE
                 WHEN v_name IS NULL OR v_name = 'Former member' THEN c.reason
                 ELSE left(replace(c.reason, v_name, 'Former member'), 500)
               END
  WHERE c.organization_id = p_organization_id
    AND c.entity_id = p_user_id
    AND c.section IN ('people', 'signIn');

  UPDATE tenancy.audit_events AS a
  SET before = tenancy.erased_snapshot(a.before::text)::jsonb,
      after = tenancy.erased_snapshot(a.after::text)::jsonb
  WHERE a.organization_id = p_organization_id
    AND a.entity = p_user_id::text;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.erase_person_history(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.erase_person_history(uuid, uuid) TO xcode_api_executor;

CREATE FUNCTION identity.erase_review_login(p_user_id uuid)
RETURNS void
LANGUAGE sql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
  DELETE FROM identity.review_accounts AS r
  WHERE r.user_id = p_user_id
    AND EXISTS (SELECT 1 FROM identity.users AS u WHERE u.id = p_user_id AND u.erased_at IS NOT NULL);
$$;

REVOKE ALL ON FUNCTION identity.erase_review_login(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION identity.erase_review_login(uuid) TO xcode_api_executor;

CREATE FUNCTION tenancy.belongs_elsewhere(p_organization_id uuid, p_user_id uuid)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT p_organization_id IS NOT NULL
     AND p_organization_id IS NOT DISTINCT FROM tenancy.current_organization()
     AND EXISTS (
       SELECT 1 FROM tenancy.memberships AS m
       WHERE m.organization_id = p_organization_id AND m.user_id = p_user_id
     )
     AND EXISTS (
       SELECT 1 FROM tenancy.memberships AS m
       WHERE m.user_id = p_user_id AND m.organization_id <> p_organization_id
     );
$$;

REVOKE ALL ON FUNCTION tenancy.belongs_elsewhere(uuid, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.belongs_elsewhere(uuid, uuid) TO xcode_api_executor;
