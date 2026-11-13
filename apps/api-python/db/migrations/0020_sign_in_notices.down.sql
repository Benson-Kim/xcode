-- Reverse 0020: drop the sign-in notice outbox and the routines and helpers that use it. Pending notices are lost; the changes stay recorded in the audit events.

SET LOCAL lock_timeout = '10s';

DROP FUNCTION IF EXISTS api.sign_in_notice_result(uuid, boolean, timestamptz);
DROP FUNCTION IF EXISTS api.sign_in_notice_claim(timestamptz, integer, uuid, uuid, text, uuid);
DROP FUNCTION IF EXISTS tenancy.sign_in_notice_org(uuid);
DROP FUNCTION IF EXISTS tenancy.sign_in_notice_sends();
DROP TABLE IF EXISTS tenancy.sign_in_notices;
