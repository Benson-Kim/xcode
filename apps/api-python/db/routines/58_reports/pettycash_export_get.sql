-- api.pettycash_export_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_from date, p_to date, p_holder_id uuid, p_view text, p_status text[], p_q text, p_format text, p_now timestamptz) RETURNS jsonb
-- Purpose: the Petty cash screen as a file's document, in one transaction with its audit row: the format first, the view (expenses or cash), the overview's period checks, the list's status words and search length, the float among the ones the actor sees, then every entry the list shows for those filters (pettycash.entry_matches, by date, kind, id) as the table "Petty cash, expenses" (date, manager, vehicle, item, units, unit amount, amount, status, note, recorded by) or "Petty cash, cash received" (date, manager, description, the amount with credit notes negative, note, recorded by); headline Cash balance (the window's closing balance of the chosen floats), figures Cash received, Expenses, Credit notes and Waiting; the change-log row holds {screen, from, to, holderId, view, status, q, rows, format}.
-- Callers: ReportsRoutines.export_pettycash; ExportPettyCash (GET /setup/pettycash/export).
-- Reads: what tenancy.require_any_permission, tenancy.business_date, tenancy.effective_permissions, reports.check_export, pettycash.check_period, pettycash.visible_holders, setup.visible_vehicles, pettycash.entry_matches, reports.pettycash_entries, pettycash.tallies and reports.document read. Writes: what reports.log_export writes.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 export_format_invalid via reports.check_export, XC422 pettycash_export_view_invalid, XC422 time_zone_invalid via tenancy.business_date, XC422 pettycash_range_both via pettycash.check_period, XC422 history_dates_order via pettycash.check_period, XC422 pettycash_range_length via pettycash.check_period, XC422 pettycash_range_start via pettycash.check_period, XC422 pettycash_too_old via pettycash.check_period, XC422 pettycash_status_invalid, XC422 history_text_length, XC404 not_found, XC422 export_too_many_rows via reports.check_export.
-- Tests: tests/db/test_report_routines.py, tests/api/test_reports.py.

