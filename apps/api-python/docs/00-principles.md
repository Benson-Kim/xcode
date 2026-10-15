# Principles and how this codebase enforces them

This document is normative. Every prompt in `docs/prompts/` cites it, every reviewer checks
against it, and a pull request that violates a rule here is not done. Each principle is
stated once, then turned into rules that can be checked against code, and into the
mechanism in this project that carries it.

The project is **xcode**: a revenue-management API for passenger-service-vehicle (PSV)
operators. "Auth" is one feature of it, never the name of the project, package, database,
schema, settings section or test project.

## 1. DRY (Don't Repeat Yourself)

Meaning: every piece of knowledge has one authoritative representation. Duplication of
*knowledge* (a rule, a constant, a contract shape) is the problem, not duplication of
characters.

Rules:
- A business rule lives in exactly one PostgreSQL routine or constraint. Python never
  re-implements it "for a quick check"; it validates shape and normalises values, the
  database decides.
- Authorization lives in one SQL function (`tenancy.require_permission`), called through
  `tenancy.enter_organization` by every tenant-scoped `api.*` routine. Routers and use cases
  do not test permissions.
- SQL text appears in Python only inside `src/xcode_api/db/routines/*.py`, and only as a
  routine call. No table names in Python outside the migration runner and the structural
  tests.
- Vocabulary (enum values, record fields, error codes) is defined once in `domain/`; where
  the database must know the same values (`CHECK` constraints), a parity test proves both
  agree rather than a second hand-maintained list.
- One `Settings` class, one error-translation table, one problem-details encoder, one
  request-logging middleware, one pagination type, one money type, one container.
- Test fixtures are shared through `tests/conftest.py` and `tests/support/`; a scenario
  builder (an organization with an owner and a vehicle) is written once; fakes of the ports
  are written once in `tests/support/fakes.py`.
- Documentation of a contract lives next to its single source: the OpenAPI document is
  generated from the Pydantic models, never hand-maintained.

Smells that fail review: the same validation message in SQL and Python; two routines that
compute "effective permissions"; two JSON encoders for dates; copy-pasted router bodies; a
use case that re-checks what the routine it calls already checks.

## 2. SOLID

### Single responsibility
Each ring changes for one reason (`docs/01-architecture.md` section 2):
- `domain/`: the vocabulary and the few pure rules of the business.
- `application/`: use cases: assembling a command from actor, organization and time, telling
  a port, mapping the outcome.
- `http/`: the HTTP contract (paths, status codes, header names, JSON shapes).
- `db/`: speaking to PostgreSQL (pool, transactions, routine calls, SQLSTATE translation).
- `db/routines/*.sql`: business rules and data integrity.
- `security/`: cryptography (tokens, PIN hashing, code hashing, constant-time compare).
- `infra/`: adapters for the outside world (SMTP, logging, clock, rate-limit storage).
- `container.py`, `main.py`, `cli/`: wiring.

### Open/closed
Adding a feature adds files; it does not edit a switch statement:
- a new settings section registers a descriptor in the domain registry and a payload model;
- a new mail or rate-limit backend is a new adapter selected by configuration;
- a new endpoint is a new use case, a new routine, a new repository method and a router
  handler, included by the app factory's router list and the container.

### Liskov substitution
Every adapter for a port (in-memory rate limiter vs PostgreSQL rate limiter; log mailer
vs SMTP mailer; test clock vs system clock; fake repository vs routines gateway) honours the
port's documented contract, including failure behaviour. Tests for a port run against every
adapter (`tests/unit/test_rate_limiter_contract.py` is parametrised over adapters; the fakes
in `tests/support/fakes.py` carry the same docstring contract as the routines they stand in
for, and `tests/db/test_fakes_match_routines.py` runs the shared contract cases against both).

### Interface segregation
Ports are small `typing.Protocol`s: `Clock`, `TokenIssuer`, `PinHasher`, `CodeHasher`,
`Mailer`, `RateLimiter`, and one repository per bounded context (`IdentityRepository`,
`TenancyRepository`, `SetupRepository`, `RevenueRepository`, `OpsRepository`). A use case
receives only the ports it uses. No "God repository", no service locator.

