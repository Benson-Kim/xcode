-- tenancy.refuse_role_in_use(p_role tenancy.roles) RETURNS void
-- Purpose: refuse a role that anyone in its organization holds, active or blocked, with in_use naming the role and how many people hold it ("1 person", "3 people"); return when nobody does.
-- Callers: api.access_role_delete.
-- Reads: tenancy.person_roles. Writes: nothing.
-- Raises: XC409 in_use.
-- Tests: tests/db/test_role_routines.py.

CREATE OR REPLACE FUNCTION tenancy.refuse_role_in_use(p_role tenancy.roles)
RETURNS void
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_holders bigint;
BEGIN
  SELECT count(*) INTO v_holders
  FROM tenancy.person_roles AS pr
  WHERE pr.organization_id = p_role.organization_id AND pr.role_id = p_role.id;
  IF v_holders > 0 THEN
    PERFORM tenancy.refuse(
      'in_use', 'XC409',
      jsonb_build_object(
        'name', p_role.name,
        'use', 'role_people',
        'people', v_holders || CASE WHEN v_holders = 1 THEN ' person' ELSE ' people' END
      )
    );
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.refuse_role_in_use(tenancy.roles) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.refuse_role_in_use(tenancy.roles) TO xcode_api_executor;
