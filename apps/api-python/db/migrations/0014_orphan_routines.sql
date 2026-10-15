-- Drop routines whose signatures changed after their migrations were applied: two api routines `db routines` left behind without a caller (auth_sign_in gained the checked PIN hash, people_list the role and status filters), and the posting helpers that gain kinds and item filters.

SET LOCAL lock_timeout = '10s';

DROP FUNCTION IF EXISTS api.auth_sign_in(text, uuid, text, boolean, text, text, boolean, timestamptz);
DROP FUNCTION IF EXISTS api.people_list(uuid, uuid, text, integer, integer, timestamptz);
DROP FUNCTION IF EXISTS setup.scheduled_runs(uuid[], date, date, date);
DROP FUNCTION IF EXISTS setup.fleet_postings(uuid[], date, date, date);