### Dependency inversion
Dependencies point inwards: `http/` -> `application/` <- `db/`, `security/`, `infra/`; both
depend on `domain/`; `domain/` depends on nothing. Ports are declared in `application/` and
implemented outside it. Wiring happens once, in `container.py`, consumed by `main.py` and
`cli/`. Tests substitute ports through the container, never by monkey-patching modules.
`tests/unit/test_layers.py` fails on any import that points outwards.

## 3. Tell, don't ask

Meaning: send a command to the object that owns the state and let it decide; do not fetch
state, decide outside, then write back.

Rules:
- Use cases issue commands to repositories (`revenue.capture`, `tenancy.create_person`,
  `identity.sign_in`) and receive an outcome. They never read a row to decide
  whether a write is allowed.
- Read-modify-write cycles in Python are forbidden. Optimistic concurrency is expressed as
  an `expected_version` parameter; the routine compares and raises `XC409`.
- Where cryptography forces a round trip (the PIN hash must be verified in Python, the
  database must never see a PIN), the database still owns the decision state machine:
  `api.auth_account_lookup` returns the material to verify, `api.auth_sign_in` records
  the verdict under the account's row lock and decides. Python contributes only the verdict.
- Routers map outcomes to HTTP; they do not inspect domain state to branch, beyond the
  outcome discriminator the routine returned.

## 4. Integrity

Meaning: data can never reach a state the domain forbids, regardless of which code path,
client, replica or operator touched it.

Rules:
- Invariants are enforced by the database: `CHECK`, `UNIQUE`, `FOREIGN KEY`, `NOT NULL`,
  exclusion constraints for date ranges, and routine preconditions. Python validation is a
  courtesy for error messages, never the only guard.
- Tenant isolation is enforced twice: every routine scopes by the verified organization,
  and row-level security (RLS) on every tenant table makes a forgotten predicate return no
  rows instead of another tenant's rows. The application role has no table privileges at
  all (`docs/03-database.md`).
- Every concurrency token (`version` columns) is bumped by the routine that writes the row,
  compared against `expected_version` on update, and covered by a test that proves a stale
  writer gets `XC409` and therefore HTTP 409.
- Replayable commands (revenue capture, keyed by vehicle and day; petty-cash entry create,
  keyed by the client-supplied entry id) rely on a unique constraint, not on a prior
  `SELECT`: an identical repeat answers with the stored row and no second change-log row.
  No other client-supplied ids or idempotency keys exist.
- Every command runs in exactly one transaction; one routine call is one transaction unless
  a use case documents why it needs two.

## 5. Scalability

Meaning: throughput grows by adding replicas and database capacity, not by rewriting.

Rules:
- The API process is stateless: no in-process locks keyed by account (PostgreSQL row locks
  replace the .NET `AuthGate`), no caches whose invalidation another replica could miss.
- One request means one routine call for the common path; the budget per endpoint is
  recorded in `docs/06-http-contract.md` and asserted by tests through the repository's
  statement counter.
- Paging is capped (`page_size` at most 100) in one domain constant and again in the
  routine, with a parity test.
- Every query a routine runs has an index listed for it in `docs/04-schema.md`.
- No hot rows: a capture must not update a per-organization counter row. Ordering uses
  sequences, not `max()+1`.
- CPU-bound work (PBKDF2) runs in a worker thread; the event loop is never blocked.
- Connection pool bounds, statement timeouts and lock timeouts are set per role in the
  database, so a slow query cannot pile up connections.

## 6. Extensibility

Meaning: the next feature (bulk import/export, a second currency, a new settings section,
a new revenue source) fits without touching unrelated code.

Rules:
- Schemas per bounded context (`identity`, `tenancy`, `setup`, `revenue`, `ops`) and a
  single callable surface schema (`api`).
- Routines are versioned by file and applied idempotently; a signature change is a
  migration plus an updated routine file, never an edit that silently breaks callers.
- Pydantic models are per contract version; a breaking HTTP change ships under a new path
  version, documented in `docs/06-http-contract.md`.
- "How to add an endpoint" is a checklist in `docs/01-architecture.md`; if a step is not on
  the checklist, the design is wrong, not the checklist.
