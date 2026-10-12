-- tenancy.logo_snapshot() RETURNS json
-- Purpose: the change-log snapshot of the current organization's logo, its shape only and never the image: compact {"contentType", "bytes", "updatedAt"}, or null when there is no logo.
-- Callers: api.organization_logo_set, api.organization_logo_delete.
-- Reads: tenancy.organization_logos. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_organization_routines.py.

CREATE OR REPLACE FUNCTION tenancy.logo_snapshot()
RETURNS json
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_snapshot json;
BEGIN
  SELECT json_build_object(
           'contentType', g.content_type,
           'bytes', octet_length(g.data),
           'updatedAt', tenancy.fmt_instant(g.updated_at)
         )
  INTO v_snapshot
  FROM tenancy.organization_logos AS g
  WHERE g.organization_id = tenancy.current_organization();
  RETURN tenancy.compact_json(coalesce(v_snapshot, 'null'::json));
END;
$$;

REVOKE ALL ON FUNCTION tenancy.logo_snapshot() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION tenancy.logo_snapshot() TO xcode_api_executor;
