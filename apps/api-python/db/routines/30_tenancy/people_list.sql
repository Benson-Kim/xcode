-- api.people_list(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_page integer, p_page_size integer, p_role text, p_status text, p_now timestamptz) RETURNS jsonb
-- Purpose: one page of the people the actor may see (members with a role, tenancy.people_visible), kept to one role by name (letter case ignored, as role names are unique that way) and to one people status (identity.sign_in_status: active, not_signed_in, pin_reset_due, locked, blocked; the released words waiting and none stand for not_signed_in and blocked; blank or all keeps everyone), ordered by last name, first name and user id, as person documents; {total, items}.
-- Callers: TenancyRoutines.list_people; ListPeople (GET /setup/people).
-- Reads: tenancy.memberships, tenancy.person_roles, tenancy.roles, identity.users, and what tenancy.people_visible, tenancy.person_reach and tenancy.person_document read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 page_out_of_range via tenancy.check_page, XC422 people_filter_status_invalid (after the page check, as .NET reads the state inside the request).
-- Tests: tests/db/test_access_routines.py, tests/api/test_people.py.

CREATE OR REPLACE FUNCTION api.people_list(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_page integer,
  p_page_size integer,
  p_role text,
  p_status text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_viewer tenancy.scope;
  v_status text;
  v_total bigint;
  v_items jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'people.view');
  PERFORM tenancy.check_page(p_page, p_page_size);
  IF p_status IS NOT NULL AND p_status NOT IN (
    '', 'all', 'active', 'not_signed_in', 'pin_reset_due', 'locked', 'blocked', 'waiting', 'none'
  ) THEN
    PERFORM tenancy.refuse('people_filter_status_invalid', 'XC422');
  END IF;
  v_status := CASE p_status
                WHEN 'waiting' THEN 'not_signed_in'
                WHEN 'none' THEN 'blocked'
                WHEN 'all' THEN NULL
                WHEN '' THEN NULL
                ELSE p_status
              END;
  v_viewer := tenancy.person_reach(p_actor_id);

  WITH listed AS (
    SELECT m.user_id, m.last_name, m.first_name
    FROM tenancy.memberships AS m
    JOIN tenancy.person_roles AS pr
      ON pr.organization_id = m.organization_id AND pr.user_id = m.user_id
    JOIN tenancy.roles AS r
      ON r.organization_id = pr.organization_id AND r.id = pr.role_id
    JOIN identity.users AS u
      ON u.id = m.user_id
    WHERE m.organization_id = p_organization_id
      AND m.user_id IN (SELECT visible.id FROM tenancy.people_visible(p_actor_id) AS visible (id))
      AND (coalesce(p_role, '') IN ('', 'all') OR lower(r.name) = lower(p_role))
      AND (v_status IS NULL OR identity.sign_in_status(u, m.active) = v_status)
  ),
  page AS (
    SELECT listed.user_id, listed.last_name, listed.first_name
    FROM listed
    ORDER BY listed.last_name, listed.first_name, listed.user_id
    OFFSET (p_page - 1) * p_page_size
    LIMIT p_page_size
  )
  SELECT (SELECT count(*) FROM listed),
         (SELECT coalesce(
                   jsonb_agg(tenancy.person_document(page.user_id, v_viewer)
                             ORDER BY page.last_name, page.first_name, page.user_id),
                   '[]'::jsonb)
          FROM page)
  INTO v_total, v_items;

  RETURN jsonb_build_object('total', v_total, 'items', v_items);
END;
$$;
