# Verify: `area:prompt 01` (PostgreSQL foundation), mode `fix`, depth `standard`

Date 2026-10-11, 15:24 to about 16:40 local time. Written by a session that did not write
prompt 01. Method: `docs/14-verification.md`, all five modes.

## 1. Verdict

**fail** (procedural): the full suite was not run in this session. Every finding that survived is fixed or recorded, and no blocker was found. The machine was at 100% CPU with three other sessions running suites, and the user asked for resources to be freed, so the run is left for the next session (section 8, "Resume").

- Claims (41): holds 27, fails 7 (all 7 fixed or the document corrected), unproven 5,
  not checked 2.
- Surviving findings: 0 blockers, 5 majors (all fixed with a test that fails without the
  fix), 9 minors (2 fixed in documents, 2 open questions, 5 recorded below), 5 notes.

## 2. Thesis and claims

Thesis, at full strength: prompt 01 delivers D1 to D8. Roles and grants make `xcode_app`
and `xcode_operator` unable to touch data except through `api.*` routines. The runner
applies forward-only, checksummed migrations under an advisory lock and leaves every
`api.*` routine `SECURITY DEFINER`, owned by the executor and granted only to its caller.
The gateway runs one routine call per transaction, retries only idempotent calls and
translates SQLSTATEs through one table. The harness tests the current files on a fresh
template. `db verify` and the structure tests share one module and catch each violation
they name. The four first routines behave as documented. Behaviour that .NET also has
(health routes) is the same.

