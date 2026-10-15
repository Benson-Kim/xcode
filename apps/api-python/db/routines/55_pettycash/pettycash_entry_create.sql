-- api.pettycash_entry_create(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_id uuid, p_kind text, p_date date, p_unit_amount numeric, p_holder_id uuid, p_vehicle_id uuid, p_expense_item_id uuid, p_units numeric, p_payee text, p_note text, p_reimbursable boolean, p_allocations jsonb, p_now timestamptz) RETURNS jsonb
-- Purpose: record one entry: an expense (waiting) on the actor's float or, with pettycash.spend_other, on another holder's; a credit note on a holder's float (the actor's when p_holder_id is null); cash given to a holder. An expense bought for several vehicles carries p_allocations (expenses.check_purchase's rules): one waiting entry per vehicle sharing the purchase as bought, the first entry's id being the purchase's (p_id, or a new id) and the group's; one allocation is a plain entry on that vehicle; cash and credit notes take none. p_id is the client's id: an entry the actor already saved under it answers replayed without reading the body, one someone else saved is a conflict. Logs "Recorded {subject}" per entry; answers PettyCashSaved of the (first) entry with the outcome.
-- Callers: PettyCashRoutines.create; CreatePettyCashEntry (POST /setup/pettycash/entries).
-- Reads: pettycash.entries, and what tenancy.business_date, tenancy.effective_permissions, tenancy.check_writable, pettycash.check_line, expenses.check_purchase, pettycash.is_holder, pettycash.check_expense, pettycash.guard_float and pettycash.saved read. Writes: pettycash.entries, and what pettycash.log writes (row locks on the holder's membership and the vehicles).
-- Raises: XC403 not_member via tenancy.enter_organization, XC403 permission_missing via tenancy.require_any_permission, XC422 pettycash_kind_invalid via pettycash.check_line, XC422 pettycash_line_amount_zero via pettycash.check_line, XC422 expense_vehicles_invalid via expenses.check_purchase, XC422 expense_allocation_amount via expenses.check_purchase, XC422 expense_allocation_sign via expenses.check_purchase, XC422 expense_allocation_sum via expenses.check_purchase, XC422 pettycash_line_expense_payee, XC422 pettycash_line_credit_vehicle, XC422 pettycash_line_cash_shape, XC409 pettycash_already_saved, XC403 pettycash_spend_permission, XC422 pettycash_own_float_only, XC422 pettycash_holder_not_holder, XC403 pettycash_credit_permission, XC403 pettycash_cash_permission, XC422 pettycash_holder_required, XC422 pettycash_future_date via pettycash.check_date, XC422 pettycash_too_old via pettycash.check_date, XC422 record_too_old via tenancy.check_writable, XC422 pettycash_vehicle_scope via pettycash.check_expense, XC422 pettycash_vehicle_inactive via pettycash.check_expense, XC422 pettycash_item_inactive via pettycash.check_expense, XC422 pettycash_below_zero via pettycash.guard_float, XC422 time_zone_invalid via tenancy.business_date.
-- Tests: tests/db/test_pettycash_routines.py, tests/api/test_petty_cash.py.
-- Two saves under one new id race to the insert; the loser's unique violation reads the
-- winner's row and answers as a replay or a conflict, as if it had come second.
-- The float is locked before the vehicle and item are checked, so no create holds a
-- vehicle or item share while it waits for a float: a change on the same float takes the
-- float, then the entry, then those shares, and a vehicle or item write queued between
-- them would otherwise close a deadlock cycle. A shared purchase's vehicles are read in id
-- order, and its first entry carries the purchase id, so a racing retry meets the same key.

CREATE OR REPLACE FUNCTION api.pettycash_entry_create(
  p_actor_id uuid,
  p_organization_id uuid,
  p_request_id text,
  p_id uuid,
  p_kind text,
  p_date date,
  p_unit_amount numeric,
  p_holder_id uuid,
  p_vehicle_id uuid,
  p_expense_item_id uuid,
  p_units numeric,
  p_payee text,
  p_note text,
  p_reimbursable boolean,
  p_allocations jsonb,
  p_now timestamptz
)
RETURNS jsonb
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  c_none CONSTANT uuid := '00000000-0000-0000-0000-000000000000';
  v_id uuid := nullif(p_id, c_none);
  v_kind smallint := pettycash.kind_code(p_kind);
  v_vehicle uuid := nullif(p_vehicle_id, c_none);
  v_item uuid := nullif(p_expense_item_id, c_none);
  v_units numeric := coalesce(p_units, 1);
  v_payee text := tenancy.trim_text(p_payee);
  v_note text := tenancy.trim_text(p_note);
  v_reimbursable boolean := coalesce(p_reimbursable, false);
  v_shared boolean := p_allocations IS NOT NULL AND p_allocations <> '[]'::jsonb;
  v_vehicles uuid[];
  v_units_each numeric[];
  v_amounts_each numeric[];
  v_size integer := 1;
  v_part uuid;
  v_parts uuid[] := ARRAY[]::uuid[];
  v_permissions text[];
  v_today date;
  v_holder uuid;
  v_status smallint;
  v_recorded_by uuid;
BEGIN
  PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, NULL);
  PERFORM tenancy.require_any_permission(ARRAY[
    'pettycash.spend', 'pettycash.spend_other', 'pettycash.issue', 'pettycash.credit'
  ]);
  IF v_shared AND v_kind = 2 THEN
    SELECT array_agg(c.vehicle_id ORDER BY c.position),
           array_agg(c.units ORDER BY c.position),
           array_agg(c.unit_amount ORDER BY c.position)
    INTO v_vehicles, v_units_each, v_amounts_each
    FROM expenses.check_purchase(p_date, v_item, v_units, p_unit_amount, v_note, p_allocations)
      WITH ORDINALITY AS c (vehicle_id, units, unit_amount, position);
    IF v_payee IS NOT NULL OR v_reimbursable THEN
      PERFORM tenancy.refuse('pettycash_line_expense_payee', 'XC422');
    END IF;
    v_size := cardinality(v_vehicles);
    v_vehicle := v_vehicles[1];
  ELSE
    PERFORM pettycash.check_line(
      v_kind, p_date, p_unit_amount, v_units, v_vehicle, v_item, v_payee, v_note, v_reimbursable
    );
    IF v_shared THEN
      IF v_kind = 3 THEN
        PERFORM tenancy.refuse('pettycash_line_credit_vehicle', 'XC422');
      END IF;
      PERFORM tenancy.refuse('pettycash_line_cash_shape', 'XC422');
    END IF;
  END IF;

  IF v_id IS NOT NULL THEN
    SELECT e.recorded_by INTO v_recorded_by
    FROM pettycash.entries AS e
    WHERE e.organization_id = p_organization_id AND e.id = v_id;
    IF FOUND THEN
      IF v_recorded_by <> p_actor_id THEN
        PERFORM tenancy.refuse('pettycash_already_saved', 'XC409', jsonb_build_object('current', NULL));
      END IF;
      RETURN pettycash.saved(v_id, 'replayed');
    END IF;
  END IF;

  v_permissions := tenancy.effective_permissions(p_organization_id, p_actor_id);
  IF v_kind = 2 THEN
    IF p_holder_id IS NULL OR p_holder_id = p_actor_id THEN
      IF NOT 'pettycash.spend' = ANY (v_permissions) THEN
        PERFORM tenancy.refuse('pettycash_spend_permission', 'XC403');
      END IF;
      v_holder := p_actor_id;
    ELSE
      IF NOT 'pettycash.spend_other' = ANY (v_permissions) THEN
        IF 'pettycash.spend' = ANY (v_permissions) THEN
          PERFORM tenancy.refuse('pettycash_own_float_only', 'XC422');
        END IF;
        PERFORM tenancy.refuse('pettycash_spend_permission', 'XC403');
      END IF;
      IF NOT pettycash.is_holder(p_holder_id) THEN
        PERFORM tenancy.refuse('pettycash_holder_not_holder', 'XC422');
      END IF;
      v_holder := p_holder_id;
    END IF;
    v_status := 1;
  ELSIF v_kind = 3 THEN
    IF NOT 'pettycash.credit' = ANY (v_permissions) THEN
      PERFORM tenancy.refuse('pettycash_credit_permission', 'XC403');
    END IF;
    v_holder := coalesce(p_holder_id, p_actor_id);
    IF NOT pettycash.is_holder(v_holder) THEN
      PERFORM tenancy.refuse('pettycash_holder_not_holder', 'XC422');
    END IF;
  ELSE
    IF NOT 'pettycash.issue' = ANY (v_permissions) THEN
      PERFORM tenancy.refuse('pettycash_cash_permission', 'XC403');
    END IF;
    IF p_holder_id IS NULL THEN
      PERFORM tenancy.refuse('pettycash_holder_required', 'XC422');
    END IF;
    IF NOT pettycash.is_holder(p_holder_id) THEN
      PERFORM tenancy.refuse('pettycash_holder_not_holder', 'XC422');
    END IF;
    v_holder := p_holder_id;
  END IF;

  v_today := tenancy.business_date(p_organization_id, p_now);
  PERFORM pettycash.check_date(p_date, v_today);
  PERFORM tenancy.check_writable(p_date, p_now);
  PERFORM pettycash.lock_float(v_holder);
  IF v_size > 1 THEN
    PERFORM 1
    FROM setup.fleet_vehicles AS f
    WHERE f.organization_id = p_organization_id AND f.id = ANY (v_vehicles)
    ORDER BY f.id
    FOR SHARE;
    FOR i IN 1 .. v_size LOOP
      PERFORM pettycash.check_expense(v_vehicles[i], v_item, p_date, true, i = 1);
    END LOOP;
  ELSIF v_kind = 2 THEN
    PERFORM pettycash.check_expense(v_vehicle, v_item, p_date, true, true);
  END IF;
  PERFORM pettycash.guard_float(
    v_holder, v_kind, pettycash.effect(v_kind, v_status, round(v_units * p_unit_amount, 2))
  );

  BEGIN
    IF v_size = 1 THEN
      INSERT INTO pettycash.entries (
        organization_id, id, holder_id, kind, entry_date, vehicle_id, expense_item_id, units,
        unit_amount, payee, note, reimbursable, status, recorded_by, recorded_at, updated_by, updated_at
      )
      VALUES (
        p_organization_id, coalesce(v_id, gen_random_uuid()), v_holder, v_kind, p_date, v_vehicle,
        v_item, v_units, p_unit_amount, v_payee, v_note, v_reimbursable, v_status, p_actor_id, p_now,
        p_actor_id, p_now
      )
      RETURNING id INTO v_id;
      v_parts := ARRAY[v_id];
    ELSE
      v_id := coalesce(v_id, gen_random_uuid());
      FOR i IN 1 .. v_size LOOP
        v_part := CASE WHEN i = 1 THEN v_id ELSE gen_random_uuid() END;
        INSERT INTO pettycash.entries (
          organization_id, id, holder_id, kind, entry_date, vehicle_id, expense_item_id, units,
          unit_amount, payee, note, reimbursable, status, recorded_by, recorded_at, updated_by,
          updated_at, group_id, group_total, group_units, group_unit_amount
        )
        VALUES (
          p_organization_id, v_part, v_holder, v_kind, p_date, v_vehicles[i], v_item,
          v_units_each[i], v_amounts_each[i], NULL, v_note, false, v_status, p_actor_id, p_now,
          p_actor_id, p_now, v_id, round(v_units * p_unit_amount, 2), v_units, p_unit_amount
        );
        v_parts := v_parts || v_part;
      END LOOP;
    END IF;
  EXCEPTION
    WHEN unique_violation THEN
      SELECT e.recorded_by INTO v_recorded_by
      FROM pettycash.entries AS e
      WHERE e.organization_id = p_organization_id AND e.id = v_id;
      IF v_recorded_by <> p_actor_id THEN
        PERFORM tenancy.refuse('pettycash_already_saved', 'XC409', jsonb_build_object('current', NULL));
      END IF;
      RETURN pettycash.saved(v_id, 'replayed');
  END;

  FOR i IN 1 .. cardinality(v_parts) LOOP
    PERFORM pettycash.log(v_parts[i], 'null'::json, 'Recorded', NULL, 'created', p_now);
  END LOOP;
  RETURN pettycash.saved(v_id, 'created');
END;
$$;
