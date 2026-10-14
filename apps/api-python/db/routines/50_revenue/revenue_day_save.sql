-- api.revenue_day_save(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_date date, p_rows jsonb, p_now timestamptz) RETURNS jsonb
-- Purpose: save one day for many vehicles, all or nothing: p_rows [{vehicle_id, amount, reason, note, version}] (amounts and versions as text); each row runs the single capture's steps (revenue.capture_row, an identical row a replay), checked as of the request; answers {rows: [{vehicle_id, id, version}]} in the order sent.
-- Callers: RevenueRoutines.save_day; SaveRevenueDay (PUT /setup/revenue/day/{date}).
-- Reads: setup.fleet_vehicles, and what tenancy.effective_permissions, tenancy.settings_document, tenancy.business_date, tenancy.earliest_writable, setup.vehicle_visible, revenue.check_entry, revenue.capture_row and setup.decide_fleet_saving_runs read. Writes: what revenue.capture_row and setup.decide_fleet_saving_runs write.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing, XC422 revenue_day_rows_required, XC422 revenue_day_rows_limit, XC422 revenue_day_vehicle_repeated, XC404 not_found, XC422 revenue_reason_invalid via revenue.check_entry, XC422 money_invalid via revenue.check_entry, XC422 revenue_entry_required via revenue.check_entry, XC422 revenue_note_length via revenue.check_entry, XC422 revenue_note_without_other via revenue.check_entry, XC422 time_zone_invalid via revenue.capture_row, XC422 revenue_low_needs_reason via revenue.capture_row, XC422 revenue_amount_with_reason via revenue.capture_row, XC422 revenue_future_date via revenue.capture_row, XC422 revenue_vehicle_away via revenue.capture_row, XC422 revenue_vehicle_inactive via revenue.capture_row, XC403 revenue_capture_permission via revenue.capture_row, XC403 revenue_correct_permission via revenue.capture_row, XC422 record_too_old via revenue.capture_row, XC409 revenue_day_conflict, XC409 revenue_concurrent_save via revenue.capture_row, XC409 unique_conflict via revenue.capture_row.
-- Tests: tests/db/test_revenue_day_routines.py, tests/api/test_revenue_day.py.
-- Order: the row count, repeated vehicles, every vehicle visible (404, before any row), the
-- shape of every row in the order sent, then each row's capture in ascending vehicle id (one
-- lock order for every multi-row write), then one decision of the saving runs the day completes
-- for every vehicle. A row's XC422 refusal is raised again with its code and the
-- vehicle_registration added to its detail; its version conflict becomes revenue_day_conflict
-- naming the vehicle; a 403 or 404 passes unchanged. Any refusal aborts the whole call, so
-- nothing of the day is saved. What is the same for every row (the actor's rights, the low-day
-- threshold, the business date, the earliest writable date) is read once per call, and each
-- loop is one subtransaction, not one per row (a 500-row save fits the role's 5 s timeout).

CREATE OR REPLACE FUNCTION api.revenue_day_save(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_date date,
  p_rows jsonb,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  c_limit CONSTANT integer := 500;
  c_uuid CONSTANT text := '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$';
  v_vehicles uuid[];
  v_keys text[];
  v_amounts numeric[];
  v_reasons text[];
  v_notes text[];
  v_versions bigint[];
  v_registrations text[];
  v_permissions text[];
  v_threshold numeric;
  v_today date;
  v_writable_from date;
  v_count integer;
  v_i integer;
  v_at integer;
  v_result api.write_result;
  v_results jsonb := '{}'::jsonb;
  v_code text;
  v_state text;
  v_detail text;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  IF NOT v_permissions && ARRAY['revenue.capture', 'revenue.correct'] THEN
    PERFORM tenancy.refuse('permission_missing', 'XC403');
  END IF;
  IF jsonb_typeof(p_rows) IS DISTINCT FROM 'array' OR jsonb_array_length(p_rows) = 0 THEN
    PERFORM tenancy.refuse('revenue_day_rows_required', 'XC422');
  END IF;
  v_count := jsonb_array_length(p_rows);
  IF v_count > c_limit THEN
    PERFORM tenancy.refuse('revenue_day_rows_limit', 'XC422');
  END IF;

  SELECT array_agg(CASE WHEN e.value ->> 'vehicle_id' ~* c_uuid THEN (e.value ->> 'vehicle_id')::uuid END
                   ORDER BY e.n),
         array_agg(coalesce(lower(e.value ->> 'vehicle_id'), '#' || e.n) ORDER BY e.n),
         array_agg(CASE
                     WHEN (e.value ->> 'amount') ~ '^[+-]?[0-9]+([.][0-9]+)?$' THEN (e.value ->> 'amount')::numeric
                   END ORDER BY e.n),
         array_agg(e.value ->> 'reason' ORDER BY e.n),
         array_agg(e.value ->> 'note' ORDER BY e.n),
         array_agg(CASE WHEN (e.value ->> 'version') ~ '^[0-9]{1,18}$' THEN (e.value ->> 'version')::bigint END
                   ORDER BY e.n)
  INTO v_vehicles, v_keys, v_amounts, v_reasons, v_notes, v_versions
  FROM jsonb_array_elements(p_rows) WITH ORDINALITY AS e (value, n);

  IF (SELECT count(DISTINCT k) FROM unnest(v_keys) AS k) <> v_count THEN
    PERFORM tenancy.refuse('revenue_day_vehicle_repeated', 'XC422');
  END IF;
  v_registrations := ARRAY(
    SELECT f.registration
    FROM unnest(v_vehicles) WITH ORDINALITY AS s (id, n)
    LEFT JOIN setup.fleet_vehicles AS f ON f.organization_id = p_organization_id AND f.id = s.id
    ORDER BY s.n
  );
  IF EXISTS (
    SELECT 1 FROM unnest(v_vehicles, v_registrations) AS s (id, registration)
    WHERE s.registration IS NULL OR NOT setup.vehicle_visible(s.id)
  ) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;

  BEGIN
    FOR v_i IN 1 .. v_count LOOP
      v_at := v_i;
      PERFORM revenue.check_entry(v_amounts[v_i], v_reasons[v_i], v_notes[v_i]);
    END LOOP;
  EXCEPTION
    WHEN SQLSTATE 'XC422' THEN
      GET STACKED DIAGNOSTICS v_code = MESSAGE_TEXT, v_state = RETURNED_SQLSTATE,
                              v_detail = PG_EXCEPTION_DETAIL;
      PERFORM tenancy.refuse(
        v_code, v_state,
        coalesce(nullif(v_detail, '')::jsonb, '{}'::jsonb)
          || jsonb_build_object('vehicle_registration', v_registrations[v_at])
      );
  END;

  v_threshold := (tenancy.settings_document('revenue') ->> 'low_day_threshold')::numeric;
  BEGIN
    FOR v_i IN SELECT s.n FROM unnest(v_vehicles) WITH ORDINALITY AS s (id, n) ORDER BY s.id LOOP
      v_at := v_i;
      IF v_today IS NULL THEN
        v_today := tenancy.business_date(p_organization_id, p_now);
        v_writable_from := coalesce(
          tenancy.earliest_writable(p_organization_id, p_actor_id, v_today), '-infinity'::date
        );
      END IF;
      v_result := revenue.capture_row(
        p_organization_id, p_actor_id, v_permissions, v_threshold, v_today, v_writable_from,
        v_vehicles[v_i], p_date, v_amounts[v_i], v_reasons[v_i], v_notes[v_i], v_versions[v_i],
        NULL, p_now, false
      );
      v_results := v_results || jsonb_build_object(
        v_i::text, jsonb_build_object('id', v_result.id, 'version', v_result.version)
      );
    END LOOP;
  EXCEPTION
    WHEN SQLSTATE 'XC422' THEN
      GET STACKED DIAGNOSTICS v_code = MESSAGE_TEXT, v_state = RETURNED_SQLSTATE,
                              v_detail = PG_EXCEPTION_DETAIL;
      PERFORM tenancy.refuse(
        v_code, v_state,
        coalesce(nullif(v_detail, '')::jsonb, '{}'::jsonb)
          || jsonb_build_object('vehicle_registration', v_registrations[v_at])
      );
    WHEN SQLSTATE 'XC409' THEN
      GET STACKED DIAGNOSTICS v_code = MESSAGE_TEXT, v_state = RETURNED_SQLSTATE,
                              v_detail = PG_EXCEPTION_DETAIL;
      IF v_code = 'revenue_version_conflict' THEN
        PERFORM tenancy.refuse(
          'revenue_day_conflict', 'XC409',
          jsonb_build_object(
            'vehicle_id', v_vehicles[v_at],
            'registration', v_registrations[v_at],
            'current', coalesce(nullif(v_detail, '')::jsonb, '{}'::jsonb) -> 'current'
          )
        );
      END IF;
      PERFORM tenancy.refuse(v_code, v_state, coalesce(nullif(v_detail, '')::jsonb, '{}'::jsonb));
  END;
  PERFORM setup.decide_fleet_saving_runs(v_vehicles, p_date, p_date, p_now);

  RETURN jsonb_build_object(
    'rows',
    (
      SELECT jsonb_agg(jsonb_build_object('vehicle_id', s.id) || (v_results -> s.n::text) ORDER BY s.n)
      FROM unnest(v_vehicles) WITH ORDINALITY AS s (id, n)
    )
  );
END;
$$;
