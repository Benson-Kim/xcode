-- Schemas owned by xcode_owner, and a locked-down public schema (docs/03-database.md section 1).

REVOKE ALL ON SCHEMA public FROM PUBLIC;

CREATE SCHEMA IF NOT EXISTS identity AUTHORIZATION xcode_owner;
CREATE SCHEMA IF NOT EXISTS tenancy AUTHORIZATION xcode_owner;
CREATE SCHEMA IF NOT EXISTS setup AUTHORIZATION xcode_owner;
CREATE SCHEMA IF NOT EXISTS revenue AUTHORIZATION xcode_owner;
CREATE SCHEMA IF NOT EXISTS pettycash AUTHORIZATION xcode_owner;
CREATE SCHEMA IF NOT EXISTS expenses AUTHORIZATION xcode_owner;
CREATE SCHEMA IF NOT EXISTS reports AUTHORIZATION xcode_owner;
CREATE SCHEMA IF NOT EXISTS ops AUTHORIZATION xcode_owner;
CREATE SCHEMA IF NOT EXISTS api AUTHORIZATION xcode_owner;

-- Make xcode_owner the database owner where the executing role is allowed to set it
-- (the compose superuser can; a plain owner-capable role simply skips this).
DO $$
BEGIN
  BEGIN
    EXECUTE format('ALTER DATABASE %I OWNER TO xcode_owner', current_database());
  EXCEPTION
    WHEN insufficient_privilege THEN NULL;
  END;
END
$$;