| # | Claim (where stated) | Carried by | Verdict | Grade |
|---|---|---|---|---|
| C1 | 010 creates the five roles idempotently with their attributes (prompt D1) | `db/roles/010_roles.sql`; harness applies it every build; `check_row_security_binds_the_service_roles` + negative test | holds | A |
| C2 | `xcode_app`/`xcode_operator` timeouts are role settings, verified by `db verify` (prompt D1, docs/03 s2) | `010_roles.sql:24-32`; no check read them | fails -> fixed (V-D6-2) | A |
| C3 | 020 schemas owned by `xcode_owner`, `public` closed (D1) | `020_schemas.sql`; `test_verify_reports_a_missing_schema` | holds | A |
| C4 | 030: CONNECT, USAGE on `api` only for app/operator, executor DML (D1) | `030_grants.sql`; `check_declared_privileges` + negative tests; new schema check | holds | A |
| C5 | Default privileges revoke EXECUTE from PUBLIC, "verified by `db verify`" (docs/03 s2) | no check reads `pg_default_acl` | fails as worded -> doc corrected (V-D11-3) | D |
| C6 | 900 sets development passwords only (D1) | `900_local_dev.sql` header; every run logs in with them | holds | B |
| C7 | Two runners serialise on the advisory lock (D2) | `migrate.py:31,481`; old test passed with a no-op lock | fails -> fixed (V-D10-1) | A |
| C8 | The bookkeeping `CREATE TABLE IF NOT EXISTS` is the only DDL in Python besides the down drop (D2) | `migrate.py:34-51,294-320` | holds | B |
| C9 | SHA-256 checksums with CRLF normalised (D2) | `checksum_bytes`; `test_crlf_and_lf_produce_the_same_checksum` | holds | A |
| C10 | Each migration and its bookkeeping row commit together (D2) | `_apply_migration`; no test of a failing file | unproven | B |
| C11 | `db routines`: one transaction, owner, revoke PUBLIC, caller by name (D2) | `routines`, `_fix_api_routine_grants`; `test_routine_ownership_and_grants_are_fixed_up`, `..._rerun_fixes_grants...` | holds | A |
| C12 | Bookkeeping rows of deleted files are removed (D2) | `_delete_missing_routine_rows`; no test | unproven | F |
| C13 | Routines without a file are reported (D2, docs/03 s7) | was by name only, and stale overloads kept EXECUTE | fails -> fixed (V-D6-3) | A |
| C14 | `migrate` runs routines; `--to` short of latest defers them (D2) | `test_routines_wait_until_no_migration_is_pending` | holds | A |
| C15 | Edited applied file, recorded version without file, missing schemas refused (D2) | three named tests in `test_migrate.py` | holds | A |
| C16 | `down` reverses the latest only and the next `migrate` restores routines (D2) | `test_down_then_up`, `test_every_migration_reverses_and_reapplies` | holds | A |
| C17 | `down` refused outside development/testing without the flag (D2) | `migrate.py:229-233`; no test found | not checked (budget) | - |
| C18 | Every runner run writes `ops.operator_actions` (D2) | `_record_action`; no assertion (V-D8-1) | unproven | F |
| C19 | `--dry-run` changes nothing (D2 evidence) | creates the bookkeeping tables on a fresh database | fails -> doc corrected (V-D6-5) | A |
| C20 | CLI `db status|routines|verify` with `XCODE_MIGRATION_DATABASE_URL` (D2) | run in section 8 | holds | B |
| C21 | 0001: tables, index, append-only by privilege, UNLOGGED windows (D3) | declared-table, index, privilege and audit checks + negative tests | holds | A |
| C22 | The four routines follow the routine conventions (D3) | `check_api_routine_properties` + invoker negative test | holds | A |
| C23 | `api.meta_contract_version()` equals `EXPECTED_CONTRACT_VERSION`; startup refuses a mismatch (D3, D4) | `test_contract_version_is_one_as_app`, `test_startup_refuses_a_contract_version_mismatch` | holds | A |
| C24 | `api.rate_limit_hit`: floored window, atomic upsert, two connections sum, XC422 bounds (D3) | four tests in `test_ops_routines.py`, contract cases | holds (growth: V-D3-1) | A |
| C25 | `api.ops_record_operator_action` for the operator; app gets 42501 (D3) | `test_operator_records_an_action`, `test_app_cannot_execute_an_ops_routine` | holds | A |
| C26 | Pool pins UTC, sets `application_name`, warns on another role (D4) | `pool.py:58-109`; no test | unproven | F |
| C27 | One routine call is one transaction (D4) | `test_one_transaction_per_call_rolls_back_on_raise` | holds | A |
| C28 | Retries only idempotent calls on the listed SQLSTATEs (D4) | three gateway tests | holds (count wording: V-D3-2) | A |
| C29 | SQLSTATE table translated in one place (D4, docs/03 s5) | `errors.py`; parametrised test | holds (timeouts: V-D8-2) | A |
| C30 | Row adapter raises `IntegrityBug` on drift (D4) | `types.py:41-59` | not checked (budget) | - |
| C31 | The DEBUG line carries no arguments (D4) | `test_debug_log_carries_no_arguments` | holds | A |
| C32 | Lifespan: pool, ping, role check, contract check, ready, drain then close (D4) | `main.py`; readiness 200/503 tests | holds | B |
| C33 | The harness recreates `xcode_template` for the session (D5) | reused any frozen template | fails -> fixed (V-D6-4) | A |
| C34 | One database per test, xdist-safe; fixtures as listed (D5) | runs with `-n 3`; `conftest.py` | holds | A |
| C35 | `db verify` and the structure tests share `db/verify.py`; negative tests for the three named objects (D6) | `test_structure.py` | holds | A |
| C36 | `xcode_app`/`xcode_operator` hold no table or sequence privilege (invariant, D6, docs/03 s9) | missed column and schema grants | fails -> fixed (V-D6-1) | A |
| C37 | `PostgresRateLimiter` wired by the setting, passes the contract cases (D7) | `container.py:334`; `test_rate_limit_postgres.py` | holds | A |
| C38 | CI `db-verify` job runs migrate, status, verify (D8) | workflow untracked, never ran | unproven | F |
| I1 | No SQL in Python outside `db/` (invariant) | grep: psycopg outside `db/` only for types | holds | A |
| I2 | Runner at startup only in development with auto-migrate (invariant) | `main.py` guard; `test_settings.py` | holds | B |
| I3 | Lint, types and tests green; a second migrate applies nothing (invariant) | section 8; `test_second_migrate_applies_nothing` | holds | A |

## 3. Findings

