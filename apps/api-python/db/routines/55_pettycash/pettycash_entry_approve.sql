-- api.pettycash_entry_approve(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_entry_id uuid, p_expected_version bigint, p_now timestamptz) RETURNS jsonb
-- Purpose: approve a waiting expense the actor may see and may review (not on their own float, not one they recorded, within their approval limit) and that is not sent back; one the actor already approved answers replayed before the checks. Logs "Approved {subject}"; answers PettyCashSaved with the outcome.
-- Callers: PettyCashRoutines.approve; ApprovePettyCashEntry (POST /setup/pettycash/entries/{id}/approve).
-- Reads: tenancy.memberships, and what tenancy.business_date, tenancy.effective_permissions, tenancy.earliest_writable, setup.visible_vehicles, pettycash.visible_entry, pettycash.check_version and pettycash.saved read. Writes: pettycash.entries, and what pettycash.log writes (row locks on the holder's membership and the entry).
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC404 not_found via pettycash.visible_entry, XC409 pettycash_concurrent_save via pettycash.visible_entry, XC422 pettycash_cash_not_reviewed via pettycash.authorize_review, XC422 pettycash_credit_not_reviewed via pettycash.authorize_review, XC403 pettycash_own_float_review via pettycash.authorize_review, XC403 pettycash_own_entry_review via pettycash.authorize_review, XC403 pettycash_above_limit via pettycash.authorize_review, XC409 pettycash_entry_changed via pettycash.check_version, XC422 pettycash_not_waiting, XC422 pettycash_sent_back, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_pettycash_routines.py, tests/api/test_petty_cash.py.

CREATE OR REPLACE FUNCTION api.pettycash_entry_approve(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_entry_id uuid,
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
  v_permissions text[];
  v_limit numeric;
  v_entry pettycash.entries;
  v_before json;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['pettycash.approve_item']);
  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  v_entry := pettycash.visible_entry(
    p_entry_id,
    'pettycash.view_all' = ANY (v_permissions),
    ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id)),
    true
  );
  IF v_entry.status = 2 AND v_entry.reviewed_by = p_actor_id THEN
    RETURN pettycash.saved(v_entry.id, 'replayed');
  END IF;

  SELECT m.approval_limit INTO v_limit
  FROM tenancy.memberships AS m
  WHERE m.organization_id = p_organization_id AND m.user_id = p_actor_id;
  PERFORM pettycash.authorize_review(v_entry, v_limit);
  PERFORM pettycash.check_version(
    v_entry, p_expected_version, v_permissions, v_limit,
    tenancy.earliest_writable(
      p_organization_id, p_actor_id, tenancy.business_date(p_organization_id, p_now)
    )
  );
  IF v_entry.status <> 1 THEN
    PERFORM tenancy.refuse('pettycash_not_waiting', 'XC422');
  END IF;
  IF v_entry.sent_back_note IS NOT NULL THEN
    PERFORM tenancy.refuse('pettycash_sent_back', 'XC422');
  END IF;

  v_before := pettycash.entry_snapshot(v_entry);
  UPDATE pettycash.entries
  SET status = 2,
      reviewed_by = p_actor_id,
      reviewed_at = p_now,
      updated_by = p_actor_id,
      updated_at = p_now,
      version = version + 1
  WHERE organization_id = p_organization_id AND id = v_entry.id;
  PERFORM pettycash.log(v_entry.id, v_before, 'Approved', NULL, 'approved', p_now);
  RETURN pettycash.saved(v_entry.id, 'saved');
END;
$$;
