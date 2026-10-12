# Prompt 01: database foundation

Paste everything below the line into a fresh Claude Code session running Sonnet, started in
the repository root. Requires prompt 00 to be complete.

---

You are adding the PostgreSQL foundation to `apps/api-python`: roles and grants, the
migration runner, the first migration (`ops`), the first routines, the data-layer plumbing
(pool, per-call transaction helper, SQLSTATE translation, statement counter), the real
`OpsRoutines` repository, the PostgreSQL test harness, the structure tests shared with
`db verify`, the gateway tests, and readiness against the database.

## Read first, in this order

1. `CLAUDE.md`; `apps/api-python/README.md`.
2. `docs/00-principles.md`; `docs/01-architecture.md` sections 2, 3, 4, 8;
   `docs/02-stack.md` ADR-4, 5, 6, 11; `docs/03-database.md` (all);
   `docs/08-operability.md` sections 4, 6, 7, 8, 9; `docs/09-testing.md` (all);
   `docs/11-naming.md`; `docs/12-security.md` sections 2.3, 2.5, 4.
3. `db/README.md`, `db/roles/README.md`, `db/migrations/README.md`,
   `db/routines/README.md`, `tests/README.md`, `tests/support/README.md`,
   `docker-compose.yml`, `deploy/README.md`.
4. The code from prompt 00: `settings.py`, `container.py`, `main.py`,
   `application/repositories.py`, `application/ports.py`, `infra/rate_limit.py`,
   `http/routers/health.py`, `tests/support/fakes.py`, `tests/conftest.py`,
   `tests/unit/test_rate_limiter_contract.py`.

## Environment

PostgreSQL 18 must be reachable: `docker compose up -d postgres` (Docker Desktop) or an
existing server in `XCODE_TEST_DATABASE_URL` as a superuser (or a role with CREATEDB and
CREATEROLE). If neither is available, implement everything, run the unit tests, and report
that the database tests could not be executed. Never fake them.

## Deliverables

### D1 Roles and grants (`db/roles/`)

- `010_roles.sql`, idempotent (`DO` blocks checking `pg_roles`): `xcode_owner` LOGIN
  NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS; `xcode_api_executor` NOLOGIN
  NOBYPASSRLS; `xcode_app` LOGIN NOBYPASSRLS with role settings `statement_timeout='5s'`,
  `lock_timeout='2s'`, `idle_in_transaction_session_timeout='10s'` and
  `CONNECTION LIMIT 50` (sized later per `deploy/README.md`); `xcode_operator` LOGIN NOBYPASSRLS with the same role settings as `xcode_app` and
  `CONNECTION LIMIT 5`; `xcode_readonly` LOGIN NOBYPASSRLS `CONNECTION LIMIT 5`;
  `GRANT xcode_api_executor TO xcode_owner`.
- `020_schemas.sql`: `REVOKE ALL ON SCHEMA public FROM PUBLIC`;
  `CREATE SCHEMA IF NOT EXISTS` for `identity`, `tenancy`, `setup`, `revenue`, `ops`, `api`
  with `AUTHORIZATION xcode_owner`; database owner `xcode_owner` where the executing role
  may set it.
- `030_grants.sql`: `GRANT CONNECT` to the four login roles; `GRANT USAGE ON SCHEMA api TO xcode_app,
  xcode_operator`; `USAGE` on every schema to `xcode_api_executor`; default privileges for role
  `xcode_owner` in every schema: `REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC`; no default `EXECUTE` grant in `api` (the routine runner grants each routine to its caller,
  D3); in the data schemas: `GRANT SELECT, INSERT,
  UPDATE, DELETE ON TABLES` and `USAGE ON SEQUENCES` to `xcode_api_executor` (audit tables
  revoke `UPDATE, DELETE` explicitly in their migrations); nothing for `xcode_readonly`.
- `900_local_dev.sql`: development passwords equal to the role names (as `.env.example`);
  the header says it is applied only by the compose init and the test harness.
- Evidence: role and grant assertions in `tests/db/test_structure.py` (D6).

### D2 Migration runner (`db/migrate.py` and the `db` CLI commands)

