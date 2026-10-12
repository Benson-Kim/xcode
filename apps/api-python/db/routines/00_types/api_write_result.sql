-- api.write_result (id uuid, version bigint, outcome text)
-- Purpose: the row every command returns: the id it wrote, the version after the write, and created/updated/unchanged/replayed.
-- Callers: every api.* command routine; adapted to domain.values.WriteResult in db/types.py.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_tenancy_helpers.py.
-- Created once; a changed type is a versioned migration that drops and recreates it with its dependants.

DO $$
BEGIN
  IF pg_catalog.to_regtype('api.write_result') IS NULL THEN
    CREATE TYPE api.write_result AS (
      id uuid,
      version bigint,
      outcome text
    );
  END IF;
END
$$;
