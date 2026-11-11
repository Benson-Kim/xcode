-- api.deletion_notice_result(p_notice_id uuid, p_sent boolean, p_now timestamptz) RETURNS void
-- Purpose: record how a send of one deletion notice ended, only while it is pending: sent with sent_at; a failure marks it failed once it has used tenancy.deletion_notice_sends() attempts, and otherwise leaves it pending for api.deletion_notice_claim to send again. An unknown id changes nothing.
-- Callers: TenancyRoutines.record_deletion_notice; the post-commit deletion notice send and the notice sweep.
-- Reads: tenancy.deletion_notices, and what tenancy.deletion_notice_org reads. Writes: tenancy.deletion_notices (state, sent_at).
-- Raises: none.
-- Tests: tests/db/test_deletion_routines.py.

CREATE OR REPLACE FUNCTION api.deletion_notice_result(p_notice_id uuid, p_sent boolean, p_now timestamptz)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.deletion_notice_org(p_notice_id);
BEGIN
  IF v_organization_id IS NULL THEN
    RETURN;
  END IF;
  PERFORM set_config('xcode.organization_id', v_organization_id::text, true);
  IF p_sent THEN
    UPDATE tenancy.deletion_notices
    SET state = 'sent', sent_at = p_now
    WHERE id = p_notice_id AND state = 'pending';
  ELSE
    UPDATE tenancy.deletion_notices
    SET state = 'failed'
    WHERE id = p_notice_id
      AND state = 'pending'
      AND attempts >= tenancy.deletion_notice_sends();
  END IF;
END;
$$;
