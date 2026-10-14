-- expenses.entry_snapshot(p_id uuid) RETURNS json
-- Purpose: the change-log snapshot of a central expense, compact, with the .NET keys in their order: Id, Date, VehicleId, ExpenseItemId, Units, UnitAmount, Total, Note, GroupId, GroupSize, GroupTotal, GroupUnits, GroupUnitAmount, RecordedBy, RecordedAt, UpdatedBy, UpdatedAt, RemovedBy, RemovedAt, RemovalReason, Version; numbers with trailing zeros trimmed, instants in the +00:00 form; NULL for an unknown id.
-- Callers: expenses.log, api.expenses_entry_update, api.expenses_entry_remove.
-- Reads: expenses.entries, and what tenancy.fmt_instant reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_expense_routines.py.

CREATE OR REPLACE FUNCTION expenses.entry_snapshot(p_id uuid)
RETURNS json
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT tenancy.compact_json(json_build_object(
           'Id', e.id,
           'Date', e.entry_date,
           'VehicleId', e.vehicle_id,
           'ExpenseItemId', e.expense_item_id,
           'Units', trim_scale(e.units),
           'UnitAmount', trim_scale(e.unit_amount),
           'Total', trim_scale(e.total),
           'Note', e.note,
           'GroupId', e.group_id,
           'GroupSize', e.group_size,
           'GroupTotal', trim_scale(e.group_total),
           'GroupUnits', trim_scale(e.group_units),
           'GroupUnitAmount', trim_scale(e.group_unit_amount),
           'RecordedBy', e.recorded_by,
           'RecordedAt', tenancy.fmt_instant(e.recorded_at),
           'UpdatedBy', e.updated_by,
           'UpdatedAt', tenancy.fmt_instant(e.updated_at),
           'RemovedBy', e.removed_by,
           'RemovedAt', tenancy.fmt_instant(e.removed_at),
           'RemovalReason', e.removal_reason,
           'Version', e.version
         ))
  FROM expenses.entries AS e
  WHERE e.organization_id = tenancy.current_organization() AND e.id = p_id;
$$;

REVOKE ALL ON FUNCTION expenses.entry_snapshot(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION expenses.entry_snapshot(uuid) TO xcode_api_executor;