- Behaviour exactly as `docs/03-database.md` section 7: a single connection as
  `xcode_owner`; session-level `pg_advisory_lock(hashtext('xcode.migrate'))` for the whole
  run, released at the end; the runner creates `ops.schema_migrations` and
  `ops.routine_versions` with `CREATE TABLE IF NOT EXISTS` before reading them (the only
  DDL in Python); checksums are SHA-256 over file bytes with CRLF normalised to LF; each
  migration file is applied in its own transaction together with its bookkeeping row;
  `db routines` runs in one transaction: apply files in lexical path order, then for every
  function and procedure in schema `api`: `ALTER ... OWNER TO xcode_api_executor`,
  `REVOKE ALL ON FUNCTION ... FROM PUBLIC`, then `GRANT EXECUTE` to the caller chosen by
  name (`api.ops_*` to `xcode_operator`, `api.meta_*` to `xcode_operator` and `xcode_app`,
  every other routine to `xcode_app`); upsert
  `ops.routine_versions`; delete bookkeeping rows for files that no longer exist; warn for
  routines present in the database without a file. `db migrate` runs `db routines` after
  the migrations. `db status`, `db verify`, `db down NNNN` per the document. Every run
  inserts an `ops.operator_actions` row (`migrate`, `routines`, `down`) with
  `XCODE_OPERATOR`. Each applied file is logged with its duration.
- CLI: `xcode-api db migrate [--to NNNN] [--dry-run]`, `db routines [--dry-run]`,
  `db status`, `db verify`, `db down NNNN [--i-know-this-destroys-data]`, all using
  `XCODE_MIGRATION_DATABASE_URL`. Settings gain `XCODE_DATABASE_OPERATOR_URL` (role
  `xcode_operator`, optional, used only by the CLI's user and seed commands of prompts
  03 and 08; `settings-check` reports it as unset without failing).
- Evidence: `tests/db/test_migrate.py`: fresh apply; idempotent re-run (nothing pending,
  exit 0); an edited applied file is refused with its name in the message; a recorded
  version without a file is refused; two runners started concurrently serialise (the second
  waits, then finds nothing pending); `down` then `up`; ownership and grants are fixed up
  even when a routine file omitted them; CRLF and LF copies of a file produce the same
  checksum; `--dry-run` changes nothing.

### D3 First migration and routines

- `db/migrations/0001_ops.sql` and `0001_ops.down.sql`: `ops.operator_actions`
  (`id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY`, `operator text NOT NULL CHECK
  (char_length(operator) BETWEEN 1 AND 128)`, `action text NOT NULL`, `target text`,
  `detail jsonb NOT NULL DEFAULT '{}'`, `recorded_at timestamptz NOT NULL`, index on
  `recorded_at`; `REVOKE UPDATE, DELETE ... FROM xcode_api_executor`);
  `ops.rate_limit_windows` UNLOGGED (`key text`, `window_start timestamptz`,
  `count integer NOT NULL`, primary key `(key, window_start)`).
- Routines, each in its own file, following `docs/03-database.md` section 4 (header
  comment with purpose, parameters and errors; `SECURITY DEFINER`; `SET search_path =
  pg_catalog, pg_temp`; schema-qualified names):
  - `db/routines/10_common/meta_contract_version.sql`: `api.meta_contract_version()
    RETURNS integer`, returns 1. `src/xcode_api/db/contract.py` holds
    `EXPECTED_CONTRACT_VERSION = 1`; the two change together whenever a routine signature
    changes.
  - `db/routines/10_common/record_operator_action.sql`: `ops.record_operator_action(
    p_operator text, p_action text, p_target text, p_detail jsonb, p_now timestamptz)`,
    `SECURITY INVOKER`, `EXECUTE` granted to `xcode_api_executor`, used by every `api.ops_*`
    routine.
  - `db/routines/60_ops/rate_limit_hit.sql`: `api.rate_limit_hit(p_key text,
    p_limit integer, p_window_seconds integer, p_now timestamptz) RETURNS TABLE (allowed
    boolean, remaining integer, retry_after_seconds integer)`: window start floored to the
    window, `INSERT ... ON CONFLICT DO UPDATE SET count = count + 1 RETURNING count`,
    delete windows older than two windows for that key, return the decision; validates
    `p_limit >= 1`, `p_window_seconds >= 1`, `char_length(p_key) <= 256` with `XC422`.
  - `db/routines/60_ops/ops_record_operator_action.sql`: `api.ops_record_operator_action(
    p_operator text, p_action text, p_target text, p_detail jsonb, p_now timestamptz)` for
    CLI commands that have no other routine to call.
