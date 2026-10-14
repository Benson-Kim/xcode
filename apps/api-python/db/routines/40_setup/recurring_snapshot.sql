-- setup.recurring_snapshot(p_id uuid) RETURNS json
-- Purpose: the change-log snapshot of a scheduled item, compact JSON with the .NET keys Id, StoppedFrom, PausedFrom (the open pause's start), Pauses [{From, Through}] by start, Versions by revision, each with Id, Revision, EffectiveFrom, Name, Kind, Amount, Frequency, Day, LastDay, Month, Start, End, ExpenseItemId, Bucket, Note, Allocations [{VehicleId, Amount}] by vehicle id, ConditionMin and ConditionDays, then Opening {Date, Amounts [{VehicleId, Amount}] by vehicle id} or null; enumerations as numbers; the JSON null for an unknown item.
-- Callers: setup.save_recurring, api.setup_recurring_stop, api.setup_recurring_cancel_stop, api.setup_recurring_pause, api.setup_recurring_resume.
-- Reads: setup.recurring_items, setup.recurring_pauses, setup.recurring_versions, setup.recurring_allocations, setup.saving_openings, setup.saving_opening_amounts. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_setup_helpers.py.
-- The store keeps no order for a version's shares, so they are listed by vehicle id.

CREATE OR REPLACE FUNCTION setup.recurring_snapshot(p_id uuid)
RETURNS json
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT tenancy.compact_json(coalesce(
    (
      SELECT json_build_object(
               'Id', i.id,
               'StoppedFrom', i.stopped_from,
               'PausedFrom', (
                 SELECT p.paused_from
                 FROM setup.recurring_pauses AS p
                 WHERE p.organization_id = i.organization_id AND p.item_id = i.id AND p.paused_through IS NULL
               ),
               'Pauses', (
                 SELECT coalesce(
                          json_agg(
                            json_build_object('From', p.paused_from, 'Through', p.paused_through)
                            ORDER BY p.paused_from),
                          '[]'::json)
                 FROM setup.recurring_pauses AS p
                 WHERE p.organization_id = i.organization_id AND p.item_id = i.id
               ),
               'Versions', (
                 SELECT coalesce(
                          json_agg(
                            json_build_object(
                              'Id', v.id,
                              'Revision', v.revision,
                              'EffectiveFrom', v.effective_from,
                              'Name', v.name,
                              'Kind', v.kind,
                              'Amount', trim_scale(v.amount),
                              'Frequency', v.frequency,
                              'Day', v.day,
                              'LastDay', v.last_day,
                              'Month', v.month,
                              'Start', v.start_on,
                              'End', v.end_on,
                              'ExpenseItemId', v.expense_item_id,
                              'Bucket', v.bucket,
                              'Note', v.note,
                              'Allocations', (
                                SELECT coalesce(
                                         json_agg(
                                           json_build_object(
                                             'VehicleId', a.vehicle_id,
                                             'Amount', trim_scale(a.amount)
                                           ) ORDER BY a.vehicle_id),
                                         '[]'::json)
                                FROM setup.recurring_allocations AS a
                                WHERE a.organization_id = v.organization_id AND a.version_id = v.id
                              ),
                              'ConditionMin', trim_scale(v.condition_min),
                              'ConditionDays', v.condition_days
                            ) ORDER BY v.revision),
                          '[]'::json)
                 FROM setup.recurring_versions AS v
                 WHERE v.organization_id = i.organization_id AND v.item_id = i.id
               ),
               'Opening', (
                 SELECT json_build_object(
                          'Date', o.opened_on,
                          'Amounts', (
                            SELECT coalesce(
                                     json_agg(
                                       json_build_object('VehicleId', a.vehicle_id, 'Amount', trim_scale(a.amount))
                                       ORDER BY a.vehicle_id),
                                     '[]'::json)
                            FROM setup.saving_opening_amounts AS a
                            WHERE a.organization_id = o.organization_id AND a.item_id = o.item_id
                          )
                        )
                 FROM setup.saving_openings AS o
                 WHERE o.organization_id = i.organization_id AND o.item_id = i.id
               )
             )
      FROM setup.recurring_items AS i
      WHERE i.organization_id = tenancy.current_organization() AND i.id = p_id
    ),
    'null'::json
  ));
$$;

REVOKE ALL ON FUNCTION setup.recurring_snapshot(uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION setup.recurring_snapshot(uuid) TO xcode_api_executor;
