# Prompt 09: operability, remaining CLI, demo seed, deployment finish

Paste everything below the line into a fresh Claude Code session running Sonnet, started in
the repository root. Requires prompts 00 to 08 and 08b.

---

You are finishing the operational surface of `apps/api-python`: the complete OpenAPI
assertions, metrics, the startup sequence with the contract-version and unassigned-user
checks, the demo seed routine and command, response compression for `/setup/*`, the
container, CI and runbook as the operability document specifies, and the final settings
matrix. Nothing in this prompt changes a business rule.

## Read first, in this order

1. `CLAUDE.md`; `apps/api-python/README.md`.
2. `docs/08-operability.md` (all); `docs/12-security.md` (all); `docs/02-stack.md`
   ADR-8, 9, 10, 12, 13, 15; `docs/06-http-contract.md` sections 1.4, 1.5, 1.8 to 1.12,
   2.10; `docs/05-routines.md` sections 5 and 7; `docs/09-testing.md`; `docs/11-naming.md`;
   `docs/13-open-questions.md` (questions 3, 7, 8, 9, 10 and the defaults you build).
3. `docs/inventory/inventory-http-contract.md` sections 1.12, 1.13 (`OpenApiTests`
   assertions), its drift log (compression on `/setup/*`, readiness check, startup
   requirements of `ProductionStartupTests`), and `docs/inventory/inventory-tests.md` rows
   for `OpenApiTests`, `OperabilityTests`, `ProductionStartupTests`, `CompressionTests`,
   `DemoSeedTests`, `ForwardedClientTests`.
4. `deploy/README.md`, `db/seeds/README.md`, `.env.example`, `docker-compose.yml`,
   `.github/workflows/xcode-api.yml`, and the code from prompts 00 to 08 (`main.py`,
   `container.py`, `cli/`, `infra/`, `http/middleware.py`, `db/routines/ops.py`,
   `tests/api/test_operability.py`, `tests/api/test_openapi.py`).

Do not read the C# sources except in the drift check.

## Drift check (before any code)

Run `git log --since=2026-10-07 --stat -- apps/api/Program.cs apps/api/Api/OpenApiDocumentation.cs apps/api/Infrastructure apps/api/appsettings*.json tests/api/OpenApiTests.cs tests/api/OperabilityTests.cs tests/api/ProductionStartupTests.cs tests/api/DemoSeedTests.cs tests/api/CompressionTests.cs tests/api/EmailSenderTests.cs`
and `git diff HEAD --stat` over the same paths. Row 10 of the drift register in
`docs/prompts/README.md` is yours (D2): the .NET API sends mail without TLS only to a relay
on the loopback interface (commit 553dd15), and the Python `SmtpMailer` refuses plaintext
outside development, so code mail could not leave a host whose relay is on 127.0.0.1.
The demo seed and the OpenAPI assertions cover what 08b added. Correct the documents
before building; list every correction with the .NET `file:line` that caused it.

## Environment

The local cluster is PostgreSQL 16 and Docker is not installed on the development
machine (`docs/09-testing.md` section 5): build the image only where Docker exists and
say so otherwise. `git status` first; write only under `apps/api-python/` and
`.github/workflows/xcode-api.yml`.

## Deliverables

### D0 Hosting facts (before D7)

- The intended host is the shared cPanel account `priori`, not a container platform
  (`docs/08-operability.md` section 9). Questions 39 to 45 of
  `docs/13-open-questions.md` are facts to measure there: PostgreSQL and Python versions,
  whether the five roles can exist, how the app runs with its lifespan, the thread budget,
  where secrets live, how a release is proven authentic.
- If you have access to the host (ask the user), measure each one and record the command
  and its output. If you do not, write the exact commands for the user into the report and
  do not claim that anything works on the host.
- Answer each question in `docs/13-open-questions.md` only with a measured fact or a
  decision the user made; otherwise leave it open with its default.

### D1 OpenAPI

- `tests/api/test_openapi.py` completed with every assertion of `docs/06-http-contract.md`
  section 1.11: paths present, `POST /auth/sign-in` 202 and 423 with `AuthResponse` and
  no `security`, `POST /setup/people/{id}/deactivate` 409 with `application/problem+json`
  referencing `ProblemDetails` and `security: [{"Bearer": []}]`, the security scheme, 401
  documented on every secured operation, the tags `Setup`, `Organization`, `Revenue`,
  `Petty cash`, `Central expenses` and `Reports` (as the .NET API names them), operation
  ids equal to the `operationId` column of
  section 2 (read the table from a fixture you write), the route present in testing and
  absent when `XCODE_OPENAPI_ENABLED` is false. Fix the routers' metadata until it passes;
  never relax an assertion.
- Schema names: the problem body schema is named `ProblemDetails`; the auth envelope
  `AuthResponse`.

### D2 Startup and readiness

