-- setup.save_recurring(p_item_id uuid, p_name text, p_kind integer, p_amount numeric, p_frequency integer, p_day integer, p_last_day boolean, p_start date, p_end date, p_allocations jsonb, p_expense_item_id uuid, p_note text, p_month integer, p_condition jsonb, p_opening jsonb, p_reason text, p_now timestamptz) RETURNS api.write_result
-- Purpose: the nine checks and the writes of a scheduled item save, once for create (p_item_id NULL: a new item and version 1 from its start) and revise (the next revision, from the business date for a running item or a start on or after it, else from the backdated start); a cost takes its name and bucket from an expense item in use; a saving runs on any frequency from the business date (a revise keeps its start) with no end, and may carry a revenue rule (p_condition {min, days}) and an opening balance per share vehicle (p_opening {date, amounts}: SQL NULL keeps the stored one, JSON null removes it, an object replaces it; an amount of 0 is no amount); nothing different from the current version and opening answers unchanged; a saving with a rule then decides its held runs on each share vehicle from its start to today.
-- Callers: api.setup_recurring_create, api.setup_recurring_revise.
-- Reads: setup.recurring_items, setup.recurring_versions, setup.recurring_allocations, setup.expense_items, setup.expense_categories, setup.fleet_vehicles, setup.psv_companies, setup.saving_openings, setup.saving_opening_amounts, and what tenancy.business_date, setup.recurring_visible, setup.recurring_current_version, setup.visible_vehicles, setup.visible_companies and setup.recurring_snapshot read. Writes: setup.recurring_items, setup.recurring_versions, setup.recurring_allocations, setup.saving_openings, setup.saving_opening_amounts, setup.saving_runs through setup.decide_saving_runs, and through setup.record_setup_change tenancy.change_log, tenancy.audit_events and tenancy.organizations.settings_version.
-- Raises: XC422 time_zone_invalid via tenancy.business_date, XC422 reason_length via tenancy.check_typed_reason, XC422 recurring_savings_item, XC422 recurring_item_not_in_use, XC422 recurring_schedule_shape, XC404 not_found (also for an item of a kind the actor cannot view), XC403 permission_missing via tenancy.require_permission (the edit right of the current kind), XC422 recurring_name_length, XC422 money_invalid via tenancy.check_money, XC422 recurring_kind_invalid, XC403 permission_missing via tenancy.require_permission (the edit right of the new kind, on a revise), XC422 recurring_note_length, XC422 recurring_end_before_start, XC422 recurring_allocations_count, XC422 recurring_allocation_sum, XC422 recurring_daily_retired, XC422 recurring_cost_needs_item, XC422 recurring_start_required, XC422 recurring_start_too_early, XC422 recurring_share_inactive, XC422 recurring_condition_on_cost, XC422 recurring_condition_min, XC422 recurring_condition_days, XC422 recurring_opening_on_cost, XC422 recurring_opening_future, XC422 money_invalid via tenancy.check_money, XC422 recurring_opening_vehicle, XC422 recurring_savings_end, XC403 permission_missing, XC422 recurring_stopped_edit, XC422 recurring_running_start_change.
-- Tests: tests/db/test_setup_recurring_routines.py, tests/db/test_recurring_pause_routines.py.
-- The share sum is also enforced by the setup.check_allocation_sum constraint trigger, fired before the routine returns.

