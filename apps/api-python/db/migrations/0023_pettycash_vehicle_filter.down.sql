-- Reverse 0023: drop the signatures with a vehicle; `db routines` of the release before restores the ones without it.

SET LOCAL lock_timeout = '10s';

DROP FUNCTION IF EXISTS api.pettycash_entry_list(uuid, uuid, text, date, date, uuid, text[], text[], text, integer, integer, timestamptz, uuid);
DROP FUNCTION IF EXISTS api.pettycash_export_get(uuid, uuid, text, date, date, uuid, text, text[], text, text, timestamptz, uuid);
DROP FUNCTION IF EXISTS api.pettycash_day_approve(uuid, uuid, text, date, date, uuid, timestamptz, uuid);
DROP FUNCTION IF EXISTS api.pettycash_overview_get(uuid, uuid, text, date, text, uuid, date, date, timestamptz, uuid);
DROP FUNCTION IF EXISTS pettycash.entry_matches(uuid, date, date, smallint[], text[], text, boolean, uuid[], uuid);
