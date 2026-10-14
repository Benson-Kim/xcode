# Verify report: prompt 09 (operability, OpenAPI, startup, metrics, compression, demo seed, CLI, deployment)

Session revenue-81 [4ac8ce], 2026-10-14. `SCOPE: prompt:09`, `MODE: fix`, `DEPTH: standard`,
Opus. Fresh eyes: this session wrote none of 09 (built 2026-10-12 by revenue-d5 [b49167]); the
build report was read only after the pass (section 9). Security focus: W2-F of
`docs/prompts/security-waves.md` (cluster SC5 and the start of SC8 in
`docs/16-security-matrix.md`).

## 1. Verdict

**pass with findings.** No blocker survives. The full suite ran to completion once on a fresh
template built from the live tree with every fix in (shared with verify-08b, 09:16 to 11:07):
6572 passed, 3 failed, 0 errors, 0 skipped. The 3 failures are D1's stale
`tests/db/test_gateway.py` cases (reported, not fixed, as the brief asks); every 09 module and
every new test is green.

- Claims: 37. holds 30, fails 5 (C15, C19, C24 and C36 fixed or corrected, C29), unproven 1
  (C37), not checked 1 (C1, no host access). The image build and the CI run are not checked
  inside C23, C24 and C33 (no Docker; CI never ran).
- Findings that survived: 0 blocker, 4 major (V-D9-1, V-D9-2, V-D4-1, V-D8-1: all fixed or
  corrected), 6 minor (V-D5-1, V-D8-2, V-D8-3, V-D8-4, V-D11-1, V-D11-2; V-D11-2 corrected),
  2 notes (V-D9-3, V-D8-5). Attributed to other scopes: 2 (V-D6-1 to 08b, V-D8-6 to 00/05).
- Fixes: 5 new tests in 3 files, 1 workflow change, 3 documents corrected.

## 2. Thesis and claims

Thesis (steelmanned): prompt 09 delivers D1 to D7 (D0 by nature only as commands), its
invariants hold under the server it ships (`xcode-api serve`, uvicorn), the operational
surface is the .NET behaviour at `ac2f9a0` where .NET has one (health, OpenAPI, compression,
mail relay, startup warnings), every route the API answers is in `docs/06`, and the CI and the
image would work the first time they run.