| id | mode | claim attacked | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| V-D6-1 | red team (hurried DBA) | C36, docs/03 s2 "no data-schema privilege", s9 | `GRANT USAGE ON SCHEMA identity TO xcode_app; GRANT SELECT (pin_hash) ON identity.users TO xcode_app` -> expected a `db verify` failure, actual: all checks ok (the app role reads PIN hashes) | the old check read `information_schema.role_table_grants` (table-level only); no check read schema privileges | `check_declared_privileges` reads `relacl` and does catch table grants to the app or PUBLIC; membership in the executor surfaces through the ops-EXECUTE check. Column grants and schema USAGE survived | survives, major | fixed: effective privileges (`has_schema_privilege`, `has_table_privilege`, `has_any_column_privilege`/`has_column_privilege`, `has_sequence_privilege`) in `check_app_role_has_no_table_privileges`; tests `test_verify_reports_a_column_grant_to_the_app_role`, `test_verify_reports_data_schema_usage_for_the_operator` |
| V-D6-2 | falsification | C2 | `ALTER ROLE xcode_app IN DATABASE xcode SET statement_timeout = 0` (or a hand-made role on cPanel without the settings) -> `db verify` passes; one stuck statement holds a pool connection without bound | no test or check read `pg_db_role_setting` (grep `statement_timeout` in `tests/`, `verify.py`: none) | looked for a role-settings check in all 21 checks and in tests: none | survives, major | fixed: `check_role_attributes` reads the effective settings (role-wide, overridden per database); test `test_verify_reports_a_service_role_without_its_timeouts` |
| V-D6-3 | pre-mortem | C13, D6 probe "no stale overload ... with wider grants" | change `api.x(uuid, text)` to `api.x(uuid, text, int)`: the old overload stays, and `_fix_api_routine_grants` re-granted EXECUTE to `xcode_app` on every `api` function; the orphan warning compared names only, so it stayed silent | `migrate.py` (before: grant loop over all `api` functions; `_warn_orphan_routines` by file stem); gap recorded only in a memory note, in no document | `db verify` checks properties, not provenance; docs/03 s7 said the runner "only reports" | survives, major | fixed: a function whose catalogue row this transaction did not write (`p.xmin = pg_current_xact_id()::xid`) gets no caller grant, loses any it had, and is logged as `db.routines.orphan` with its signature; test `test_routines_leave_a_stale_overload_without_a_caller`; docs/03 s7 corrected |
| V-D10-1 | falsification | C7 | the old `test_concurrent_runners_serialize` started the second runner only after the first had migrated and asserted `waited >= 0` | with `ADVISORY_LOCK_SQL = "SELECT 1"` the old test still passes (the second finds nothing pending either way) | read for another serialisation test: none | survives, major | fixed: the second runner is observed waiting on the advisory lock in `pg_locks` while the first holds it; the mutant now fails ("the second runner did not wait") |
| V-D6-4 | pre-mortem (it happened) | C33, D6 template probe, earlier V-D6-1 of the docs audit | change a routine, run a test: any frozen `xcode_template` was reused, so the run tested the old routines with no signal; the manual remedy (drop it) disrupts other sessions' runs | `tests/support/database.py` `_template_is_ready` (old: `datallowconn = false` only) | the guard was a manual step in docs/09 s5 (grade D) | survives, major | fixed: the template comment carries a SHA-256 fingerprint of `db/roles`, `db/migrations`, `db/routines` and the runner; a stale template is rebuilt; every session holds `xcode.test.template.use:<template>` shared and a rebuild needs it exclusively, else the session fails with a message; `XCODE_TEST_TEMPLATE` gives a session its own template; tests in `tests/db/test_template.py`; docs/09, docs/14, verify.md updated |
| V-D3-1 | red team (outsider) | C24 | with `XCODE_RATE_LIMIT_BACKEND=postgres`, each distinct `auth:<address>` leaves one row for good (the routine deletes old windows of its own key only); rotating IPv6 addresses grow `ops.rate_limit_windows` without bound | `rate_limit_hit.sql:48-50` | backend defaults to `memory`; the in-memory limiter evicts globally | survives, minor | open question 56 |
| V-D3-2 | falsification | C28 (prompt D4 "retry up to 3 times") | `MAX_ATTEMPTS = 3` is three attempts, two retries | `session.py:144,191` | three attempts is the usual reading; nothing depends on the fourth | survives, minor | doc corrected (docs/03 s5 "three attempts in all") |
| V-D8-1 | falsification | C18 | no test asserts the `operator_actions` row the runner writes per run | `test_migrate.py` mentions the table once (existence after down) | read all runner tests | survives, minor | residual risk: add the row to docs/12 s7 when free (that file was edited by another session at 15:46); a one-assert test belongs to the next runner change |
| V-D8-2 | pre-mortem | C29 | a 2 s `lock_timeout` (55P03) or 5 s `statement_timeout` (57014) under a capture burst is translated as "unexpected database error": 500, logged at error | `errors.py:86`; docs/03 s5 table silent | .NET answers its command timeout with 500 too (parity) | survives, minor | open question 57 |
| V-D6-5 | falsification | C19 | `migrate --dry-run` on a fresh database creates the two bookkeeping tables | `migrate.py:166,268` | benign, documented DDL | survives, minor | doc corrected (docs/03 s7) |
| V-D6-6 | falsification | D6 probe "each check fails on a database built to break it" | "roles exist", "public schema is empty" and "xcode_app cannot execute api.ops_*" have no negative test | `test_structure.py`, `test_schema_structure.py` | the other 18 checks have negative tests | survives, minor | recorded here for the next runner or verify change |
| V-D11-1 | falsification | docs/12 row "The app role cannot touch data" | it names the old `role_table_grants` query as the test | `docs/12-security.md:61` | - | survives, minor | pending edit: name `check_app_role_has_no_table_privileges` and the two new tests (file edited by another session at 15:46, so not changed here) |
| V-D11-2 | falsification | docs/03 s7 `db status` "and the verify summary" | `_print_status` prints no verify summary | `cli/commands/db.py:104-113` | - | survives, minor | doc corrected |
| V-D11-3 | falsification | C5 | docs/03 s2 said the grant hygiene is "verified by `db verify`"; nothing reads `pg_default_acl` | `verify.py` | the outcome in `api` is checked; helpers in data schemas are unreachable without schema USAGE (now checked) | survives, minor | doc corrected |