- `main.py` lifespan in the order of `docs/08-operability.md` section 6: settings, logging,
  pool with a 30 s budget and the role check (`current_user` is `xcode_app`, else a
  warning), optional development auto-migrate and seed, `api.meta_contract_version()`
  compared with `EXPECTED_CONTRACT_VERSION` (refuse to start on mismatch, exit 1),
  `api.meta_unassigned_user_count()` logged as the warning sentence of `docs/07-auth.md`
  section 9 when positive, readiness true only after the version check.
- Readiness (`/health/ready`) runs `SELECT 1` within 10 s and checks the rate-limit backend
  when `postgres`; `text/plain` `Healthy`/`Unhealthy` per `docs/06-http-contract.md`
  section 1.10; the failure reason goes to the log line `health.ready.failed` only.
- Shutdown per section 7 (drain the mail queue for `XCODE_SHUTDOWN_GRACE_SECONDS`).
- Mail: plaintext SMTP is allowed in production only to a relay whose every address is
  the loopback interface (parity with the .NET rule of commit 553dd15), decided at
  startup with the same reading as `settings.connects_locally`; any other host keeps
  TLS. Evidence: settings tests for a loopback relay, a hostname that resolves
  elsewhere and a mixed list, and an `SmtpMailer` test against a local plaintext
  server.
- Evidence: `tests/api/test_operability.py`: a contract-version mismatch refuses startup;
  an unreachable database makes readiness 503 `Unhealthy`; the unassigned-user warning
  appears with a seeded user without membership; production settings without the key,
  host, from address or database URL exit 2 with every missing name listed
  (`ProductionStartupTests` parity); the log mailer and development codes outside their
  environments exit 2.

### D3 Metrics

- Prometheus exposition on `GET /metrics` (no authentication; served on the API port only
  when `XCODE_METRICS_ENABLED=true`, default off; the proxy never forwards `/metrics`) with
  exactly the series of
  `docs/08-operability.md` section 5, using `prometheus-client` (add it to
  `requirements.txt` and the lock files). Labels never carry ids, phone numbers or
  addresses; `auth_refusals_total{reason}` uses the internal reasons only.
- Evidence: `tests/api/test_metrics.py` (series present after one request of each kind;
  no high-cardinality label; the route is absent when the flag is off).

### D4 Response compression

- Gzip for responses under `/setup/` larger than 1 KiB when the client sends
  `Accept-Encoding: gzip` (Starlette `GZipMiddleware` restricted by path); never for
  `/auth/**` (the byte-for-byte rule) nor for health; `Vary: Accept-Encoding` on
  compressible routes. Brotli is not required (the clients accept gzip).
- Evidence: `tests/api/test_compression.py` (a large history page is compressed, an auth
  answer is not, `Vary` is present, `X-Request-ID` survives).

### D5 Demo seed

- `api.ops_seed_demo` per `docs/05-routines.md` section 5: the demo organization with its
  people (one per catalog role, phones and emails from `db/seeds/README.md`), companies,
  vehicles with targets and one away period, the expense catalogue, scheduled items of
  every frequency, investments and six weeks of revenue with gaps and corrections, created
  through the same helpers the business routines use (`tenancy.record_change` included,
  so the history is realistic); idempotent (`created: false` on a second run); refused
  outside development by the CLI and by a check of `XCODE_ENV` passed as a parameter
  (`p_environment`, the routine refuses anything but `development`).
- `xcode-api seed-demo` as `xcode_operator`; `XCODE_DEMO_SEED=true` runs it at startup in
  development only (settings refuse it elsewhere).
- `tests/support/scenario.py`: a scenario builder the tests use that calls the same
  routines (replaces the .NET `RevenueTestData` and `ExpenseItemTestData` helpers listed in
  `inventory-tests.md` section 1), plus a `seed_10x` helper that multiplies the demo seed
  for `EXPLAIN` runs.
