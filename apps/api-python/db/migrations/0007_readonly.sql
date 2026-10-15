-- No grants for xcode_readonly beyond the code tables and the permission catalogue: deny by default, made explicit.

SET LOCAL lock_timeout = '10s';

-- A DBA migration that grants xcode_readonly anything more must:
--   1. grant SELECT on named columns only (GRANT SELECT (col, ...) ON table), never a whole table;
--   2. never cover identity.*, tenancy.audit_events, or any column ending in _hash or _digest;
--   3. limit itself to setup.*, revenue.* and tenancy.change_log;
--   4. add a reviewed RLS policy naming xcode_readonly for every tenant table it covers
--      (without one the table returns no rows to this role);
--   5. state who reads the data, from where, and why;
--   6. pass `xcode-api db verify`, which checks the hash, digest, identity and audit rules.
