-- api.pettycash_entry_reopen(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_entry_id uuid, p_expected_version bigint, p_reason text, p_now timestamptz) RETURNS jsonb
-- Purpose: reopen an approved or rejected expense the actor may see, with a reason (1 to 200 characters, trimmed), within the actor's back-dating limit: it waits for approval again, its review, rejection and "sent back" cleared (an approved one leaves the vehicle report, a rejected one counts as spent again). Logs "Reopened {subject}. Reason: {reason}."; answers PettyCashSaved with the outcome.
-- Callers: PettyCashRoutines.reopen; ReopenPettyCashEntry (POST /setup/pettycash/entries/{id}/reopen).
-- Reads: tenancy.memberships, and what tenancy.business_date, tenancy.effective_permissions, tenancy.earliest_writable, tenancy.check_writable, setup.visible_vehicles, pettycash.visible_entry, pettycash.check_version and pettycash.saved read. Writes: pettycash.entries, and what pettycash.log writes (row locks on the holder's membership and the entry).
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC404 not_found via pettycash.visible_entry, XC409 pettycash_concurrent_save via pettycash.visible_entry, XC422 record_too_old via tenancy.check_writable, XC409 pettycash_entry_changed via pettycash.check_version, XC422 pettycash_not_decided, XC422 pettycash_reopen_reason_required, XC422 pettycash_decision_reason_length, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_pettycash_routines.py, tests/api/test_petty_cash.py.

CREATE OR REPLACE FUNCTION api.pettycash_entry_reopen(
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
  PERFORM tenancy.require_any_permission(ARRAY['pettycash.reopen']);
  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  v_entry := pettycash.visible_entry(
    p_entry_id,
    'pettycash.view_all' = ANY (v_permissions),
    ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id)),
    true
  );
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
  IF v_entry.status IS NULL OR v_entry.status NOT IN (2, 4) THEN
    PERFORM tenancy.refuse('pettycash_not_decided', 'XC422');
  END IF;
  IF v_reason IS NULL THEN
    PERFORM tenancy.refuse('pettycash_reopen_reason_required', 'XC422');
  END IF;
  IF char_length(v_reason) > 200 THEN
    PERFORM tenancy.refuse('pettycash_decision_reason_length', 'XC422');
  END IF;

  v_before := pettycash.entry_snapshot(v_entry);
  UPDATE pettycash.entries
  SET status = 1,
      reject_reason = NULL,
      sent_back_note = NULL,
      reviewed_by = NULL,
      reviewed_at = NULL,
      reopen_reason = v_reason,
      updated_by = p_actor_id,
      updated_at = p_now,
      version = version + 1
  WHERE organization_id = p_organization_id AND id = v_entry.id;
  PERFORM pettycash.log(v_entry.id, v_before, 'Reopened', v_reason, 'reopened', p_now);
  RETURN pettycash.saved(v_entry.id, 'saved');
END;
$$;
