-- revenue.capture_entry(p_organization_id uuid, p_actor_id uuid, p_vehicle_id uuid, p_day date, p_amount numeric, p_reason text, p_note text, p_expected_version bigint, p_captured_at timestamptz, p_now timestamptz) RETURNS api.write_result
-- Purpose: the steps of one revenue capture after the caller's membership and right checks: record a vehicle's revenue for a day (an amount; below the low-day threshold an amount with a reason) or a no-revenue reason, by the natural key (vehicle, day): created, updated, or replayed (an identical entry, answered with the stored id and version and nothing written); a write then decides the saving runs the day completes. p_captured_at is when the client captured the entry (NULL: now).
-- Callers: api.revenue_capture.
-- Reads: what revenue.capture_row reads; setup.fleet_vehicles, revenue.records, and what tenancy.effective_permissions, tenancy.settings_document, revenue.check_entry, setup.vehicle_visible, tenancy.business_date, setup.vehicle_active_on, setup.vehicle_away_on, tenancy.check_writable, tenancy.earliest_writable, revenue.vehicle_days, revenue.cell and revenue.record_snapshot read. Writes: through revenue.capture_row: revenue.records, setup.saving_runs through setup.decide_saving_runs, and what tenancy.record_change writes.
-- Raises: XC422 revenue_reason_invalid via revenue.capture_row, XC422 money_invalid via revenue.capture_row, XC422 revenue_entry_required via revenue.capture_row, XC422 revenue_note_length via revenue.capture_row, XC422 revenue_note_without_other via revenue.capture_row, XC404 not_found via revenue.capture_row, XC422 time_zone_invalid via revenue.capture_row, XC422 revenue_low_needs_reason via revenue.capture_row, XC422 revenue_amount_with_reason via revenue.capture_row, XC422 revenue_future_date via revenue.capture_row, XC422 revenue_vehicle_away via revenue.capture_row, XC422 revenue_vehicle_inactive via revenue.capture_row, XC403 revenue_capture_permission via revenue.capture_row, XC403 revenue_correct_permission via revenue.capture_row, XC422 record_too_old via revenue.capture_row, XC409 revenue_version_conflict via revenue.capture_row, XC409 revenue_concurrent_save via revenue.capture_row, XC409 unique_conflict via revenue.capture_row.
-- Tests: tests/db/test_revenue_routines.py, tests/db/test_revenue_day_routines.py, tests/api/test_revenue.py.
-- The steps run in this order, the first failing one answering: the entry's shape; the vehicle
-- in the caller's view, its row held FOR SHARE so a retirement or join-date change in flight
-- (which locks the vehicle and then looks for revenue it would strand) commits first and is
-- read, or waits for this one; the day's record locked without waiting (a save holding it makes
-- this one revenue_concurrent_save, and the lock keeps the version read until the write); an
-- identical entry answered as replayed, whatever version was sent, whatever the date, the
-- threshold, the limit and the permissions, so a phone draining its queue late always
-- succeeds, also with an entry saved under earlier rules; the amount against the
-- organization's low-day threshold; a future day; a day the vehicle is not in the fleet; the
-- permission of the path (capture fills a day without a record, correct changes a saved one),
-- before anything stored is shown; the caller's back-dating limit on the day, as of the
-- capture time held to the last 72 hours; the version, a conflict carrying the stored cell as
-- current; the write, a first capture racing another one ending as unique_conflict; the
-- change-log row; the saving runs the day completes. Days are captured in any order.

CREATE OR REPLACE FUNCTION revenue.capture_entry(
  p_organization_id uuid,
  p_actor_id uuid,
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
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
  RETURN revenue.capture_row(
    p_organization_id, p_actor_id, NULL, NULL, NULL, NULL, p_vehicle_id, p_day, p_amount,
    p_reason, p_note, p_expected_version, p_captured_at, p_now, true
  );
END;
$$;

REVOKE ALL ON FUNCTION revenue.capture_entry(
  uuid, uuid, uuid, date, numeric, text, text, bigint, timestamptz, timestamptz
) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION revenue.capture_entry(
  uuid, uuid, uuid, date, numeric, text, text, bigint, timestamptz, timestamptz
) TO xcode_api_executor;
