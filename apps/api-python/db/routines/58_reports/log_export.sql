-- reports.log_export(p_table jsonb, p_row_count integer, p_filters text, p_q text, p_format text, p_snapshot jsonb, p_now timestamptz) RETURNS void
-- Purpose: the audit row of an export, in the export's own transaction: one change-log entry in section reports under a new entity id with no vehicle, before null, after the snapshot (the export's filters and row count, compact), reason "Exported {title}[ for {period}][, searched for "{q}"] to {Excel|PDF}", and the audit event reports.exported with the snapshot and the filters text.
-- Callers: api.report_export_get, api.revenue_export_get, api.expenses_export_get, api.pettycash_export_get.
-- Reads: nothing. Writes: what tenancy.record_change writes.
-- Raises: XC403 not_member via tenancy.record_change.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.log_export(
  p_table jsonb,
  p_row_count integer,
  p_filters text,
  p_q text,
  p_format text,
  p_snapshot jsonb,
  p_now timestamptz
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_from date := (p_table ->> 'from_date')::date;
  v_to date := (p_table ->> 'to_date')::date;
  v_period text;
  v_id uuid := gen_random_uuid();
  v_snapshot json := tenancy.compact_json(p_snapshot::json);
BEGIN
  v_period := CASE
                WHEN v_from IS NULL THEN NULL
                WHEN v_from = v_to THEN tenancy.fmt_day(v_from)
                ELSE tenancy.fmt_day(v_from) || ' to ' || tenancy.fmt_day(v_to)
              END;
  PERFORM tenancy.record_change(
    'reports',
    v_id,
    NULL,
    'null'::json,
    v_snapshot,
    'Exported ' || (p_table ->> 'title')
      || coalesce(' for ' || v_period, '')
      || coalesce(', searched for "' || p_q || '"', '')
      || ' to ' || CASE p_format WHEN 'pdf' THEN 'PDF' ELSE 'Excel' END,
    'reports.exported',
    v_id::text,
    NULL,
    p_snapshot || jsonb_build_object('filters', p_filters, 'rows', p_row_count),
    p_now
  );
END;
$$;

REVOKE ALL ON FUNCTION reports.log_export(jsonb, integer, text, text, text, jsonb, timestamptz) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.log_export(jsonb, integer, text, text, text, jsonb, timestamptz)
  TO xcode_api_executor;
