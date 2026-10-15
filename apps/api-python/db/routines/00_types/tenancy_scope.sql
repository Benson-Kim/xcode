-- tenancy.scope (all_companies boolean, company_ids uuid[], vehicle_ids uuid[])
-- Purpose: the current actor's data scope rows.
-- Callers: tenancy.actor_scope and the visibility helpers of later areas.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_tenancy_helpers.py.
-- Created once; a changed type is a versioned migration that drops and recreates it with its dependants.

DO $$
BEGIN
  IF pg_catalog.to_regtype('tenancy.scope') IS NULL THEN
    CREATE TYPE tenancy.scope AS (
      all_companies boolean,
      company_ids uuid[],
      vehicle_ids uuid[]
    );
  END IF;
END
$$;
