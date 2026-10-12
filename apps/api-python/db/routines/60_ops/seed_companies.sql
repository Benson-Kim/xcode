-- ops.seed_companies(p_organization_id uuid, p_owner_id uuid, p_request_id text, p_at timestamptz) RETURNS uuid[]
-- Purpose: make sure the two demo companies exist as the Owner, found by name or added through api.setup_company_create, and return their ids in the order of the vehicle plan.
-- Callers: api.ops_seed_demo.
-- Reads: setup.psv_companies. Writes: what api.setup_company_create writes.
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py.

CREATE OR REPLACE FUNCTION ops.seed_companies(
  p_organization_id uuid,
  p_owner_id uuid,
  p_request_id text,
  p_at timestamptz
)
RETURNS uuid[]
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_name text;
  v_id uuid;
  v_ids uuid[] := '{}';
BEGIN
  FOREACH v_name IN ARRAY ARRAY['Zuri Genesis', 'Metro Trans'] LOOP
    SELECT c.id INTO v_id
    FROM setup.psv_companies AS c
    WHERE c.organization_id = p_organization_id AND c.normalized_name = upper(v_name COLLATE "C");
    IF v_id IS NULL THEN
      v_id := (
        api.setup_company_create(p_owner_id, p_organization_id, p_request_id, v_name, NULL, p_at)
      ).id;
    END IF;
    v_ids := v_ids || v_id;
  END LOOP;
  RETURN v_ids;
END;
$$;

REVOKE ALL ON FUNCTION ops.seed_companies(uuid, uuid, text, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ops.seed_companies(uuid, uuid, text, timestamptz) TO xcode_api_executor;
