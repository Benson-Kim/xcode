# Roles and grants

Files (idempotent, re-runnable, no passwords for production roles):

- `010_roles.sql`: `xcode_owner`, `xcode_api_executor`, `xcode_app`, `xcode_operator`, `xcode_readonly`
  with the attributes in `docs/03-database.md` section 2, and role settings (timeouts).
- `020_schemas.sql`: schema creation with `AUTHORIZATION xcode_owner`, `REVOKE ALL ON
  SCHEMA public FROM PUBLIC`.
- `030_grants.sql`: schema usage, default privileges (revoke `EXECUTE` from `PUBLIC`
  everywhere; no default grant in `api`, the routine runner grants each routine to
  `xcode_app` or `xcode_operator` by name), default DML grants to `xcode_api_executor` for
  tables created later (each migration then sets its own tables' grants), nothing for
  `xcode_readonly`. It never grants on existing tables, so re-running it on a migrated
  database changes no table grant (`tests/db/test_role_files.py`).
- `900_local_dev.sql`: development-only passwords matching `.env.example`; mounted by
  `docker-compose.yml`; never applied elsewhere.

Production: a DBA applies `010` to `030` once per database; passwords are set out of band.
Tests: the harness applies all four to the throwaway server.

## DBA checklist for non-development databases (`docs/12-security.md`)

- Passwords set out of band; `scram-sha-256` only; TLS required (`ssl = on`, `hostssl` rules).
- `pg_hba.conf`: `xcode_app` only from the application network; `xcode_owner` only from
  the migration job's network; `xcode_operator` only from the operators' network;
  `xcode_readonly` only from the analysts' network.
- `ALTER ROLE xcode_app CONNECTION LIMIT` sized per `deploy/README.md`.
- `pg_stat_statements` enabled; `log_connections = on`; `pgaudit` optional for `ops` and
  `identity` DDL.
- Extensions limited to the allow-list in `docs/03-database.md` section 9.
- Backups encrypted; a restore drill recorded before cutover.