- The locality table (`docs/01-architecture.md` section 8) predicts which files a kind of
  change touches; a change that spills outside its row is a design defect to fix, not a
  habit to accept.

## 7. Reliability

Meaning: correct behaviour under failure: database restarts, mail outages, concurrent
writers, process kills mid-request, deploys.

Rules:
- Transient PostgreSQL failures (`40001`, `40P01`, class `08`) are retried a bounded number
  of times, only for idempotent commands, with jittered backoff. Nothing else is retried.
- Timeouts everywhere: statement, lock, idle-in-transaction (database side); request body
  read, SMTP connect/send (application side).
- Graceful shutdown: stop accepting, finish in-flight requests, drain the mail queue for at
  most 10 s, close the pool.
- Schema changes are a separate step (`xcode-api db migrate`) run before the new release
  starts; the service never migrates at startup outside development.
- Mail is enqueued only after the transaction that created the code committed, so a
  rolled-back attempt never sends a code.
- Tests run against real PostgreSQL (`docs/03-database.md` says which versions have
  actually run). There is no SQLite, no mocked database.

## 8. Operability

Meaning: the people running it can see what it is doing, change its configuration safely,
and fix it at 3 a.m. without reading the source.

Rules:
- JSON logs outside development; every line carries `request_id`, `actor_id` (when
  authenticated), `organization_id` (when scoped), `route`, `status`, `duration_ms`.
  Never bodies, PINs, codes, tokens, phone numbers or emails.
- `X-Request-ID` is honoured when sent, generated when not, returned always, and included
  in every problem-details body as `requestId`.
- `/health/live` (process up), `/health/ready` (database reachable within 10 s, else 503),
  `/health` (legacy 200 `{ "status": "ok" }`, which the staging start script depends on).
- Configuration only through `XCODE_*` environment variables, validated at startup;
  the process refuses to start on a bad or missing production setting.
- One CLI, `xcode-api`, for `serve`, `db migrate|routines|status|verify`, `provision-user`,
  `remove-user`, `clear-pause`, `revoke-sessions`, `seed-demo`, `openapi`. Every
  operator action is recorded in `ops.operator_actions` with the operator's name.
- The routine catalogue (`docs/05-routines.md`) is the DBA's map; `db verify` proves the
  database matches it (ownership, security definer, search_path, grants, RLS).

## 9. Safety

Meaning: safe by default; dangerous behaviour needs explicit, named, environment-checked
opt-in; nothing destructive happens by accident.

Rules:
- Development-only features (log mailer, development codes in responses, demo seed,
  auto-migrate, OpenAPI route) each have their own flag and are refused when
  `XCODE_ENV` is not `development` (or `testing` where stated). The .NET
  `IsLocalDatabase` substring heuristic is not carried over.
- Migrations are forward-only with a reviewed `.down.sql`, applied by a runner that holds an
  advisory lock, verifies checksums of already-applied files, and refuses drift.
- Data backfills are separate migrations with row counts logged and a verification query.
- Sign-in refusal paths are uniform (unknown number, paused account, capped device look the
  same) and take similar time.
- The data migration from SQL Server runs in dry-run mode first and reports counts and
  checksums before any write to the target.

## 10. Security: zero trust

Meaning: no request, process, network position or role is trusted because of where it
comes from. Three tenets, applied to six pillars; the full matrix with mechanisms and the
test that proves each one is `docs/12-security.md`.

Tenets:
- Verify explicitly. Every request proves identity, device and session against the
  database (`api.auth_resolve_session`, no cache). Every routine re-verifies membership and
  permission (`tenancy.enter_organization`) even though the HTTP layer already
  authenticated: the database does not trust the application tier. Every input is validated
  at each gate it crosses (Pydantic shape, domain normalisation, routine and constraint).
- Least privilege. `xcode_app` can only execute `api.*`; routines run as a non-owner role
  under RLS; `xcode_readonly` has no policy on tenant tables and no access to `identity`
  until a DBA adds one; tokens carry identity, not permissions; permissions are explicit
  grants with anti-escalation rules in the database; the container runs as a non-root user
  on a read-only filesystem; migration credentials are not runtime credentials.
