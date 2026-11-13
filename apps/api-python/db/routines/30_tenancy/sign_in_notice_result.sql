-- api.sign_in_notice_result(p_notice_id uuid, p_sent boolean, p_now timestamptz) RETURNS void
-- Purpose: record how a send of one sign-in notice ended, only while it is pending: sent with sent_at; a failure marks it failed once it has used tenancy.sign_in_notice_sends() attempts, and otherwise leaves it pending for api.sign_in_notice_claim to send again. Sent or failed, the address is cleared. An unknown id changes nothing.
-- Callers: TenancyRoutines.record_sign_in_notice; the post-commit sign-in notice send and the notice sweep.
-- Reads: tenancy.sign_in_notices, and what tenancy.sign_in_notice_org reads. Writes: tenancy.sign_in_notices (state, address, sent_at).
-- Raises: none.
-- Tests: tests/db/test_sign_in_notices.py.

CREATE OR REPLACE FUNCTION api.sign_in_notice_result(p_notice_id uuid, p_sent boolean, p_now timestamptz)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
  v_organization_id uuid := tenancy.sign_in_notice_org(p_notice_id);
BEGIN
  IF v_organization_id IS NULL THEN
    RETURN;
  END IF;
  PERFORM set_config('xcode.organization_id', v_organization_id::text, true);
  IF p_sent THEN
    UPDATE tenancy.sign_in_notices
    SET state = 'sent', sent_at = p_now, address = NULL
    WHERE id = p_notice_id AND state = 'pending';
  ELSE
    UPDATE tenancy.sign_in_notices
    SET state = 'failed', address = NULL
    WHERE id = p_notice_id
      AND state = 'pending'
      AND attempts >= tenancy.sign_in_notice_sends();
  END IF;
END;
$$;
