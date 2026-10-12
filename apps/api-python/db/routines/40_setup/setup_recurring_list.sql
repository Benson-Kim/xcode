-- api.setup_recurring_list(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_page integer, p_page_size integer, p_kind text, p_company_id uuid, p_status text, p_now timestamptz) RETURNS jsonb
-- Purpose: one page of the scheduled items the actor can see (items of a kind whose view right they lack are left out, also from the total), filtered by the current version's kind (cost, savings), by a company owning a visible vehicle the current version shares to, and by whether the item runs (not stopped or ended on the business date and sharing to a visible vehicle in the fleet that day: running, stopped; blank or all keeps every item), each as its latest version, running items first, then by name and item id, with only the shares on vehicles the actor can see (partial when others exist), the amount of those shares, the part still on vehicles in the fleet, the expense item's name and the reported bucket (a cost without one reports recurring charges, 2); {total, items}.
-- Callers: SetupRoutines.list_recurring; ListRecurring (GET /setup/recurring).
-- Reads: setup.recurring_items, setup.recurring_versions, setup.recurring_allocations, setup.fleet_vehicles, setup.expense_items, and what tenancy.business_date, tenancy.has_permission, tenancy.actor_scope and setup.visible_vehicles read. Writes: nothing.
-- Raises: XC422 recurring_filter_kind_invalid, XC422 recurring_filter_status_invalid (both before the membership check, as the filter is read before the request runs), XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 page_out_of_range via tenancy.check_page, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_setup_recurring_routines.py, tests/api/test_setup_recurring.py.