- Evidence: `tests/db/test_ops_routines.py` as `xcode_app` for `api.rate_limit_hit` and
  `api.meta_contract_version`, as `xcode_operator` for `api.ops_record_operator_action`,
  plus the negative case that `xcode_app` calling an `api.ops_*` routine gets SQLSTATE
  `42501`: rate-limit decisions across
  window boundaries driven by `p_now`; two connections hitting the same key sum correctly;
  operator-action rows; contract version; `XC422` cases. `tests/db/test_structure.py`
  generic routine assertions cover them.

### D4 Data layer (`db/`)

- `db/pool.py`: `open_pool(settings) -> AsyncConnectionPool` (min and max from settings,
  `application_name='xcode-api'` through connection kwargs, `configure` hook `SET TIME
  ZONE 'UTC'`, a one-time `SELECT current_user` at open that logs a warning when the role
  is not `xcode_app`); `check_connection(pool, timeout_seconds)` runs `SELECT 1`. These are
  the only raw statements allowed in Python besides the runner and `db/verify.py`.
- `db/session.py`: `call(pool, routine, *args, row=<dataclass>, idempotent=False)`:
  acquire a connection, `async with conn.transaction()`, execute `SELECT * FROM
  api.<routine>(%s, ...)` with server-side binding, adapt rows through `db/types.py`;
  increment the statement counter (a `contextvars` counter) per routine call; retry
  idempotent calls on `40001`, `40P01`, class `08` and `57P01` up to 3 times with jittered
  backoff (50 ms base); translate SQLSTATE through `db/errors.py`; log `db.routine` at
  DEBUG with routine name and duration, never arguments.
- `db/errors.py`: the table in `docs/03-database.md` section 5, mapping `MESSAGE` to
  `code` and `DETAIL` JSON to `detail` on the raised exception.
- `db/types.py`: map `RETURNS TABLE` rows and composite values into frozen dataclasses by
  field name; an unknown or missing column raises `IntegrityBug` (drift between a routine
  and a record is a bug, never a silent `None`).
- `db/routines/ops.py`: `OpsRoutines(pool)` implementing `OpsRepository` (`ping` through
  `check_connection`; the other methods through routines).
- `container.py`: `build_container(settings, pool, ...)` builds `OpsRoutines` by default.
  `main.py` lifespan: open the pool, `check_connection`, role check, development-only
  auto-migrate, contract-version check (log one clear line and exit 1 on mismatch),
  readiness true only after that; on shutdown drain mail, then close the pool.
- Evidence: `tests/db/test_gateway.py`: one transaction per call (a routine that raises
  leaves no row); retries only when idempotent and only on the listed SQLSTATEs (install a
  test routine as owner that raises a chosen SQLSTATE for its first N calls); translation
  of every SQLSTATE row to its exception with `code` and `detail`; statement counter
  increments; the DEBUG log line has no arguments. `tests/api/test_operability.py`:
  `/health/ready` 200 against the database and 503 without error text when the pool points
  at a closed port; startup refusal on contract-version mismatch (run the lifespan with a
  patched `EXPECTED_CONTRACT_VERSION`).

### D5 Test harness (`tests/conftest.py`, `tests/support/database.py`)

- Session fixture: connect with `XCODE_TEST_DATABASE_URL` or start `testcontainers`
  `postgres:18`; apply `db/roles/*.sql` (idempotent); recreate `xcode_template`; run the
  runner (`migrate` then `routines`) into it as `xcode_owner`; set `datallowconn = false`.
- Per-test fixture `database`: `CREATE DATABASE test_<worker>_<n> TEMPLATE xcode_template`;
  yields `app_url` (as `xcode_app`) and `owner_url`; drops the database afterwards; names
  are safe under pytest-xdist.
- Fixtures: `settings` (`Settings.for_tests(database_url=app_url,
  migration_database_url=owner_url)`), `pool`, `container` (real `OpsRoutines`,
  `ManualClock`, `MailSpy`, `MemoryRateLimiter`), `app`, `client` (httpx ASGI transport with
  the lifespan run), `statement_counter`, `owner_conn`, `app_conn`, `competing_writer`.
