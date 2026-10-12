-- pettycash.entry_snapshot(p_entry pettycash.entries) RETURNS json
-- Purpose: the change-log snapshot of an entry, compact, with the .NET keys in their order and RejectReason and ReopenReason after SentBackNote; Kind and Status as names (Cash, Expense, Credit; Waiting, Approved, Rejected, or null), money with trailing zeros trimmed, instants in the +00:00 form.
-- Callers: pettycash.log, api.pettycash_entry_update, api.pettycash_entry_approve, api.pettycash_entries_approve, api.pettycash_entry_send_back, api.pettycash_entry_reject, api.pettycash_entry_reopen, api.pettycash_entry_remove, api.pettycash_day_approve.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_pettycash_helpers.py.

CREATE OR REPLACE FUNCTION pettycash.entry_snapshot(p_entry pettycash.entries)
RETURNS json
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT tenancy.compact_json(json_build_object(
           'Id', p_entry.id,
           'HolderId', p_entry.holder_id,
           'Kind', CASE p_entry.kind WHEN 1 THEN 'Cash' WHEN 2 THEN 'Expense' WHEN 3 THEN 'Credit' END,
           'Date', p_entry.entry_date,
           'VehicleId', p_entry.vehicle_id,
           'ExpenseItemId', p_entry.expense_item_id,
           'Units', trim_scale(p_entry.units),
           'UnitAmount', trim_scale(p_entry.unit_amount),
           'Total', trim_scale(p_entry.total),
           'Payee', p_entry.payee,
           'Note', p_entry.note,
           'Reimbursable', p_entry.reimbursable,
           'Status', CASE p_entry.status WHEN 1 THEN 'Waiting' WHEN 2 THEN 'Approved' WHEN 4 THEN 'Rejected' END,
           'SentBackNote', p_entry.sent_back_note,
           'RejectReason', p_entry.reject_reason,
           'ReopenReason', p_entry.reopen_reason,
           'ReviewedBy', p_entry.reviewed_by,
           'ReviewedAt', tenancy.fmt_instant(p_entry.reviewed_at),
           'RecordedBy', p_entry.recorded_by,
           'RecordedAt', tenancy.fmt_instant(p_entry.recorded_at),
           'UpdatedBy', p_entry.updated_by,
           'UpdatedAt', tenancy.fmt_instant(p_entry.updated_at),
           'RemovedBy', p_entry.removed_by,
           'RemovedAt', tenancy.fmt_instant(p_entry.removed_at),
           'RemovalReason', p_entry.removal_reason,
           'Version', p_entry.version
         ));
$$;

REVOKE ALL ON FUNCTION pettycash.entry_snapshot(pettycash.entries) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.entry_snapshot(pettycash.entries) TO xcode_api_executor;