CREATE OR REPLACE FUNCTION api.setup_recurring_list(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_page integer,
  p_page_size integer,
  p_kind text,
  p_company_id uuid,
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
  v_today date;
  v_all boolean;
  v_vehicles uuid[];
  v_kind smallint;
  v_sees_costs boolean;
  v_sees_savings boolean;
  v_running boolean;
  v_total bigint;
  v_items jsonb;
BEGIN
  IF p_kind IS NOT NULL AND p_kind NOT IN ('', 'all', 'cost', 'savings') THEN
    PERFORM tenancy.refuse('recurring_filter_kind_invalid', 'XC422');
  END IF;
  IF p_status IS NOT NULL AND p_status NOT IN ('', 'all', 'running', 'stopped') THEN
    PERFORM tenancy.refuse('recurring_filter_status_invalid', 'XC422');
  END IF;
  v_kind := CASE p_kind WHEN 'cost' THEN 1 WHEN 'savings' THEN 2 END;
  v_running := CASE p_status WHEN 'running' THEN true WHEN 'stopped' THEN false END;
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['scheduled.view', 'savings.view']);
  v_sees_costs := tenancy.has_permission('scheduled.view');
  v_sees_savings := tenancy.has_permission('savings.view');
  PERFORM tenancy.check_page(p_page, p_page_size);
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_all := (tenancy.actor_scope()).all_companies;
  v_vehicles := ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id));

  WITH visible_items AS (
    SELECT i.id, i.stopped_from, cv.*,
           (i.stopped_from IS NULL OR i.stopped_from > v_today)
             AND (cv.end_on IS NULL OR cv.end_on >= v_today)
             AND EXISTS (
               SELECT 1
               FROM setup.recurring_allocations AS a
               JOIN setup.fleet_vehicles AS f
                 ON f.organization_id = a.organization_id AND f.id = a.vehicle_id
               WHERE a.organization_id = i.organization_id
                 AND a.version_id = cv.version_id
                 AND a.vehicle_id = ANY (v_vehicles)
                 AND f.joined_on <= v_today
                 AND (f.left_on IS NULL OR f.left_on > v_today)
             ) AS running
    FROM setup.recurring_items AS i
    CROSS JOIN LATERAL (
      SELECT v.id AS version_id, v.revision, v.name, v.kind, v.frequency, v.day, v.last_day,
             v.month, v.start_on, v.end_on, v.expense_item_id, v.bucket, v.note
      FROM setup.recurring_versions AS v
      WHERE v.organization_id = i.organization_id AND v.item_id = i.id
      ORDER BY v.revision DESC
      LIMIT 1
    ) AS cv
    WHERE i.organization_id = p_organization_id
      AND (
        v_all
        OR EXISTS (
          SELECT 1
          FROM setup.recurring_versions AS v
          JOIN setup.recurring_allocations AS a
            ON a.organization_id = v.organization_id AND a.version_id = v.id
          WHERE v.organization_id = i.organization_id
            AND v.item_id = i.id
            AND a.vehicle_id = ANY (v_vehicles)
        )
      )
      AND (v_kind IS NULL OR cv.kind = v_kind)
      AND CASE WHEN cv.kind = 2 THEN v_sees_savings ELSE v_sees_costs END
      AND (
        p_company_id IS NULL
        OR EXISTS (
          SELECT 1
          FROM setup.recurring_allocations AS a
          JOIN setup.fleet_vehicles AS f
            ON f.organization_id = a.organization_id AND f.id = a.vehicle_id
          WHERE a.organization_id = i.organization_id
            AND a.version_id = cv.version_id
            AND a.vehicle_id = ANY (v_vehicles)
            AND f.company_id = p_company_id
        )
      )
  ),
  listed AS (
    SELECT * FROM visible_items WHERE v_running IS NULL OR running = v_running
  )
  SELECT (SELECT count(*) FROM listed),
         (
           SELECT coalesce(jsonb_agg(page.document ORDER BY page.running DESC, page.name, page.id), '[]'::jsonb)
           FROM (
             SELECT r.running, r.name, r.id,
                    jsonb_build_object(
                      'id', r.id,
                      'version_id', r.version_id,
                      'revision', r.revision,
                      'name', r.name,
                      'kind', r.kind,
                      'amount', coalesce(shares.amount, 0),
                      'frequency', r.frequency,
                      'day', r.day,
                      'last_day', r.last_day,
                      'start_on', r.start_on,
                      'end_on', r.end_on,
                      'stopped_from', r.stopped_from,
                      'allocations', coalesce(shares.allocations, '[]'::jsonb),
                      'partial', EXISTS (
                        SELECT 1 FROM setup.recurring_allocations AS hidden
                        WHERE hidden.organization_id = p_organization_id
                          AND hidden.version_id = r.version_id
                          AND NOT hidden.vehicle_id = ANY (v_vehicles)
                      ),
                      'expense_item_id', r.expense_item_id,
                      'expense_item_name', (
                        SELECT e.name FROM setup.expense_items AS e
                        WHERE e.organization_id = p_organization_id AND e.id = r.expense_item_id
                      ),
                      'bucket', CASE WHEN r.kind = 1 THEN coalesce(r.bucket, 2::smallint) END,
                      'note', r.note,
                      'month', r.month,
                      'active_amount', coalesce(shares.active_amount, 0)
                    ) AS document
             FROM listed AS r
             LEFT JOIN LATERAL (
               SELECT sum(a.amount) AS amount,
                      sum(a.amount) FILTER (WHERE s.active) AS active_amount,
                      jsonb_agg(
                        jsonb_build_object(
                          'vehicle_id', a.vehicle_id,
                          'amount', a.amount,
                          'registration', f.registration,
                          'active', s.active
                        ) ORDER BY f.registration, a.vehicle_id
                      ) AS allocations
               FROM setup.recurring_allocations AS a
               JOIN setup.fleet_vehicles AS f
                 ON f.organization_id = a.organization_id AND f.id = a.vehicle_id
               CROSS JOIN LATERAL (
                 SELECT f.joined_on <= v_today AND (f.left_on IS NULL OR f.left_on > v_today) AS active
               ) AS s
               WHERE a.organization_id = p_organization_id
                 AND a.version_id = r.version_id
                 AND a.vehicle_id = ANY (v_vehicles)
             ) AS shares ON true
             ORDER BY r.running DESC, r.name, r.id
             OFFSET (p_page - 1) * p_page_size
             LIMIT p_page_size
           ) AS page
         )
  INTO v_total, v_items;

  RETURN jsonb_build_object('total', v_total, 'items', v_items);
END;
$$;