CREATE OR REPLACE FUNCTION api.pettycash_export_get(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_from date,
  p_to date,
  p_holder_id uuid,
  p_view text,
  p_status text[],
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
  v_view text := tenancy.trim_text(p_view);
  v_text text := tenancy.trim_text(p_q);
  v_today date;
  v_permissions text[];
  v_view_all boolean;
  v_holders uuid[];
  v_vehicles uuid[];
  v_kinds smallint[];
  v_statuses text[];
  v_columns jsonb;
  v_rows jsonb;
  v_count integer;
  v_opening numeric;
  v_cash numeric;
  v_expenses numeric;
  v_credit numeric;
  v_waiting numeric;
  v_table jsonb;
  v_filters text;
  v_document jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'pettycash.export');
  PERFORM tenancy.require_any_permission(ARRAY['pettycash.view']);
  v_format := reports.check_export(p_format, NULL);
  IF v_view IS NULL OR v_view NOT IN ('expenses', 'cash') THEN
    PERFORM tenancy.refuse('pettycash_export_view_invalid', 'XC422');
  END IF;
  v_today := tenancy.business_date(p_organization_id, p_now);
  PERFORM pettycash.check_period(p_from, p_to, v_today);
  IF EXISTS (
    SELECT 1 FROM unnest(p_status) AS s
    WHERE s IS NULL OR s NOT IN ('waiting', 'approved', 'sentBack', 'rejected')
  ) THEN
    PERFORM tenancy.refuse('pettycash_status_invalid', 'XC422');
  END IF;
  IF char_length(v_text) > 200 THEN
    PERFORM tenancy.refuse('history_text_length', 'XC422');
  END IF;

  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  v_view_all := 'pettycash.view_all' = ANY (v_permissions);
  v_holders := ARRAY(
    SELECT h.user_id
    FROM pettycash.visible_holders(v_view_all) AS h
    WHERE p_holder_id IS NULL OR h.user_id = p_holder_id
  );
  IF p_holder_id IS NOT NULL AND cardinality(v_holders) = 0 THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  v_vehicles := ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id));
  v_kinds := CASE v_view WHEN 'expenses' THEN ARRAY[2::smallint] ELSE ARRAY[1::smallint, 3::smallint] END;
  v_statuses := CASE WHEN v_view = 'expenses' THEN p_status END;

  WITH listed AS (
    SELECT m.id, m.entry_date, m.kind, m.status, m.sent_back_note, m.payee, m.total AS signed_total
    FROM pettycash.entry_matches(
           p_holder_id, p_from, p_to, v_kinds, v_statuses, v_text, v_view_all, v_vehicles
         ) AS m
  ),
  lines AS (
    SELECT l.id, l.entry_date, l.kind, n.holder_name, n.registration, n.item_name, n.units,
           n.unit_amount, n.total, n.note, n.recorded_by_name, n.payee,
           CASE pettycash.status_word(l.status, l.sent_back_note)
             WHEN 'waiting' THEN 'Waiting'
             WHEN 'sentBack' THEN 'Sent back'
             WHEN 'approved' THEN 'Approved'
             WHEN 'rejected' THEN 'Rejected'
           END AS status_label
    FROM listed AS l
    JOIN reports.pettycash_entries(v_holders, v_view_all, v_vehicles) AS n ON n.id = l.id
  )
  SELECT CASE
           WHEN v_view = 'expenses' THEN coalesce(
             jsonb_agg(
               jsonb_build_array(
                 l.entry_date, l.holder_name, l.registration, l.item_name, l.units, l.unit_amount,
                 l.total, l.status_label, l.note, l.recorded_by_name
               ) ORDER BY l.entry_date, l.kind, l.id),
             '[]'::jsonb
           )
           ELSE coalesce(
             jsonb_agg(
               jsonb_build_array(
                 l.entry_date,
                 l.holder_name,
                 CASE l.kind
                   WHEN 1 THEN CASE WHEN l.total < 0 THEN 'Cash taken back' ELSE 'Cash given' END
                   ELSE 'Credit note' || coalesce(' to ' || l.payee, '')
                 END,
                 CASE l.kind WHEN 3 THEN -l.total ELSE l.total END,
                 l.note,
                 l.recorded_by_name
               ) ORDER BY l.entry_date, l.kind, l.id),
             '[]'::jsonb
           )
         END,
         count(*)
  INTO v_rows, v_count
  FROM lines AS l;

  PERFORM reports.check_export(v_format, v_count);

  SELECT coalesce(sum(pettycash.effect(t.kind, t.status, t.total)) FILTER (WHERE t.window_position = 0), 0),
         coalesce(sum(t.total) FILTER (WHERE t.window_position = 1 AND t.kind = 1), 0),
         coalesce(sum(t.total) FILTER (WHERE t.window_position = 1 AND t.kind = 2 AND t.status <> 4), 0),
         coalesce(sum(t.total) FILTER (WHERE t.window_position = 1 AND t.kind = 3), 0),
         coalesce(sum(t.total) FILTER (
           WHERE t.window_position = 1 AND t.kind = 2 AND t.status = 1 AND NOT t.sent_back), 0)
  INTO v_opening, v_cash, v_expenses, v_credit, v_waiting
  FROM pettycash.tallies(v_holders, p_from, p_to, v_view_all, v_vehicles) AS t;

  v_columns := CASE
    WHEN v_view = 'expenses' THEN jsonb_build_array(
      reports.heading('date', 'Date', 'date', false),
      reports.heading('manager', 'Manager', 'text', false),
      reports.heading('vehicle', 'Vehicle', 'vehicle', false),
      reports.heading('item', 'Item', 'text', false),
      reports.heading('units', 'Units', 'quantity', true),
      reports.heading('unitAmount', 'Unit amount', 'money', false),
      reports.heading('amount', 'Amount', 'money', true),
      reports.heading('status', 'Status', 'text', false),
      reports.heading('note', 'Note', 'text', false),
      reports.heading('recordedBy', 'Recorded by', 'text', false)
    )
    ELSE jsonb_build_array(
      reports.heading('date', 'Date', 'date', false),
      reports.heading('manager', 'Manager', 'text', false),
      reports.heading('description', 'Description', 'text', false),
      reports.heading('amount', 'Amount', 'net', true),
      reports.heading('note', 'Note', 'text', false),
      reports.heading('recordedBy', 'Recorded by', 'text', false)
    )
  END;
  v_table := reports.build_table(
    'pettycash',
    v_view,
    CASE WHEN v_view = 'expenses' THEN 'Petty cash, expenses' ELSE 'Petty cash, cash received' END,
    p_from,
    least(p_to, v_today),
    v_today,
    reports.figure('Cash balance', v_opening + v_cash - v_expenses - v_credit, 'money'),
    jsonb_build_array(
      reports.figure('Cash received', v_cash, 'money'),
      reports.figure('Expenses', v_expenses, 'money'),
      reports.figure('Credit notes', v_credit, 'money'),
      reports.figure('Waiting', v_waiting, 'money')
    ),
    v_columns,
    v_rows
  );
  v_filters := coalesce(
    (SELECT h.name FROM pettycash.visible_holders(v_view_all) AS h WHERE h.user_id = p_holder_id),
    'All floats'
  ) || coalesce(', ' || nullif(array_to_string(v_statuses, ', '), ''), '');
  v_document := reports.document(v_table, v_rows, v_filters, v_format, p_now);
  PERFORM reports.log_export(
    v_table,
    v_count,
    v_filters,
    v_text,
    v_format,
    jsonb_build_object(
      'screen', 'pettycash',
      'from', p_from,
      'to', p_to,
      'holderId', p_holder_id,
      'view', v_view,
      'status', to_jsonb(v_statuses),
      'q', v_text,
      'rows', v_count,
      'format', v_format
    ),
    p_now
  );
  RETURN v_document;
END;
$$;