Notes (no failure scenario today):
- N1: `MemoryRateLimiter._evict` uses the calling key's window as the cutoff for every
  key; with a second limit of a longer window, short-window hits would reset it. One window
  is in use (60 s), so latent. Prompt-00 code; the prompt-00 audit did not list it.
- N2: `xcode_api_executor` keeps `CREATE` on `api` permanently although only
  `ALTER ... OWNER` needs it; the runner could grant and revoke it around the fix-up.
- N3: between a worker's release of the build lock and its shared use lock there is a
  window of microseconds in which a session with other files could rebuild.
- N4: a contract-version mismatch makes uvicorn exit 3, the prompt says 1; not checked.
- N5: `db/routines/60_ops/meta_unassigned_user_count.sql` (prompt 03) was outside scope.

## 4. Per domain

- **D1 tenancy and authorization** (as prompt 01 touches it: grants, RLS checks):
  privilege probe fails -> fixed (V-D6-1); RLS policy check holds (A, negative tests);
  owner-owned definers: `identity.active_organization` and `tenancy.organization_ids` set
  `search_path` (sweep), the rest is prompt 03; scoped viewers, `{id}` routes,
  anti-escalation, catalogue parity: n/a (no such routes in scope).
- **D2 identity**: n/a except the rate limit; the auth limiter is charged once per request
  (prompt 00, not re-checked here). Hardest attacks tried on the limiter: two connections on
  one key (sum correct, A); window edge with `p_now` on the boundary (floor correct, A);
  NULL limit (refused only by the Python caller: noted, not reachable from a request).
- **D3 data integrity**: retries idempotent-only holds (A); one call one transaction holds
  (A); append-only operator actions hold (A, privilege); runner serialisation was unproven
  -> fixed (V-D10-1); per-file atomicity unproven (C10).
