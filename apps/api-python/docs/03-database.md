# Database conventions

PostgreSQL: the suite has only ever run on 16 (the local cluster); CI is configured for 18
but has not run yet, because nothing under `apps/api-python` is committed. The SQL must
work on both; the production host's version is open (`docs/13-open-questions.md` question
39), and any feature newer than 16 needs an entry here before it is used. Database name `xcode`.
Everything in this document is a rule;
`xcode-api db verify` and `tests/db/test_structure.py` check the rules that can be checked
mechanically.

## 1. Schemas

| Schema | Holds | Who may touch it |
|---|---|---|
| `identity` | users, PIN material, trusted devices, refresh tokens, verification codes, sign-in attempt state | routines only |
| `tenancy` | organizations, memberships, roles, permissions and data scopes, organization settings, change log, audit events | routines only |
| `setup` | PSV companies, fleet vehicles, away periods, expense catalog, recurring items and schedules, vehicle investments, setup execution/lifecycle | routines only |
| `revenue` | revenue records (one per vehicle and day; replay by payload equality), derived report helpers | routines only |
| `pettycash` | petty-cash entries (cash given, expenses, credit notes), their approvals and balances | routines only |
| `ops` | migration bookkeeping, routine versions, operator action audit (`ops.operator_actions`), rate-limit windows, outbound mail (if adopted) | runner and routines |
| `api` | every routine the application or the CLI may call; nothing else lives here | `xcode_app` (EXECUTE on everything except `api.ops_*`), `xcode_operator` (EXECUTE on `api.ops_*` and `api.meta_*`) |

Internal helper functions live in the data schema they serve (for example
`tenancy.require_permission`, `tenancy.enter_organization`, `identity.touch_version`) and are
never granted to `xcode_app` or `xcode_operator`. The `public` schema is empty; `CREATE` on it is revoked from
`PUBLIC`.

## 2. Roles

| Role | Attributes | Purpose | Privileges |
|---|---|---|---|
| `xcode_owner` | LOGIN, NOBYPASSRLS | migrations, DBA maintenance | owns all schemas, tables, sequences, types; member of `xcode_api_executor` so it can assign routine ownership |
| `xcode_api_executor` | NOLOGIN, NOBYPASSRLS | effective identity of every `api.*` routine (they are `SECURITY DEFINER` owned by this role) | `USAGE` on all schemas; `SELECT/INSERT/UPDATE/DELETE` on data tables; `USAGE` on sequences; `EXECUTE` on helper routines. Not the table owner, so RLS applies to it |
| `xcode_app` | LOGIN, NOBYPASSRLS, `statement_timeout='5s'`, `lock_timeout='2s'`, `idle_in_transaction_session_timeout='10s'`, `application_name` set by the pool | the API process | `CONNECT`; `USAGE` on schema `api`; `EXECUTE` on routines in `api` except `api.ops_*`. Nothing else: no table, sequence or data-schema privilege |
| `xcode_operator` | LOGIN, NOBYPASSRLS, the same timeouts as `xcode_app`, `CONNECTION LIMIT 5` | the CLI's user and seed commands (`provision-user`, `remove-user`, `clear-pause`, `revoke-sessions`, `seed-demo`), connected through `XCODE_DATABASE_OPERATOR_URL`; the API process never holds this credential | `CONNECT`; `USAGE` on schema `api`; `EXECUTE` on `api.ops_*` and `api.meta_*` only |
| `xcode_readonly` | LOGIN, optional, NOBYPASSRLS | BI/reporting, DBAs | deny by default: no privilege on `identity` or on audit tables; `SELECT` only on columns a DBA grants in a reviewed migration; no RLS policy names this role, so tenant tables return no rows until a DBA adds a reviewed policy |

