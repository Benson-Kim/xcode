-- api.access_catalog_list(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_now timestamptz) RETURNS jsonb
-- Purpose: the permission catalogue for any member: the catalogue groups in order, each with its items (key, label, the permissions it directly needs in catalogue order, the petty-cash section or null); retired and hidden keys are left out.
-- Callers: TenancyRoutines.access_catalog; GetAccessCatalog (GET /setup/access/catalog).
-- Reads: tenancy.permissions, tenancy.permission_dependencies. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization.
-- Tests: tests/db/test_access_routines.py, tests/api/test_access.py.

CREATE OR REPLACE FUNCTION api.access_catalog_list(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  RETURN (
    SELECT coalesce(jsonb_agg(grouped.document ORDER BY grouped.group_order), '[]'::jsonb)
    FROM (
      SELECT p.group_order,
             jsonb_build_object(
               'name', min(p.group_name),
               'items', jsonb_agg(
                 jsonb_build_object(
                   'key', p.key,
                   'label', p.label,
                   'section', p.section,
                   'needs', (
                     SELECT coalesce(jsonb_agg(d.needs ORDER BY n.group_order, n.item_order), '[]'::jsonb)
                     FROM tenancy.permission_dependencies AS d
                     JOIN tenancy.permissions AS n ON n.key = d.needs
                     WHERE d.permission = p.key
                   )
                 )
                 ORDER BY p.item_order
               )
             ) AS document
      FROM tenancy.permissions AS p
      WHERE p.catalogue
      GROUP BY p.group_order
    ) AS grouped
  );
END;
$$;