- Evidence: `tests/db/test_ops_routines.py` extended (seed twice; counts; every seeded
  organization passes `db verify`'s data checks; refused for `production`);
  `tests/api/test_cli.py` (`seed-demo` refused outside development).

### D6 CLI completion

- `cli/main.py` registry complete: `serve`, `db ...`, `provision-user`, `remove-user`,
  `clear-pause`, `revoke-sessions`, `account-state`, `seed-demo`, `openapi`,
  `settings-check`; `--help` for each; exit codes 0, 1 (refusal), 2 (settings or usage);
  every command that changes state records `ops.operator_actions` with `XCODE_OPERATOR`.
- Evidence: `tests/unit/test_cli.py` (registry equals the table of
  `docs/08-operability.md` section 8; help texts name no secrets), `tests/api/test_cli.py`.

### D7 Deployment and CI finish

- `deploy/Dockerfile` final per `docs/08-operability.md` section 9 (digest pinned and
  recorded in `deploy/README.md` with the date; read-only root filesystem; `/tmp` tmpfs
  documented for the platform; healthcheck on `/health/live`); `.dockerignore`.
- `.github/workflows/xcode-api.yml`: jobs `lint`, `typecheck`, `test`, `audit`,
  `db-verify` (fresh database: `db migrate && db status && db verify`, plus `seed-demo`
  and a second `db verify`), `image` (build, vulnerability scan failing on critical
  findings, run the container and assert `id -u` is 10001, push on tags only).
- `deploy/runbook.md` with every entry of `docs/08-operability.md` section 10 written as
  numbered steps with the exact commands and log event names; `deploy/README.md`
  connection-limit table filled for the compose environment (1 replica, pool max 10 ->
  limit 14).
- `deploy/README.md` gains a section for the cPanel host built from D0's facts: how the
  process runs with its lifespan, the measured thread count, the roles, where secrets
  live, how a release is verified; where a fact is missing, the open question number.
- `docs/08-operability.md` section 2 settings table, `.env.example` and
  `tests/unit/test_settings.py` matrix agree on every setting (add `XCODE_METRICS_ENABLED`,
  `XCODE_SHUTDOWN_GRACE_SECONDS` if missing, `XCODE_EMAIL_TIMEOUT_SECONDS` from prompt 04).

## Invariants at the end

- `xcode-api openapi` output passes every assertion of `docs/06-http-contract.md`
  section 1.11; the document is served only when enabled.
- The process starts as `xcode_app` only; no command of the service reads
  `XCODE_DATABASE_OPERATOR_URL` or `XCODE_MIGRATION_DATABASE_URL`.
- `/auth/**` answers are never compressed; every response still carries the security
  headers and `X-Request-ID`.
- Every safety switch of `docs/08-operability.md` section 11 is refused outside its
  environments by the settings test matrix.
- Lint, types, all tests green; `db verify` exit 0; the image builds (or Docker's absence
  is reported); no TODO/FIXME; no plan or prompt identifiers.

## Verify (paste the outputs into the report)

```
cd apps/api-python
ruff check . && ruff format --check . && mypy
pytest <the test modules you touched> -q
pytest -n 3 -q -p no:cacheprovider > <scratchpad>/full.log 2>&1
xcode-api db migrate && xcode-api db routines && xcode-api db verify ; echo "exit=$?"
XCODE_ENV=development XCODE_DATABASE_OPERATOR_URL=... xcode-api seed-demo ; echo "exit=$?"
xcode-api openapi > <scratchpad>/openapi.json && python -c "import json,sys;d=json.load(open(sys.argv[1]));print(len(d['paths']))" <scratchpad>/openapi.json
docker build -f deploy/Dockerfile -t xcode-api:dev . && docker run --rm xcode-api:dev --help   # only where Docker exists
xcode-api serve --port 5055 &   # a free port: a .NET Kestrel often holds 5000 locally
curl -s -i localhost:5055/health/ready
```

Run the touched modules while you work and the full suite once at the end, in the
background, with its log in your scratchpad; report passed, failed, skipped and errors
from the log. Before that run, drop `xcode_template` if you changed a migration or routine
file, after checking that no other session's run uses the cluster (`docs/09-testing.md`
section 5).

## Challenge pass (before the report)

Apply `docs/14-verification.md` to your own work as if nobody, including you earlier in
this session, had reviewed it:
1. Steelman: list every deliverable bullet and invariant above as a claim, with the code
   that carries it.
2. Falsify: for each claim, name the observation that would disprove it and look for it;
   grade the evidence (section 5). Tenancy, security and integrity claims need grade A.
3. Run the five modes over D2 (startup refusals), D6, D7 (threads and connections on the real host), D8 and D9 (hosting facts, supply chain, the mail and database TLS rules), plus D10 (tests as evidence) and D11 (documents);
   give every probe of section 4 for those domains a verdict.
4. Try to refute each finding; fix the survivors with a test that fails first, or record
   them (corrected document, open question, residual risk).
5. Report the findings table (section 7), the conceded challenges with the guard that
   defeated each, and the three hardest attacks for any domain without findings.

This pass does not replace the separate `verify.md` run on this prompt; it makes that run
cheaper.

## Report format

1. Checklist: one row per deliverable D1 to D7 and per bullet: done or not, `file:symbol`,
   test name.
2. Verify outputs, trimmed.
3. Deviations from the documents with reasons; document lines changed.
4. Platform settings that cannot be created from the repository (secrets, proxy, TLS,
   `pg_hba`), listed for the operators.
5. What remains before the rename to `apps/api` (`docs/13-open-questions.md` question 14).

Add the challenge-pass results and the drift-check corrections as the last section of
the report.

## House rules

- Shared tree: `git status` first; edit only under `apps/api-python/` and the one
  workflow file; never revert or reformat others' changes; never kill processes you did
  not start; never bare `git stash`.
- No commits unless the user asks. No AI attribution anywhere.
- No comments unless needed; no plan or prompt identifiers anywhere; names per
  `docs/11-naming.md` (`xcode`, never `Auth`).
- Never weaken a test to make it pass. If a document is wrong, fix the document and report
  it.