| # | Claim (where stated) | Code that carries it | Verdict | Grade |
|---|---|---|---|---|
| C1 | D0: hosting facts measured, or left open with the exact commands (prompt D0) | `deploy/README.md` "The cPanel account `priori`"; `docs/13` q39 to q45 | not checked: no host access (the commands are present and the questions open with defaults) | - |
| C2 | D1: the `docs/06` 1.11 assertions (sign-in 202/423 `AuthResponse`, no security; deactivate 409 `ProblemDetails`, Bearer; scheme; 401 on every secured operation) | `http/openapi.py`, routers | holds | A (`tests/api/test_openapi.py`, 13 passed) |
| C3 | D1: operation ids equal the `docs/06` section 2 column through a fixture | `tests/support/operations.json` | holds: 93 of 93 rows equal in `docs/06`, the fixture and the served document (my sweep, section 8) | A |
| C4 | D1: tags `Setup`, `Organization`, `Revenue`, `Petty cash`, `Central expenses`, `Reports` | routers | holds (56, 7, 6, 14, 6, 4 operations; 22 auth untagged) | A |
| C5 | D1: the document is served only when enabled; off by default in production | `main.py:109`, `settings.py:207-211` | holds | A |
| C6 | SC5: no shadow endpoint; every served route is in `docs/06` and the reverse | routers, `docs/06` 2 | holds now; was unproven (V-D4-1): no test covered `/auth/*` routes or routes hidden from the document | A after the fix |
| C7 | D2: startup order of `docs/08` 6 (threads, pool 30 s, role check, dev migrate and seed, contract version, unassigned users, mail queue, readiness) | `main.py:211-224`, `95-104` | holds | B (reading plus a test per step) |
| C8 | D2: a contract mismatch refuses to start, exit 1, under the server the project ships | `main.py:170-181`, `cli/commands/serve.py:42-59` | holds; was unproven (V-D8-1): every startup test drove `lifespan_context` or mocked `uvicorn.run` | A after the fix |
| C9 | D2: readiness is `SELECT 1` and the version within 10 s, plus the limiter when `postgres`; `text/plain`; the reason only in `health.ready.failed` | `application/ops/check_readiness.py`, `http/routers/health.py` | holds | A (`test_operability`, `test_http_plumbing`) |
| C10 | D2: the unassigned-user warning sentence | `main.py:184-189` | holds | A |
| C11 | D2: production without key, host, from or database URL exits 2 naming each | `settings.py`, `serve.py:32-38` | holds | A (`test_production_startup`, 18) |
| C12 | D2: shutdown drains the mail queue for `XCODE_SHUTDOWN_GRACE_SECONDS`, then closes the pool | `main.py:100-104`, `219-221` | holds | B |
| C13 | D2: plaintext SMTP outside development only to a loopback relay | `settings.py:312-320`, `is_local_host` | holds (parity with `apps/api/Infrastructure/Security.cs:108-113`, a literal check, no resolution); the prompt's wording (resolve, mixed list) is stale: V-D11-1 | A |
| C14 | D3: exactly the series of `docs/08` 5; default off; route absent when off | `infra/metrics.py`, `main.py:130-147` | holds | A (`test_metrics`, 4) |
| C15 | D3: no label carries unbounded values | `http/middleware.py:291-297` | fails narrowly: `method` is the raw request method (V-D8-2); bounded under the shipped httptools parser | B |
| C16 | D3, `docs/06` 1.10: `/metrics` and the probes are exempt from `XCODE_ALLOWED_HOSTS`, exact paths only | `http/middleware.py:205-223` | holds | A (`test_health_hosts_and_request_log`, `test_metrics`) |
| C17 | D4: gzip for `/setup/` over 1 KiB, never `/auth/**` nor health; `Vary`; `X-Request-ID` survives | `http/middleware.py:226-262` | holds | A (`test_compression`, 8) |
| C18 | D5: `api.ops_seed_demo` per `docs/05` 5, idempotent, refused outside development by the CLI and the routine | `db/routines/60_ops/ops_seed_demo.sql`, `cli/commands/seed.py` | holds | A (`test_ops_routines` seed tests, `test_cli`) |
| C19 | D5 and the drift check: "the demo seed ... cover what 08b added" (prompt 09 line 40) | `db/routines/60_ops/seed_*.sql` | fails: no central expense, shared purchase or scheduled-run pause is seeded (V-D5-1) | A (grep, section 8) |
| C20 | D5: `tests/support/scenario.py` and `seed_10x` | `tests/support/scenario.py` | holds | A (`test_seed_10x_gives_ten_times_the_vehicles_and_their_rows`) |
| C21 | D6: registry equals `docs/08` 8; help names no secret; exit codes 0, 1, 2 | `cli/main.py` | holds | A (`tests/unit/test_cli.py`, 36) |
| C22 | D6: every state-changing command records `ops.operator_actions` | `ops_*` routines | holds | A (`tests/api/test_cli.py`, 9) |
| C23 | D7: Dockerfile digest pinned and recorded, uid 10001, read-only root with `/tmp` tmpfs documented, healthcheck on `/health/live`, `.dockerignore` | `deploy/Dockerfile`, `deploy/README.md` | holds by reading; the digest resolves and still equals the tag (registry, section 8); the image itself not checked (no Docker) | B |
| C24 | D7: the CI jobs as `docs/08` 9 lists them | `.github/workflows/xcode-api.yml` | failed (V-D9-1: the `image` job could never tag its image), fixed; the rest holds by reading plus local reproduction of the lock-drift step and `pip-audit`; CI never ran | B |
| C25 | D7, D9: actions pinned by commit | workflow | holds: the three SHAs equal their tags (`gh api`, section 8) | A |
| C26 | D7: `deploy/runbook.md` has every `docs/08` 10 entry with commands and event names | `deploy/runbook.md` | holds: 8 entries plus startup; every cited event name is emitted in `src` | B |
| C27 | D7: connection-limit table for compose (1 x 10 -> 14) | `deploy/README.md` | holds | D (a table; nothing to execute) |
| C28 | D7: cPanel section built from D0 facts or open question numbers | `deploy/README.md` | holds, with the question 86 default corrected (V-D9-2) | D |
| C29 | D7: `docs/08` 1, `.env.example`, `Settings` and `tests/unit/test_settings.py` agree on every setting | | holds for the first three (37 = 37 = 37); fails narrowly for the tests: `XCODE_EMAIL_USERNAME` is never set or asserted there (V-D8-4) | A (sweep) |
| C30 | Invariant: the process starts as `xcode_app` only and never reads the operator or migration URL outside development | `main.py:211-224` | holds | A (`test_the_default_startup_reads_and_never_migrates`) |
| C31 | Invariant: `/auth/**` never compressed; every response carries the security headers and `X-Request-ID` | middleware; `http/errors.py:82,125,183,228` for the responses Starlette sends outside the middleware | holds | A |
| C32 | Invariant: every safety switch of `docs/08` 11 refused outside its environments by the matrix | `tests/unit/test_settings.py` matrix | holds | A |
| C33 | Invariant: lint, types, all tests green; `db verify` 0; the image builds or Docker's absence reported; no TODO; no plan ids | | lint, format, mypy clean; sweeps empty; `db verify` exit 0 on `xcode`; tests: full run 6572 passed, 3 failed (D1's `test_gateway` drift, not 09's); the image: not checked (no Docker) | A |
| C34 | SC5: 1 MiB body cap, declared and streamed | `http/middleware.py:303-345` | holds | A (`test_body_cap_returns_413`, `test_chunked_body_over_cap_returns_the_same_413`) |
| C35 | SC5: 429 with an empty body and `Retry-After` | `http/dependencies.py:136-142` | holds | A (`test_rate_limit_returns_429_empty_with_retry_after`) |
| C36 | SC5, q86: the loopback trusted-proxy default on a shared host | `settings.py` default `127.0.0.1,::1`; `docs/12` 7 | fails: its documented mitigation was unsafe (V-D9-2), corrected; the risk itself stays recorded (owner added) | B |
| C37 | D2, D5: in development, `XCODE_AUTO_MIGRATE` and `XCODE_DEMO_SEED` run at startup as their own roles | `main.py:248-288` | unproven: no test runs `prepare_development` (V-D8-3) | F |

