-- ops.seed_pettycash_day(p_organization_id uuid, p_owner_id uuid, p_request_id text, p_days_back integer, p_day date, p_at timestamptz) RETURNS void
-- Purpose: the petty-cash events of one demo day through the pettycash routines: the Owner gives the demo fleet manager cash and a credit note and approves, rejects, sends back or removes expenses, and the fleet manager records expenses on the vehicles, so every entry state exists; nothing happens when the fleet manager is missing or keeps no float.
-- Callers: ops.seed_fleet.
-- Reads: identity.users, tenancy.memberships, setup.fleet_vehicles, setup.expense_items, pettycash.entries, and what pettycash.is_holder reads. Writes: what api.pettycash_entry_create, api.pettycash_entry_approve, api.pettycash_entry_reject, api.pettycash_entry_send_back and api.pettycash_entry_remove write.
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py.
-- An expense is found again by its note, which is unique among the demo entries.

CREATE OR REPLACE FUNCTION ops.seed_pettycash_day(
  p_organization_id uuid,
  p_owner_id uuid,
  p_request_id text,
  p_days_back integer,
  p_day date,
  p_at timestamptz
)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_event record;
  v_manager_id uuid;
  v_vehicle_id uuid;
  v_item_id uuid;
  v_entry pettycash.entries;
BEGIN
  PERFORM tenancy.enter_organization_as_operator(p_organization_id);
  SELECT m.user_id INTO v_manager_id
  FROM tenancy.memberships AS m
  JOIN identity.users AS u ON u.id = m.user_id
  WHERE m.organization_id = p_organization_id AND m.active AND u.status = 'active'
    AND u.email = 'brian.mwangi@metrotrans.co.ke';
  IF v_manager_id IS NULL OR NOT pettycash.is_holder(v_manager_id) THEN
    RETURN;
  END IF;

  FOR v_event IN
    SELECT e.*
    FROM (
      VALUES
        (38, 'cash', NULL, NULL, 1, 30000, 'Float top-up, week 1', NULL),
        (36, 'expense', 'KDA 482M', 'Spares', 2, 2350, 'Spares for KDA 482M', NULL),
        (35, 'approve', NULL, NULL, NULL, NULL, 'Spares for KDA 482M', NULL),
        (33, 'expense', 'KDD 921K', 'Tyres', 1, 8500, 'Rear tyre for KDD 921K', NULL),
        (32, 'reject', NULL, NULL, NULL, NULL, 'Rear tyre for KDD 921K', 'No receipt attached'),
        (29, 'expense', 'KDB 117P', 'Towing', 1, 4000, 'Towing for KDB 117P', NULL),
        (28, 'send_back', NULL, NULL, NULL, NULL, 'Towing for KDB 117P', 'Add the garage name'),
        (25, 'expense', 'KDE 640J', 'Service and maintenance', 1, 6200, 'Service for KDE 640J', NULL),
        (24, 'approve', NULL, NULL, NULL, NULL, 'Service for KDE 640J', NULL),
        (20, 'credit', NULL, NULL, 1, 1500, 'Spares returned to the supplier', NULL),
        (17, 'expense', 'KDC 305T', 'Garage labour', 3, 1200, 'Labour for KDC 305T', NULL),
        (16, 'approve', NULL, NULL, NULL, NULL, 'Labour for KDC 305T', NULL),
        (12, 'cash', NULL, NULL, 1, 15000, 'Float top-up, week 4', NULL),
        (9, 'expense', 'KDA 482M', 'Parking', 1, 800, 'Parking for KDA 482M', NULL),
        (6, 'expense', 'KDF 758L', 'Body work', 1, 5400, 'Body work for KDF 758L', NULL),
        (5, 'expense', 'KDF 758L', 'Body work', 1, 5400, 'Body work for KDF 758L, again', NULL),
        (4, 'remove', NULL, NULL, NULL, NULL, 'Body work for KDF 758L, again', 'Recorded twice'),
        (3, 'expense', 'KDB 117P', 'Inspection', 1, 1000, 'Inspection for KDB 117P', NULL)
    ) AS e (days_back, action, registration, item, units, amount, note, detail)
    WHERE e.days_back = p_days_back
  LOOP
    PERFORM tenancy.enter_organization_as_operator(p_organization_id);
    IF v_event.action IN ('cash', 'credit') THEN
      PERFORM api.pettycash_entry_create(
        p_owner_id, p_organization_id, p_request_id, NULL::uuid, v_event.action, p_day,
        v_event.amount, v_manager_id, NULL::uuid, NULL::uuid, v_event.units, NULL::text,
        v_event.note, false, p_at
      );
    ELSIF v_event.action = 'expense' THEN
      SELECT f.id INTO v_vehicle_id
      FROM setup.fleet_vehicles AS f
      WHERE f.organization_id = p_organization_id AND f.registration = v_event.registration;
      SELECT i.id INTO v_item_id
      FROM setup.expense_items AS i
      WHERE i.organization_id = p_organization_id
        AND i.normalized_name = upper(v_event.item COLLATE "C");
      PERFORM api.pettycash_entry_create(
        v_manager_id, p_organization_id, p_request_id, NULL::uuid, 'expense', p_day,
        v_event.amount, NULL::uuid, v_vehicle_id, v_item_id, v_event.units, NULL::text,
        v_event.note, false, p_at
      );
    ELSE
      SELECT e.* INTO v_entry
      FROM pettycash.entries AS e
      WHERE e.organization_id = p_organization_id AND e.note = v_event.note;
      IF v_event.action = 'approve' THEN
        PERFORM api.pettycash_entry_approve(
          p_owner_id, p_organization_id, p_request_id, v_entry.id, v_entry.version, p_at
        );
      ELSIF v_event.action = 'reject' THEN
        PERFORM api.pettycash_entry_reject(
          p_owner_id, p_organization_id, p_request_id, v_entry.id, v_entry.version, v_event.detail,
          p_at
        );
      ELSIF v_event.action = 'send_back' THEN
        PERFORM api.pettycash_entry_send_back(
          p_owner_id, p_organization_id, p_request_id, v_entry.id, v_entry.version, v_event.detail,
          p_at
        );
      ELSE
        PERFORM api.pettycash_entry_remove(
          p_owner_id, p_organization_id, p_request_id, v_entry.id, v_entry.version, v_event.detail,
          p_at
        );
      END IF;
    END IF;
  END LOOP;
END;
$$;

REVOKE ALL ON FUNCTION ops.seed_pettycash_day(uuid, uuid, text, integer, date, timestamptz)
  FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ops.seed_pettycash_day(uuid, uuid, text, integer, date, timestamptz)
  TO xcode_api_executor;