- Assume breach. A `security_version` bump ends every session of a user at once; reuse of
  a rotated refresh token revokes the family; signing-key rotation is supported without
  downtime (`XCODE_AUTH_PREVIOUS_SIGNING_KEYS`, verify-only); privileged actions are
  audited (`ops.operator_actions`, `tenancy.change_log`, `identity.sign_in_attempts`);
  refusals are counted (`auth_refusals_total`); secrets exist at rest only as hashes; logs
  redact; a compromised API process still cannot read another tenant's rows or any table
  directly.

Pillars (summary; mechanisms in `docs/12-security.md`):
- Identity: JWT HS256 with pinned algorithm, `iss`/`aud`/`exp`, zero leeway; per-request
  session resolution; PIN hashed with the .NET parameters, constant-time compare, dummy hash
  for unknown accounts; uniform refusals; lockout state owned by the database.
- Endpoints (devices): device id is opaque, bounded and untrusted; trust is a server-side,
  revocable record with optional expiry; untrusted devices are capped per account; a new
  device needs a verified email code.
- Data: RLS on every tenant table, privilege-less app role, `SECURITY DEFINER` routines with
  fixed `search_path`, TLS `verify-full` to PostgreSQL outside development unless the
  connection stays on the machine (Unix socket or loopback), hashes only for
  secret material, no PII in logs or error details, backups encrypted by the platform.
- Applications: parameterised routine calls only, no dynamic SQL from inputs, body size
  cap, security headers, exact CORS origins and trusted hosts, OpenAPI off in production,
  lock file plus `pip-audit`, problem details without stack traces.
- Infrastructure: minimal image pinned by digest and scanned in CI, non-root, read-only
  root filesystem, secrets injected at runtime and never baked or committed, separate
  roles with connection limits and timeouts, readiness that reveals nothing.
- Network: TLS at the proxy, forwarded addresses believed only from `XCODE_TRUSTED_PROXIES`,
  rate limiting on the sign-in surface, egress limited to PostgreSQL and SMTP, no outbound
  HTTP from the API.

## 11. Challenge

Meaning: nothing is done because it was reviewed before. Every claim of "done", "correct",
"secure" or "matches .NET" is attacked as if for the first time, and survives only with
evidence.

Rules:
- Every prompt ends with the challenge pass of `docs/14-verification.md`: the five modes
  (assumptions, falsification, pre-mortem, red team, dialectic) over the domains the change
  touched, plus tests-as-evidence and document accuracy every time.
- Earlier audits, validations, memory notes and documents are claims, not evidence; a
  verifier reads them only after their own pass.
- Every surviving challenge ends in a fix with a failing-first test, a corrected document,
  an open question with a default, or a recorded residual risk; never a bare objection.
- "Validated" means a run of `docs/prompts/verify.md` in a session that did not write the
  code, with its report in `docs/audit/`.

## Review checklist (paste into every PR description)

- [ ] Rule lives in one place (SQL routine/constraint), Python only validates shape.
- [ ] Router -> use case -> repository port -> routines gateway -> routine; no SQL outside
      `db/routines/*.py`; no import points outwards (`test_layers.py` green).
- [ ] Command style: no read-modify-write; `expected_version` where a row is updated.
- [ ] Constraint or routine precondition for every invariant touched, with a failing test.
- [ ] Every new tenant-scoped routine calls `tenancy.enter_organization`; RLS policy present
      on any new tenant table; `db verify` extended for new object kinds.
- [ ] No new privilege for `xcode_app` or `xcode_readonly`; new secret columns are hashes.
- [ ] Statement budget per endpoint recorded and asserted.
- [ ] New setting documented in `docs/08-operability.md` and `.env.example`, validated.
- [ ] No PII or secrets in logs or error `DETAIL`; request id present.
- [ ] Dev-only behaviour behind its own flag and refused outside development.
- [ ] The change touched only the files its locality row predicts, or the PR says why.
- [ ] Naming: `xcode` for the project, domain words for everything else, no plan IDs.
- [ ] Challenge pass done (`docs/14-verification.md`): findings fixed, documented or
      recorded; the verification report is linked.