Counted: holds 30 (C2 to C14, C16 to C18, C20 to C23, C25 to C28, C30 to C35; C6 and C8
after their fixes), fails 5 (C15, C19, C24, C29, C36), unproven 1 (C37), not checked 1 (C1).
37 in all.

## 3. Findings (`docs/14-verification.md` section 7)

| id | mode | claim attacked | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| V-D9-1 | pre-mortem | C24: the `image` job builds, scans and pushes | The job set `IMAGE: ghcr.io/${{ github.repository_owner }}/xcode-api`. The owner is `Benson-Kim` (`git remote -v`). Docker's reference grammar allows only lower case in the repository path, so `docker build -t ghcr.io/Benson-Kim/xcode-api:<sha>` stops with "repository name must be lowercase": no scan, no uid check, no push, on the first run and every run | `.github/workflows/xcode-api.yml` image job (before); the distribution reference grammar | Looked for a lower-casing step or a lower-case owner: none. Docker is absent here and CI never ran, so this is proven against the grammar, not by a failed run | survives, major (CI and release path) | fixed: a step writes `IMAGE=ghcr.io/${GITHUB_REPOSITORY_OWNER,,}/xcode-api` to `$GITHUB_ENV`; `tests/unit/test_ci_workflow.py::test_every_image_name_is_a_valid_docker_repository_for_a_mixed_case_owner` failed before (`ghcr.io/Benson-Kim/xcode-api`) and passes after. The one edit outside `apps/api-python`: the file is 09's own deliverable |
| V-D9-2 | red team (neighbour on the host), pre-mortem | C36: question 86's default, "serve on a Unix socket only the proxy's account can open (`uvicorn --uds`, file mode 0660)", closes the shared-loopback gap | Following it fails three ways. (1) `xcode-api serve` has no `--uds` (`cli/commands/serve.py:28-30`), so an operator runs uvicorn by hand and loses the settings check, the exit-code mapping, `proxy_headers=False` and `server_header=False`. (2) uvicorn chmods the socket to 0666 unless the file already exists (`uvicorn/server.py:166-174`), so any account can connect unless the parent directory keeps them out. (3) A socket peer has no address (`uvicorn/protocols/utils.py:13-27` returns `None` for a non-tuple peer), so `client_address` answers `unknown` for every request (`http/middleware.py:81-84`, `http/dependencies.py:33-34`) and `auth:unknown`, `auth_pin:address:unknown` become one bucket for every user: 30 sign-in requests a minute for the whole user base, and one attacker locks everyone out of PIN checks for ten minutes with 20 attempts | the files above; `dependencies.py:84-87,105,118` | Looked for a socket-peer rule in `client_address`, a `--uds` option or a socket-mode step in `deploy/`: none. Nobody has deployed it yet (question 86 is open), so no live system is affected | survives, major (a documented default that would build the wrong thing) | doc corrected: `docs/13` q86 default (a loopback port the host firewall keeps to the proxy's account; a socket only after `serve --uds` trusts its peer as the proxy), `docs/12` 7 (the two q86 bullets, owners added), `deploy/README.md` (q86 in the defaults paragraph). For the user: section 10 |
| V-D4-1 | falsification | C6, SC5: "every route in the OpenAPI document is documented in `docs/06` and vice versa" | `test_every_served_operation_is_catalogued_or_an_untagged_auth_route` accepts any `/auth/*` operation without looking at `docs/06` (`tests/api/test_openapi.py:268-277`), and nothing looks at routes with `include_in_schema=False` (health, `/metrics`, the document). A new `GET /auth/debug`, or any route marked hidden, would pass every test | `tests/api/test_openapi.py` before the change | Swept by hand: the 115 document operations plus 4 hidden routes equal the 120 `docs/06` section 2 routes, and every one of the 99 .NET routes is in `docs/06` (section 8). So no shadow endpoint exists today; the gap is the missing guard | survives, major (a missing test for a security claim) | fixed: `test_every_served_route_is_in_the_contract_and_every_contract_route_is_served` walks the app's routes (hidden ones included) and compares both ways with `docs/06` section 2; it then adds a hidden `GET /auth/debug` and asserts that exactly that route is reported (the check bites) |
| V-D8-1 | falsification | C8 and the W2-F focus: the readiness and startup checks run under the chosen server, not skipped by an adapter | Every startup test drives `app.router.lifespan_context` itself (`tests/api/test_operability.py:60-70,158-205`) or replaces `uvicorn.run` (`tests/unit/test_production_startup.py:38,106,119`). If `serve` ran uvicorn with `lifespan="off"`, or under an adapter, every test would still pass | the tests named | Read uvicorn 0.54: `lifespan="auto"` with Starlette's `lifespan.startup.failed` ends startup with code 3, which `serve` maps to 1. That is reading, grade C | survives, major (a missing test for an integrity claim) | fixed (tests; the behaviour was right): `test_serve_runs_the_startup_checks_under_uvicorn` starts the real `xcode-api serve` on a free port against a test database and needs `/health/ready` 200 and `startup.contract_version_ok`; `test_serve_exits_1_when_the_contract_version_differs` replaces `api.meta_contract_version()` with 9999 in that database and needs exit 1 and `startup.contract_version_mismatch`. Both pass. Under `lifespan="off"` the first answers 503 (`started` stays false, `health.py:28`) and the second never exits |
| V-D5-1 | falsification | C19: the demo seed covers what 08b added (prompt 09 line 40, and this run's brief) | No seed routine writes `expenses.entries`, a shared petty-cash purchase or a scheduled-run pause: `grep -i -E 'expenses\.|alloc|pause|shared' db/routines/60_ops/*.sql` finds only a deferred allocation constraint in `seed_fleet_setup.sql:80`. The demo's Central expenses screen and the expenses ledger are empty, and `seed_10x` gives no 10x central-expense rows | `db/routines/60_ops/` | `docs/05` 5 (the seed's own contract) does not list them, and the .NET `DemoSeed.cs` seeds none of it either, so it is not a parity break | survives, minor | recorded; README row 09 names it as owed to the next build that touches the seed |
| V-D8-2 | red team (scanner) | C15: "labels never carry ... a raw path" and no high-cardinality label (`docs/08` 5, prompt D3) | `http_requests_total{method}` takes `scope["method"]` as sent (`http/middleware.py:295`). h11 accepts any token as a method, so `FOO1`, `FOO2`, ... each add a series that lives for the process | `infra/metrics.py:82-84` | The shipped server runs httptools (in the lock; uvicorn picks it), whose parser accepts only its fixed method list, so the series stay bounded there; `/metrics` is off by default | survives, minor (holds only by the parser's choice) | recorded; recommended fix: map any method outside GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS to `other` |
| V-D8-3 | falsification | C37: development startup migrates as the owner and seeds as the operator | `prepare_development`, `_auto_migrate`, `_seed_demo` (`main.py:248-288`) are called by no test; only their refusals outside development are | `tests/unit/test_settings.py:353-358` | none | survives, minor (development only) | recorded as unproven |
| V-D8-4 | falsification | C29: every `XCODE_*` setting appears in `tests/unit/test_settings.py` (`docs/14` D8) | `XCODE_EMAIL_USERNAME` (field `email_username`) is neither set nor asserted there | sweep, section 8 | It appears in `.env.example`, `docs/08` 1 and the summary; the summary test covers the password only | survives, minor | recorded |
| V-D11-1 | Socratic | C13: prompt 09 D2 asks for "a relay whose every address is the loopback interface ... the same reading as `settings.connects_locally` ... a hostname that resolves elsewhere and a mixed list" | The code checks the literal (`localhost` or a loopback literal), never resolving | `settings.py:464-474`; `docs/08` 1 row `XCODE_EMAIL_TLS` | .NET does the same (`Security.cs:111-113`, `IPAddress.TryParse`), and `docs/08` states it; the prompt text is the stale part | conceded for the code; the prompt wording survives as minor | recorded (the build prompt is history; `docs/08` is the contract) |
| V-D11-2 | Socratic | `docs/12` 7: the demo PINs "never reach a real account"; the two q86 bullets | The routine cannot know its environment, it trusts `p_environment`: an operator calling `api.ops_seed_demo(..., 'development', ...)` by hand seeds an empty production database. The two q86 risks had no owner | `ops_seed_demo.sql:33-39` | The routine refuses a database holding any other organization, and the operator credential already allows `provision-user` | survives, minor (documentation) | doc corrected in `docs/12` 7 (wording; owners: operations) |
| V-D9-3 | red team (supply chain) | D9: dependencies install from the lock files | The `audit` job runs `pip install pip-audit` (no version, no hash) although `requirements-dev.lock.txt` pins it with hashes; `pip install --no-deps .` in the Dockerfile and in CI builds the package with an unpinned `setuptools` (build isolation) | workflow `audit` job; `deploy/Dockerfile:24` | the scanner's own integrity is not the product's; a hostile `pip-audit` could still pass a vulnerable lock | survives, note | recorded; recommended: install the audit tool from the dev lock, and build with `--no-build-isolation` from a hashed `setuptools` |
| V-D8-5 | Socratic | `docs/08` 8: "stdout carries only the command's own output" | `openapi`, `settings-check`, `seed-demo` and `serve` print settings errors on stdout (`cli/commands/openapi.py:29-31` and siblings), so `xcode-api openapi > doc.json` with a bad environment writes `XCODE_ENV: Field required` into the file and exits 2; `openapi` also needs `XCODE_DATABASE_URL` although it connects to nothing | measured, section 8 | the exit code is 2, so a careful pipe notices | survives, note | recorded |
| V-D6-1 | Socratic | attributed to 08b, not 09 | `xcode-api db status` on the CLI database `xcode`: "migration checksum drift: [14]". `ops.schema_migrations` has 0014 applied 2026-10-13 20:29:44; `db/migrations/0014_orphan_routines.sql` was modified at 20:35 (both files untracked): an applied migration edited afterwards. Routine drift there in four `40_setup` files (20:35 to 20:37) | section 8 | The runner's checksum check caught it, which is the D6 probe biting on a real database | not 09's | told revenue-59 [cb8561] (verify-08b) by message at 08:47; not touched |
| V-D8-6 | Socratic | attributed to 00/05, not 09 | `http/errors.py:118` logs `request.refusal_without_message` with `code=exc.code`; the redaction processor drops every key containing `code` (`infra/logging.py:17-30`, only `code_id` allowed), so the line loses the one field that says which refusal had no message | the files named | none | not 09's, note | recorded here only |

## 4. Per domain

09 touches D4 (routes), D6, D7, D8, D9, plus D10 and D11 always. D1, D2 (identity), D3 and D5
are n/a except where named.

D4 Contract parity
- Routes: holds. .NET 99 routes (`apps/api/Api/*.cs`, `Program.cs`) all in `docs/06`; `docs/06`
  section 2 lists 120 = the 115 document operations + `/health/live`, `/health/ready`,
  `/health`, `/metrics`, `/openapi/v1.json`; the extra 21 over .NET are the design-register
  routes of 2.12. Operation ids and tags equal for 93 of 93 rows.
- Bodies: n/a (09 adds none). Errors: the empty 429 and the 413 problem hold (C34, C35).
- Clients: n/a. Drift: holds; since the build only `ac2f9a0` touched `apps/api`, in 08b's
  areas (recurring pauses, petty cash, fleet postings); none of the operability files.

D6 Database craft
- `db verify` exit 0 on `xcode` (8 data checks printed, all ok). Whether each check bites:
  not re-proven in this run, except the runner's checksum check, observed biting on `xcode`
  (V-D6-1).
- `SECURITY DEFINER` with a fixed `search_path`: holds (sweep; the two files with an extra
  match carry it in a comment). No dynamic SQL: holds (sweep; only `GRANT EXECUTE`).
- Migrations checksummed: holds (observed). Version features: holds (no `MERGE`,
  `JSON_TABLE`, `uuidv7`, `RETURNING OLD`, `ANY_VALUE`, `NULLS NOT DISTINCT`,
  `pg_input_is_valid`).
- Template: the full run's `xcode_template_v09full` carried fingerprint `0ab278f3...` (comment
  `xcode test template <sha>`), equal at 13:16 to `template_fingerprint(db/)` of the live tree,
  so the run tested today's `db/` files; `xcode_template_v09` (targeted runs) carried the same.

D7 Performance and scale
- Threads: holds (`test_concurrent_requests_start_no_more_worker_threads_than_the_cap`); the
  host count is question 43, not checked.
- Readiness budget: holds (one routine, two with `postgres`; `docs/06` 2.10).
- Connections: holds for compose; staging and production open (question 3).
- Hardest attacks that failed: a readiness flood through the proxy (anonymous, unthrottled,
  each probe a pool checkout): parity with .NET's `MapHealthChecks`, bounded by the pool; an
  unbounded `/metrics` body: series are bounded by templates (V-D8-2 aside); a chunked body
  that streams forever: cut at 1 MiB (C34).

D8 Reliability and operability
- Startup order, contract version, readiness, shutdown: holds (C7 to C12, C8 now grade A).
- Every timeout: startup pool 30 s, readiness 10 s, SMTP `XCODE_EMAIL_TIMEOUT_SECONDS`, uvicorn
  graceful 30 s: holds by reading.
- Logs: holds for 09's lines (sweep: no body, PIN, code, token, phone, email; one out-of-scope
  note V-D8-6).
- CLI exit codes and operator rows: holds (C21, C22). Settings everywhere: fails narrowly
  (V-D8-4).

D9 Hosting and supply chain
- Hosting facts (q39 to q45): not checked, no host access; never probed `priori`.
- Lock files with hashes: holds; `uv pip compile` reproduces both locks byte for byte (uv
  0.12.23). `pip-audit --strict -r requirements.lock.txt`: no known vulnerabilities.
- Actions pinned: holds (three SHAs equal their tags; trivy-action v0.36.0 is an annotated
  tag of 2026-04-22 whose commit is the pin; its inner `setup-trivy` and `cache` are pinned by
  SHA too). Workflow permissions: `contents: read`, `packages: write` on `image` only: holds.
- The image job: fixed (V-D9-1). Supply-chain notes: V-D9-3.
- The production TLS rule read as libpq reads it: n/a (prompt 01's, unchanged).

D10 Tests as evidence
- Sweep of 09's tests: no skip, xfail or broad except; one `time.sleep(0.25)` in the new
  polling loop (a subprocess, no event loop to yield).
- Wrong implementations the tests would catch, checked: `serve` with the lifespan off (now
  caught); a hidden or `/auth/*` shadow route (now caught); compression on `/auth` (caught,
  `test_compression`); a 429 with a body (caught); a contract mismatch accepted (caught in
  process and now under uvicorn). Not caught: an unbounded `method` label (V-D8-2), the
  development startup path (V-D8-3).
- Full run: 09:16 to 11:07, `-n 0`, 6575 tests: 6572 passed, 3 failed, 0 errors, 0 skipped
  (1:50:49). Failed: `tests/db/test_gateway.py::test_identity_routines_map_every_outcome_with_one_statement_each`,
  `::test_verify_device_maps_through_the_gateway`, `::test_ops_routines_map_the_operator_routines`
  (`CodeCheck` and `DeviceVerification` need `now`; `ClearedPause` has no `was_paused`): D1's
  domain change of 2026-10-12 22:36, the same three as the full runs of 12 and 13 October; not
  fixed here. 09 modules: openapi 13, operability 14, ci workflow 2, metrics 4, compression 8,
  api cli 9, unit cli 36, ops routines 80, production startup 18, settings 150, client address
  3, layers 5, http plumbing 32, grants 84, structure 14, migrate 19, routine headers 1722,
  message codes 6, messages 514; the five new tests passed (the two `serve` subprocess tests in
  4.8 s and 4.6 s).

D11 Documents and prompts
- `docs/08` 1, 5, 6, 8, 9, 10, 11 match the code (sweeps above). `docs/13` q86 and `docs/12` 7
  corrected (V-D9-2, V-D11-2). Prompt 09's mail wording stale (V-D11-1); its line 40 claim
  unmet (V-D5-1).

## 5. Per mode

Assumption inventory (Socratic)

| Assumption | Where stated | Enforced by |
|---|---|---|
| The proxy never forwards `/metrics` | `docs/08` 5, `routers/metrics.py` docstring | nothing in code; platform config (residual risk, owner operations) |
| The API port is reachable only by the proxy | `docs/08` 9 checklist | nothing on a shared host (q86) |
| uvicorn runs the lifespan | `serve.py` docstring | now `test_serve_runs_the_startup_checks_under_uvicorn` |
| A method label is bounded | `infra/metrics.py` docstring | the httptools parser only (V-D8-2) |
| A Unix socket is a safe default for q86 | `docs/13` q86 (before) | nothing; false (V-D9-2) |
| The repository owner is lower case | the workflow (implicitly) | nothing; false (V-D9-1) |
| The seed's environment check holds | `docs/12` 7 | the CLI and settings; the routine trusts its caller (V-D11-2) |

Falsification: the claims table of section 2 is the table (falsifier per row: the test or
sweep named; grades given).

Pre-mortem (three months after cutover)
1. The release tag is pushed; the `image` job fails at `docker build` on the owner's upper
   case; nobody has a scanned image; someone builds by hand without the scan. Inversion: the
   condition existed (fixed, V-D9-1). Early sign: the first CI run.
2. The operators follow question 86 and serve on a Unix socket: from 09:00 every sign-in
   answers 429 after 30 requests a minute across the company; the clerks are locked out of PIN
   checks whenever anyone mistypes 20 times. Inversion: the documented default guaranteed it
   (corrected, V-D9-2). Early sign: `rate_limit_rejections_total` rising with one `client`
   value, `unknown`, in the logs.
3. cPanel runs the app under Passenger with an ASGI-to-WSGI adapter: no lifespan, so the pool
   never opens; every route answers 500 and readiness 503. Inversion: fail-closed by
   construction (the pool opens only in the lifespan, `main.py:214`, `db/pool.py:80`), so it
   is loud, not silent; q41 stays open.
4. A scanner hits the API port directly with random methods while metrics are on under h11:
   the registry grows until the process is killed. Inversion: needs h11 and metrics on; the
   shipped stack has neither (V-D8-2).
5. A routine deployment moves the contract: readiness turns 503 within one probe and the
   platform takes the process out of rotation (holds, `test_readiness_unhealthy_when_the_contract_version_moved`).

Red team

| Persona | Vector | Defence or gap |
|---|---|---|
| Outsider | a shadow route (`/auth/*` or hidden) | none in tests before; guarded now (V-D4-1) |
| Outsider | 1 MiB+ bodies, chunked, to `/auth/sign-in` to dodge the limiter | 413 before the router; no PIN check happens, so nothing to dodge |
| Outsider | `Host:` spoofing to reach routes past `XCODE_ALLOWED_HOSTS` via an exempt path | exact-path exemption; `/health/live/` still checked (test) |
| Neighbour on the host | believed `X-Forwarded-For` from loopback; scrape `/metrics` for enumeration | residual risk q86 (owner operations); the documented fix was unsafe (V-D9-2) |
| Neighbour on the host | a world-writable socket | uvicorn's 0666 (V-D9-2) |
| Operator | seed demo PINs into an empty production database by calling the routine | operator credential only (V-D11-2) |
| Hurried DBA | edit an applied migration | the runner's checksum check catches it (seen on `xcode`, V-D6-1) |
| Scanner | random methods to grow the metric registry | parser-bounded only (V-D8-2) |

Dialectic

| Decision | Strongest counter | Verdict, confidence |
|---|---|---|
| `/metrics` on the API port, off by default | a separate listener bound to loopback or a socket makes "the proxy never forwards it" structural | keep (off by default; q86 keeps it off on a shared host); a separate listener is the next step if metrics go on there. Medium |
| Plaintext SMTP only to a literal loopback host | resolving would accept a host alias of the relay | keep: parity with .NET, and resolution adds a DNS time-of-check gap. High |
| Health probes exempt from the host check | DNS rebinding could aim a browser at `/health/ready` | keep: nothing to read, bounded cost, parity. High |
| One uvicorn process, capped executors | gunicorn workers for CPU | keep: the host counts threads (q43). High |
| Readiness re-checks the contract on every probe | one more routine call per probe | keep: it is what takes a stale process out of rotation. High |
| Unix socket as q86's default | the socket is the strongest isolation on a shared host | change: not until `serve` binds it and trusts its peer (V-D9-2). High |

## 6. Conceded

- 500 answers lack the security headers because Starlette sends them outside the middleware:
  defeated by `http/errors.py:228` (and `82`, `125`, `183`), which set them and
  `X-Request-ID` itself; `test_security_headers_on_500`.
- A lifespan skipped by an adapter serves silently: defeated by the pool opening only in the
  lifespan (fail closed) and readiness requiring `app.state.started`.
- `readiness` exceeds the `docs/06` budget of 1: defeated by the definition (the gateway counts
  routine calls; `SELECT 1` is not one).
- Gzip on `/setup/` as a BREACH oracle: no token, cookie or CSRF secret is ever in a `/setup/`
  body; `/auth/**` is never compressed.
- The base image tag moved since the pin: the recorded digest still equals the tag today.
- An action SHA that does not match its tag (the trivy-action compromise of 2026): all three
  match.
- Lock drift in CI: reproduced locally with the CI's exact command, no difference.
- A route answering only `HEAD`: Starlette adds `HEAD` to `GET` routes only.

## 7. Fixes

| Finding | Files | Test that failed before and passes now |
|---|---|---|
| V-D9-1 | `.github/workflows/xcode-api.yml` (image job); new `tests/unit/test_ci_workflow.py` | `test_every_image_name_is_a_valid_docker_repository_for_a_mixed_case_owner` (failed: `ghcr.io/Benson-Kim/xcode-api`) |
| V-D4-1 | `tests/api/test_openapi.py` (appended) | `test_every_served_route_is_in_the_contract_and_every_contract_route_is_served` (its own last assertion injects a hidden route and sees it reported) |
| V-D8-1 | `tests/api/test_operability.py` (appended) | `test_serve_runs_the_startup_checks_under_uvicorn`, `test_serve_exits_1_when_the_contract_version_differs` (the behaviour was right; they fail if `serve` stops running the lifespan) |
| V-D9-2, V-D11-2 | `docs/13-open-questions.md` q86; `docs/12-security.md` 7; `deploy/README.md` | documents |

## 8. Commands and outputs (trimmed)

```
git status --short   (303 entries; 08b and 10 work uncommitted; HEAD ac2f9a0 2026-10-12 22:22)
SELECT version()     PostgreSQL 16.15 (5433, the local test cluster); CI image postgres:18, never run
python --version     Python 3.13.2
fastapi 0.142.4, starlette 1.7.0, uvicorn 0.54.0, httptools 0.8.0, prometheus-client 0.26.0

baseline, live tree, -n 0, one module per process, template xcode_template_v09:
  unit test_cli 36, test_settings 150, test_production_startup 18, test_client_address 3;
  api test_operability 12, test_openapi 12, test_metrics 4, test_compression 8, test_cli 9,
  test_http_plumbing 32; db test_ops_routines 80          -> 364 passed, 0 failed
after the changes: test_openapi 13, test_operability 14, test_ci_workflow 2 -> all passed
ruff check .  -> All checks passed;  ruff format --check . -> 493 files already formatted
mypy          -> Success: no issues found in 227 source files

xcode-api openapi (XCODE_ENV=testing, a dummy database URL) -> 102 paths, 115 operations
  router walk: 119 operations, hidden: GET /health/live, /health/ready, /health, /metrics
  (+ /openapi/v1.json) ; schema routes == document operations
  docs/06 section 2: 120 routes = document + the 5 hidden ; .NET 99 routes, all in docs/06
  operationIds: docs/06 93 = operations.json 93 = document 93, tags equal
XCODE_* names: Settings 37 = .env.example 37 = docs/08 table 37; test_settings misses
  XCODE_EMAIL_USERNAME (XCODE_DATABASE_ALLOW_REQUIRE_SSLMODE and XCODE_EMAIL_PASSWORD covered
  by field name)
uv pip compile (runtime and dev, the CI's flags) -> no drift ; pip-audit --strict -> no known
  vulnerabilities
gh api: checkout v7.0.1 = 3d3c42e5, setup-python v7.0.0 = 5fda3b95, trivy-action v0.36.0
  (annotated, 2026-04-22) -> ed142fd0
registry: python@sha256:a1165e27... HTTP 200; tag 3.13-slim-bookworm -> the same digest
xcode-api db status (xcode): applied 0001-0014, pending none, routine drift 4 files
  (40_setup), migration checksum drift [14]   (08b's, V-D6-1)
xcode-api db verify (xcode) -> every check ok, exit 0
xcode-api db routines: not run on xcode (the shared CLI database, with 08b's open drift under
  another verifier); the template build applies every routine file instead
sweeps: now()/current_date/clock_timestamp()/random() in db/routines: none; EXECUTE/format(:
  only GRANT EXECUTE; TODO/FIXME/plan ids in src, db, tests: none
full run: XCODE_TEST_TEMPLATE=xcode_template_v09full pytest -n 0 -q -p no:cacheprovider -rfE
  --junitxml=full.xml (09:16:16 to 11:07:14) -> 6572 passed, 3 failed (test_gateway), exit 1
```

## 9. Regressions and misses against earlier audits

Read after the pass: `docs/audit/2026-10-12-build-09.md`.
- Regressions: none. Its fixes still hold: actions pinned by commit (re-checked against
  GitHub), hashed locks (reproduced), the digest (resolves), the compression test (passes),
  the settings rows and `settings-check` row (sweep equal).
- Missed by it: V-D9-1 (it fixed the trivy tag but not the image name), V-D9-2 (it opened
  question 86 with the socket default without checking how uvicorn creates a socket or what a
  socket peer's address is), V-D4-1 and V-D8-1 (its "three hardest attacks" for D2 cite tests
  that drive the lifespan directly), V-D5-1 (built before 08b; the brief for this run says the
  seed now covers 08b, which it does not), V-D8-2 to V-D8-5.

## 10. For the user

1. Question 86 (shared host): choose between (a) a loopback port that the host firewall keeps
   to the proxy's account (needs the host's root, for example an owner-match rule), and (b) a
   Unix socket, which needs a small code change first (`serve --uds`, the socket peer trusted
   as the proxy, the socket's directory restricted to the proxy's group). Recommendation: (a)
   if the hosting company will add the rule, because it needs no code; otherwise (b), built and
   verified before go-live. Either way `XCODE_METRICS_ENABLED` stays off there.
2. D0 (questions 39 to 45) still needs someone with access to the `priori` account to run the
   commands in `deploy/README.md`; nothing about the real host is proven yet.
