-- reports.build(p_group text, p_report text, p_from date, p_to date, p_company_id uuid, p_holder_id uuid, p_today date) RETURNS jsonb
-- Purpose: the whole table of one report for the current actor: an unknown group or report is not found; the investment report needs reports.investment and a petty-cash report pettycash.reports, with a holder among the floats the actor sees (every float with pettycash.view_all, else their own) or not found; a dated report's period is checked and cut to the business date (reports.check_period); then the builder runs over the actor's visible vehicles (of one company when given) or floats.
-- Callers: api.report_get, api.report_export_get.
-- Reads: what tenancy.has_permission, pettycash.visible_holders, setup.visible_vehicles and the report builders read. Writes: nothing.
-- Raises: XC404 not_found, XC403 report_investment_permission, XC403 report_pettycash_permission, XC422 report_period_both via reports.check_period, XC422 report_period_order via reports.check_period, XC422 report_period_length via reports.check_period, XC422 report_period_future via reports.check_period.
-- Tests: tests/db/test_report_routines.py.

CREATE OR REPLACE FUNCTION reports.build(
  p_group text,
  p_report text,
  p_from date,
  p_to date,
  p_company_id uuid,
  p_holder_id uuid,
  p_today date
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_span daterange;
  v_view_all boolean;
  v_holders uuid[];
  v_vehicles uuid[];
BEGIN
  IF p_group = 'fleet' THEN
    IF p_report IS NULL
       OR p_report NOT IN ('net', 'target', 'moneyOut', 'gaps', 'savings', 'investment') THEN
      PERFORM tenancy.refuse('not_found', 'XC404');
    END IF;
    IF p_report = 'investment' THEN
      IF NOT tenancy.has_permission('reports.investment') THEN
        PERFORM tenancy.refuse('report_investment_permission', 'XC403');
      END IF;
      RETURN reports.fleet_investment(p_company_id, p_today);
    END IF;
    v_span := reports.check_period(p_from, p_to, p_today);
    RETURN CASE p_report
             WHEN 'net' THEN
               reports.fleet_net(lower(v_span), upper(v_span) - 1, p_company_id, p_today)
             WHEN 'target' THEN
               reports.fleet_target(lower(v_span), upper(v_span) - 1, p_company_id, p_today)
             WHEN 'moneyOut' THEN
               reports.fleet_money_out(lower(v_span), upper(v_span) - 1, p_company_id, p_today)
             WHEN 'gaps' THEN
               reports.fleet_gaps(lower(v_span), upper(v_span) - 1, p_company_id, p_today)
             ELSE
               reports.fleet_savings(lower(v_span), upper(v_span) - 1, p_company_id, p_today)
           END;
  END IF;

  IF p_group = 'pettycash' THEN
    IF p_report IS NULL
       OR p_report NOT IN ('cashBook', 'managers', 'vehicles', 'items', 'waiting', 'sentBack', 'rejected') THEN
      PERFORM tenancy.refuse('not_found', 'XC404');
    END IF;
    IF NOT tenancy.has_permission('pettycash.reports') THEN
      PERFORM tenancy.refuse('report_pettycash_permission', 'XC403');
    END IF;
    v_view_all := tenancy.has_permission('pettycash.view_all');
    v_holders := ARRAY(
      SELECT h.user_id
      FROM pettycash.visible_holders(v_view_all) AS h
      WHERE p_holder_id IS NULL OR h.user_id = p_holder_id
    );
    IF p_holder_id IS NOT NULL AND cardinality(v_holders) = 0 THEN
      PERFORM tenancy.refuse('not_found', 'XC404');
    END IF;
    v_vehicles := ARRAY(SELECT visible.id FROM setup.visible_vehicles() AS visible (id));
    IF p_report = 'waiting' THEN
      RETURN reports.pettycash_waiting(v_holders, v_view_all, v_vehicles, p_today);
    END IF;
    v_span := reports.check_period(p_from, p_to, p_today);
    RETURN CASE p_report
             WHEN 'cashBook' THEN reports.pettycash_cash_book(
               lower(v_span), upper(v_span) - 1, v_holders, v_view_all, v_vehicles, p_today)
             WHEN 'managers' THEN reports.pettycash_managers(
               lower(v_span), upper(v_span) - 1, v_holders, v_view_all, v_vehicles, p_today)
             WHEN 'vehicles' THEN reports.pettycash_vehicles(
               lower(v_span), upper(v_span) - 1, v_holders, v_view_all, v_vehicles, p_today)
             WHEN 'items' THEN reports.pettycash_items(
               lower(v_span), upper(v_span) - 1, v_holders, v_view_all, v_vehicles, p_today)
             WHEN 'sentBack' THEN reports.pettycash_sent_back(
               lower(v_span), upper(v_span) - 1, v_holders, v_view_all, v_vehicles, p_today)
             ELSE reports.pettycash_rejected(
               lower(v_span), upper(v_span) - 1, v_holders, v_view_all, v_vehicles, p_today)
           END;
  END IF;

  PERFORM tenancy.refuse('not_found', 'XC404');
  RETURN NULL;
END;
$$;

REVOKE ALL ON FUNCTION reports.build(text, text, date, date, uuid, uuid, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION reports.build(text, text, date, date, uuid, uuid, date) TO xcode_api_executor;