Grant hygiene applied by `db/roles/*.sql`; `db verify` checks the outcome (the routine,
privilege and timeout checks of sections 7 and 9), not `pg_default_acl` itself:
- `REVOKE ALL ON SCHEMA public FROM PUBLIC;`
- `ALTER DEFAULT PRIVILEGES FOR ROLE xcode_owner IN SCHEMA api REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;` and the same for every data schema (functions are executable by `PUBLIC` by default; that default is removed everywhere).
- No default `EXECUTE` grant in `api`: `db routines` grants every routine to its caller by name (`api.ops_*` to `xcode_operator`, `api.meta_*` to `xcode_operator` and `xcode_app`, everything else to `xcode_app`), so a new routine is unreachable until the runner names its caller.
- `GRANT CREATE ON SCHEMA api TO xcode_api_executor`: PostgreSQL lets `ALTER FUNCTION ...
  OWNER TO` succeed only when the new owner holds `CREATE` on the function's schema, so the
  runner's ownership fix-up needs it. The executor still holds no privilege on any table or
  sequence beyond the DML grants, and `db verify` forbids dynamic SQL in routines, so the
  grant cannot be exercised from inside a routine.
- Timeouts are role settings (`ALTER ROLE xcode_app SET ...`), not connection-string options, so they hold under any pooler.
- Passwords are never in these files; the files use `CREATE ROLE ... LOGIN` and the operator sets passwords, except the local compose init which uses the obvious development passwords in `.env.example`.
- `ALTER ROLE xcode_app CONNECTION LIMIT <replicas x pool max + headroom>`; the number is
  recorded in `deploy/README.md` per environment. `xcode_operator` and `xcode_readonly`
  keep `CONNECTION LIMIT 5`.
- Audit tables (`identity.sign_in_attempts`, `tenancy.change_log`, `tenancy.audit_events`,
  `ops.operator_actions`) grant `INSERT` and `SELECT` only to `xcode_api_executor`:
  append-only by privilege.
- `xcode_readonly` is created with no grants; the schema migrations give it `SELECT` on the
  code tables and the permission catalogue, and `USAGE` on the schemas holding them
  (`tenancy`, `setup`, `revenue`), nothing else; further access is added per column by reviewed
  migrations and never covers hash or digest columns.

## 3. Row-level security

- Every table that has an `organization_id` column is a tenant table. It has
  `ENABLE ROW LEVEL SECURITY` and exactly one policy:
  `CREATE POLICY tenant_isolation ON <table> TO xcode_api_executor USING (organization_id = tenancy.current_organization()) WITH CHECK (organization_id = tenancy.current_organization());`
- `tenancy.current_organization()` is `STABLE`, `SECURITY INVOKER`, and returns
  `nullif(current_setting('xcode.organization_id', true), '')::uuid`. With the setting unset
  it returns `NULL`, so every policy evaluates to not-true and no row is visible or writable.
- `tenancy.enter_organization(p_actor_id uuid, p_organization_id uuid, p_permission text)`
  is the only function that sets `xcode.organization_id` (and `xcode.actor_id`), always with
  `set_config(..., true)` (transaction-local). It raises `XC403` unless the actor has an
  active membership in that organization holding `p_permission` (or `p_permission IS NULL`
  for "member is enough"). Every tenant-scoped `api.*` routine calls it first.
- Identity tables (`identity.*`) are not tenant tables; they are protected by being
  reachable only through routines.
