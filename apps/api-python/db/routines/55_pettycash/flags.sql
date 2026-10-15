-- pettycash.flags(p_entry pettycash.entries, p_permissions text[], p_limit numeric, p_earliest date) RETURNS jsonb
-- Purpose: what the current actor may do with an entry now, as pettycash.authorize_change, authorize_remove and authorize_review decide it, with edit, delete and reopen also off on a row dated before p_earliest (the back-dating limit, NULL for none): {can_edit, can_remove, can_review (approve), above_limit, can_send_back, can_reject, can_reopen}.
-- Callers: pettycash.entry_document.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_pettycash_helpers.py.

CREATE OR REPLACE FUNCTION pettycash.flags(
  p_entry pettycash.entries,
  p_permissions text[],
  p_limit numeric,
  p_earliest date
)
RETURNS jsonb
LANGUAGE sql
STABLE
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT jsonb_build_object(
           'can_edit', x.writable AND x.expense AND p_entry.status = 1
             AND ('pettycash.edit' = ANY (p_permissions) OR (x.own AND 'pettycash.edit_own' = ANY (p_permissions))),
           'can_remove', x.writable AND CASE
             WHEN NOT x.expense THEN 'pettycash.delete_cash' = ANY (p_permissions)
             WHEN p_entry.status = 1 THEN 'pettycash.delete' = ANY (p_permissions)
               OR (x.own AND 'pettycash.delete_own' = ANY (p_permissions))
             WHEN p_entry.status = 2 THEN 'pettycash.delete_approved' = ANY (p_permissions)
             ELSE false
           END,
           'can_review', x.ready AND x.reviewer AND 'pettycash.approve_item' = ANY (p_permissions),
           'above_limit', x.ready AND NOT x.within,
           'can_send_back', x.ready AND x.reviewer AND 'pettycash.send_back' = ANY (p_permissions),
           'can_reject', x.waiting AND x.reviewer AND 'pettycash.reject' = ANY (p_permissions),
           'can_reopen', x.writable AND x.expense AND p_entry.status IN (2, 4)
             AND 'pettycash.reopen' = ANY (p_permissions)
         )
  FROM (
    SELECT w.*,
           w.waiting AND p_entry.sent_back_note IS NULL AS ready,
           NOT w.own AND p_entry.recorded_by <> tenancy.current_actor() AND w.within AS reviewer
    FROM (
      SELECT p_entry.kind = 2 AS expense,
             p_entry.kind = 2 AND p_entry.status = 1 AS waiting,
             p_entry.holder_id = tenancy.current_actor() AS own,
             p_limit IS NULL OR abs(p_entry.total) <= p_limit AS within,
             p_earliest IS NULL OR p_entry.entry_date >= p_earliest AS writable
    ) AS w
  ) AS x;
$$;

REVOKE ALL ON FUNCTION pettycash.flags(pettycash.entries, text[], numeric, date) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pettycash.flags(pettycash.entries, text[], numeric, date) TO xcode_api_executor;
