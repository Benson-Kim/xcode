-- api.expenses_export_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_from date, p_to date, p_source text, p_q text, p_format text, p_now timestamptz) RETURNS jsonb
-- Purpose: the Central expenses screen as a file's document, in one transaction with its audit row: the format first, then the ledger's own checks (expenses.check_ledger), then every row the ledger lists for the period, source and search (expenses.ledger_rows, matched, in the screen's order) as the table Central expenses: date, vehicle, item, category, quantity, unit amount, amount, source and recorded by ("Standing order" for a scheduled row, "{recorder}, {holder}'s float" for petty cash); headline Central expenses (the matched rows' amount), figures Central, Petty cash and Scheduled over every row of the period; the change-log row holds {screen, from, to, source, q, rows, format}.
-- Callers: ReportsRoutines.export_expenses; ExportExpenseLedger (GET /setup/expenses/export).
-- Reads: what tenancy.require_permission, tenancy.business_date, reports.check_export, expenses.check_ledger, setup.visible_vehicles, expenses.ledger_rows and reports.document read. Writes: what reports.log_export writes.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC403 permission_missing via tenancy.require_permission, XC422 export_format_invalid via reports.check_export, XC422 expense_period_required via expenses.check_ledger, XC422 expense_period_order via expenses.check_ledger, XC422 expense_period_length via expenses.check_ledger, XC422 expense_source_invalid via expenses.check_ledger, XC422 expense_search_length via expenses.check_ledger, XC422 time_zone_invalid via tenancy.business_date, XC422 export_too_many_rows via reports.check_export.
-- Tests: tests/db/test_report_routines.py, tests/api/test_reports.py.

CREATE OR REPLACE FUNCTION api.expenses_export_get(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_from date,
  p_to date,
  p_source text,
  p_q text,
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
  v_source text;
  v_text text := tenancy.trim_text(p_q);
  v_today date;
  v_rows jsonb;
  v_count integer;
  v_amount numeric;
  v_central numeric;
  v_pettycash numeric;
  v_scheduled numeric;
  v_table jsonb;
  v_filters text;
  v_document jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'expenses.export');
  PERFORM tenancy.require_permission('expenses.view');
  v_format := reports.check_export(p_format, NULL);
  v_source := expenses.check_ledger(p_from, p_to, p_source, p_q);
  v_today := tenancy.business_date(p_organization_id, p_now);

  WITH rows AS MATERIALIZED (
    SELECT r.*
    FROM expenses.ledger_rows(
           ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id)),
           p_from,
           p_to,
           v_today,
           v_source,
           v_text,
           p_actor_id,
           false,
           false,
           NULL
         ) AS r
  )
  SELECT coalesce(
           (
             SELECT jsonb_agg(
                      jsonb_build_array(
                        r.entry_date,
                        r.registration,
                        r.item_name,
                        r.category_name,
                        r.units,
                        r.unit_amount,
                        r.total,
                        CASE r.source_order WHEN 1 THEN 'Central' WHEN 2 THEN 'Petty cash' ELSE 'Scheduled' END,
                        CASE r.source_order
                          WHEN 1 THEN r.recorded_by_name
                          WHEN 2 THEN r.recorded_by_name || ', ' || r.holder_name || '''s float'
                          ELSE 'Standing order'
                        END
                      )
                      ORDER BY r.entry_date DESC, r.source_order, r.registration COLLATE "C", r.id COLLATE "C")
             FROM rows AS r
             WHERE r.matched
           ),
           '[]'::jsonb
         ),
         (SELECT count(*) FROM rows AS r WHERE r.matched),
         (SELECT coalesce(sum(r.total), 0) FROM rows AS r WHERE r.matched),
         (SELECT coalesce(sum(r.total), 0) FROM rows AS r WHERE r.source_order = 1),
         (SELECT coalesce(sum(r.total), 0) FROM rows AS r WHERE r.source_order = 2),
         (SELECT coalesce(sum(r.total), 0) FROM rows AS r WHERE r.source_order = 3)
  INTO v_rows, v_count, v_amount, v_central, v_pettycash, v_scheduled;

  PERFORM reports.check_export(v_format, v_count);
  v_table := reports.build_table(
    'expenses',
    'ledger',
    'Central expenses',
    p_from,
    least(p_to, v_today),
    v_today,
    reports.figure('Central expenses', v_amount, 'money'),
    jsonb_build_array(
      reports.figure('Central', v_central, 'money'),
      reports.figure('Petty cash', v_pettycash, 'money'),
      reports.figure('Scheduled', v_scheduled, 'money')
    ),
    jsonb_build_array(
      reports.heading('date', 'Date', 'date', false),
      reports.heading('vehicle', 'Vehicle', 'vehicle', false),
      reports.heading('item', 'Item', 'text', false),
      reports.heading('category', 'Category', 'text', false),
      reports.heading('quantity', 'Quantity', 'quantity', true),
      reports.heading('unitAmount', 'Unit amount', 'money', false),
      reports.heading('amount', 'Amount', 'money', true),
      reports.heading('source', 'Source', 'text', false),
      reports.heading('recordedBy', 'Recorded by', 'text', false)
    ),
    v_rows
  );
  v_filters := CASE v_source
                 WHEN 'central' THEN 'Central'
                 WHEN 'pettycash' THEN 'Petty cash'
                 WHEN 'scheduled' THEN 'Scheduled'
                 ELSE 'All sources'
               END;
  v_document := reports.document(v_table, v_rows, v_filters, v_format, p_now);
  PERFORM reports.log_export(
    v_table,
    v_count,
    v_filters,
    v_text,
    v_format,
    jsonb_build_object(
      'screen', 'expenses',
      'from', p_from,
      'to', p_to,
      'source', v_source,
      'q', v_text,
      'rows', v_count,
      'format', v_format
    ),
    p_now
  );
  RETURN v_document;
END;
$$;
