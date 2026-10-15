-- Reverse of 0014_orphan_routines.sql: nothing to restore; the api routines had no file and no caller, and `db routines` creates the posting helpers with their new signatures.

SET LOCAL lock_timeout = '10s';
