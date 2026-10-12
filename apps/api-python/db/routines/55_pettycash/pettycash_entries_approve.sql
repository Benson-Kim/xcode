-- api.pettycash_entries_approve(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_entries jsonb, p_now timestamptz) RETURNS jsonb
-- Purpose: approve the ticked entries, p_entries = [{id, version}] (a repeated id counts once, the first kept; 1 to 100 of them): each in the order sent must be visible, is skipped when already approved, else must pass the reviewer rule and its version; only then are they approved, each waiting and not sent back, so one refusal approves none. One change-log and one audit row per approved entry; answers PettyCashDayApproved {approved, total (signed), skipped}.
-- Callers: PettyCashRoutines.approve_entries; ApprovePettyCashEntries (POST /setup/pettycash/approve).
-- Reads: pettycash.entries, tenancy.memberships, and what tenancy.business_date, tenancy.effective_permissions, tenancy.earliest_writable, setup.visible_vehicles, pettycash.visible_entry and pettycash.check_version read. Writes: pettycash.entries, and what pettycash.log writes (row locks on the holders' memberships, in id order, and the entries).
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 pettycash_approve_none, XC422 pettycash_approve_many, XC404 not_found via pettycash.visible_entry, XC409 pettycash_concurrent_save via pettycash.visible_entry, XC422 pettycash_cash_not_reviewed via pettycash.authorize_review, XC422 pettycash_credit_not_reviewed via pettycash.authorize_review, XC403 pettycash_own_float_review via pettycash.authorize_review, XC403 pettycash_own_entry_review via pettycash.authorize_review, XC403 pettycash_above_limit via pettycash.authorize_review, XC409 pettycash_entry_changed via pettycash.check_version, XC422 pettycash_not_waiting, XC422 pettycash_sent_back, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_pettycash_routines.py, tests/api/test_petty_cash.py.

CREATE OR REPLACE FUNCTION api.pettycash_entries_approve(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_entries jsonb,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_ids uuid[];
  v_versions bigint[];
  v_permissions text[];
  v_view_all boolean;
  v_vehicles uuid[];
  v_limit numeric;
  v_earliest date;
  v_holder uuid;
  v_entry pettycash.entries;
  v_chosen pettycash.entries[] := '{}';
  v_before json;
  v_total numeric := 0;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['pettycash.approve_item']);
  SELECT coalesce(array_agg(d.id ORDER BY d.position), '{}'),
         coalesce(array_agg(d.version ORDER BY d.position), '{}')
  INTO v_ids, v_versions
  FROM (
    SELECT DISTINCT ON (x.id) x.id, x.version, x.position
    FROM (
      SELECT (t.item ->> 'id')::uuid AS id, (t.item ->> 'version')::bigint AS version, t.position
      FROM jsonb_array_elements(coalesce(p_entries, '[]'::jsonb)) WITH ORDINALITY AS t (item, position)
    ) AS x
    ORDER BY x.id, x.position
  ) AS d;
  IF cardinality(v_ids) = 0 THEN
    PERFORM tenancy.refuse('pettycash_approve_none', 'XC422');
  END IF;
  IF cardinality(v_ids) > 100 THEN
    PERFORM tenancy.refuse('pettycash_approve_many', 'XC422');
  END IF;

  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  v_view_all := 'pettycash.view_all' = ANY (v_permissions);
  v_vehicles := ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id));
  SELECT m.approval_limit INTO v_limit
  FROM tenancy.memberships AS m
  WHERE m.organization_id = p_organization_id AND m.user_id = p_actor_id;
  v_earliest := tenancy.earliest_writable(
    p_organization_id, p_actor_id, tenancy.business_date(p_organization_id, p_now)
  );

  FOR v_holder IN
    SELECT DISTINCT e.holder_id
    FROM pettycash.entries AS e
    WHERE e.organization_id = p_organization_id AND e.id = ANY (v_ids)
    ORDER BY e.holder_id
  LOOP
    PERFORM pettycash.lock_float(v_holder);
  END LOOP;

  FOR i IN 1 .. cardinality(v_ids) LOOP
    v_entry := pettycash.visible_entry(v_ids[i], v_view_all, v_vehicles, true);
    CONTINUE WHEN v_entry.status = 2;
    PERFORM pettycash.authorize_review(v_entry, v_limit);
    PERFORM pettycash.check_version(v_entry, v_versions[i], v_permissions, v_limit, v_earliest);
    v_chosen := v_chosen || v_entry;
  END LOOP;

  FOREACH v_entry IN ARRAY v_chosen LOOP
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
    v_total := v_total + v_entry.total;
  END LOOP;

  RETURN jsonb_build_object(
    'approved', cardinality(v_chosen),
    'total', v_total,
    'skipped', cardinality(v_ids) - cardinality(v_chosen)
  );
END;
$$;