- **D4 contract parity**: routes in scope are `/health/live`, `/health/ready`, `/health`;
  .NET `Program.cs:179-181` maps the same three, readiness tagged and timed out at 10 s;
  bodies `Healthy`/`Unhealthy` text/plain and `{"status":"ok"}` match. Drift: 27 uncommitted
  .NET files (setup, petty cash, reports, recurring pause), none in health, ops or rate
  limiting; drift register rows 1-12 cover them. Hardest attacks: readiness leaking error
  text (503 body is `Unhealthy`, A); legacy `/health` shape (A); 405 on `POST /health/ready`
  (framework empty body, prompt 00).
- **D5 domain rules and time**: sweep of `now()`, `current_date`, `clock_timestamp(`,
  `random(` in `db/routines`: no hit. `rate_limit_hit` takes `p_now`. Hardest attacks:
  a session time zone other than UTC (window from epoch, zone-free); `p_now` with
  microseconds (floor); retry-after at the last second of a window (ceil, A).
- **D6 database craft**: `db verify` exit 0 on the CLI database with 21 checks; privilege
  and timeout checks were blind -> fixed; stale overloads -> fixed; template -> fixed;
  dynamic SQL sweep: the only `EXECUTE` words are `GRANT EXECUTE` lines, no `format(`
  outside `030_grants.sql`'s DO blocks (roles files, not routines); version features newer
  than 16: none found in scope (`pg_current_xact_id()::xid` is 13+); three checks without a
  negative test (V-D6-6).
- **D7 performance**: one `INSERT ... ON CONFLICT` and one keyed `DELETE` per hit on the
  primary key; the gateway counts one statement per routine call (failed calls are not
  counted; budget tests count successes only). Thread and connection budgets: prompt 00/09.
- **D8 operability**: log sweep (keyword arguments named phone, email, pin, code, token,
  body, password, secret): one hit, `http/errors.py:112` `code=exc.code`, a refusal code,
  not a secret. `XCODE_*` sweep: every setting is in `.env.example`; docs/08 abbreviates
  `POOL_MIN`/`_MAX` and `EMAIL_HOST/PORT/...` (conceded); `test_settings.py` does not name
  `XCODE_EMAIL_PORT/USERNAME/PASSWORD` (minor, prompt 00 area). Timeouts mapping: V-D8-2.
- **D9 hosting and supply chain**: CI image `postgres:18` in `.github/workflows/xcode-api.yml`,
  file untracked, never ran (C38); the local cluster is 16.15. Role creation on cPanel is
  open question 39 onwards; V-D6-2 makes a hand-made role without timeouts visible.
- **D10 tests as evidence**: sweep of `skip`, `xfail`, `importorskip`, `sleep(`, bare
  `except` in `tests/`: the superuser skips in `test_structure.py` (2, environmental), the
  no-database skip and the testcontainers `except Exception` in the harness, `skipif`
  for the shared package in `test_permission_keys.py`, and short `asyncio.sleep` yields in
  mail, PIN-pool and client tests (scheduling, not timing assertions). Wrong
  implementations tried against the tests: a no-op advisory lock (old test passed, now
  fails); a runner that grants every `api` function (now fails); a verify without the
  timeout loop (now fails); a check that reads only table-level grants (now fails).
- **D11 documents**: docs/03 s2, s5, s7, s9, docs/09 s2 and s5, docs/14 D6, verify.md
  corrected; docs/12 row 61 pending (V-D11-1); docs/05 entries for the four routines exist
  and match their signatures.

## 5. Per mode

**Assumptions** (assumption, where stated, enforced by):
1. "the app role has no data privilege" (docs/03 s2) -> was `role_table_grants` + `relacl`;
   now effective privileges (`verify.py` `check_app_role_has_no_table_privileges`).
2. "timeouts hold under any pooler" (docs/03 s2) -> role settings in 010; enforced by
   nothing until V-D6-2.
3. "a frozen template is current" (harness) -> nothing until V-D6-4.
4. "a routine without a file is only reported" (docs/03 s7) -> it was also granted;
   V-D6-3.
