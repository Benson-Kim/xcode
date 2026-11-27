-- Petty cash vehicle filter (Web v2.39): the entry list, its export, approve-day and the overview gain a vehicle; their old signatures go so `db routines` re-creates them with it.

SET LOCAL lock_timeout = '10s';

DROP FUNCTION IF EXISTS api.pettycash_entry_list(uuid, uuid, text, date, date, uuid, text[], text[], text, integer, integer, timestamptz);
DROP FUNCTION IF EXISTS api.pettycash_export_get(uuid, uuid, text, date, date, uuid, text, text[], text, text, timestamptz);
DROP FUNCTION IF EXISTS api.pettycash_day_approve(uuid, uuid, text, date, date, uuid, timestamptz);
DROP FUNCTION IF EXISTS api.pettycash_overview_get(uuid, uuid, text, date, text, uuid, date, date, timestamptz);
DROP FUNCTION IF EXISTS pettycash.entry_matches(uuid, date, date, smallint[], text[], text, boolean, uuid[]);
