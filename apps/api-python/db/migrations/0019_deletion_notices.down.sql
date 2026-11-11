-- Reverse 0019: drop the deletion-notice outbox and the routines that use it. Pending notices are lost; the requests stay recorded in the change log.

SET LOCAL lock_timeout = '10s';

DROP FUNCTION IF EXISTS api.deletion_notice_result(uuid, uuid, boolean, timestamptz);
DROP FUNCTION IF EXISTS api.deletion_notice_claim(timestamptz, integer);
DROP TABLE IF EXISTS tenancy.deletion_notices;