CREATE OR REPLACE FUNCTION setup.save_recurring(
  p_item_id uuid,
  p_name text,
  p_kind integer,
  p_amount numeric,
  p_frequency integer,
  p_day integer,
  p_last_day boolean,
  p_start date,
  p_end date,
  p_allocations jsonb,
  p_expense_item_id uuid,
  p_note text,
  p_month integer,
  p_condition jsonb,
  p_opening jsonb,
  p_reason text,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.current_organization();
  v_today date := tenancy.business_date(v_organization_id, p_now);
  v_last_day boolean := coalesce(p_last_day, false);
  v_reason text;
  v_name text;
  v_bucket smallint;
  v_note text;
  v_item setup.recurring_items;
  v_current setup.recurring_versions;
  v_vehicle_texts text[] := '{}';
  v_amount_texts text[] := '{}';
  v_vehicles uuid[];
  v_amounts numeric[];
  v_share numeric;
  v_failure record;
  v_parts text[] := '{}';
  v_item_id uuid;
  v_version_id uuid;
  v_effective date;
  v_revision integer;
  v_before json := 'null'::json;
  v_automatic text;
  v_version bigint;
  v_start date;
  v_condition_min numeric;
  v_condition_days smallint;
  v_keep_opening boolean := p_opening IS NULL;
  v_opening_date date;
  v_opening_vehicle_texts text[] := '{}';
  v_opening_amount_texts text[] := '{}';
  v_opening_vehicles uuid[] := '{}';
  v_opening_amounts numeric[] := '{}';
  v_opening_amount numeric;
  v_vehicle uuid;
BEGIN
  v_reason := tenancy.check_typed_reason(p_reason);

  IF p_kind IS DISTINCT FROM 1 THEN
    IF p_expense_item_id IS NOT NULL THEN
      PERFORM tenancy.refuse('recurring_savings_item', 'XC422');
    END IF;
    v_name := tenancy.trim_text(p_name);
  ELSIF p_expense_item_id IS NOT NULL THEN
    SELECT i.name, c.bucket INTO v_name, v_bucket
    FROM setup.expense_items AS i
    JOIN setup.expense_categories AS c
      ON c.organization_id = i.organization_id AND c.id = i.category_id
    WHERE i.organization_id = v_organization_id
      AND i.id = p_expense_item_id
      AND (i.stopped_on IS NULL OR i.stopped_on > v_today)
      AND (c.stopped_on IS NULL OR c.stopped_on > v_today)
    FOR SHARE;
    IF NOT FOUND THEN
      PERFORM tenancy.refuse('recurring_item_not_in_use', 'XC422');
    END IF;
  ELSE
    v_name := tenancy.trim_text(p_name);
  END IF;

  IF NOT setup.schedule_valid(p_frequency, p_day, v_last_day, p_month) THEN
    PERFORM tenancy.refuse('recurring_schedule_shape', 'XC422');
  END IF;

  IF p_item_id IS NOT NULL THEN
    SELECT i.* INTO v_item
    FROM setup.recurring_items AS i
    WHERE i.organization_id = v_organization_id AND i.id = p_item_id
    FOR UPDATE;
    IF NOT FOUND OR NOT setup.recurring_visible(p_item_id) THEN
      PERFORM tenancy.refuse('not_found', 'XC404');
    END IF;
    v_current := setup.recurring_current_version(p_item_id);
    PERFORM tenancy.require_permission(setup.recurring_kind_right(v_current.kind, 'edit'));
  END IF;

  IF v_name IS NULL OR char_length(v_name) > 160 THEN
    PERFORM tenancy.refuse('recurring_name_length', 'XC422');
  END IF;
  PERFORM tenancy.check_money(p_amount);
  IF p_kind IS NULL OR p_kind NOT IN (1, 2) THEN
    PERFORM tenancy.refuse('recurring_kind_invalid', 'XC422');
  END IF;
  v_start := CASE WHEN p_kind = 2 THEN coalesce(v_current.start_on, v_today) ELSE p_start END;
  IF p_item_id IS NOT NULL THEN
    PERFORM tenancy.require_permission(setup.recurring_kind_right(p_kind, 'edit'));
  END IF;
  v_note := tenancy.trim_text(p_note);
  IF char_length(v_note) > 200 THEN
    PERFORM tenancy.refuse('recurring_note_length', 'XC422');
  END IF;
  IF p_end < v_start THEN
    PERFORM tenancy.refuse('recurring_end_before_start', 'XC422');
  END IF;
  IF jsonb_typeof(p_allocations) = 'array' THEN
    SELECT coalesce(array_agg(e.value ->> 'vehicle_id' ORDER BY e.ordinality), '{}'),
           coalesce(array_agg(e.value ->> 'amount' ORDER BY e.ordinality), '{}')
    INTO v_vehicle_texts, v_amount_texts
    FROM jsonb_array_elements(p_allocations) WITH ORDINALITY AS e (value, ordinality);
  END IF;
  IF cardinality(v_vehicle_texts) NOT BETWEEN 1 AND 500
     OR EXISTS (
       SELECT 1 FROM unnest(v_vehicle_texts) AS t (vehicle)
       WHERE CASE
               WHEN t.vehicle ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                 THEN t.vehicle::uuid = '00000000-0000-0000-0000-000000000000'::uuid
               ELSE true
             END
     )
     OR (SELECT count(DISTINCT lower(t.vehicle)) FROM unnest(v_vehicle_texts) AS t (vehicle))
        <> cardinality(v_vehicle_texts) THEN
    PERFORM tenancy.refuse('recurring_allocations_count', 'XC422');
  END IF;
  v_vehicles := ARRAY(SELECT t.vehicle::uuid FROM unnest(v_vehicle_texts) WITH ORDINALITY AS t (vehicle, n) ORDER BY t.n);
  v_amounts := ARRAY(SELECT t.amount::numeric FROM unnest(v_amount_texts) WITH ORDINALITY AS t (amount, n) ORDER BY t.n);
  PERFORM 1
  FROM setup.fleet_vehicles AS f
  WHERE f.organization_id = v_organization_id AND f.id = ANY (v_vehicles)
  ORDER BY f.id
  FOR SHARE;
  PERFORM 1
  FROM setup.psv_companies AS c
  WHERE c.organization_id = v_organization_id
    AND c.id IN (
      SELECT f.company_id FROM setup.fleet_vehicles AS f
      WHERE f.organization_id = v_organization_id AND f.id = ANY (v_vehicles)
    )
  ORDER BY c.id
  FOR SHARE;
  FOREACH v_share IN ARRAY v_amounts LOOP
    PERFORM tenancy.check_money(v_share);
  END LOOP;
  IF (SELECT sum(t.amount) FROM unnest(v_amounts) AS t (amount)) <> p_amount THEN
    PERFORM tenancy.refuse('recurring_allocation_sum', 'XC422');
  END IF;

  IF p_frequency = 1 AND p_kind = 1 THEN
    PERFORM tenancy.refuse('recurring_daily_retired', 'XC422');
  END IF;
  IF p_kind = 1 AND p_expense_item_id IS NULL THEN
    PERFORM tenancy.refuse('recurring_cost_needs_item', 'XC422');
  END IF;
  IF v_start IS NULL THEN
    PERFORM tenancy.refuse('recurring_start_required', 'XC422');
  END IF;
  IF v_start < date_trunc('month', v_today)::date AND v_start IS DISTINCT FROM v_current.start_on THEN
    PERFORM tenancy.refuse('recurring_start_too_early', 'XC422');
  END IF;

  -- The shares in the order they were sent: the first that is out of reach or (new to the item)
  -- not in the fleet with an active company decides the refusal.
  SELECT share.vehicle_id,
         share.vehicle_id IN (SELECT visible.id FROM setup.visible_vehicles() AS visible (id))
           AND f.company_id IN (SELECT visible.id FROM setup.visible_companies() AS visible (id))
           AS reachable
  INTO v_failure
  FROM unnest(v_vehicles) WITH ORDINALITY AS share (vehicle_id, n)
  LEFT JOIN setup.fleet_vehicles AS f
    ON f.organization_id = v_organization_id AND f.id = share.vehicle_id
  LEFT JOIN setup.psv_companies AS c
    ON c.organization_id = f.organization_id AND c.id = f.company_id
  WHERE f.id IS NULL
     OR share.vehicle_id NOT IN (SELECT visible.id FROM setup.visible_vehicles() AS visible (id))
     OR f.company_id NOT IN (SELECT visible.id FROM setup.visible_companies() AS visible (id))
     OR (
       NOT (
         f.joined_on <= v_today
         AND (f.left_on IS NULL OR f.left_on > v_today)
         AND (c.archived_on IS NULL OR c.archived_on > v_today)
       )
       AND NOT EXISTS (
         SELECT 1 FROM setup.recurring_allocations AS a
         WHERE a.organization_id = v_organization_id
           AND a.version_id = v_current.id
           AND a.vehicle_id = share.vehicle_id
       )
     )
  ORDER BY share.n
  LIMIT 1;
  IF FOUND THEN
    IF NOT coalesce(v_failure.reachable, false) THEN
      PERFORM tenancy.refuse('not_found', 'XC404');
    END IF;
    PERFORM tenancy.refuse('recurring_share_inactive', 'XC422');
  END IF;

  IF jsonb_typeof(p_condition) = 'object' THEN
    IF p_kind = 1 THEN
      PERFORM tenancy.refuse('recurring_condition_on_cost', 'XC422');
    END IF;
    v_condition_min := CASE
                         WHEN jsonb_typeof(p_condition -> 'min') IN ('number', 'string')
                              AND (p_condition ->> 'min') ~ '^[+-]?[0-9]+([.][0-9]+)?$'
                           THEN (p_condition ->> 'min')::numeric
                       END;
    IF v_condition_min IS NULL OR v_condition_min <= 0 OR v_condition_min > 999999999999.99
       OR round(v_condition_min, 2) <> v_condition_min THEN
      PERFORM tenancy.refuse('recurring_condition_min', 'XC422');
    END IF;
    v_condition_days := CASE
                          WHEN jsonb_typeof(p_condition -> 'days') = 'number'
                               AND (p_condition ->> 'days')::numeric IN (1, 7, 30)
                            THEN (p_condition ->> 'days')::numeric::smallint
                        END;
    IF v_condition_days IS NULL THEN
      PERFORM tenancy.refuse('recurring_condition_days', 'XC422');
    END IF;
  END IF;
  IF p_kind = 1 AND v_keep_opening THEN
    v_keep_opening := NOT EXISTS (
      SELECT 1 FROM setup.saving_openings AS o
      WHERE o.organization_id = v_organization_id AND o.item_id = p_item_id
    );
  END IF;
  IF jsonb_typeof(p_opening) = 'object' THEN
    IF p_kind = 1 THEN
      PERFORM tenancy.refuse('recurring_opening_on_cost', 'XC422');
    END IF;
    v_opening_date := CASE
                        WHEN jsonb_typeof(p_opening -> 'date') = 'string'
                             AND (p_opening ->> 'date') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                          THEN (p_opening ->> 'date')::date
                      END;
    IF v_opening_date IS NULL OR v_opening_date > v_today THEN
      PERFORM tenancy.refuse('recurring_opening_future', 'XC422');
    END IF;
    IF jsonb_typeof(p_opening -> 'amounts') = 'array' THEN
      SELECT coalesce(array_agg(e.value ->> 'vehicle_id' ORDER BY e.ordinality), '{}'),
             coalesce(array_agg(e.value ->> 'amount' ORDER BY e.ordinality), '{}')
      INTO v_opening_vehicle_texts, v_opening_amount_texts
      FROM jsonb_array_elements(p_opening -> 'amounts') WITH ORDINALITY AS e (value, ordinality);
    END IF;
    FOREACH v_opening_amount IN ARRAY ARRAY(
      SELECT t.amount::numeric FROM unnest(v_opening_amount_texts) WITH ORDINALITY AS t (amount, n) ORDER BY t.n
    ) LOOP
      IF v_opening_amount IS DISTINCT FROM 0 THEN
        PERFORM tenancy.check_money(v_opening_amount);
      END IF;
    END LOOP;
    IF EXISTS (
         SELECT 1 FROM unnest(v_opening_vehicle_texts) AS t (vehicle)
         WHERE CASE
                 WHEN t.vehicle ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
                   THEN NOT t.vehicle::uuid = ANY (v_vehicles)
                 ELSE true
               END
       )
       OR (SELECT count(DISTINCT lower(t.vehicle)) FROM unnest(v_opening_vehicle_texts) AS t (vehicle))
          <> cardinality(v_opening_vehicle_texts) THEN
      PERFORM tenancy.refuse('recurring_opening_vehicle', 'XC422');
    END IF;
    SELECT coalesce(array_agg(t.vehicle::uuid ORDER BY t.n), '{}'),
           coalesce(array_agg(t.amount::numeric ORDER BY t.n), '{}')
    INTO v_opening_vehicles, v_opening_amounts
    FROM unnest(v_opening_vehicle_texts, v_opening_amount_texts) WITH ORDINALITY AS t (vehicle, amount, n)
    WHERE t.amount::numeric <> 0;
    IF cardinality(v_opening_vehicles) = 0 THEN
      v_opening_date := NULL;
    END IF;
  END IF;
  IF p_kind = 2 AND p_end IS NOT NULL AND p_end IS DISTINCT FROM v_current.end_on THEN
    PERFORM tenancy.refuse('recurring_savings_end', 'XC422');
  END IF;

  IF p_item_id IS NOT NULL THEN
    IF EXISTS (
      SELECT 1 FROM setup.recurring_allocations AS a
      WHERE a.organization_id = v_organization_id
        AND a.version_id = v_current.id
        AND a.vehicle_id NOT IN (SELECT visible.id FROM setup.visible_vehicles() AS visible (id))
    ) THEN
      PERFORM tenancy.refuse('permission_missing', 'XC403');
    END IF;
    IF p_kind <> v_current.kind THEN
      v_parts := v_parts || 'type'::text;
    END IF;
    IF p_expense_item_id IS DISTINCT FROM v_current.expense_item_id THEN
      v_parts := v_parts || 'expense item'::text;
    ELSIF v_name <> v_current.name THEN
      v_parts := v_parts || 'name'::text;
    END IF;
    IF p_expense_item_id IS NOT DISTINCT FROM v_current.expense_item_id
       AND v_bucket IS DISTINCT FROM v_current.bucket THEN
      v_parts := v_parts || 'bucket'::text;
    END IF;
    IF p_amount <> v_current.amount THEN
      v_parts := v_parts || 'amount'::text;
    END IF;
    IF p_frequency <> v_current.frequency
       OR p_day IS DISTINCT FROM v_current.day::integer
       OR v_last_day <> v_current.last_day
       OR p_month IS DISTINCT FROM v_current.month::integer THEN
      v_parts := v_parts || 'schedule'::text;
    END IF;
    IF v_start <> v_current.start_on THEN
      v_parts := v_parts || 'start date'::text;
    END IF;
    IF p_end IS DISTINCT FROM v_current.end_on THEN
      v_parts := v_parts || 'end date'::text;
    END IF;
    IF EXISTS (
      (SELECT s.vehicle_id, s.amount FROM unnest(v_vehicles, v_amounts) AS s (vehicle_id, amount)
       EXCEPT
       SELECT a.vehicle_id, a.amount FROM setup.recurring_allocations AS a
       WHERE a.organization_id = v_organization_id AND a.version_id = v_current.id)
      UNION ALL
      (SELECT a.vehicle_id, a.amount FROM setup.recurring_allocations AS a
       WHERE a.organization_id = v_organization_id AND a.version_id = v_current.id
       EXCEPT
       SELECT s.vehicle_id, s.amount FROM unnest(v_vehicles, v_amounts) AS s (vehicle_id, amount))
    ) THEN
      v_parts := v_parts || 'vehicles'::text;
    END IF;
    IF v_note IS DISTINCT FROM v_current.note THEN
      v_parts := v_parts || 'note'::text;
    END IF;
    IF v_condition_min IS DISTINCT FROM v_current.condition_min
       OR v_condition_days IS DISTINCT FROM v_current.condition_days THEN
      v_parts := v_parts || 'revenue rule'::text;
    END IF;
    IF NOT v_keep_opening AND (
         v_opening_date IS DISTINCT FROM (
           SELECT o.opened_on FROM setup.saving_openings AS o
           WHERE o.organization_id = v_organization_id AND o.item_id = p_item_id
         )
         OR EXISTS (
           (SELECT s.vehicle_id, s.amount
            FROM unnest(v_opening_vehicles, v_opening_amounts) AS s (vehicle_id, amount)
            EXCEPT
            SELECT a.vehicle_id, a.amount FROM setup.saving_opening_amounts AS a
            WHERE a.organization_id = v_organization_id AND a.item_id = p_item_id)
           UNION ALL
           (SELECT a.vehicle_id, a.amount FROM setup.saving_opening_amounts AS a
            WHERE a.organization_id = v_organization_id AND a.item_id = p_item_id
            EXCEPT
            SELECT s.vehicle_id, s.amount
            FROM unnest(v_opening_vehicles, v_opening_amounts) AS s (vehicle_id, amount))
         )
       ) THEN
      v_parts := v_parts || 'opening balance'::text;
    END IF;
    IF cardinality(v_parts) = 0 THEN
      RETURN setup.unchanged_result(p_item_id);
    END IF;
    IF v_item.stopped_from <= v_today THEN
      PERFORM tenancy.refuse('recurring_stopped_edit', 'XC422');
    END IF;
    IF v_current.start_on < v_today AND v_start <> v_current.start_on THEN
      PERFORM tenancy.refuse('recurring_running_start_change', 'XC422');
    END IF;
    v_item_id := p_item_id;
    v_before := setup.recurring_snapshot(p_item_id);
    v_revision := v_current.revision + 1;
    v_effective := CASE
                     WHEN v_current.start_on < v_today OR v_start >= v_today THEN v_today
                     ELSE v_start
                   END;
    v_automatic := setup.recurring_change_reason(p_kind, v_name);
    UPDATE setup.recurring_items SET updated_at = p_now
    WHERE organization_id = v_organization_id AND id = p_item_id;
  ELSE
    INSERT INTO setup.recurring_items (organization_id, created_at, updated_at)
    VALUES (v_organization_id, p_now, p_now)
    RETURNING id INTO v_item_id;
    v_revision := 1;
    v_effective := v_start;
    v_automatic := setup.recurring_change_reason(p_kind, v_name);
  END IF;

  INSERT INTO setup.recurring_versions (
    organization_id, item_id, revision, effective_from, name, kind, amount, frequency, day,
    last_day, month, start_on, end_on, expense_item_id, bucket, note, condition_min, condition_days,
    created_at
  )
  VALUES (
    v_organization_id, v_item_id, v_revision, v_effective, v_name, p_kind, p_amount, p_frequency,
    p_day, v_last_day, p_month, v_start, p_end, p_expense_item_id, v_bucket, v_note, v_condition_min,
    v_condition_days, p_now
  )
  RETURNING id INTO v_version_id;
  INSERT INTO setup.recurring_allocations (organization_id, version_id, vehicle_id, amount)
  SELECT v_organization_id, v_version_id, s.vehicle_id, s.amount
  FROM unnest(v_vehicles, v_amounts) AS s (vehicle_id, amount);
  -- Fire the deferred share-sum check now, as the routine owner: at commit it would run as the
  -- calling role, which cannot read the setup schema.
  SET CONSTRAINTS setup.check_allocation_sum IMMEDIATE;
  IF NOT v_keep_opening THEN
    DELETE FROM setup.saving_openings
    WHERE organization_id = v_organization_id AND item_id = v_item_id;
    IF v_opening_date IS NOT NULL THEN
      INSERT INTO setup.saving_openings (organization_id, item_id, opened_on, created_at, updated_at)
      VALUES (v_organization_id, v_item_id, v_opening_date, p_now, p_now);
      INSERT INTO setup.saving_opening_amounts (organization_id, item_id, vehicle_id, amount)
      SELECT v_organization_id, v_item_id, s.vehicle_id, s.amount
      FROM unnest(v_opening_vehicles, v_opening_amounts) AS s (vehicle_id, amount);
    END IF;
  END IF;

  v_version := setup.record_setup_change(
    'recurring', v_item_id, NULL, v_before, setup.recurring_snapshot(v_item_id),
    tenancy.compose_reason(v_automatic, v_reason), p_now
  );
  IF v_condition_min IS NOT NULL THEN
    FOR v_vehicle IN SELECT s.id FROM unnest(v_vehicles) AS s (id) ORDER BY s.id LOOP
      PERFORM setup.decide_saving_runs(v_vehicle, v_start, v_today, p_now);
    END LOOP;
  END IF;
  RETURN ROW(
    v_item_id, v_version, CASE WHEN p_item_id IS NULL THEN 'created' ELSE 'updated' END
  )::api.write_result;
END;
$$;

REVOKE ALL ON FUNCTION setup.save_recurring(
  uuid, text, integer, numeric, integer, integer, boolean, date, date, jsonb, uuid, text, integer,
  jsonb, jsonb, text, timestamptz
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.save_recurring(
  uuid, text, integer, numeric, integer, integer, boolean, date, date, jsonb, uuid, text, integer,
  jsonb, jsonb, text, timestamptz
) TO xcode_api_executor;
