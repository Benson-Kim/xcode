-- api.pettycash_overview_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_date date, p_period text, p_holder_id uuid, p_from date, p_to date, p_now timestamptz) RETURNS jsonb
-- Purpose: the petty-cash screen (PettyCashOverviewDto): the business date; the window (p_from..p_to, else the day or the organization week holding p_date, default the business date); the actor's petty-cash rights and earliest writable date; the floats the actor may see; the window's figures and the to-date row of each chosen float (p_holder_id, else every visible float), both over the entries the actor may see.
-- Callers: PettyCashRoutines.overview; GetPettyCashOverview (GET /setup/pettycash/overview).
-- Reads: tenancy.memberships, and what tenancy.business_date, tenancy.effective_permissions, tenancy.earliest_writable, setup.visible_vehicles, revenue.week_start, pettycash.visible_holders and pettycash.tallies read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 time_zone_invalid via tenancy.business_date, XC422 pettycash_range_both via pettycash.check_period, XC422 history_dates_order via pettycash.check_period, XC422 pettycash_range_length via pettycash.check_period, XC422 pettycash_range_start via pettycash.check_period, XC422 pettycash_too_old via pettycash.check_period, XC422 pettycash_future_date via pettycash.check_date, XC422 pettycash_period_invalid, XC404 not_found.
-- Tests: tests/db/test_pettycash_routines.py, tests/api/test_petty_cash.py.

