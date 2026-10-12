-- api.setup_vehicle_list(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_page integer, p_page_size integer, p_company_id uuid, p_now timestamptz) RETURNS jsonb
-- Purpose: one page of the vehicles the actor can see, of one company when p_company_id is given (counted and paged as the matches only), by registration, each with its company, fleet number, initial investment, whether it is in the fleet on the business date, the target set in force (its seven day figures and their weekly total), the next set and its start, its target history in the shape released clients read (one entry per set: start, weekly total, ordinal), the scheduled items still posting to it and its away periods; investment viewers without vehicles.view get no target, no history and no scheduled-item count; {total, items}.
-- Callers: SetupRoutines.list_vehicles; ListVehicles (GET /setup/vehicles).
-- Reads: setup.fleet_vehicles, setup.psv_companies, setup.vehicle_target_sets, setup.vehicle_away_periods, setup.recurring_items, setup.recurring_versions, setup.recurring_allocations, and what tenancy.business_date, tenancy.has_permission, setup.visible_vehicles, setup.target_set_on and setup.target_on read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 page_out_of_range via tenancy.check_page, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_setup_vehicle_routines.py, tests/api/test_setup_vehicles.py.

CREATE OR REPLACE FUNCTION api.setup_vehicle_list(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_page integer,
  p_page_size integer,
  p_company_id uuid,
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
  v_manages boolean;
  v_vehicles uuid[];
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['vehicles.view', 'reports.investment']);
  PERFORM tenancy.check_page(p_page, p_page_size);
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_manages := tenancy.has_permission('vehicles.view');
  v_vehicles := ARRAY(
    SELECT visible.id
    FROM setup.visible_vehicles() AS visible (id)
    WHERE p_company_id IS NULL
       OR EXISTS (
            SELECT 1 FROM setup.fleet_vehicles AS f
            WHERE f.organization_id = p_organization_id
              AND f.id = visible.id
              AND f.company_id = p_company_id
          )
  );
  RETURN jsonb_build_object(
    'total', cardinality(v_vehicles),
    'items', (
      SELECT coalesce(jsonb_agg(page.document ORDER BY page.registration, page.id), '[]'::jsonb)
      FROM (
        SELECT v.registration, v.id,
               jsonb_build_object(
                 'id', v.id,
                 'company_id', v.company_id,
                 'company_name', c.name,
                 'registration', v.registration,
                 'fleet_number', v.fleet_number,
                 'initial_investment', v.initial_investment,
                 'joined_on', v.joined_on,
                 'left_on', v.left_on,
                 'active', v.active,
                 'weekly_target', CASE
                                    WHEN NOT v_manages THEN NULL
                                    WHEN v.active THEN v.target_today
                                    ELSE 0
                                  END,
                 'targets', CASE
                              WHEN NOT v_manages THEN '[]'::jsonb
                              ELSE (
                                SELECT coalesce(
                                         jsonb_agg(
                                           jsonb_build_object(
                                             'effective_from', t.starts_on,
                                             'weekly_amount', t.week_total,
                                             'revision', t.revision
                                           ) ORDER BY t.starts_on),
                                         '[]'::jsonb)
                                FROM (
                                  SELECT s.starts_on, setup.week_total(s) AS week_total,
                                         row_number() OVER (ORDER BY s.starts_on) AS revision
                                  FROM setup.vehicle_target_sets AS s
                                  WHERE s.organization_id = v.organization_id
                                    AND s.vehicle_id = v.id
                                    AND s.starts_on <= v_today
                                ) AS t
                              )
                            END,
                 'recurring_items', CASE
                                      WHEN NOT v_manages THEN NULL
                                      WHEN NOT v.active THEN 0
                                      ELSE (
                                        SELECT count(DISTINCT rv.item_id)
                                        FROM setup.recurring_allocations AS a
                                        JOIN setup.recurring_versions AS rv
                                          ON rv.organization_id = a.organization_id AND rv.id = a.version_id
                                        JOIN setup.recurring_items AS i
                                          ON i.organization_id = rv.organization_id AND i.id = rv.item_id
                                        WHERE a.organization_id = v.organization_id
                                          AND a.vehicle_id = v.id
                                          AND rv.revision = (
                                            SELECT max(latest.revision)
                                            FROM setup.recurring_versions AS latest
                                            WHERE latest.organization_id = rv.organization_id
                                              AND latest.item_id = rv.item_id
                                          )
                                          AND (rv.end_on IS NULL OR rv.end_on >= v_today)
                                          AND (i.stopped_from IS NULL OR i.stopped_from > v_today)
                                      )
                                    END,
                 'day_targets', CASE
                                  WHEN NOT v_manages OR (v.in_force).id IS NULL THEN NULL
                                  ELSE jsonb_build_array(
                                         (v.in_force).monday, (v.in_force).tuesday,
                                         (v.in_force).wednesday, (v.in_force).thursday,
                                         (v.in_force).friday, (v.in_force).saturday,
                                         (v.in_force).sunday
                                       )
                                END,
                 'next_target', CASE
                                  WHEN NOT v_manages THEN NULL
                                  ELSE (
                                    SELECT jsonb_build_object(
                                             'starts_on', n.starts_on,
                                             'day_targets', jsonb_build_array(
                                               n.monday, n.tuesday, n.wednesday, n.thursday,
                                               n.friday, n.saturday, n.sunday
                                             ),
                                             'weekly_target', setup.week_total(n)
                                           )
                                    FROM setup.vehicle_target_sets AS n
                                    WHERE n.organization_id = v.organization_id
                                      AND n.vehicle_id = v.id
                                      AND n.starts_on > v_today
                                    ORDER BY n.starts_on
                                    LIMIT 1
                                  )
                                END,
                 'away', (
                   SELECT coalesce(
                            jsonb_agg(
                              jsonb_build_object('left_on', a.left_on, 'returned_on', a.returned_on)
                              ORDER BY a.left_on),
                            '[]'::jsonb)
                   FROM setup.vehicle_away_periods AS a
                   WHERE a.organization_id = v.organization_id AND a.vehicle_id = v.id
                 )
               ) AS document
        FROM (
          SELECT f.*,
                 f.joined_on <= v_today AND (f.left_on IS NULL OR f.left_on > v_today) AS active,
                 setup.target_set_on(f.id, v_today) AS in_force,
                 setup.target_on(f.id, v_today) AS target_today
          FROM setup.fleet_vehicles AS f
          WHERE f.organization_id = p_organization_id AND f.id = ANY (v_vehicles)
          ORDER BY f.registration, f.id
          OFFSET (p_page - 1) * p_page_size
          LIMIT p_page_size
        ) AS v
        JOIN setup.psv_companies AS c ON c.organization_id = v.organization_id AND c.id = v.company_id
      ) AS page
    )
  );
END;
$$;
