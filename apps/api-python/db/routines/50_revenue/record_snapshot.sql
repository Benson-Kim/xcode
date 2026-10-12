-- revenue.record_snapshot(p_id uuid) RETURNS json
-- Purpose: the change-log snapshot of a revenue record with the .NET keys in order (Id, VehicleId, BusinessDate, Amount, Reason, Note, CapturedAt, CapturedBy, UpdatedAt, UpdatedBy, CorrectedAfterDate, Version); Reason is the .NET enum name (NoCrew), the amount has no trailing zeros; the string null for an unknown id.
-- Callers: api.revenue_capture.
-- Reads: revenue.records, revenue.no_earnings_reasons. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_revenue_helpers.py, tests/db/test_revenue_routines.py.

CREATE OR REPLACE FUNCTION revenue.record_snapshot(p_id uuid)
RETURNS json
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT tenancy.compact_json(coalesce(
    (
      SELECT json_build_object(
               'Id', r.id,
               'VehicleId', r.vehicle_id,
               'BusinessDate', r.business_date,
               'Amount', trim_scale(r.amount),
               'Reason', replace(l.label, ' ', ''),
               'Note', r.note,
               'CapturedAt', tenancy.fmt_instant(r.captured_at),
               'CapturedBy', r.captured_by,
               'UpdatedAt', tenancy.fmt_instant(r.updated_at),
               'UpdatedBy', r.updated_by,
               'CorrectedAfterDate', r.corrected_after_date,
               'Version', r.version
             )
      FROM revenue.records AS r
      LEFT JOIN revenue.no_earnings_reasons AS l ON l.code = r.reason
      WHERE r.organization_id = tenancy.current_organization() AND r.id = p_id
    ),
    'null'::json
  ));
$$;

REVOKE ALL ON FUNCTION revenue.record_snapshot(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION revenue.record_snapshot(uuid) TO xcode_api_executor;