CREATE OR REPLACE FUNCTION api.pettycash_overview_get(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_date date,
  p_period text,
  p_holder_id uuid,
  p_from date,
  p_to date,
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
  v_date date;
  v_period text;
  v_from date;
  v_to date;
  v_holders jsonb;
  v_chosen uuid[];
  v_figures jsonb;
  v_floats jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['pettycash.view']);
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  v_view_all := 'pettycash.view_all' = ANY (v_permissions);

  IF p_from IS NOT NULL OR p_to IS NOT NULL THEN
    PERFORM pettycash.check_period(p_from, p_to, v_today);
    v_from := p_from;
    v_to := p_to;
    v_date := p_to;
    v_period := CASE WHEN p_from = p_to THEN 'day' ELSE 'range' END;
  ELSE
    v_date := coalesce(p_date, v_today);
    PERFORM pettycash.check_date(v_date, v_today);
    v_period := coalesce(tenancy.trim_text(p_period), 'day');
    IF v_period = 'day' THEN
      v_from := v_date;
      v_to := v_date;
    ELSIF v_period = 'week' THEN
      v_from := revenue.week_start(v_date);
      v_to := v_from + 6;
    ELSE
      PERFORM tenancy.refuse('pettycash_period_invalid', 'XC422');
    END IF;
  END IF;

  SELECT coalesce(jsonb_agg(jsonb_build_object('id', h.user_id, 'name', h.name, 'active', h.active)
                            ORDER BY h.position), '[]'::jsonb),
         coalesce(array_agg(h.user_id ORDER BY h.position) FILTER (
           WHERE p_holder_id IS NULL OR h.user_id = p_holder_id), '{}')
  INTO v_holders, v_chosen
  FROM pettycash.visible_holders(v_view_all) WITH ORDINALITY AS h (user_id, name, active, position);
  IF p_holder_id IS NOT NULL AND cardinality(v_chosen) = 0 THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;

  SELECT m.approval_limit INTO v_limit
  FROM tenancy.memberships AS m
  WHERE m.organization_id = p_organization_id AND m.user_id = p_actor_id;
  v_vehicles := ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id));

  WITH t AS MATERIALIZED (
    SELECT * FROM pettycash.tallies(v_chosen, v_from, v_to, v_view_all, v_vehicles)
  ),
  figures AS (
    SELECT coalesce(sum(pettycash.effect(t.kind, t.status, t.total)) FILTER (WHERE t.window_position = 0), 0) AS opening,
           coalesce(sum(t.total) FILTER (WHERE t.window_position = 1 AND t.kind = 1), 0) AS cash,
           coalesce(sum(t.total) FILTER (WHERE t.window_position = 1 AND t.kind = 2 AND t.status <> 4), 0) AS expenses,
           coalesce(sum(t.total) FILTER (WHERE t.window_position = 1 AND t.kind = 3), 0) AS credit,
           coalesce(sum(t.total) FILTER (
             WHERE t.window_position = 1 AND t.kind = 2 AND t.status = 1 AND NOT t.sent_back), 0) AS waiting,
           coalesce(sum(t.entries) FILTER (
             WHERE t.window_position = 1 AND t.kind = 2 AND t.status = 1 AND NOT t.sent_back), 0) AS waiting_count
    FROM t
  ),
  floats AS (
    SELECT t.holder_id,
           coalesce(sum(t.total) FILTER (WHERE t.kind = 1), 0) AS cash,
           coalesce(sum(t.total) FILTER (WHERE t.kind = 3), 0) AS credit,
           coalesce(sum(t.total) FILTER (WHERE t.kind = 2 AND t.status <> 4), 0) AS expenses,
           coalesce(sum(t.total) FILTER (WHERE t.kind = 2 AND t.status = 1 AND NOT t.sent_back), 0) AS waiting,
           coalesce(sum(t.entries) FILTER (WHERE t.kind = 2 AND t.status = 1 AND NOT t.sent_back), 0) AS waiting_count,
           coalesce(sum(t.total) FILTER (WHERE t.kind = 2 AND t.status = 2), 0) AS approved,
           coalesce(sum(t.total) FILTER (WHERE t.kind = 2 AND t.status = 1 AND t.sent_back), 0) AS sent_back,
           coalesce(sum(t.total) FILTER (WHERE t.kind = 2 AND t.status = 4), 0) AS rejected,
           max(t.latest) FILTER (WHERE t.kind = 1) AS last_cash_on
    FROM t
    GROUP BY t.holder_id
  )
  SELECT (
           SELECT jsonb_build_object(
                    'opening_balance', f.opening,
                    'cash_received', f.cash,
                    'expenses', f.expenses,
                    'credit_notes', f.credit,
                    'money_out', f.expenses + f.credit,
                    'closing_balance', f.opening + f.cash - f.expenses - f.credit,
                    'waiting', f.waiting,
                    'waiting_count', f.waiting_count
                  )
           FROM figures AS f
         ),
         (
           SELECT coalesce(jsonb_agg(
                    jsonb_build_object(
                      'holder_id', h.user_id,
                      'name', h.name,
                      'active', h.active,
                      'cash_received', coalesce(r.cash, 0),
                      'credit_notes', coalesce(r.credit, 0),
                      'expenses', coalesce(r.expenses, 0),
                      'waiting', coalesce(r.waiting, 0),
                      'waiting_count', coalesce(r.waiting_count, 0),
                      'approved', coalesce(r.approved, 0),
                      'sent_back', coalesce(r.sent_back, 0),
                      'balance', coalesce(r.cash - r.credit - r.expenses, 0),
                      'last_cash_on', r.last_cash_on,
                      'rejected', coalesce(r.rejected, 0)
                    ) ORDER BY h.position), '[]'::jsonb)
           FROM pettycash.visible_holders(v_view_all) WITH ORDINALITY AS h (user_id, name, active, position)
           LEFT JOIN floats AS r ON r.holder_id = h.user_id
           WHERE h.user_id = ANY (v_chosen)
         )
  INTO v_figures, v_floats;

  RETURN jsonb_build_object(
    'business_date', v_today,
    'day', v_date,
    'period', v_period,
    'from_date', v_from,
    'to_date', v_to,
    'permissions', jsonb_build_object(
      'holder_id', CASE WHEN 'pettycash.spend' = ANY (v_permissions) THEN p_actor_id END,
      'can_spend', 'pettycash.spend' = ANY (v_permissions),
      'can_view_all', v_view_all,
      'can_issue', 'pettycash.issue' = ANY (v_permissions),
      'can_issue_negative', 'pettycash.issue_negative' = ANY (v_permissions),
      'can_approve_item', 'pettycash.approve_item' = ANY (v_permissions),
      'can_approve_day', 'pettycash.approve_day' = ANY (v_permissions),
      'approval_limit', v_limit,
      'can_view', 'pettycash.view' = ANY (v_permissions),
      'can_spend_other', 'pettycash.spend_other' = ANY (v_permissions),
      'can_edit_own', 'pettycash.edit_own' = ANY (v_permissions),
      'can_edit', 'pettycash.edit' = ANY (v_permissions),
      'can_delete_own', 'pettycash.delete_own' = ANY (v_permissions),
      'can_delete', 'pettycash.delete' = ANY (v_permissions),
      'can_delete_approved', 'pettycash.delete_approved' = ANY (v_permissions),
      'can_send_back', 'pettycash.send_back' = ANY (v_permissions),
      'can_reject', 'pettycash.reject' = ANY (v_permissions),
      'can_reopen', 'pettycash.reopen' = ANY (v_permissions),
      'can_credit', 'pettycash.credit' = ANY (v_permissions),
      'can_delete_cash', 'pettycash.delete_cash' = ANY (v_permissions),
      'earliest_date', tenancy.earliest_writable(p_organization_id, p_actor_id, v_today)
    ),
    'holders', v_holders,
    'figures', v_figures,
    'floats', v_floats
  );
END;
$$;
