-- api.pettycash_entry_update(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_entry_id uuid, p_kind text, p_date date, p_unit_amount numeric, p_holder_id uuid, p_vehicle_id uuid, p_expense_item_id uuid, p_units numeric, p_payee text, p_note text, p_reimbursable boolean, p_expected_version bigint, p_now timestamptz) RETURNS jsonb
-- Purpose: change a waiting expense (sent back included) the actor may see: same kind and float; an unchanged line of an entry not sent back answers replayed before the permission and version checks; else the change rights, the date, the back-dating limit on the stored and the new date, the version, and the vehicle and item checks for what changed (a new date counting as both); the expense waits for approval again, "sent back" and the review cleared. Logs "Changed {subject}" (read after); answers PettyCashSaved with the outcome.
-- Callers: PettyCashRoutines.update; UpdatePettyCashEntry (PUT /setup/pettycash/entries/{id}).
-- Reads: pettycash.entries, tenancy.memberships, and what tenancy.business_date, tenancy.effective_permissions, tenancy.earliest_writable, tenancy.check_writable, setup.visible_vehicles, pettycash.check_line, pettycash.visible_entry, pettycash.check_version, pettycash.check_expense and pettycash.saved read. Writes: pettycash.entries, and what pettycash.log writes (row locks on the holder's membership and the entry).
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 pettycash_kind_invalid via pettycash.check_line, XC404 not_found via pettycash.visible_entry, XC409 pettycash_concurrent_save via pettycash.visible_entry, XC422 pettycash_kind_change, XC422 pettycash_holder_change, XC422 pettycash_change_cash, XC422 pettycash_change_decided via pettycash.authorize_change, XC403 pettycash_change_own_permission via pettycash.authorize_change, XC403 pettycash_change_other_permission via pettycash.authorize_change, XC422 pettycash_future_date via pettycash.check_date, XC422 pettycash_too_old via pettycash.check_date, XC422 record_too_old via tenancy.check_writable, XC409 pettycash_entry_changed via pettycash.check_version, XC422 pettycash_vehicle_scope via pettycash.check_expense, XC422 pettycash_vehicle_inactive via pettycash.check_expense, XC422 pettycash_item_inactive via pettycash.check_expense, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_pettycash_routines.py, tests/api/test_petty_cash.py.

CREATE OR REPLACE FUNCTION api.pettycash_entry_update(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_entry_id uuid,
  p_kind text,
  p_date date,
  p_unit_amount numeric,
  p_holder_id uuid,
  p_vehicle_id uuid,
  p_expense_item_id uuid,
  p_units numeric,
  p_payee text,
  p_note text,
  p_reimbursable boolean,
  p_expected_version bigint,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  c_none CONSTANT uuid := '00000000-0000-0000-0000-000000000000';
  v_kind smallint := pettycash.kind_code(p_kind);
  v_vehicle uuid := nullif(p_vehicle_id, c_none);
  v_item uuid := nullif(p_expense_item_id, c_none);
  v_units numeric := coalesce(p_units, 1);
  v_payee text := tenancy.trim_text(p_payee);
  v_note text := tenancy.trim_text(p_note);
  v_reimbursable boolean := coalesce(p_reimbursable, false);
  v_permissions text[];
  v_view_all boolean;
  v_vehicles uuid[];
  v_limit numeric;
  v_today date;
  v_entry pettycash.entries;
  v_before json;
  v_date_changed boolean;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['pettycash.edit_own', 'pettycash.edit']);
  PERFORM pettycash.check_line(
    v_kind, p_date, p_unit_amount, v_units, v_vehicle, v_item, v_payee, v_note, v_reimbursable
  );

  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  v_view_all := 'pettycash.view_all' = ANY (v_permissions);
  v_vehicles := ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id));
  v_entry := pettycash.visible_entry(p_entry_id, v_view_all, v_vehicles, true);

  IF v_entry.kind <> v_kind THEN
    PERFORM tenancy.refuse('pettycash_kind_change', 'XC422');
  END IF;
  IF p_holder_id IS NOT NULL AND p_holder_id <> v_entry.holder_id THEN
    PERFORM tenancy.refuse('pettycash_holder_change', 'XC422');
  END IF;
  IF v_entry.kind <> 2 THEN
    PERFORM tenancy.refuse('pettycash_change_cash', 'XC422');
  END IF;
  IF v_entry.sent_back_note IS NULL
     AND v_entry.entry_date = p_date
     AND v_entry.vehicle_id IS NOT DISTINCT FROM v_vehicle
     AND v_entry.expense_item_id IS NOT DISTINCT FROM v_item
     AND v_entry.units = v_units
     AND v_entry.unit_amount = p_unit_amount
     AND v_entry.reimbursable = v_reimbursable
     AND v_entry.payee IS NOT DISTINCT FROM v_payee
     AND v_entry.note IS NOT DISTINCT FROM v_note THEN
    RETURN pettycash.saved(v_entry.id, 'replayed');
  END IF;

  PERFORM pettycash.authorize_change(v_entry, v_permissions);
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_date_changed := p_date <> v_entry.entry_date;
  IF v_date_changed THEN
    PERFORM pettycash.check_date(p_date, v_today);
  END IF;
  PERFORM tenancy.check_writable(v_entry.entry_date, p_now);
  PERFORM tenancy.check_writable(p_date, p_now);
  SELECT m.approval_limit INTO v_limit
  FROM tenancy.memberships AS m
  WHERE m.organization_id = p_organization_id AND m.user_id = p_actor_id;
  PERFORM pettycash.check_version(
    v_entry, p_expected_version, v_permissions, v_limit,
    tenancy.earliest_writable(p_organization_id, p_actor_id, v_today)
  );
  PERFORM pettycash.check_expense(
    v_vehicle,
    v_item,
    p_date,
    v_date_changed OR v_vehicle IS DISTINCT FROM v_entry.vehicle_id,
    v_date_changed OR v_item IS DISTINCT FROM v_entry.expense_item_id
  );

  v_before := pettycash.entry_snapshot(v_entry);
  UPDATE pettycash.entries
  SET entry_date = p_date,
      vehicle_id = v_vehicle,
      expense_item_id = v_item,
      units = v_units,
      unit_amount = p_unit_amount,
      payee = v_payee,
      note = v_note,
      reimbursable = v_reimbursable,
      status = 1,
      sent_back_note = NULL,
      reviewed_by = NULL,
      reviewed_at = NULL,
      updated_by = p_actor_id,
      updated_at = p_now,
      version = version + 1
  WHERE organization_id = p_organization_id AND id = v_entry.id;

  PERFORM pettycash.log(v_entry.id, v_before, 'Changed', NULL, 'changed', p_now);
  RETURN pettycash.saved(v_entry.id, 'saved');
END;
$$;
