-- api.revenue_capture(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_vehicle_id uuid, p_day date, p_amount numeric, p_reason text, p_note text, p_expected_version bigint, p_captured_at timestamptz, p_now timestamptz) RETURNS api.write_result
-- Purpose: record a vehicle's revenue for a day (an amount; below the low-day threshold an amount with a reason) or a no-revenue reason, by the natural key (vehicle, day): created, updated, or replayed (an identical entry, answered with the stored id and version and nothing written); the capture and offline-replay endpoint. p_captured_at is when the client captured the entry (NULL: now).
-- Callers: RevenueRoutines.capture; CaptureRevenue (PUT /setup/revenue/{vehicleId}/{date}).
-- Reads: setup.fleet_vehicles, revenue.records, and what tenancy.effective_permissions, tenancy.settings_document, setup.vehicle_visible, tenancy.business_date, setup.vehicle_active_on, setup.vehicle_away_on, tenancy.check_writable, tenancy.earliest_writable, revenue.vehicle_days, revenue.cell and revenue.record_snapshot read. Writes: revenue.records, and what tenancy.record_change writes.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing, XC422 revenue_reason_invalid, XC422 money_invalid via tenancy.check_money, XC422 revenue_entry_required, XC422 revenue_note_length, XC422 revenue_note_without_other, XC404 not_found, XC422 time_zone_invalid via tenancy.business_date, XC422 revenue_low_needs_reason, XC422 revenue_amount_with_reason, XC422 revenue_future_date, XC422 revenue_vehicle_away, XC422 revenue_vehicle_inactive, XC403 revenue_capture_permission, XC403 revenue_correct_permission, XC422 record_too_old via tenancy.check_writable, XC409 revenue_version_conflict, XC409 revenue_concurrent_save, XC409 unique_conflict.
-- Tests: tests/db/test_revenue_routines.py, tests/api/test_revenue.py.
-- The steps run in this order, the first failing one answering: membership and one of
-- revenue.capture or revenue.correct; the entry's shape (an amount of 0 with a reason is the
-- reason alone); the vehicle in the caller's view, its row held FOR SHARE so a retirement or
-- join-date change in flight (which locks the vehicle and then looks for revenue it would
-- strand) commits first and is read, or waits for this one; the day's record locked without
-- waiting (a save holding it makes this one revenue_concurrent_save, and the lock keeps the
-- version read until the write); an identical entry answered as replayed, whatever version was
-- sent, whatever the date, the threshold, the limit and the permissions, so a phone draining
-- its queue late always succeeds, also with an entry saved under earlier rules; the amount
-- against the organization's low-day threshold; a future day; a day the vehicle is not in the
-- fleet; the permission of the path (capture fills a day without a record, correct changes a
-- saved one), before anything stored is shown; the caller's back-dating limit on the day, as of
-- the capture time held to the last 72 hours; the version, a conflict carrying the stored cell
-- as current; the write, a first capture racing another one ending as unique_conflict; the
-- change-log row. Days are captured in any order.