5. "CREATE OR REPLACE rewrites the catalogue row" (the new orphan test relies on it) ->
   PostgreSQL behaviour, proven by the test passing on 16.
6. "the clock is the caller's `p_now`" (rate limit) -> routine signature; Python passes
   `Clock.now()`.

**Falsification**: the claims table in section 2 (falsifier per claim: the input in each
finding row; results and grades in the table).

**Pre-mortem** (likelihood x impact, early sign, mitigation):
1. Three months after cutover, a DBA fixing a report grants `identity` usage and two columns
   to `xcode_app`; nobody notices, and a leaked app credential later reads PIN hashes.
   Early sign: none before V-D6-1. Mitigation: fixed.
2. A routine signature changes; the old overload keeps its grant and a caller with an
   ambiguous argument list reaches the old body without the new rule. Early sign: none.
   Fixed (V-D6-3).
3. The cPanel role is created by hand without timeouts; one blocked statement pins a
   connection per request until the pool is exhausted. Fixed in `db verify` (V-D6-2).
4. A session tests changed routines against a stale template and reports green. It happened
   on 2026-10-11 (docs audit V-D6-1). Fixed (V-D6-4).
5. The postgres limiter's table grows under address rotation. Open question 56.
Inversion: what guarantees failure? An unchecked grant path, a reused template and a
runner that re-grants everything. All three existed at the start of this run; none remains.

**Red team**:
1. Hurried DBA: column grant plus schema USAGE -> was invisible (V-D6-1), now caught.
2. Hurried DBA: per-database `statement_timeout = 0` -> was invisible, now caught.
3. Operator: `api.ops_record_operator_action` as `xcode_app` -> 42501 (A, holds).
4. Outsider: address rotation against the postgres limiter -> unbounded rows (V-D3-1).
5. Compromised neighbour: reads `900_local_dev.sql` passwords -> development only; the
   production passwords are out of band (docs/03 s2); not verifiable on the host yet (q39+).

