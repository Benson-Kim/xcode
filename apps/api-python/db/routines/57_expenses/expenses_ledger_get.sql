-- api.expenses_ledger_get(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_from date, p_to date, p_source text, p_q text, p_page integer, p_page_size integer, p_now timestamptz) RETURNS jsonb
-- Purpose: one page of the central-expenses ledger over p_from..p_to (at most 367 days, nothing after the business date) on the vehicles the actor sees (ExpenseLedgerDto with snake_case keys): figures sum every row of the period by source whatever p_source and p_q say; total, amount and the page count the rows matching both; newest day first, then central, petty cash, scheduled, then registration and row id ordinally; the actor's record and correct rights and each central row's change and remove flags.
-- Callers: ExpensesRoutines.ledger; GetExpenseLedger (GET /setup/expenses/ledger).
-- Reads: setup.fleet_vehicles, tenancy.memberships, and what expenses.check_ledger, tenancy.effective_permissions, tenancy.business_date, tenancy.earliest_writable, setup.visible_vehicles, setup.fleet_postings and expenses.ledger_rows read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 page_out_of_range via tenancy.check_page, XC422 expense_period_required via expenses.check_ledger, XC422 expense_period_order via expenses.check_ledger, XC422 expense_period_length via expenses.check_ledger, XC422 expense_source_invalid via expenses.check_ledger, XC422 expense_search_length via expenses.check_ledger, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_expense_routines.py, tests/api/test_expenses.py.

CREATE OR REPLACE FUNCTION api.expenses_ledger_get(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_from date,
  p_to date,
  p_source text,
  p_q text,
  p_page integer,
  p_page_size integer,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_source text;
  v_kind smallint;
  v_text text := tenancy.trim_text(p_q);
  v_pattern text;
  v_permissions text[];
  v_capture boolean;
  v_correct boolean;
  v_today date;
  v_earliest date;
  v_result jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'expenses.view');
  PERFORM tenancy.check_page(p_page, p_page_size);
  v_source := expenses.check_ledger(p_from, p_to, p_source, p_q);
  v_kind := CASE v_source WHEN 'central' THEN 1 WHEN 'pettycash' THEN 2 WHEN 'scheduled' THEN 3 END;
  v_pattern := '%' || replace(replace(replace(v_text, '\', '\\'), '%', '\%'), '_', '\_') || '%';

  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  v_capture := 'expenses.capture' = ANY (v_permissions);
  v_correct := 'expenses.correct' = ANY (v_permissions);
  v_today := tenancy.business_date(p_organization_id, p_now);
  v_earliest := tenancy.earliest_writable(p_organization_id, p_actor_id, v_today);

  -- Figures, count and page come from the postings' keys (a uuid sorts as its text does); only the
  -- page's rows are built, by expenses.ledger_rows over the page's vehicles and days.
  WITH postings AS MATERIALIZED (
    SELECT p.source,
           p.day,
           p.vehicle_id,
           p.id,
           p.amount,
           f.registration,
           (v_kind IS NULL OR p.source = v_kind)
             AND (v_text IS NULL
                  OR f.registration ILIKE v_pattern
                  OR p.name ILIKE v_pattern
                  OR p.category_name ILIKE v_pattern
                  OR p.note ILIKE v_pattern
                  OR (p.source = 1 AND coalesce(btrim(r.first_name || ' ' || r.last_name), '') ILIKE v_pattern)
                  OR (p.source = 2 AND coalesce(btrim(h.first_name || ' ' || h.last_name), '') ILIKE v_pattern))
             AS matched
    FROM setup.fleet_postings(
           ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id)), p_from, p_to, v_today,
           '{1}'
         ) AS p
    JOIN setup.fleet_vehicles AS f ON f.organization_id = p_organization_id AND f.id = p.vehicle_id
    LEFT JOIN tenancy.memberships AS r ON r.organization_id = p_organization_id AND r.user_id = p.recorded_by
    LEFT JOIN tenancy.memberships AS h ON h.organization_id = p_organization_id AND h.user_id = p.holder_id
    WHERE p.kind = 1
  ),
  page AS MATERIALIZED (
    SELECT k.source, k.day, k.vehicle_id, k.id
    FROM postings AS k
    WHERE k.matched
    ORDER BY k.day DESC, k.source, k.registration COLLATE "C", k.id, k.vehicle_id
    OFFSET (p_page - 1) * p_page_size
    LIMIT p_page_size
  ),
  sums AS (
    SELECT coalesce(sum(k.amount), 0) AS total,
           coalesce(sum(k.amount) FILTER (WHERE k.source = 1), 0) AS central,
           coalesce(sum(k.amount) FILTER (WHERE k.source = 2), 0) AS petty_cash,
           coalesce(sum(k.amount) FILTER (WHERE k.source = 3), 0) AS scheduled,
           count(*) FILTER (WHERE k.matched) AS matched,
           coalesce(sum(k.amount) FILTER (WHERE k.matched), 0) AS amount
    FROM postings AS k
  )
  SELECT jsonb_build_object(
           'business_date', v_today,
           'from_date', p_from,
           'to_date', p_to,
           'permissions', jsonb_build_object('can_record', v_capture, 'can_correct', v_correct),
           'figures', jsonb_build_object(
                        'total', s.total,
                        'central', s.central,
                        'petty_cash', s.petty_cash,
                        'scheduled', s.scheduled
                      ),
           'items', (
             SELECT coalesce(jsonb_agg(
                      to_jsonb(r) - 'source_order' - 'matched'
                      ORDER BY r.entry_date DESC, r.source_order, r.registration COLLATE "C", r.id COLLATE "C"),
                      '[]'::jsonb)
             FROM expenses.ledger_rows(
                    ARRAY(SELECT DISTINCT g.vehicle_id FROM page AS g),
                    (SELECT min(g.day) FROM page AS g),
                    (SELECT max(g.day) FROM page AS g),
                    v_today,
                    v_source,
                    v_text,
                    p_actor_id,
                    v_capture,
                    v_correct,
                    v_earliest
                  ) AS r
             WHERE EXISTS (
               SELECT 1
               FROM page AS g
               WHERE g.source = r.source_order
                 AND g.day = r.entry_date
                 AND g.vehicle_id = r.vehicle_id
                 AND g.id::text = coalesce(r.schedule_id::text, r.id)
             )
           ),
           'page_number', p_page,
           'page_size', p_page_size,
           'total', s.matched,
           'amount', s.amount
         )
  INTO v_result
  FROM sums AS s;
  RETURN v_result;
END;
$$;
