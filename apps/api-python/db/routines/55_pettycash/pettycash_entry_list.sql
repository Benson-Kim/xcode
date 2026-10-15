-- api.pettycash_entry_list(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_from date, p_to date, p_holder_id uuid, p_kinds text[], p_statuses text[], p_q text, p_page integer, p_page_size integer, p_now timestamptz) RETURNS jsonb
-- Purpose: one page of the entries the actor may see (PettyCashEntryDto with the actor's flags), of one float when p_holder_id is given, dated p_from..p_to (either end open), of the kinds and status words asked (empty or null = all; cash and credit notes have no status), whose note, payee, holder name, registration or item name holds p_q (literally, ignoring case); by date, kind, id; {total, items}.
-- Callers: PettyCashRoutines.list_entries; ListPettyCashEntries (GET /setup/pettycash/entries).
-- Reads: tenancy.memberships, and what tenancy.business_date, tenancy.effective_permissions, tenancy.earliest_writable, setup.visible_vehicles, pettycash.visible_holders, pettycash.entry_matches and pettycash.entry_document read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 page_out_of_range via tenancy.check_page, XC422 history_dates_order, XC422 history_text_length, XC422 pettycash_kind_invalid, XC422 pettycash_status_invalid, XC404 not_found, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_pettycash_routines.py, tests/api/test_petty_cash.py.

CREATE OR REPLACE FUNCTION api.pettycash_entry_list(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_from date,
  p_to date,
  p_holder_id uuid,
  p_kinds text[],
  p_statuses text[],
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
  v_text text := tenancy.trim_text(p_q);
  v_kinds smallint[];
  v_permissions text[];
  v_view_all boolean;
  v_vehicles uuid[];
  v_limit numeric;
  v_today date;
  v_earliest date;
  v_total integer;
  v_items jsonb;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY['pettycash.view']);
  PERFORM tenancy.check_page(p_page, p_page_size);
  IF p_from > p_to THEN
    PERFORM tenancy.refuse('history_dates_order', 'XC422');
  END IF;
  IF char_length(v_text) > 200 THEN
    PERFORM tenancy.refuse('history_text_length', 'XC422');
  END IF;
  v_kinds := ARRAY(SELECT pettycash.kind_code(k) FROM unnest(p_kinds) AS k);
  IF array_position(v_kinds, NULL) IS NOT NULL THEN
    PERFORM tenancy.refuse('pettycash_kind_invalid', 'XC422');
  END IF;
  IF EXISTS (
    SELECT 1 FROM unnest(p_statuses) AS s
    WHERE s IS NULL OR s NOT IN ('waiting', 'approved', 'sentBack', 'rejected')
  ) THEN
    PERFORM tenancy.refuse('pettycash_status_invalid', 'XC422');
  END IF;

  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  v_view_all := 'pettycash.view_all' = ANY (v_permissions);
  IF p_holder_id IS NOT NULL AND NOT EXISTS (
    SELECT 1 FROM pettycash.visible_holders(v_view_all) AS h WHERE h.user_id = p_holder_id
  ) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;

  v_today := tenancy.business_date(p_organization_id, p_now);
  v_earliest := tenancy.earliest_writable(p_organization_id, p_actor_id, v_today);
  SELECT m.approval_limit INTO v_limit
  FROM tenancy.memberships AS m
  WHERE m.organization_id = p_organization_id AND m.user_id = p_actor_id;
  v_vehicles := ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id));

  WITH matches AS MATERIALIZED (
    SELECT m AS e
    FROM pettycash.entry_matches(
           p_holder_id, p_from, p_to, v_kinds, p_statuses, v_text, v_view_all, v_vehicles
         ) AS m
  )
  SELECT (SELECT count(*)::integer FROM matches),
         (
           SELECT coalesce(jsonb_agg(
                    pettycash.entry_document(page.e, v_permissions, v_limit, v_earliest)
                    ORDER BY (page.e).entry_date, (page.e).kind, (page.e).id), '[]'::jsonb)
           FROM (
             SELECT m.e
             FROM matches AS m
             ORDER BY (m.e).entry_date, (m.e).kind, (m.e).id
             OFFSET (p_page - 1) * p_page_size
             LIMIT p_page_size
           ) AS page
         )
  INTO v_total, v_items;

  RETURN jsonb_build_object('total', v_total, 'items', v_items);
END;
$$;
