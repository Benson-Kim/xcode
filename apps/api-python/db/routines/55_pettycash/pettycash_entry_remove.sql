-- api.pettycash_entry_remove(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_entry_id uuid, p_expected_version bigint, p_reason text, p_now timestamptz) RETURNS jsonb
-- Purpose: remove an entry the actor may see (the row stays, flagged): a waiting expense with pettycash.delete_own (own float) or pettycash.delete, the reason optional; an approved expense with pettycash.delete_approved, and cash or a credit note with pettycash.delete_cash, both with a reason (1 to 500 characters, trimmed); a rejected expense never; within the actor's back-dating limit; taking cash back below zero needs pettycash.issue_negative. Logs "Removed {subject}", with ". Reason: {reason}." when one was given; answers PettyCashSaved with the last status, the balance after and the outcome.
-- Callers: PettyCashRoutines.remove; RemovePettyCashEntry (POST /setup/pettycash/entries/{id}/remove).
-- Reads: tenancy.memberships, and what tenancy.business_date, tenancy.effective_permissions, tenancy.earliest_writable, tenancy.check_writable, setup.visible_vehicles, pettycash.visible_entry, pettycash.check_version, pettycash.guard_float and pettycash.saved read. Writes: pettycash.entries, and what pettycash.log writes (row locks on the holder's membership and the entry).
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 reason_length, XC404 not_found via pettycash.visible_entry, XC409 pettycash_concurrent_save via pettycash.visible_entry, XC403 pettycash_delete_cash_permission via pettycash.authorize_remove, XC422 pettycash_delete_rejected via pettycash.authorize_remove, XC403 pettycash_delete_approved_permission via pettycash.authorize_remove, XC403 pettycash_delete_own_permission via pettycash.authorize_remove, XC403 pettycash_delete_other_permission via pettycash.authorize_remove, XC422 record_too_old via tenancy.check_writable, XC409 pettycash_entry_changed via pettycash.check_version, XC422 pettycash_below_zero via pettycash.guard_float, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_pettycash_routines.py, tests/api/test_petty_cash.py.

CREATE OR REPLACE FUNCTION api.pettycash_entry_remove(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_entry_id uuid,
  p_expected_version bigint,
  p_reason text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_reason text := tenancy.trim_text(p_reason);
  v_permissions text[];
  v_limit numeric;
  v_entry pettycash.entries;
  v_before json;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY[
    'pettycash.delete_own', 'pettycash.delete', 'pettycash.delete_approved', 'pettycash.delete_cash'
  ]);
  IF char_length(v_reason) > 500 THEN
    PERFORM tenancy.refuse('reason_length', 'XC422');
  END IF;
  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  v_entry := pettycash.visible_entry(
    p_entry_id,
    'pettycash.view_all' = ANY (v_permissions),
    ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id)),
    true
  );
  PERFORM pettycash.authorize_remove(v_entry, v_permissions, v_reason);
  PERFORM tenancy.check_writable(v_entry.entry_date, p_now);
  SELECT m.approval_limit INTO v_limit
  FROM tenancy.memberships AS m
  WHERE m.organization_id = p_organization_id AND m.user_id = p_actor_id;
  PERFORM pettycash.check_version(
    v_entry, p_expected_version, v_permissions, v_limit,
    tenancy.earliest_writable(
      p_organization_id, p_actor_id, tenancy.business_date(p_organization_id, p_now)
    )
  );
  PERFORM pettycash.guard_float(
    v_entry.holder_id, v_entry.kind, -pettycash.effect(v_entry.kind, v_entry.status, v_entry.total)
  );

  v_before := pettycash.entry_snapshot(v_entry);
  UPDATE pettycash.entries
  SET removed_by = p_actor_id,
      removed_at = p_now,
      removal_reason = v_reason,
      updated_by = p_actor_id,
      updated_at = p_now,
      version = version + 1
  WHERE organization_id = p_organization_id AND id = v_entry.id;
  PERFORM pettycash.log(v_entry.id, v_before, 'Removed', v_reason, 'removed', p_now);
  RETURN pettycash.saved(v_entry.id, 'saved');
END;
$$;
