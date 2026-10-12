-- api.setup_vehicle_report(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_vehicle_id uuid, p_period text, p_from date, p_through date, p_now timestamptz) RETURNS jsonb
-- Purpose: a visible vehicle's figures for the current week or month, or for a range of at most 367 days ending by the business date: money in, the target of the days that count, every scheduled posting and approved petty-cash expense (source pettycash) with its bucket, the bucket and savings totals, money out, net, after savings and costs.
-- Callers: SetupRoutines.vehicle_report; GetVehicleReport (GET /setup/vehicles/{id}/report).
-- Reads: revenue.records, and what tenancy.business_date, tenancy.settings_document, setup.vehicle_visible, setup.report_window, setup.vehicle_money_in, setup.vehicle_postings, pettycash.vehicle_postings, setup.vehicle_net and setup.day_target read. Writes: nothing.
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.enter_organization, XC422 time_zone_invalid via tenancy.business_date, XC422 report_period_invalid, XC422 report_range_required, XC422 report_range_invalid, XC404 not_found.
-- Tests: tests/db/test_setup_vehicle_routines.py, tests/api/test_setup_vehicles.py, tests/db/test_pettycash_routines.py.
-- A week starts on the organization's first day of the week. The target counts the days before
-- the business date and any day with a record, each at its day target in the set in force that day.

CREATE OR REPLACE FUNCTION api.setup_vehicle_report(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_vehicle_id uuid,
  p_period text,
  p_from date,
  p_through date,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_today date;
  v_period text := tenancy.trim_text(p_period);
  v_first_day integer;
  v_from date;
  v_through date;
  v_window daterange;
  v_money_in numeric;
  v_target numeric;
  v_postings jsonb;
  v_repairs numeric;
  v_charges numeric;
  v_loans numeric;
  v_savings numeric;
  v_money_out numeric;
  v_net numeric;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, 'vehicles.view');
  v_today := tenancy.business_date(p_organization_id, p_now);
  IF v_period IS NOT NULL THEN
    IF v_period = 'week' THEN
      v_first_day := (tenancy.settings_document('localization') ->> 'first_day_of_week')::integer;
      v_from := v_today - (extract(dow FROM v_today)::integer - v_first_day + 7) % 7;
    ELSIF v_period = 'month' THEN
      v_from := date_trunc('month', v_today)::date;
    ELSE
      PERFORM tenancy.refuse('report_period_invalid', 'XC422');
    END IF;
    v_through := v_today;
  ELSE
    IF p_from IS NULL OR p_through IS NULL THEN
      PERFORM tenancy.refuse('report_range_required', 'XC422');
    END IF;
    IF p_through < p_from OR p_through - p_from > 366 OR p_through > v_today THEN
      PERFORM tenancy.refuse('report_range_invalid', 'XC422');
    END IF;
    v_from := p_from;
    v_through := p_through;
  END IF;
  IF NOT setup.vehicle_visible(p_vehicle_id) THEN
    PERFORM tenancy.refuse('not_found', 'XC404');
  END IF;

  v_window := setup.report_window(p_vehicle_id, v_from, v_through, v_today);
  v_money_in := setup.vehicle_money_in(p_vehicle_id, v_window);
  SELECT coalesce(sum(setup.day_target(p_vehicle_id, d.day)), 0) INTO v_target
  FROM (
    SELECT g::date AS day
    FROM generate_series(lower(v_window)::timestamp, (upper(v_window) - 1)::timestamp, interval '1 day') AS g
    WHERE NOT isempty(v_window)
  ) AS d
  WHERE d.day < v_today
     OR EXISTS (
       SELECT 1 FROM revenue.records AS r
       WHERE r.organization_id = p_organization_id
         AND r.vehicle_id = p_vehicle_id
         AND r.business_date = d.day
     );

  SELECT coalesce(
           jsonb_agg(
             jsonb_build_object(
               'item_id', p.item_id,
               'version_id', p.version_id,
               'day', p.day,
               'name', p.name,
               'kind', p.kind,
               'amount', p.amount,
               'bucket', p.bucket,
               'source', p.source
             ) ORDER BY p.day, p.name COLLATE "C", p.item_id, p.version_id),
           '[]'::jsonb),
         coalesce(sum(p.amount) FILTER (WHERE p.kind = 1 AND p.bucket = 1), 0),
         coalesce(sum(p.amount) FILTER (WHERE p.kind = 1 AND p.bucket = 2), 0),
         coalesce(sum(p.amount) FILTER (WHERE p.kind = 1 AND p.bucket = 3), 0),
         coalesce(sum(p.amount) FILTER (WHERE p.kind = 2), 0)
  INTO v_postings, v_repairs, v_charges, v_loans, v_savings
  FROM (
    SELECT s.*, NULL::text AS source FROM setup.vehicle_postings(p_vehicle_id, v_window) AS s
    UNION ALL
    SELECT c.*, 'pettycash' FROM pettycash.vehicle_postings(p_vehicle_id, v_window) AS c
  ) AS p;
  v_money_out := v_repairs + v_charges + v_loans;
  v_net := setup.vehicle_net(p_vehicle_id, v_from, v_through, v_today);

  RETURN jsonb_build_object(
    'vehicle_id', p_vehicle_id,
    'from_date', v_from,
    'through', v_through,
    'money_in', v_money_in,
    'target', v_target,
    'repairs', v_repairs,
    'charges', v_charges,
    'loans', v_loans,
    'money_out', v_money_out,
    'net', v_net,
    'savings', v_savings,
    'after_savings', v_net - v_savings,
    'costs', v_money_out,
    'postings', v_postings
  );
END;
$$;
