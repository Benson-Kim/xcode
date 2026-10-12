-- api.pettycash_day_approve(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_date date, p_to date, p_holder_id uuid, p_now timestamptz) RETURNS jsonb
-- Purpose: approve a day (p_date) or the days p_date..p_to: the waiting expenses not sent back that the actor may see, of one float when p_holder_id is given, dated in the days; those the actor may review (not on their own float, not recorded by them, within their approval limit) are approved and the rest skipped, with no version check and no refusal for a skipped one. One change-log and one audit row per approved entry; answers PettyCashDayApproved {approved, total (signed), skipped}.
-- Callers: PettyCashRoutines.approve_day; ApprovePettyCashDay (POST /setup/pettycash/approve-day).
-- Reads: pettycash.entries, tenancy.memberships, and what tenancy.business_date, tenancy.effective_permissions, setup.visible_vehicles, pettycash.visible_holders and pettycash.entry_visible read. Writes: pettycash.entries, and what pettycash.log writes (row locks on the holders' memberships, in id order, and the entries).
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 time_zone_invalid via tenancy.business_date, XC422 pettycash_future_date via pettycash.check_date, XC422 pettycash_too_old via pettycash.check_date, XC422 pettycash_range_both via pettycash.check_period, XC422 history_dates_order via pettycash.check_period, XC422 pettycash_range_length via pettycash.check_period, XC422 pettycash_range_start via pettycash.check_period, XC404 not_found.
-- Tests: tests/db/test_pettycash_routines.py, tests/api/test_petty_cash.py.
-- A missing date reads as 0001-01-01, as the released clients' binder read it, and is refused
-- as too old.

CREATE OR REPLACE FUNCTION api.pettycash_day_approve(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_date date,
  p_to date,
  p_holder_id uuid,
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
  v_view_all boolean;
  v_vehicles uuid[];
  v_limit numeric;
  v_today date;
  v_from date := coalesce(p_date, date '0001-01-01');
  v_to date;
  v_holder uuid;
  v_entry pettycash.entries;
  v_before json;
  v_waiting integer := 0;
  v_approved integer := 0;
  v_total numeric := 0;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['pettycash.approve_day']);
  v_today := tenancy.business_date(p_organization_id, p_now);
  IF p_to IS NULL THEN
    PERFORM pettycash.check_date(v_from, v_today);
    v_to := v_from;
  ELSE
    PERFORM pettycash.check_period(p_date, p_to, v_today);
    v_to := p_to;
  END IF;
  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  v_view_all := 'pettycash.view_all' = ANY (v_permissions);
  IF p_holder_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM pettycash.visible_holders(v_view_all) AS h WHERE h.user_id = p_holder_id
  ) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;
  v_vehicles := ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id));
  SELECT m.approval_limit INTO v_limit
  FROM tenancy.memberships AS m
  WHERE m.organization_id = p_organization_id AND m.user_id = p_actor_id;

  FOR v_holder IN
    SELECT DISTINCT e.holder_id
    FROM pettycash.entries AS e
    WHERE e.organization_id = p_organization_id
      AND e.kind = 2
      AND e.status = 1
      AND e.entry_date BETWEEN v_from AND v_to
      AND (p_holder_id IS NULL OR e.holder_id = p_holder_id)
      AND pettycash.entry_visible(e, v_view_all, v_vehicles)
    ORDER BY e.holder_id
  LOOP
    PERFORM pettycash.lock_float(v_holder);
  END LOOP;

  FOR v_entry IN
    SELECT e.*
    FROM pettycash.entries AS e
    WHERE e.organization_id = p_organization_id
      AND e.kind = 2
      AND e.status = 1
      AND e.sent_back_note IS NULL
      AND e.entry_date BETWEEN v_from AND v_to
      AND (p_holder_id IS NULL OR e.holder_id = p_holder_id)
      AND pettycash.entry_visible(e, v_view_all, v_vehicles)
    ORDER BY e.id
    FOR UPDATE
  LOOP
    v_waiting := v_waiting + 1;
    CONTINUE WHEN v_entry.holder_id = p_actor_id
      OR v_entry.recorded_by = p_actor_id
      OR (v_limit IS NOT NULL AND abs(v_entry.total) > v_limit);
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
    v_approved := v_approved + 1;
    v_total := v_total + v_entry.total;
  END LOOP;

  RETURN jsonb_build_object('approved', v_approved, 'total', v_total, 'skipped', v_waiting - v_approved);
END;
$$;
