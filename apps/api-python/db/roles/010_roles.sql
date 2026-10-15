-- Roles for the xcode database (docs/03-database.md section 2); idempotent, no production passwords.

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'xcode_owner') THEN
    CREATE ROLE xcode_owner LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'xcode_api_executor') THEN
    CREATE ROLE xcode_api_executor NOLOGIN NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'xcode_app') THEN
    CREATE ROLE xcode_app LOGIN NOBYPASSRLS CONNECTION LIMIT 50;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'xcode_operator') THEN
    CREATE ROLE xcode_operator LOGIN NOBYPASSRLS CONNECTION LIMIT 5;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'xcode_readonly') THEN
    CREATE ROLE xcode_readonly LOGIN NOBYPASSRLS CONNECTION LIMIT 5;
  END IF;
END
$$;

-- Role settings (held under any pooler because they are role attributes, not URL options).
ALTER ROLE xcode_app SET statement_timeout = '5s';
ALTER ROLE xcode_app SET lock_timeout = '2s';
ALTER ROLE xcode_app SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE xcode_app CONNECTION LIMIT 50;

ALTER ROLE xcode_operator SET statement_timeout = '5s';
ALTER ROLE xcode_operator SET lock_timeout = '2s';
ALTER ROLE xcode_operator SET idle_in_transaction_session_timeout = '10s';
ALTER ROLE xcode_operator CONNECTION LIMIT 5;

ALTER ROLE xcode_readonly CONNECTION LIMIT 5;

-- The owner is a member of the executor so it can assign routine ownership to it.
GRANT xcode_api_executor TO xcode_owner;
