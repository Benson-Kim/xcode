-- api.pettycash_dashboard_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_now timestamptz) RETURNS jsonb
-- Purpose: the petty-cash dashboard cards (PettyCashDashboardDto): the float card for a person who keeps a float (pettycash.spend): their balance, their waiting expenses (count and total, sent back not included), how many are sent back, and the approved expenses dated from the first of the business month to the business date; the approvals card for a person who approves (pettycash.approve_item): the waiting expenses not sent back that they may see, counted, summed, with their approval limit, how many are above it and one row per float (oldest first, then name); each card null otherwise.
-- Callers: PettyCashRoutines.dashboard; GetPettyCashDashboard (GET /setup/pettycash/dashboard).
-- Reads: pettycash.entries, tenancy.memberships, and what tenancy.business_date, tenancy.effective_permissions, setup.visible_vehicles, pettycash.balance, pettycash.entry_visible and pettycash.member_name read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_pettycash_routines.py, tests/api/test_petty_cash.py.

CREATE OR REPLACE FUNCTION api.pettycash_dashboard_get(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_permissions text[];
  v_view_all boolean;
  v_vehicles uuid[];
  v_limit numeric;
  v_today date;
  v_float jsonb;
  v_approvals jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['dash.pettycash']);
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);

  IF 'pettycash.spend' = ANY (v_permissions) THEN
    SELECT jsonb_build_object(
             'balance', pettycash.balance(p_actor_id),
             'waiting_count', count(*) FILTER (WHERE e.status = 1 AND e.sent_back_note IS NULL),
             'waiting_total', coalesce(sum(e.total) FILTER (WHERE e.status = 1 AND e.sent_back_note IS NULL), 0),
             'sent_back_count', count(*) FILTER (WHERE e.status = 1 AND e.sent_back_note IS NOT NULL),
             'approved_this_month', coalesce(sum(e.total) FILTER (
               WHERE e.status = 2
                 AND e.entry_date >= date_trunc('month', v_today)::date
                 AND e.entry_date <= v_today), 0)
           )
    INTO v_float
    FROM pettycash.entries AS e
    WHERE e.organization_id = p_organization_id
      AND e.holder_id = p_actor_id
      AND e.kind = 2
      AND e.removed_at IS NULL;
  END IF;

  IF 'pettycash.approve_item' = ANY (v_permissions) THEN
    v_view_all := 'pettycash.view_all' = ANY (v_permissions);
    v_vehicles := ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id));
    SELECT m.approval_limit INTO v_limit
    FROM tenancy.memberships AS m
    WHERE m.organization_id = p_organization_id AND m.user_id = p_actor_id;

    WITH waiting AS MATERIALIZED (
      SELECT e.holder_id, e.total, e.entry_date
      FROM pettycash.entries AS e
      WHERE e.organization_id = p_organization_id
        AND e.kind = 2
        AND e.status = 1
        AND e.sent_back_note IS NULL
        AND pettycash.entry_visible(e, v_view_all, v_vehicles)
    ),
    per_holder AS (
      SELECT w.holder_id,
             coalesce(pettycash.member_name(w.holder_id), '') AS name,
             count(*)::integer AS entries,
             sum(w.total) AS total,
             min(w.entry_date) AS oldest
      FROM waiting AS w
      GROUP BY w.holder_id
    )
    SELECT jsonb_build_object(
             'count', (SELECT count(*) FROM waiting),
             'total', (SELECT coalesce(sum(w.total), 0) FROM waiting AS w),
             'approval_limit', v_limit,
             'above_limit', (
               SELECT count(*) FROM waiting AS w WHERE v_limit IS NOT NULL AND abs(w.total) > v_limit
             ),
             'holders', (
               SELECT coalesce(jsonb_agg(
                        jsonb_build_object(
                          'holder_id', p.holder_id,
                          'name', p.name,
                          'count', p.entries,
                          'total', p.total,
                          'oldest', p.oldest
                        ) ORDER BY p.oldest, p.name COLLATE "C", p.holder_id), '[]'::jsonb)
               FROM per_holder AS p
             )
           )
    INTO v_approvals;
  END IF;

  RETURN jsonb_build_object('float_card', v_float, 'approvals', v_approvals);
END;
$$;