- `tests/support/clock.py` `ManualClock(start)` with `advance(seconds)`;
  `tests/support/mail.py` `MailSpy` implementing `Mailer`; `tests/support/fakes.py`
  `FakeOpsRepository` kept in step with `OpsRoutines`.
- Evidence: `tests/db` and `tests/api` use only these fixtures; `pytest -n 4` passes with
  parallel workers; a test that leaves rows behind cannot affect another.

### D6 Structure tests and `db verify` share one module

- `db/verify.py` holds the assertion queries; `tests/db/test_structure.py` (as owner) and
  `xcode-api db verify` both run them: every generic item of `docs/03-database.md`
  sections 2, 3, 7 and 9 (roles and settings; default privileges; `xcode_app` has zero
  table and sequence privileges; `api.*` routine properties; `public` empty; RLS and the
  `tenant_isolation` policy on every table with `organization_id`, a query that today
  matches no table; secret column-name rule; `EXECUTE` and `format(` scan with an
  allow-list; audit-table grants; extension allow-list; `rolconnlimit` and `rolbypassrls`).
  `db verify` prints one line per check and exits 1 on any failure.
- Evidence: the suite, plus negative tests that create a violating object in a test
  database as owner (a table with `organization_id` and no policy; a `SECURITY INVOKER`
  function in `api`; a column named `token`) and assert `verify` reports each one.

### D7 PostgreSQL rate limiter

- `PostgresRateLimiter` wired when `XCODE_RATE_LIMIT_BACKEND=postgres`; the readiness log
  line names the backend.
- Evidence: `tests/db/test_rate_limit_postgres.py` imports the case list from
  `tests/unit/test_rate_limiter_contract.py` and runs it against the real adapter.

### D8 Documentation touch-ups

- `db/migrations/README.md` records 0001; `docs/05-routines.md` gains entries for
  `api.meta_contract_version`, `api.rate_limit_hit`, `api.ops_record_operator_action`
  and `ops.record_operator_action` in that document's entry format; CI job `db-verify`
  now runs `xcode-api db migrate && xcode-api db status && xcode-api db verify` against the
  service container. Any deviation from `docs/03-database.md` is a change to the document,
  stated in the report.

## Invariants at the end

- `xcode_app` and `xcode_operator` have no privilege on any table or sequence, and
  `xcode_app` cannot execute `api.ops_*` (`db verify`).
- Every `api.*` routine: `SECURITY DEFINER`, owner `xcode_api_executor`, `search_path` set,
  no `PUBLIC` execute.
- One routine call is one transaction; retries only for idempotent calls.
- No SQL in Python outside `db/session.py` (the call template), `db/pool.py` (the two
  allowed statements), `db/migrate.py` and `db/verify.py`.
- The runner never runs at application startup unless `XCODE_ENV=development` and
  `XCODE_AUTO_MIGRATE=true`.
- Lint, types and all tests green; after `db migrate` on a fresh database, `db status`
  exits 0 and a second `db migrate` applies nothing.

## Verify (paste the outputs into the report)

```
cd apps/api-python
docker compose up -d postgres
ruff check . && ruff format --check . && mypy
pytest -n auto -q
xcode-api db migrate && xcode-api db status && xcode-api db verify ; echo "exit=$?"
xcode-api db migrate                                  # second run: nothing pending
xcode-api serve & sleep 3; curl -s localhost:5000/health/ready; kill %1
```

## Report format

1. Checklist: one row per deliverable D1 to D8 and per bullet: done or not, `file:symbol`,
   test name.
2. Verify outputs, trimmed, including the full `db verify` output.
3. Deviations from the documents with reasons; documents changed.
4. Items left for later prompts.

## House rules

- Shared tree: `git status` first; edit only under `apps/api-python/` and the CI workflow
  file; never revert or reformat others' changes; never kill processes you did not start;
  never bare `git stash`.
- No commits unless the user asks. No AI attribution anywhere.
- No comments unless needed; routine files carry the header comment the conventions
  require and nothing decorative; no plan or prompt identifiers anywhere.
- Never weaken a test to make it pass. If a document is wrong, fix the document and report
  it.