CREATE OR REPLACE FUNCTION api.revenue_capture(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_vehicle_id uuid,
  p_day date,
  p_amount numeric,
  p_reason text,
  p_note text,
  p_expected_version bigint,
  p_captured_at timestamptz,
  p_now timestamptz
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  c_other CONSTANT smallint := 4;
  c_offline_window CONSTANT interval := interval '72 hours';
  v_permissions text[];
  v_threshold numeric;
  v_amount numeric := p_amount;
  v_reason_text text := tenancy.trim_text(p_reason);
  v_reason smallint;
  v_note text := tenancy.trim_text(p_note);
  v_registration text;
  v_today date;
  v_record revenue.records;
  v_exists boolean;
  v_current jsonb;
  v_before json;
  v_after json;
  v_id uuid;
  v_version bigint;
  v_which text;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  IF NOT v_permissions && ARRAY['revenue.capture', 'revenue.correct'] THEN
    PERFORM tenancy.refuse('permission_missing', 'XC403');
  END IF;

  v_threshold := (tenancy.settings_document('revenue') ->> 'low_day_threshold')::numeric;
  IF v_reason_text IS NOT NULL THEN
    v_reason := revenue.reason_code(v_reason_text);
    IF v_reason IS NULL THEN
      PERFORM tenancy.refuse('revenue_reason_invalid', 'XC422');
    END IF;
  END IF;
  IF p_amount = 0 AND v_reason IS NOT NULL THEN
    v_amount := NULL;
  END IF;
  IF v_amount IS NOT NULL THEN
    PERFORM tenancy.check_money(v_amount);
  END IF;
  IF v_amount IS NULL AND v_reason IS NULL THEN
    PERFORM tenancy.refuse('revenue_entry_required', 'XC422');
  END IF;
  IF char_length(v_note) > 80 THEN
    PERFORM tenancy.refuse('revenue_note_length', 'XC422');
  END IF;
  IF v_note IS NOT NULL AND v_reason IS DISTINCT FROM c_other THEN
    PERFORM tenancy.refuse('revenue_note_without_other', 'XC422');
  END IF;

  SELECT f.registration INTO v_registration
  FROM setup.fleet_vehicles AS f
  WHERE f.organization_id = p_organization_id AND f.id = p_vehicle_id
  FOR SHARE;
  IF NOT FOUND OR NOT setup.vehicle_visible(p_vehicle_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  v_today := tenancy.business_date(p_organization_id, p_now);

  BEGIN
    SELECT r.* INTO v_record
    FROM revenue.records AS r
    WHERE r.organization_id = p_organization_id
      AND r.vehicle_id = p_vehicle_id
      AND r.business_date = p_day
    FOR UPDATE NOWAIT;
    v_exists := FOUND;

    IF v_exists
       AND v_record.amount IS NOT DISTINCT FROM v_amount
       AND v_record.reason IS NOT DISTINCT FROM v_reason
       AND v_record.note IS NOT DISTINCT FROM v_note THEN
      RETURN ROW(v_record.id, v_record.version, 'replayed')::api.write_result;
    END IF;

    IF v_amount < v_threshold AND v_reason IS NULL THEN
      PERFORM tenancy.refuse(
        'revenue_low_needs_reason', 'XC422',
        jsonb_build_object(
          'currency', tenancy.settings_document('localization') ->> 'currency',
          'threshold', tenancy.fmt_money(v_threshold)
        )
      );
    END IF;
    IF v_amount >= v_threshold AND v_reason IS NOT NULL THEN
      PERFORM tenancy.refuse(
        'revenue_amount_with_reason', 'XC422',
        jsonb_build_object(
          'currency', tenancy.settings_document('localization') ->> 'currency',
          'threshold', tenancy.fmt_money(v_threshold)
        )
      );
    END IF;

    IF p_day IS NULL OR p_day = date '0001-01-01' OR p_day > v_today THEN
      PERFORM tenancy.refuse('revenue_future_date', 'XC422');
    END IF;
    IF NOT setup.vehicle_active_on(p_vehicle_id, p_day) THEN
      IF setup.vehicle_away_on(p_vehicle_id, p_day) THEN
        PERFORM tenancy.refuse('revenue_vehicle_away', 'XC422');
      END IF;
      PERFORM tenancy.refuse('revenue_vehicle_inactive', 'XC422');
    END IF;

    IF NOT v_exists AND NOT 'revenue.capture' = ANY (v_permissions) THEN
      PERFORM tenancy.refuse('revenue_capture_permission', 'XC403');
    END IF;
    IF v_exists AND NOT 'revenue.correct' = ANY (v_permissions) THEN
      PERFORM tenancy.refuse('revenue_correct_permission', 'XC403');
    END IF;

    PERFORM tenancy.check_writable(
      p_day, greatest(least(coalesce(p_captured_at, p_now), p_now), p_now - c_offline_window)
    );

    IF v_exists AND p_expected_version IS DISTINCT FROM v_record.version THEN
      SELECT revenue.cell(
               d,
               v_today,
               'revenue.capture' = ANY (v_permissions),
               'revenue.correct' = ANY (v_permissions),
               tenancy.earliest_writable(p_organization_id, p_actor_id, v_today)
             )
      INTO v_current
      FROM revenue.vehicle_days(ARRAY[p_vehicle_id], p_day, p_day, v_today) AS d;
      PERFORM tenancy.refuse(
        'revenue_version_conflict', 'XC409', jsonb_build_object('current', v_current)
      );
    END IF;

    IF v_exists THEN
      v_before := revenue.record_snapshot(v_record.id);
      UPDATE revenue.records
      SET amount = v_amount,
          reason = v_reason,
          note = v_note,
          updated_at = p_now,
          updated_by = p_actor_id,
          corrected_after_date = corrected_after_date OR p_day < v_today,
          version = version + 1
      WHERE organization_id = p_organization_id AND id = v_record.id
      RETURNING id, version INTO v_id, v_version;
    ELSE
      v_before := 'null'::json;
      INSERT INTO revenue.records (
        organization_id, vehicle_id, business_date, amount, reason, note,
        captured_at, captured_by, updated_at, updated_by
      )
      VALUES (
        p_organization_id, p_vehicle_id, p_day, v_amount, v_reason, v_note,
        p_now, p_actor_id, p_now, p_actor_id
      )
      RETURNING id, version INTO v_id, v_version;
    END IF;
  EXCEPTION
    WHEN lock_not_available THEN
      PERFORM tenancy.refuse('revenue_concurrent_save', 'XC409');
    WHEN unique_violation THEN
      PERFORM tenancy.refuse('unique_conflict', 'XC409');
  END;

  v_after := revenue.record_snapshot(v_id);
  v_which := ' for ' || v_registration || ' on ' || tenancy.fmt_day(p_day);
  PERFORM tenancy.record_change(
    'revenue',
    v_id,
    p_vehicle_id,
    v_before,
    v_after,
    CASE
      WHEN NOT v_exists AND v_amount IS NULL THEN
        'Recorded no revenue' || v_which || ': ' || revenue.reason_label(v_reason)
      WHEN NOT v_exists AND v_reason IS NOT NULL THEN
        'Recorded revenue' || v_which || ': ' || revenue.reason_label(v_reason)
      WHEN NOT v_exists THEN 'Recorded revenue' || v_which
      WHEN p_day < v_today THEN 'Corrected revenue' || v_which
      ELSE 'Updated revenue' || v_which
    END,
    'revenue.recorded',
    v_id::text,
    v_before::jsonb,
    v_after::jsonb,
    p_now
  );
  RETURN ROW(v_id, v_version, CASE WHEN v_exists THEN 'updated' ELSE 'created' END)::api.write_result;
END;
$$;

