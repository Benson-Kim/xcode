-- pettycash.entry_document(p_entry pettycash.entries, p_permissions text[], p_limit numeric, p_earliest date) RETURNS jsonb
-- Purpose: one entry as the list and the 409 current member serve it (PettyCashEntryDto with snake_case keys): kind and status words, the holder's, reviewer's and recorder's names ("" for a missing holder or recorder, NULL for a missing reviewer), registration, item name and its category's bucket (expenses only), and the actor's flags of pettycash.flags.
-- Callers: pettycash.check_version, api.pettycash_entry_list, api.pettycash_entries_approve.
-- Reads: setup.fleet_vehicles, setup.expense_items, setup.expense_categories, pettycash.kinds, and what pettycash.member_name reads. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_pettycash_helpers.py, tests/db/test_pettycash_routines.py.

CREATE OR REPLACE FUNCTION pettycash.entry_document(
  p_entry pettycash.entries,
  p_permissions text[],
  p_limit numeric,
  p_earliest date
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_registration text;
  v_item text;
  v_bucket smallint;
  v_flags jsonb := pettycash.flags(p_entry, p_permissions, p_limit, p_earliest);
BEGIN
  IF p_entry.vehicle_id IS NOT NULL THEN
    SELECT f.registration INTO v_registration
    FROM setup.fleet_vehicles AS f
    WHERE f.organization_id = p_entry.organization_id AND f.id = p_entry.vehicle_id;
  END IF;
  IF p_entry.expense_item_id IS NOT NULL THEN
    SELECT i.name, c.bucket INTO v_item, v_bucket
    FROM setup.expense_items AS i
    JOIN setup.expense_categories AS c
      ON c.organization_id = i.organization_id AND c.id = i.category_id
    WHERE i.organization_id = p_entry.organization_id AND i.id = p_entry.expense_item_id;
  END IF;
  RETURN jsonb_build_object(
    'id', p_entry.id,
    'kind', (SELECT k.name FROM pettycash.kinds AS k WHERE k.code = p_entry.kind),
    'holder_id', p_entry.holder_id,
    'holder_name', coalesce(pettycash.member_name(p_entry.holder_id), ''),
    'entry_date', p_entry.entry_date,
    'vehicle_id', p_entry.vehicle_id,
    'registration', v_registration,
    'expense_item_id', p_entry.expense_item_id,
    'expense_item_name', v_item,
    'bucket', v_bucket,
    'units', p_entry.units,
    'unit_amount', p_entry.unit_amount,
    'total', p_entry.total,
    'payee', p_entry.payee,
    'note', p_entry.note,
    'reimbursable', p_entry.reimbursable,
    'status', pettycash.status_word(p_entry.status, p_entry.sent_back_note),
    'sent_back_note', p_entry.sent_back_note,
    'reviewed_by_name', pettycash.member_name(p_entry.reviewed_by),
    'reviewed_at', p_entry.reviewed_at,
    'recorded_by_name', coalesce(pettycash.member_name(p_entry.recorded_by), ''),
    'recorded_at', p_entry.recorded_at,
    'updated_at', p_entry.updated_at,
    'version', p_entry.version,
    'can_edit', v_flags -> 'can_edit',
    'can_remove', v_flags -> 'can_remove',
    'can_review', v_flags -> 'can_review',
    'above_limit', v_flags -> 'above_limit',
    'reject_reason', p_entry.reject_reason,
    'reopen_reason', p_entry.reopen_reason,
    'can_send_back', v_flags -> 'can_send_back',
    'can_reject', v_flags -> 'can_reject',
    'can_reopen', v_flags -> 'can_reopen'
  );
END;
$$;

REVOKE ALL ON FUNCTION pettycash.entry_document(pettycash.entries, text[], numeric, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.entry_document(pettycash.entries, text[], numeric, date) TO xcode_api_executor;