**Dialectic**:
| Decision | Strongest counter | Verdict | Confidence |
|---|---|---|---|
| One template name with a fingerprint and a shared use lock (this run) | one template per content hash never blocks anybody (the docs audit's proposal) | keep the single name: 14 documents name it, and the lock makes the refusal explicit; `XCODE_TEST_TEMPLATE` covers isolation | medium |
| Orphan routines lose grants instead of being dropped | drop them: files are the source of truth | keep: a drop belongs in a reviewed migration (docs/03 s7) | high |
| No `FORCE ROW LEVEL SECURITY` | force it so the owner is bound too | keep (migrations and the two definers rely on owner exemption); the service-role check guards deployments | high |
| Timeouts as role settings, checked non-zero, not equal to 5 s/2 s/10 s | pin the exact values | keep: values are sized per environment; zero or missing is the failure | medium |
| Timeouts surface as 500 | 503 tells clients to retry | open question 57 | medium |

## 6. Conceded

- `db status` exits 0 despite drift: my first measurement read `tail`'s exit code; the
  code returns 1 when anything is pending or drifts (`cli/commands/db.py:113`).
- PUBLIC or direct table grants to `xcode_app`: caught by `check_declared_privileges`.
- `xcode_app` as a member of `xcode_api_executor`: caught by the ops-EXECUTE check (the
  executor owns every `api.ops_*`).
- `SECURITY DEFINER` without `search_path` in two helper files: the grep counted the header
  comment; both set it.
- Rate-limit decisions under concurrency: `ON CONFLICT DO UPDATE` serialises per row;
  `test_two_connections_share_the_same_window` (A).
- `.NET` health parity: same three routes and bodies.

## 7. Fixes

| Finding | Files changed | Test that failed before and passes now |
|---|---|---|
| V-D6-1 | `src/xcode_api/db/verify.py` | `tests/db/test_structure.py::test_verify_reports_a_column_grant_to_the_app_role`, `::test_verify_reports_data_schema_usage_for_the_operator` (both "assert not True" before) |
| V-D6-2 | `src/xcode_api/db/verify.py` (check renamed "role attributes (connlimit, timeouts, not bypassrls)") | `tests/db/test_structure.py::test_verify_reports_a_service_role_without_its_timeouts` (fails with the timeout loop removed) |
| V-D6-3 | `src/xcode_api/db/migrate.py` | `tests/db/test_migrate.py::test_routines_leave_a_stale_overload_without_a_caller` (fails with the old grant loop: `xcode_app` can execute `api.meta_contract_version(integer)`) |
| V-D10-1 | `tests/db/test_migrate.py` | `::test_concurrent_runners_serialize` (fails with a no-op advisory lock) |
| V-D6-4 | `tests/support/database.py` | `tests/db/test_template.py` (3 tests; the module did not import before) |
| docs | `docs/03-database.md`, `docs/09-testing.md`, `docs/14-verification.md`, `docs/prompts/verify.md`, `docs/13-open-questions.md` (q56, q57) | - |

## 8. Commands and outputs

- `git status --short apps/api-python`: `?? apps/api-python/` (all untracked). A prompt-07
  session was editing `db/routines/50_revenue/*`, docs 01, 05, 06, 07, 12, 13 during the
  run; none of those files were changed here except docs/13 (two appended rows, 38 minutes
  after its last change).
- Versions: PostgreSQL 16.15 (local cluster, port 5433); Python 3.13.2; psycopg 3.3.6;
  FastAPI 0.142.4; CI image `postgres:18` (never ran).
- Baseline (before changes), scope modules: `113 passed in 170.75s`.
- After fixes, scope modules plus `test_template.py` and `test_routine_headers.py`, on a
  private template: `1042 passed in 802.89s`.
- `ruff check .`: all checks passed; `ruff format --check .`: 321 files already formatted;
  `mypy`: no issues in 153 source files.
- CLI database `xcode`: `db status` (before) applied 0001-0007, routine drift in three
  `50_revenue` files; `db routines` exit 0 (no orphan warnings); `db verify` exit 0,
  21 lines `ok`, including the two strengthened checks.
- Full suite: not run. Resume: when no other session runs a suite (`pg_stat_activity`, `pg_locks` for `xcode.test.template.use:*`), run `pytest -n 3 -q -p no:cacheprovider > <scratchpad>/full.log 2>&1` from `apps/api-python` with `XCODE_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5433/postgres`; the first run rebuilds `xcode_template` from the current fingerprint by itself. The run's counts (passed, failed, skipped, errors, duration) go in the next verify report, which this file does not replace (`docs/audit/README.md`).
- Incident: the new harness reached the tree while another session's full run
  (`pytest -n 3`, started 15:42:39 with the old harness) was active. At 15:45:52 a
  short-lived run from another session rebuilt `xcode_template` with the new code (its
  comment equals the fingerprint of the current files, so the routines were current). A
  clone attempted by the 15:42 run during those seconds would have failed at setup. The old
  run held no shared lock, which is the transition gap; every run started since then holds
  it. My own runs after the runner change used private templates (`xcode_template_v01`,
  `xcode_template_mut01`) so they could not rebuild the shared one.

## 9. Regressions and misses against earlier audits

- `docs/audit/2026-10-11-verify-area-docs.md` V-D6-1 (shared template) asked for a
  content-hashed template; resolved here by a fingerprint and a use lock instead (dialectic
  above). Not a regression.
- `docs/audit/2026-10-11-verify-area-prompt-00.md`: no finding of it is broken again by
  this run's changes. Its V-D7-1 (eviction cost) did not note the cross-window eviction (N1).
- Missed by every earlier review of prompt 01: V-D6-1, V-D6-2, V-D6-3, V-D10-1. V-D6-3 was
  known only as a memory note ("open gap"), in no document.

- Cleanup: `xcode_template_v01` and `xcode_template_mut01` dropped at the end (no
  connections); no other database was created by this session.

## 10. For the user

Nothing irreversible came up. One coordination point: the prompt-07 session should rerun
its last targeted run if it saw setup errors around 15:46 (section 8, incident).
