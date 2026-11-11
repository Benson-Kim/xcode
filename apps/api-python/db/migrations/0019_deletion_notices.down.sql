-- Reverse 0019: drop the deletion-notice outbox and the routines and helpers that use it. Pending notices are lost; the requests stay recorded in the change log.

SET LOCAL lock_timeout = '10s';

DROP FUNCTION IF EXISTS api.deletion_notice_result(uuid, boolean, timestamptz);
DROP FUNCTION IF EXISTS api.deletion_notice_claim(timestamptz, integer);
DROP FUNCTION IF EXISTS tenancy.deletion_notice_org(uuid);
DROP FUNCTION IF EXISTS tenancy.deletion_notice_sends();
DROP TABLE IF EXISTS tenancy.deletion_notices;
