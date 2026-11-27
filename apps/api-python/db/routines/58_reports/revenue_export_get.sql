-- api.revenue_export_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_week_start date, p_company_id uuid, p_format text, p_now timestamptz) RETURNS jsonb
-- Purpose: the Revenue screen as a file's document, in one transaction with its audit row: the format first, then the week grid exactly as api.revenue_week_get serves it to the screen (the legacy page of at most 500 vehicles, the company filter), as the Revenue table: vehicle, company, the seven days (the amount, "12,600, Not fueled" for an amount the vehicle was not fueled on, the no-earnings reason, "Missing" or nothing), Week total, and while Targets is on Target to date (Target for a finished week) and the signed Gap; headline Revenue; figures Gap to target so far (Gap to target) while Targets is on, Low days, Not fueled and Missing days; the change-log row holds {screen, weekStart, companyId, rows, format}.
-- Callers: ReportsRoutines.export_revenue; ExportRevenueWeek (GET /setup/revenue/export).
-- Reads: what tenancy.require_permission, tenancy.setting_enabled, reports.check_export, api.revenue_week_get and reports.document read. Writes: what reports.log_export writes.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC403 permission_missing via tenancy.require_permission, XC422 export_format_invalid via reports.check_export, XC422 time_zone_invalid via api.revenue_week_get, XC422 revenue_week_range via api.revenue_week_get, XC422 export_too_many_rows via reports.check_export.
-- Tests: tests/db/test_report_routines.py, tests/api/test_reports.py.

CREATE OR REPLACE FUNCTION api.revenue_export_get(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_week_start date,
  p_company_id uuid,
  p_format text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_format text;
  v_week jsonb;
  v_today date;
  v_start date;
  v_through date;
  v_finished boolean;
  v_targets boolean;
  v_columns jsonb;
  v_rows jsonb;
  v_count integer;
  v_table jsonb;
  v_filters text;
  v_document jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'revenue.export');
  PERFORM tenancy.require_permission('revenue.view');
  v_format := reports.check_export(p_format, NULL);
  v_week := api.revenue_week_get(
    p_actor_id, p_organization_id, p_request_id, p_week_start, p_company_id,
    NULL, NULL, NULL, NULL, p_now
  );
  v_today := (v_week ->> 'business_date')::date;
  v_start := (v_week ->> 'week_start')::date;
  v_through := (v_week ->> 'week_through')::date;
  v_finished := v_through < v_today;
  v_targets := tenancy.setting_enabled('targets');

  SELECT jsonb_build_array(
           reports.heading('vehicle', 'Vehicle', 'vehicle', false),
           reports.heading('company', 'Company', 'text', false)
         )
         || coalesce(
              (
                SELECT jsonb_agg(
                         reports.heading(
                           to_char(d.day, 'YYYY-MM-DD'), to_char(d.day, 'Dy FMDD'), 'money', false
                         ) ORDER BY d.day)
                FROM generate_series(v_start::timestamp, v_through::timestamp, interval '1 day')
                     AS d (day)
              ),
              '[]'::jsonb
            )
         || jsonb_build_array(reports.heading('total', 'Week total', 'money', true))
         || CASE
              WHEN v_targets THEN jsonb_build_array(
                reports.heading(
                  'target', CASE WHEN v_finished THEN 'Target' ELSE 'Target to date' END, 'money',
                  true
                ),
                reports.heading('gap', 'Gap', 'net', true)
              )
              ELSE '[]'::jsonb
            END
  INTO v_columns;

  WITH vehicles AS (
    SELECT v.doc, v.ord
    FROM jsonb_array_elements(v_week -> 'vehicles') WITH ORDINALITY AS v (doc, ord)
  ),
  lines AS (
    SELECT v.ord,
           v.doc,
           (
             SELECT coalesce(
                      jsonb_agg(
                        CASE d.cell ->> 'status'
                          WHEN 'amount' THEN
                            CASE
                              WHEN d.cell ->> 'fuel' = 'no' THEN to_jsonb(
                                tenancy.fmt_money((d.cell ->> 'amount')::numeric) || ', Not fueled'
                              )
                              ELSE d.cell -> 'amount'
                            END
                          WHEN 'reason' THEN d.cell -> 'reason'
                          WHEN 'missing' THEN to_jsonb('Missing'::text)
                          ELSE 'null'::jsonb
                        END ORDER BY d.ord),
                      '[]'::jsonb
                    )
             FROM jsonb_array_elements(v.doc -> 'days') WITH ORDINALITY AS d (cell, ord)
           ) AS day_cells
    FROM vehicles AS v
  )
  SELECT coalesce(
           jsonb_agg(
             jsonb_build_array(l.doc ->> 'registration', l.doc ->> 'company_name')
             || l.day_cells
             || jsonb_build_array(l.doc -> 'total_amount')
             || CASE
                  WHEN v_targets THEN jsonb_build_array(l.doc -> 'total_expected', l.doc -> 'gap')
                  ELSE '[]'::jsonb
                END
             ORDER BY l.ord),
           '[]'::jsonb
         ),
         count(*)
  INTO v_rows, v_count
  FROM lines AS l;

  PERFORM reports.check_export(v_format, v_count);
  v_table := reports.build_table(
    'revenue',
    'week',
    'Revenue',
    v_start,
    least(v_through, v_today),
    v_today,
    reports.figure('Revenue', (v_week ->> 'total_amount')::numeric, 'money'),
    CASE
      WHEN v_targets THEN jsonb_build_array(
        reports.figure(
          CASE WHEN v_finished THEN 'Gap to target' ELSE 'Gap to target so far' END,
          (v_week ->> 'gap')::numeric,
          'net'
        )
      )
      ELSE '[]'::jsonb
    END
    || jsonb_build_array(
      reports.figure('Low days', (v_week ->> 'below_threshold_days')::numeric, 'count'),
      reports.figure('Not fueled', (v_week ->> 'not_fueled_days')::numeric, 'count'),
      reports.figure('Missing days', (v_week ->> 'missing_days')::numeric, 'count')
    ),
    v_columns,
    v_rows
  );
  v_filters := coalesce(
    (
      SELECT c.doc ->> 'name'
      FROM jsonb_array_elements(v_week -> 'companies') AS c (doc)
      WHERE (c.doc ->> 'id')::uuid = p_company_id
    ),
    'All companies'
  );
  v_document := reports.document(v_table, v_rows, v_filters, v_format, p_now);
  PERFORM reports.log_export(
    v_table,
    v_count,
    v_filters,
    NULL,
    v_format,
    jsonb_build_object(
      'screen', 'revenue',
      'weekStart', v_start,
      'companyId', p_company_id,
      'rows', v_count,
      'format', v_format
    ),
    p_now
  );
  RETURN v_document;
END;
$$;
