-- tenancy.insert_organization_with_free_slug(p_id uuid, p_base_slug text, p_name text, p_demo boolean, p_at timestamptz) RETURNS void
-- Purpose: insert the organization row under p_base_slug, or the first free p_base_slug-2, p_base_slug-3 and so on when another organization holds it, so a slug clash never surfaces as a unique violation; the one place that rule lives, for the real organization and the demo one alike.
-- Callers: api.ops_provision_user, ops.seed_demo_organization (each has entered p_id as the operator first).
-- Reads: tenancy.organizations (the slug index). Writes: tenancy.organizations.
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py, tests/db/test_review_account.py.
-- Other organizations' rows are invisible under row-level security, so the slug index decides; each taken slug belongs to another organization, so the search ends. Two runs at once on the same slug are not serialised here: the demo creators hold the demo-organization advisory lock.

CREATE OR REPLACE FUNCTION tenancy.insert_organization_with_free_slug(
  p_id uuid,
  p_base_slug text,
  p_name text,
  p_demo boolean,
  p_at timestamptz
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_slug text := p_base_slug;
  v_tries integer := 1;
BEGIN
  LOOP
    INSERT INTO tenancy.organizations (id, slug, name, demo, created_at, updated_at)
    VALUES (p_id, v_slug, p_name, p_demo, p_at, p_at)
    ON CONFLICT (slug) DO NOTHING;
    EXIT WHEN FOUND;
    v_tries := v_tries + 1;
    v_slug := p_base_slug || '-' || v_tries;
  END LOOP;
END;
$$;

REVOKE ALL ON FUNCTION tenancy.insert_organization_with_free_slug(uuid, text, text, boolean, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.insert_organization_with_free_slug(uuid, text, text, boolean, timestamptz) TO xcode_api_executor;