- Two lookups run before any organization can be entered: the organization of a user's
  active membership (sign-in, session resolution, the unassigned-user count) and the list of
  organizations (provisioning's one-organization rule). They are the helpers
  `identity.active_organization(uuid)` and `tenancy.organization_ids()`, `SECURITY DEFINER`
  and owned by `xcode_owner`, which owns the tables and so is not subject to their policies.
  Each returns ids only and is executable by `xcode_api_executor` alone; every other
  function outside `api` is `SECURITY INVOKER`. `tests/db/test_routine_headers.py` pins
  that list, the owner and the grants.
- `FORCE ROW LEVEL SECURITY` is not used: the owner runs migrations and backfills freely;
  isolation is enforced on the executor, which is the only role that runs application SQL.
- Tests prove it: `tests/db/test_structure.py` asserts every table with `organization_id`
  has RLS enabled and the policy; `tests/db/test_tenancy_isolation.py` proves that a routine
  called with an actor from organization A cannot read or write organization B rows, and
  that a routine that skips `enter_organization` sees nothing.

## 4. Routine conventions

Naming:
- `api.<area>_<verb>_<noun>`: `api.auth_sign_in`, `api.revenue_capture`,
  `api.setup_vehicle_create`, `api.people_create`, `api.organization_settings_get`.
- Parameters `p_<name>`, locals `v_<name>`, `OUT` columns plain snake_case.
- Composite return types in `api` named after the noun: `api.revenue_record_row`,
  `api.session_row`. One routine, one file: `db/routines/50_revenue/revenue_capture.sql`.

Shape:
- `LANGUAGE plpgsql` (or `sql` for pure queries), `SECURITY DEFINER`,
  `SET search_path = pg_catalog, pg_temp`, every object name schema-qualified.
- Owned by `xcode_api_executor` (the runner sets ownership after applying files; `db verify`
  fails if any `api.*` routine is owned by someone else, is `SECURITY INVOKER`, or lacks the
  `search_path` setting).
- Reads are `STABLE`; writes are `VOLATILE`. No `IMMUTABLE` unless truly so.
- Routines return rows (`RETURNS TABLE`, `RETURNS SETOF api.<row type>`, or a single
  composite). They do not build JSON documents, except for settings blobs that are JSON in
  the domain.
- Writes take `p_actor_id` first, then `p_organization_id`, then the command fields, then
  `p_expected_version` where a row is updated, then `p_now timestamptz` last. The
  application always passes `p_now` from its `Clock` port so tests can control time and
  replicas agree on "now".
- Replayable commands (revenue capture) are keyed by the row's natural key and return the
  existing row with an `outcome` column (`created` | `replayed`) instead of raising; no
  idempotency keys and no client-supplied ids exist anywhere.
- Pagination inputs `p_page int` (1-based) and `p_page_size int` are validated inside the
  routine: `p_page` 1 to 100000 and `p_page_size` 1 to 100, else `XC422` with the code the
  contract maps to the .NET sentence (`docs/06-http-contract.md` section 3); nothing is
  clamped silently.
- Every write that changes a row with a `version` column increments `version` in the same
  statement and raises `XC409` when `p_expected_version` does not match.
- Inputs are validated inside the routine regardless of who calls it (lengths, formats,
  enum values, ranges), raising `XC422`; the application tier is assumed compromisable.
- No dynamic SQL built from parameters: `EXECUTE` and `format()` with inputs are forbidden;
  the structure test fails on any routine body containing them unless the file is
  allow-listed with a reason.
- Routines make no network calls and use no extensions beyond `pgcrypto` where listed.

Transactions and locks:
- One routine call is one transaction; the Python gateway wraps every call in
  `async with conn.transaction()`. Routines never `COMMIT`.
- Per-account serialization uses `SELECT ... FOR UPDATE` on `identity.users` (replaces the
  .NET in-process `AuthGate`). Per-organization serialization is avoided (the organization
  settings and logo writes, which merge into the organization's own rows, are the one
  exception: `docs/05-routines.md` section 1.5); where ordering is
  needed, sequences and append-only tables are used.
- Multi-step flows that must span two transactions by nature (PIN verification happens in
  Python between two routine calls) are documented in `docs/07-auth.md`.

## 5. Error protocol (SQLSTATE)

Routines signal expected failures with `RAISE EXCEPTION USING ERRCODE = '<code>', MESSAGE =
'<machine_code>', DETAIL = '<json>'`. Classes starting with `X` are reserved for
implementation-defined codes, so `XC` is ours.

| SQLSTATE | Meaning | Python exception | HTTP |
|---|---|---|---|
| `XC401` | session invalid (resolve-session failed) | `SessionInvalid` | 401 |
| `XC403` | actor lacks membership or permission | `Forbidden` | 403 |
| `XC404` | entity not found in the actor's organization | `NotFound` | 404 |
| `XC409` | version mismatch or uniqueness conflict | `Conflict` | 409 |
| `XC422` | domain rule violation (invalid value, illegal state transition) | `RuleViolation` | 400 or 422 per endpoint contract (`docs/06-http-contract.md`) |
| `XC429` | reserved for a cap a routine refuses outright; no routine raises it today (code caps are silent and attempt caps answer `refused`, `docs/07-auth.md` section 1; the rate limiter returns a decision) | `CapExceeded` | 429 |
| `23505` | unique violation not pre-empted by the routine | `Conflict` | 409 |
| `23503`, `23514`, `23502` | FK/check/not-null violation (a bug: the routine should have raised `XC422` first) | `IntegrityBug` | 500, logged at error |
| `40001`, `40P01` | serialization failure, deadlock | retried by the gateway for idempotent calls (three attempts in all), then `TransientFailure` | 503 |
| class `08`, `57P01` | connection lost, admin shutdown | retried by the gateway for idempotent calls, then `TransientFailure` | 503 |

- `MESSAGE` is a stable snake_case code (for example `revenue_version_conflict`,
  `vehicle_registration_taken`, `away_period_overlaps`) that the HTTP layer may surface as
  the `code` field where the contract has one. `DETAIL` is a JSON object with fields the
  client needs (`expected_version`, `actual_version`, `field`). Never put user data that
  would leak across tenants into `DETAIL`.
- Enumeration-sensitive outcomes (auth denial) are returned as outcome rows, not raised, so
  that the transaction commits the attempt accounting and the HTTP answer is uniform.
- The translation table lives in `src/xcode_api/db/errors.py` and nowhere else.

## 6. Column conventions

- Keys: `id uuid PRIMARY KEY DEFAULT gen_random_uuid()`; clients never supply ids, with one
  contract exception: the petty-cash entry create accepts an optional `id` as its replay
  key (`docs/04-schema.md` section 6.2). Revenue replay uses the natural key.
- Timestamps: `timestamptz`, always UTC in and out; business dates: `date`.
- Money: `numeric(14,2)` (every .NET `decimal(18,2)` value in use fits; `docs/04-schema.md`
  section 12); never `float`. Currency is `text` constrained to ISO-4217 where stored.
- Enumerations: `smallint` columns referencing a code table in the same schema
  (`docs/04-schema.md` section 2) whose rows carry the .NET integer and the name; the wire
  value stays the integer the clients already use (one exception: the revenue cell status,
  a string on the wire). No PostgreSQL `ENUM` types; adding a member is a reviewed
  migration that inserts a row.
- Concurrency tokens: `version bigint NOT NULL`, starting at the value the .NET table used
  (0 or 1, listed per table in `docs/04-schema.md`).
- Audit: `created_at timestamptz NOT NULL`, `updated_at timestamptz NOT NULL`, maintained
  by the routine (from `p_now`) so the write path stays visible in one place. The trigger
  `ops.touch_updated_at()` is only a backstop: it sets `now()` when an update left
  `updated_at` unchanged, and never overrides a value the routine set.
- Soft deletes only where the .NET model had them (users `Removed` status, memberships
  `active`); everything else hard-deletes with FK `ON DELETE RESTRICT` unless the schema
  spec says otherwise.
- Names: snake_case, singular column names, plural table names; no `tbl_` prefixes; no
  abbreviations that are not domain words (`psv` is a domain word).

## 7. Migration runner (`xcode-api db ...`)

Files:
- `db/migrations/NNNN_<name>.sql` and `db/migrations/NNNN_<name>.down.sql`; `NNNN` is a
  zero-padded integer, strictly increasing, no gaps required. First line of each file is a
  comment stating its purpose; data backfills end with a verification `DO` block that raises
  when counts are not as expected.
- `db/routines/<NN>_<area>/<name>.sql`: applied in lexical order of the full path, every
  deploy, all in one transaction (types first in `00_types`, helpers in `10_common`).
- `db/roles/*.sql`: not applied by the runner in production (DBAs own roles); applied by
  the compose init locally and by the test harness.

Commands (connect with `XCODE_MIGRATION_DATABASE_URL`, i.e. as `xcode_owner`):
- `db migrate [--to NNNN] [--dry-run]`: takes the session-level `pg_advisory_lock(hashtext('xcode.migrate'))`
  on its single owner connection for the whole run (released at the end, or by the server if the connection drops), computes pending files, applies each pending file in
  its own transaction together with its bookkeeping row `(version, name, checksum, applied_at, applied_by, duration_ms)`
  into `ops.schema_migrations`. Refuses to start when the schemas of `db/roles/020_schemas.sql`
  are missing (the DBA step was skipped), when any applied file's checksum differs
  from the recorded one or when a recorded version has no file. Then runs `db routines`
  when no migration remains pending (`--to` short of the latest defers them: routines are
  written against the complete schema).
  Checksums are SHA-256 over the file bytes with CRLF normalised to LF, so Windows and
  Linux checkouts agree. The runner creates `ops.schema_migrations` and
  `ops.routine_versions` itself with `CREATE TABLE IF NOT EXISTS` before reading them (the
  only DDL that lives in Python); everything else in `ops` is a migration. Every run
  records an `ops.operator_actions` row (`migrate`, `routines`, `down`) with
  `XCODE_OPERATOR`.
- `db routines [--dry-run]`: refused while a migration is pending; otherwise, in one
  transaction, applies every routine file, then sets
  `OWNER TO xcode_api_executor`, `REVOKE EXECUTE ... FROM PUBLIC` and the caller grant by
  name (`api.ops_*` to `xcode_operator`, `api.meta_*` to `xcode_operator` and `xcode_app`,
  every other routine to `xcode_app`) for every function and procedure in schema `api`, upserts `ops.routine_versions
  (path, checksum, applied_at)`, and deletes bookkeeping rows for files that no longer exist
  (the drop of the routine itself must be a versioned migration). An `api` function that no
  file re-created in that transaction (a removed routine, or the old overload of a changed
  signature: `CREATE OR REPLACE` rewrites the catalogue row, an untouched row has no file)
  gets no caller grant, loses any it had, and is reported as an orphan with its signature.
- `db status`: prints applied and pending migrations, routine checksum drift and migration
  checksum drift (run `db verify` for the structural checks). Exit code 0 only when nothing
  is pending and nothing drifts. `--dry-run` on `migrate` and `routines` creates the two
  bookkeeping tables when they are missing and changes nothing else.
- `db verify`: structural assertions, exit code 1 on any failure:
  every schema of section 1 exists; every `api.*` routine is `SECURITY DEFINER`, owned by `xcode_api_executor`, has
  `search_path=pg_catalog, pg_temp` in `proconfig`, and `PUBLIC` has no `EXECUTE`;
  `xcode_app` and `xcode_operator` have no privilege on any table or sequence in any
  schema; `xcode_app` has no `EXECUTE` on any `api.ops_*` routine; every table with an
  `organization_id` column has RLS enabled with the `tenant_isolation` policy; every
  tenant-table index listed in `docs/04-schema.md` exists; `public` schema is empty; and
  the declarations of `src/xcode_api/db/schema_spec.py` hold: every table of
  `docs/04-schema.md` section 1 exists with its primary key and no undeclared table exists,
  the policy is exactly `tenant_isolation` (permissive, `xcode_api_executor`, `ALL`, `USING`
  and `WITH CHECK` on the tenant column), privileges per table equal the "Writes" column for
  the executor and the code tables and catalogue for `xcode_readonly`, every `updated_at` has
  its trigger, tenant foreign keys start with `organization_id`, and every code table equals
  its domain enum.
- `db down NNNN`: applies `NNNN_<name>.down.sql` for the latest applied version only, when
  it equals `NNNN`, and deletes the bookkeeping row. In the same transaction it first drops
  every function the routine files define (their signatures name table row types the down
  file may drop) and clears `ops.routine_versions`; the next `db migrate` applies them again.
  Refused in production unless `--i-know-this-destroys-data` is passed and `XCODE_ENV` is
  explicitly named.

Behaviour rules: the runner never runs at API startup outside `XCODE_ENV=development`
(and there only with `XCODE_AUTO_MIGRATE=true`); it logs every file it applies with its
duration; it is tested in `tests/db/test_migrate.py` (fresh database, idempotent re-run,
checksum drift refused, concurrent runners serialized, down then up).

## 8. Performance conventions

- Every routine's queries are listed with their supporting index in `docs/04-schema.md`;
  a new routine adds its index rows before it is merged.
- `EXPLAIN (ANALYZE, BUFFERS)` output for every list/report routine on the demo seed at
  10x scale is attached to the PR that introduces it (the prompt says how).
- `pg_stat_statements` is enabled in every non-development database; the operability doc
  names the dashboard queries.
- Append-only tables (`tenancy.change_log`) are ordered by a `bigint` identity column, not
  by timestamp, and read with keyset conditions when the contract allows (page/pageSize
  stays for the current contract).

## 9. Zero-trust checks (`db verify` and `tests/db/test_structure.py`)

In addition to the structural assertions in section 7, both check:
- `xcode_app` and `xcode_operator` have no privilege on any table, column or sequence in
  any schema and no schema privilege beyond `USAGE` on `api`, read as effective privileges
  (direct, through `PUBLIC` or through role membership), and `xcode_app` has no `EXECUTE`
  on `api.ops_*`;
- `xcode_readonly` has no privilege on `identity.*` or on any column whose name ends in
  `_hash` or `_digest`;
- no column named `pin`, `code`, `token`, `secret` or `password` exists unless its name ends
  in `_hash` or `_digest` (the `code` key of the code tables is an enumeration integer and is
  exempt by table);
- every `api.*` routine that takes `p_organization_id` calls `tenancy.enter_organization`
  (routine source read from `pg_proc.prosrc`; the check selects routines by that parameter
  name, so the identity-level `api.auth_*`, `api.ops_*`, `api.meta_*` and
  `api.rate_limit_hit` routines, which take none, are outside it; the allow-list
  `TENANT_GUARD_ALLOW_LIST` in `src/xcode_api/db/verify.py` is empty);
- no routine body contains `EXECUTE` or `format(` outside the allow-list;
- audit tables carry no `UPDATE` or `DELETE` grant for `xcode_api_executor`;
- `xcode_app`, `xcode_operator` and `xcode_readonly` have `rolconnlimit` set and
  `rolbypassrls = false`; `xcode_app` and `xcode_operator` carry non-zero
  `statement_timeout`, `lock_timeout` and `idle_in_transaction_session_timeout` role
  settings, with a per-database setting overriding the role-wide one;
- row-level security binds every service role: none of `xcode_api_executor`, `xcode_app`,
  `xcode_operator` and `xcode_readonly` is a superuser, has `BYPASSRLS`, or is (or is a
  member of) the owner of a table under RLS. No table forces its policies, because
  migrations and the two cross-organization helpers run as the owner on purpose; this
  check is what stops a deployment from running the service as the owner;
- installed extensions are within the allow-list;
- every code table (`docs/04-schema.md` section 2) holds exactly the members of the
  matching `domain/` enum, integer and name (the parity test reads both).

The full control matrix with the HTTP-level and process-level checks is
`docs/12-security.md`.
