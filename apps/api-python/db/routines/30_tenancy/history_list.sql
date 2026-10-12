-- api.history_list(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_page integer, p_page_size integer, p_section text, p_from date, p_to date, p_text text, p_before bigint, p_include_total boolean, p_now timestamptz) RETURNS jsonb
-- Purpose: the change log newest first, filtered by section, organization-zone days and text, paged by offset or by seeking below a version, limited to what the actor may see (people snapshots redacted for scoped viewers); {items, total, has_more, next_before}.
-- Callers: TenancyRoutines.list_history; ListHistory (GET /setup/history).
-- Reads: tenancy.change_log, tenancy.memberships, setup.recurring_versions, setup.recurring_allocations, and what tenancy.settings_document, tenancy.actor_scope, tenancy.has_permission, tenancy.people_visible, tenancy.person_reach, setup.visible_vehicles and setup.visible_companies read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 history_dates_order, XC422 history_text_length, XC422 history_before_invalid, XC422 page_out_of_range via tenancy.check_page, XC422 time_zone_invalid via tenancy.check_time_zone.
-- Tests: tests/db/test_history_routines.py, tests/api/test_history.py, tests/db/test_pettycash_routines.py.
-- Visibility: people rows need people.view and, for a scoped viewer, a person they can see; an
-- all-companies viewer sees every other row; a scoped viewer sees companies rows of visible
-- companies, vehicles, investment, revenue and petty-cash rows of visible vehicles (a petty-cash
-- row without a vehicle, cash or a credit note, only for an all-companies viewer), recurring rows whose
-- current version shares only visible vehicles, every expenses row and no settings row.

CREATE OR REPLACE FUNCTION api.history_list(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_page integer,
  p_page_size integer,
  p_section text,
  p_from date,
  p_to date,
  p_text text,
  p_before bigint,
  p_include_total boolean,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_section text := tenancy.trim_text(p_section);
  v_text text := tenancy.trim_text(p_text);
  v_pattern text;
  v_zone text;
  v_from timestamptz;
  v_to timestamptz;
  v_all boolean;
  v_sees_people boolean;
  v_vehicles uuid[] := '{}';
  v_companies uuid[] := '{}';
  v_people uuid[] := '{}';
  v_reach tenancy.scope;
  v_total bigint;
  v_rows jsonb;
  v_items jsonb;
  v_has_more boolean;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'audit.view');
  IF p_from > p_to THEN
    PERFORM tenancy.refuse('history_dates_order', 'XC422');
  END IF;
  IF char_length(v_text) > 200 THEN
    PERFORM tenancy.refuse('history_text_length', 'XC422');
  END IF;
  IF p_before < 1 THEN
    PERFORM tenancy.refuse('history_before_invalid', 'XC422');
  END IF;
  PERFORM tenancy.check_page(p_page, p_page_size);

  IF p_from IS NOT NULL OR p_to IS NOT NULL THEN
    v_zone := tenancy.check_time_zone(tenancy.settings_document('localization') ->> 'time_zone');
    v_from := p_from::timestamp AT TIME ZONE v_zone;
    v_to := (p_to + 1)::timestamp AT TIME ZONE v_zone;
  END IF;
  -- The search text is matched literally: the LIKE wildcards and the escape character are escaped.
  v_pattern := '%' || replace(replace(replace(v_text, '\', '\\'), '%', '\%'), '_', '\_') || '%';

  v_all := (tenancy.actor_scope()).all_companies;
  v_sees_people := tenancy.has_permission('people.view');
  IF NOT v_all THEN
    v_vehicles := ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id));
    v_companies := ARRAY(SELECT visible.id FROM setup.visible_companies() AS visible (id));
    v_people := ARRAY(SELECT visible.id FROM tenancy.people_visible(p_actor_id) AS visible (id));
    v_reach := tenancy.person_reach(p_actor_id);
  END IF;

  WITH matching AS NOT MATERIALIZED (
    SELECT c.version, c.section, c.entity_id, c.reason, c.occurred_at, c.actor_id,
           coalesce(m.first_name || ' ' || m.last_name, '') AS actor_name,
           c.before, c.after
    FROM tenancy.change_log AS c
    LEFT JOIN tenancy.memberships AS m
      ON m.organization_id = c.organization_id AND m.user_id = c.actor_id
    WHERE c.organization_id = p_organization_id
      AND (v_section IS NULL OR c.section = v_section)
      AND (v_from IS NULL OR c.occurred_at >= v_from)
      AND (v_to IS NULL OR c.occurred_at < v_to)
      AND (v_text IS NULL
           OR c.reason ILIKE v_pattern
           OR (m.first_name || ' ' || m.last_name) ILIKE v_pattern)
      AND CASE
            WHEN c.section IN ('people', 'signIn') THEN
              v_sees_people AND (v_all OR c.entity_id = ANY (v_people))
            WHEN v_all THEN true
            WHEN c.section = 'companies' THEN c.entity_id = ANY (v_companies)
            WHEN c.section IN ('vehicles', 'investment', 'revenue', 'pettycash') THEN c.vehicle_id = ANY (v_vehicles)
            WHEN c.section = 'recurring' THEN NOT EXISTS (
              SELECT 1
              FROM setup.recurring_versions AS rv
              JOIN setup.recurring_allocations AS a
                ON a.organization_id = rv.organization_id AND a.version_id = rv.id
              WHERE rv.organization_id = c.organization_id
                AND rv.item_id = c.entity_id
                AND rv.revision = (
                  SELECT max(latest.revision)
                  FROM setup.recurring_versions AS latest
                  WHERE latest.organization_id = c.organization_id AND latest.item_id = c.entity_id
                )
                AND NOT a.vehicle_id = ANY (v_vehicles)
            )
            WHEN c.section = 'expenses' THEN true
            ELSE false
          END
  )
  SELECT CASE WHEN p_include_total IS DISTINCT FROM false THEN (SELECT count(*) FROM matching) END,
         (SELECT coalesce(jsonb_agg(page.document ORDER BY page.version DESC), '[]'::jsonb)
          FROM (
            SELECT matching.version,
                   jsonb_build_object(
                     'version', matching.version,
                     'section', matching.section,
                     'entity_id', matching.entity_id,
                     'reason', matching.reason,
                     'occurred_at', matching.occurred_at,
                     'actor_id', matching.actor_id,
                     'actor_name', matching.actor_name,
                     'before', CASE
                                 WHEN matching.section = 'people' AND NOT v_all THEN
                                   tenancy.redact_person_snapshot(
                                     matching.before, v_reach.company_ids, v_reach.vehicle_ids)
                                 ELSE matching.before
                               END,
                     'after', CASE
                                WHEN matching.section = 'people' AND NOT v_all THEN
                                  tenancy.redact_person_snapshot(
                                    matching.after, v_reach.company_ids, v_reach.vehicle_ids)
                                ELSE matching.after
                              END
                   ) AS document
            FROM matching
            WHERE p_before IS NULL OR matching.version < p_before
            ORDER BY matching.version DESC
            OFFSET CASE WHEN p_before IS NULL THEN (p_page - 1) * p_page_size ELSE 0 END
            LIMIT p_page_size + 1
          ) AS page)
  INTO v_total, v_rows;

  v_has_more := jsonb_array_length(v_rows) > p_page_size;
  v_items := CASE WHEN v_has_more THEN v_rows - p_page_size ELSE v_rows END;
  RETURN jsonb_build_object(
    'items', v_items,
    'total', v_total,
    'has_more', v_has_more,
    'next_before', CASE WHEN v_has_more THEN v_items -> (p_page_size - 1) -> 'version' END
  );
END;
$$;
