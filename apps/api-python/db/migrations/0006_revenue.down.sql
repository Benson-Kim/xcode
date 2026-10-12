-- Reverse of 0006_revenue.sql.

SET LOCAL lock_timeout = '10s';

REVOKE USAGE ON SCHEMA revenue FROM xcode_readonly;
DROP TABLE revenue.records;
DROP FUNCTION revenue.forbid_date_change();
DROP TABLE revenue.no_earnings_reasons;
