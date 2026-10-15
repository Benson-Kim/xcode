-- revenue.capture_row(p_organization_id uuid, p_actor_id uuid, p_permissions text[], p_threshold numeric, p_today date, p_writable_from date, p_vehicle_id uuid, p_day date, p_amount numeric, p_reason text, p_note text, p_expected_version bigint, p_captured_at timestamptz, p_now timestamptz, p_decide boolean) RETURNS api.write_result
-- Purpose: the steps of revenue.capture_entry for one vehicle and day, with what is the same for every row of a call given by the caller: the actor's rights, the low-day threshold, the business date and the earliest writable date as of the capture time (-infinity: no limit; each NULL: worked out here, at the step that needs it). p_decide false leaves the saving runs to the caller (one decision for many vehicles).
-- Callers: revenue.capture_entry, api.revenue_day_save.
-- Reads: setup.fleet_vehicles, revenue.records, and what tenancy.effective_permissions, tenancy.settings_document, revenue.check_entry, setup.vehicle_visible, tenancy.business_date, setup.vehicle_active_on, setup.vehicle_away_on, tenancy.check_writable, tenancy.earliest_writable, revenue.vehicle_days, revenue.cell and revenue.record_snapshot read. Writes: revenue.records, setup.saving_runs through setup.decide_saving_runs, and what tenancy.record_change writes.
-- Raises: XC422 revenue_reason_invalid via revenue.check_entry, XC422 money_invalid via revenue.check_entry, XC422 revenue_entry_required via revenue.check_entry, XC422 revenue_note_length via revenue.check_entry, XC422 revenue_note_without_other via revenue.check_entry, XC404 not_found, XC422 time_zone_invalid via tenancy.business_date, XC409 revenue_concurrent_save, XC422 revenue_low_needs_reason, XC422 revenue_amount_with_reason, XC422 revenue_future_date, XC422 revenue_vehicle_away, XC422 revenue_vehicle_inactive, XC403 revenue_capture_permission, XC403 revenue_correct_permission, XC422 record_too_old, XC422 record_too_old via tenancy.check_writable, XC409 revenue_version_conflict, XC409 unique_conflict.
-- Tests: tests/db/test_revenue_routines.py, tests/db/test_revenue_day_routines.py, tests/api/test_revenue.py.
-- The steps and their order are revenue.capture_entry's. A given earliest writable date stands
-- for tenancy.check_writable as of the capture time: the same refusal, with the same detail.
-- No subtransaction per row: the day's record is locked with SKIP LOCKED, and a record that
-- exists but was skipped is held by another save (revenue_concurrent_save); a first capture
-- inserts with ON CONFLICT DO NOTHING, and no row back means another first capture won the
-- day (unique_conflict).

CREATE OR REPLACE FUNCTION revenue.capture_row(
  p_organization_id uuid,
  p_actor_id uuid,
  p_permissions text[],
  p_threshold numeric,
  p_today date,
  p_writable_from date,
  p_vehicle_id uuid,
  p_day date,
  p_amount numeric,
  p_reason text,
  p_note text,
  p_expected_version bigint,
  p_captured_at timestamptz,
  p_now timestamptz,
  p_decide boolean
)
RETURNS api.write_result
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  c_offline_window CONSTANT interval := interval '72 hours';
  v_permissions text[] := coalesce(p_permissions, tenancy.effective_permissions(p_organization_id, p_actor_id));
  v_threshold numeric;
  v_amount numeric;
  v_reason smallint;
  v_note text;
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
  v_threshold := coalesce(
    p_threshold, (tenancy.settings_document('revenue') ->> 'low_day_threshold')::numeric
  );
  SELECT e.amount, e.reason, e.note INTO v_amount, v_reason, v_note
  FROM revenue.check_entry(p_amount, p_reason, p_note) AS e;

  SELECT f.registration INTO v_registration
  FROM setup.fleet_vehicles AS f
  WHERE f.organization_id = p_organization_id AND f.id = p_vehicle_id
  FOR SHARE;
  IF NOT FOUND OR NOT setup.vehicle_visible(p_vehicle_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  v_today := coalesce(p_today, tenancy.business_date(p_organization_id, p_now));

  SELECT r.* INTO v_record
  FROM revenue.records AS r
  WHERE r.organization_id = p_organization_id
    AND r.vehicle_id = p_vehicle_id
    AND r.business_date = p_day
  FOR UPDATE SKIP LOCKED;
  v_exists := FOUND;
  IF NOT v_exists AND EXISTS (
    SELECT 1
    FROM revenue.records AS r
    WHERE r.organization_id = p_organization_id
      AND r.vehicle_id = p_vehicle_id
      AND r.business_date = p_day
  ) THEN
    PERFORM tenancy.refuse('revenue_concurrent_save', 'XC409');
  END IF;

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

  IF p_writable_from IS NULL THEN
    PERFORM tenancy.check_writable(
      p_day, greatest(least(coalesce(p_captured_at, p_now), p_now), p_now - c_offline_window)
    );
  ELSIF p_day < p_writable_from THEN
    PERFORM tenancy.refuse(
      'record_too_old', 'XC422',
      jsonb_build_object('earliest', to_char(p_writable_from, 'YYYY-MM-DD'))
    );
  END IF;

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
    ON CONFLICT ON CONSTRAINT uq_records_vehicle_day DO NOTHING
    RETURNING id, version INTO v_id, v_version;
    IF NOT FOUND THEN
      PERFORM tenancy.refuse('unique_conflict', 'XC409');
    END IF;
  END IF;

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
  IF p_decide THEN
    PERFORM setup.decide_saving_runs(p_vehicle_id, p_day, p_day, p_now);
  END IF;
  RETURN ROW(v_id, v_version, CASE WHEN v_exists THEN 'updated' ELSE 'created' END)::api.write_result;
END;
$$;

REVOKE ALL ON FUNCTION revenue.capture_row(
  uuid, uuid, text[], numeric, date, date, uuid, date, numeric, text, text, bigint, timestamptz, timestamptz, boolean
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION revenue.capture_row(
  uuid, uuid, text[], numeric, date, date, uuid, date, numeric, text, text, bigint, timestamptz, timestamptz, boolean
) TO xcode_api_executor;
