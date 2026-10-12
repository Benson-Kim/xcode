-- Schema usage, default privileges and executor DML grants (docs/03-database.md sections 1, 2).
-- No default EXECUTE grant in api: the routine runner grants each routine to its caller by name.

-- Connect for the four login roles (the current database, whatever it is named).
DO $$
BEGIN
  EXECUTE format(
    'GRANT CONNECT ON DATABASE %I TO xcode_owner, xcode_app, xcode_operator, xcode_readonly',
    current_database()
  );
END
$$;

-- Schema usage.
GRANT USAGE ON SCHEMA api TO xcode_app, xcode_operator;
GRANT USAGE ON SCHEMA identity, tenancy, setup, revenue, pettycash, ops, api TO xcode_api_executor;
-- The executor owns every api.* routine (SECURITY DEFINER); assigning it ownership needs
-- CREATE on the api schema. It still has no table or sequence privilege outside the DML
-- grants below, so least privilege holds for data.
GRANT CREATE ON SCHEMA api TO xcode_api_executor;

-- Functions are executable by PUBLIC by default; remove that default everywhere.
ALTER DEFAULT PRIVILEGES FOR ROLE xcode_owner IN SCHEMA api REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE xcode_owner IN SCHEMA identity REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE xcode_owner IN SCHEMA tenancy REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE xcode_owner IN SCHEMA setup REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE xcode_owner IN SCHEMA revenue REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE xcode_owner IN SCHEMA pettycash REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
ALTER DEFAULT PRIVILEGES FOR ROLE xcode_owner IN SCHEMA ops REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;

-- Data schemas: the executor reads and writes new tables and uses new sequences. Each
-- migration then sets its tables' grants (append-only tables keep INSERT only), so this file
-- never grants on existing tables: re-running it must not undo those revokes.
DO $$
DECLARE
  v_schema text;
BEGIN
  FOREACH v_schema IN ARRAY ARRAY['identity', 'tenancy', 'setup', 'revenue', 'pettycash', 'ops'] LOOP
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE xcode_owner IN SCHEMA %I '
      'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO xcode_api_executor',
      v_schema
    );
    EXECUTE format(
      'ALTER DEFAULT PRIVILEGES FOR ROLE xcode_owner IN SCHEMA %I '
      'GRANT USAGE ON SEQUENCES TO xcode_api_executor',
      v_schema
    );
  END LOOP;
END
$$;

-- xcode_readonly gets nothing here; access is added per column by reviewed migrations.
