-- api.meta_contract_version() RETURNS integer
-- Purpose: the routine-contract version the database exposes; compared at startup with the package constant.
-- Callers: OpsRoutines.contract_version; main.py startup contract check.
-- Reads: nothing. Writes: nothing.
-- Raises: none.
-- Tests: tests/db/test_ops_routines.py, tests/db/test_structure.py.

CREATE OR REPLACE FUNCTION api.meta_contract_version()
RETURNS integer
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
  SELECT 5;
$$;
