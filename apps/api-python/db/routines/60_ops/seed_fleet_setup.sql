-- ops.seed_fleet_setup(p_organization_id uuid, p_owner_id uuid, p_request_id text, p_company_ids uuid[], p_days_back integer, p_day date, p_at timestamptz) RETURNS void
-- Purpose: the setup events of one demo day, as the Owner through the setup routines: the first vehicles and the scheduled items on the first day, investments, a vehicle away and back, target sets that start on a day, and the vehicle that joined two weeks ago.
-- Callers: ops.seed_fleet.
-- Reads: setup.fleet_vehicles, setup.expense_items. Writes: what api.setup_vehicle_create, api.setup_recurring_create, api.setup_investment_create, api.setup_vehicle_retire, api.setup_vehicle_restore and api.setup_target_set_save write.
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py.
-- p_days_back is how many days before the business date p_day lies; the events are keyed by it. The share-sum check that api.setup_recurring_create makes immediate is deferred again after each item, because the next item's version row precedes its shares.

CREATE OR REPLACE FUNCTION ops.seed_fleet_setup(
  p_organization_id uuid,
  p_owner_id uuid,
  p_request_id text,
  p_company_ids uuid[],
  p_days_back integer,
  p_day date,
  p_at timestamptz
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_plan record;
  v_event record;
  v_vehicle_id uuid;
  v_item_id uuid;
  v_shares jsonb;
  v_count integer;
BEGIN
  PERFORM tenancy.enter_organization_as_operator(p_organization_id);

  FOR v_plan IN
    SELECT p.* FROM ops.seed_vehicle_plan() AS p
    WHERE p.joined_days_back = p_days_back
    ORDER BY p.idx
  LOOP
    PERFORM api.setup_vehicle_create(
      p_owner_id, p_organization_id, p_request_id, p_company_ids[v_plan.company_index],
      v_plan.registration, v_plan.fleet_number, p_day, v_plan.day_targets,
      v_plan.initial_investment, NULL, p_at
    );
  END LOOP;

  IF p_days_back = 42 THEN
    SELECT count(*), jsonb_agg(to_jsonb(f.id) ORDER BY f.registration)
    INTO v_count, v_shares
    FROM setup.fleet_vehicles AS f
    WHERE f.organization_id = p_organization_id;

    FOR v_event IN
      SELECT e.*
      FROM (
        VALUES
          (1, 'Insurance', 1, 2400, 3, 1, false, NULL::integer, 'Insurance'),
          (2, 'SACCO fee', 1, 500, 3, NULL, true, NULL, 'SACCO fee'),
          (3, 'Parking', 1, 300, 2, 1, false, NULL, 'Parking'),
          (4, 'Licence', 1, 5000, 4, 15, false, 3, 'Licence'),
          (5, 'Tyre fund', 2, 500, 2, 5, false, NULL, NULL),
          (6, 'Service reserve', 2, 2000, 3, 28, false, NULL, NULL)
      ) AS e (ord, name, kind, share, frequency, day, last_day, month, item)
      ORDER BY e.ord
    LOOP
      v_item_id := NULL;
      IF v_event.item IS NOT NULL THEN
        SELECT i.id INTO v_item_id
        FROM setup.expense_items AS i
        WHERE i.organization_id = p_organization_id
          AND i.normalized_name = upper(v_event.item COLLATE "C");
      END IF;
      PERFORM api.setup_recurring_create(
        p_owner_id, p_organization_id, p_request_id, v_event.name, v_event.kind,
        v_event.share * v_count, v_event.frequency, v_event.day, v_event.last_day, p_day, NULL,
        (
          SELECT jsonb_agg(jsonb_build_object('vehicle_id', s #>> '{}', 'amount', v_event.share))
          FROM jsonb_array_elements(v_shares) AS s
        ),
        v_item_id, NULL, v_event.month, NULL, p_at
      );
      SET CONSTRAINTS setup.check_allocation_sum DEFERRED;
    END LOOP;
  END IF;

  FOR v_event IN
    SELECT i.*
    FROM (
      VALUES
        (40, 'KDA 482M', 'Engine overhaul', 180000),
        (38, 'KDB 117P', 'Body repaint', 95000),
        (35, 'KDD 921K', 'New tyres, full set', 64000),
        (30, 'KDE 640J', 'Seat refit', 48000)
    ) AS i (days_back, registration, description, amount)
    WHERE i.days_back = p_days_back
  LOOP
    SELECT f.id INTO v_vehicle_id
    FROM setup.fleet_vehicles AS f
    WHERE f.organization_id = p_organization_id AND f.registration = v_event.registration;
    PERFORM api.setup_investment_create(
      p_owner_id, p_organization_id, p_request_id, v_vehicle_id, p_day, v_event.description,
      v_event.amount, p_at
    );
  END LOOP;

  IF p_days_back IN (30, 24) THEN
    SELECT f.id INTO v_vehicle_id
    FROM setup.fleet_vehicles AS f
    WHERE f.organization_id = p_organization_id AND f.registration = 'KDC 305T';
    IF p_days_back = 30 THEN
      PERFORM api.setup_vehicle_retire(
        p_owner_id, p_organization_id, p_request_id, v_vehicle_id, p_day, 'In the garage for repairs',
        p_at
      );
    ELSE
      PERFORM api.setup_vehicle_restore(
        p_owner_id, p_organization_id, p_request_id, v_vehicle_id, p_day, NULL, p_at
      );
    END IF;
  END IF;

  IF p_days_back = 21 THEN
    FOR v_plan IN
      SELECT p.* FROM ops.seed_vehicle_plan() AS p WHERE p.registration IN ('KDA 482M', 'KDD 921K')
    LOOP
      SELECT f.id INTO v_vehicle_id
      FROM setup.fleet_vehicles AS f
      WHERE f.organization_id = p_organization_id AND f.registration = v_plan.registration;
      PERFORM api.setup_target_set_save(
        p_owner_id, p_organization_id, p_request_id, v_vehicle_id, p_day,
        ARRAY(SELECT t.figure + 500 FROM unnest(v_plan.day_targets) WITH ORDINALITY AS t (figure, n) ORDER BY t.n),
        p_at
      );
    END LOOP;
  END IF;
END;
$$;

REVOKE ALL ON FUNCTION ops.seed_fleet_setup(uuid, uuid, text, uuid[], integer, date, timestamptz)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ops.seed_fleet_setup(uuid, uuid, text, uuid[], integer, date, timestamptz)
  TO xcode_api_executor;
