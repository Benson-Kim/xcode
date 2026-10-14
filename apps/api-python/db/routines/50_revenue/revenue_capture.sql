-- api.revenue_capture(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_vehicle_id uuid, p_day date, p_amount numeric, p_reason text, p_note text, p_expected_version bigint, p_captured_at timestamptz, p_now timestamptz) RETURNS api.write_result
-- Purpose: record a vehicle's revenue for a day (an amount; below the low-day threshold an amount with a reason) or a no-revenue reason, by the natural key (vehicle, day): created, updated, or replayed (an identical entry, answered with the stored id and version and nothing written); the capture and offline-replay endpoint. p_captured_at is when the client captured the entry (NULL: now). Membership and either right here; every other step in revenue.capture_entry.
-- Callers: RevenueRoutines.capture; CaptureRevenue (PUT /setup/revenue/{vehicleId}/{date}).
-- Reads: what tenancy.effective_permissions and revenue.capture_entry read. Writes: what revenue.capture_entry writes.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing, XC422 revenue_reason_invalid via revenue.capture_entry, XC422 money_invalid via revenue.capture_entry, XC422 revenue_entry_required via revenue.capture_entry, XC422 revenue_note_length via revenue.capture_entry, XC422 revenue_note_without_other via revenue.capture_entry, XC404 not_found via revenue.capture_entry, XC422 time_zone_invalid via revenue.capture_entry, XC422 revenue_low_needs_reason via revenue.capture_entry, XC422 revenue_amount_with_reason via revenue.capture_entry, XC422 revenue_future_date via revenue.capture_entry, XC422 revenue_vehicle_away via revenue.capture_entry, XC422 revenue_vehicle_inactive via revenue.capture_entry, XC403 revenue_capture_permission via revenue.capture_entry, XC403 revenue_correct_permission via revenue.capture_entry, XC422 record_too_old via revenue.capture_entry, XC409 revenue_version_conflict via revenue.capture_entry, XC409 revenue_concurrent_save via revenue.capture_entry, XC409 unique_conflict via revenue.capture_entry.
-- Tests: tests/db/test_revenue_routines.py, tests/db/test_revenue_day_routines.py, tests/api/test_revenue.py.

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
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  IF NOT tenancy.effective_permissions(p_organization_id, p_actor_id)
         && ARRAY['revenue.capture', 'revenue.correct'] THEN
    PERFORM tenancy.refuse('permission_missing', 'XC403');
  END IF;
  RETURN revenue.capture_entry(
    p_organization_id, p_actor_id, p_vehicle_id, p_day, p_amount, p_reason, p_note,
    p_expected_version, p_captured_at, p_now
  );
END;
$$;
