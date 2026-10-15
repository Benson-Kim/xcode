# Architecture

## 1. Shape in one paragraph

A stateless FastAPI process receives HTTP, authenticates the bearer token, validates the
request body into a Pydantic model, builds a command and hands it to a use case. The use
case depends only on ports (repositories, clock, token issuer, PIN hasher, mailer, rate
limiter) and on the pure domain vocabulary; it tells a repository to perform a command and
receives an outcome. The repository implementation (a "routines gateway") opens one
transaction on a pooled psycopg connection, calls one PostgreSQL routine in schema `api`,
translates any SQLSTATE into a typed domain error and returns typed domain records. The
routine, running as `xcode_api_executor` under row-level security, enforces authorization,
tenant scope, invariants and concurrency, and writes the data. Business rules that touch
data therefore live in SQL files a DBA can read end to end; the Python domain holds the
pure vocabulary and the few rules the API tier must apply itself; Python adapters own the
HTTP contract, cryptography, configuration, mail and observability.

## 2. Rings and the dependency rule

Dependencies point inwards only. The inner rings know nothing about the outer ones.

```
          inbound adapter                                   outbound adapters
   http/  (FastAPI routers, schemas,      ----->   application/  <-----   db/        (repositories = routine gateways)
           dependencies, middleware)                (use cases,            security/  (tokens, PIN and code hashing)
                                                     ports, commands)       infra/     (clock, mail, logging, rate limit)
                                                        |
                                                        v
                                                     domain/
                                       (entities, value objects, enumerations,
                                        outcomes, refusal errors, pure policies)

   composition root: main.py (create_app), container.py (build_container), cli/
```

Mapping to the three-layer rule "UI -> Domain <- Data":

| Layer in the rule | Here | Platform it may know |
|---|---|---|
| UI (screens, state holders, platform-specific) | `http/` routers (the screens), Pydantic request/response models (the state holders), middleware | FastAPI, Starlette, Pydantic |
| Domain (use cases -> entities + business rules; pure) | `application/` (use cases, ports, commands) and `domain/` (entities, values, policies) | standard library only |
| Data (repository implementations owning connections, caches, clients) | `db/` (PostgreSQL repositories), `security/`, `infra/` | psycopg, PyJWT, aiosmtplib, prometheus-client (`infra/metrics.py` only), XlsxWriter and ReportLab (`infra/exports/` only), structlog |

Import rules, enforced by `tests/unit/test_layers.py` (an `ast` walk over every module in
`src/xcode_api`; no third-party tool):

1. `xcode_api.domain` imports the standard library only. No pydantic, no settings, no
   framework, no driver, no other package module.
2. `xcode_api.application` imports `domain` and the standard library. It must not import
   `fastapi`, `pydantic`, `psycopg`, `jwt`, `aiosmtplib`, `structlog`, `xcode_api.settings`,
   or any adapter package.
3. `xcode_api.http` imports `application`, `domain`, `settings`, FastAPI/Starlette/Pydantic
   and structlog, plus the `Container` type from `container`. It never imports `db`,
   `security` or `infra`; the adapters it needs arrive through the container (section 5).
4. `xcode_api.db`, `xcode_api.security`, `xcode_api.infra` import `application.ports`,
   `application.repositories`, `application.errors`, `domain`, `settings` and their own
   third-party library. They never import `http` or each other.
5. `xcode_api.settings` imports nothing from the package.
6. `xcode_api.main`, `xcode_api.container`, `xcode_api.cli` are the composition root and may
   import everything.

Because the inner rings are pure, every use case runs in a unit test with in-memory fakes
of its ports and no framework, no database and no network (`tests/unit/test_use_case_*.py`,
fakes in `tests/support/fakes.py`). Those tests prove orchestration: which port is told what,
in which order, and what outcome is returned. They are not evidence for a business rule;
rules live in routines and are proven in `tests/db/` against PostgreSQL.

## 3. What lives where

### `domain/` (pure)

| Module | Holds |
|---|---|
| `errors.py` | the refusal vocabulary: `SessionInvalid`, `Forbidden`, `NotFound`, `Conflict`, `RuleViolation`, `CapExceeded`; each carries a stable `code` (snake_case) and a `detail` mapping, nothing HTTP |
| `values.py` | value objects with their normalisation rules: `PhoneNumber`, `Pin`, `Email`, `Money`, `Version`, `PageRequest` (`MAX_PAGE_SIZE = 100`), `DeviceId` (opaque, bounded) |
| `identity.py` | `User`, `TrustedDevice`, `SignInAttempt`, `UserStatus`, `CodePurpose`, the sign-in operations, outcomes and refusals, `AccountState` and `AccountPolicy`, `AuthOutcome`, the envelope (`AuthEnvelope`, `EnvelopeStatus`), `AccessGrant`, `TokenClaims`, `Principal`, `SessionView`, and the commands of the `api.auth_*` and operator user routines |
| `tenancy.py` | `Organization`, `Membership`, `Role`, `Permission` (the wire names), `DataScope`, `ChangeLogEntry`, settings-section registry (`SettingsSection` descriptors: name, permission, payload kind) |
| `setup.py` | `PsvCompany`, `Vehicle`, `VehicleAwayPeriod`, `ExpenseItem`, `RecurringItem`, `RecurringSchedule`, `VehicleInvestment`, `VehicleTarget` (the dated weekly-target history) |
| `revenue.py` | `RevenueRecord`, `NoEarningsReason`, `CellStatus`, `DashboardPeriod`; the week view, dashboard and capture records arrive with the revenue feature |
| `pettycash.py` | `PettyCashEntry`, `PettyCashKind`, `PettyCashStatus`, overview, float, figures and dashboard records, the save command |
| `policies.py` | the pure rules the API tier applies itself because the database cannot: uniform refusal shaping for sign-in (`refusal_answer()` is the one answer every refusal gets; `envelope_for(outcome)` maps a routine outcome to the envelope), PIN shape before hashing (`pin_shape_valid`, `PIN_FLOOR`), the dummy-hash rule for unknown accounts (`needs_dummy_hash`), `UNTRUSTED_DEVICE_LIMIT` |

Entities are frozen dataclasses whose field names are the domain vocabulary
(`docs/11-naming.md`). Enumerations that reach the wire as strings are `StrEnum`s whose
values are those strings; enumerations that reach the wire as integers (`kind`, `frequency`,
`bucket`, the no-earnings reason) are `IntEnum`s whose values are the code-table integers of
`docs/04-schema.md` section 2. `tests/db/test_enum_parity.py` asserts that each code table
and each `CHECK` list holds exactly the enum's members, so there is one source and one
parity check, not two sources.

The Python domain is small by design. Rules that need data (uniqueness, versions, caps,
lockout, tenant scope, due-date generation, week arithmetic over stored records) are
"entity behaviour" implemented in routines, where DBAs review them. `domain/` never grows a
second copy of such a rule.

### `application/` (use cases and ports; pure)

| Module | Holds |
|---|---|
| `ports.py` | `Clock`, `TokenIssuer`, `PinHasher`, `CodeHasher`, `SecretSource`, `CodeMailer`, `Mailer`, `RateLimiter` Protocols |
| `repositories.py` | `IdentityRepository`, `TenancyRepository`, `SetupRepository`, `RevenueRepository`, `PettyCashRepository`, `OpsRepository` Protocols: one async method per routine in `docs/05-routines.md`, typed with domain commands, records and outcomes |
| `errors.py` | `TransientFailure`, `IntegrityBug`: failures of the data layer surfaced at the use-case boundary (not domain refusals) |
| `auth/`, `access/`, `organization/`, `setup/`, `revenue/`, `pettycash/`, `ops/` | one module per use case, named `<verb>_<noun>.py`, containing the `<Verb><Noun>Command` (or `...Query`) frozen dataclass and the `<Verb><Noun>` class with `__init__(ports it needs)` and `async def execute(command) -> outcome` |

A use case is where "who" and "when" are attached: it receives the authenticated actor and
the organization from the caller, takes `now` from the `Clock`, builds the repository call,
and maps the outcome. It never reads state to decide whether a write is allowed; it sends
the command and the routine decides (`docs/00-principles.md` section 3). Pass-through use
cases exist and are short; they are still the only place an endpoint's command is assembled.

There is no unit-of-work abstraction: one repository call is one transaction that has
committed when the `await` returns, so "after commit" is simply the next statement in the
use case (this is how a verification mail is enqueued only after the code row exists).

### Adapters

| Module | Responsibility | Must not |
|---|---|---|
| `http/middleware.py` | request id (honour `X-Request-ID`, else UUID4), trusted-proxy client address, request log line, security headers (`Cache-Control: no-store`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`), request body cap (1 MiB, 413) | parse bodies, decide anything |
| `http/errors.py` | handlers: domain refusals and `RequestValidationError` to the status and body the contract pins, with `requestId`; `TransientFailure` to 503; `IntegrityBug` and unexpected exceptions to 500 without detail | log request bodies |
| `http/dependencies.py` | `container(request)`, `current_principal` (verify token through `TokenIssuer`, resolve the session through the `ResolveSession` use case, bind log context), `client_address`, `auth_rate_limit` | construct adapters, check permissions |
| `http/schemas/*.py` | Pydantic request/response models per feature with camelCase aliases; `common.py` has `Page[T]`, `Problem`, `Money`; conversion `to_command()` / `from_record()` | import use cases, hold rules |
| `http/routers/*.py` | one module per feature area; each handler: parse, build command, call one use case, map outcome to status and response model | branch on domain state beyond the outcome discriminator |
| `db/pool.py` | `open_pool(settings)`, connection configure hook (`application_name`, UTC, role check), `statement_counter` for tests | SQL text |
| `db/session.py` | `call(conn, routine, *args, row=...)`: one transaction per call, retry policy for transient SQLSTATEs on calls marked idempotent, DEBUG timing log | business decisions |
| `db/errors.py` | the SQLSTATE translation table from `docs/03-database.md` section 5 | anything else |
| `db/types.py` | composite-row adapters: `api.<noun>_row` to domain records | |
| `db/routines/identity.py` etc. | `IdentityRoutines`, `TenancyRoutines`, `SetupRoutines`, `RevenueRoutines`, `OpsRoutines`: the repository implementations, one typed method per routine | string-build SQL from input, import `http` |
| `db/migrate.py` | the runner from `docs/03-database.md` section 7 | application imports |
| `security/tokens.py` | `JwtTokenIssuer` (HS256): issue, verify (current key, then previous keys), claims extraction | database access |
| `security/pins.py` | `Pbkdf2PinHasher`: hash, constant-time verify, dummy hash for unknown accounts, derivations on a bounded pool of its own (2 threads, 16 waiting, `TransientFailure` past it) | logging |
| `security/codes.py` | six-digit code generation with `secrets` and its format | mail |
| `security/refresh_tokens.py` | opaque 48-byte token generation | storage |
| `security/secret_source.py` | `RandomSecretSource`: the `SecretSource` port over the two generators above | |
| `security/digests.py` | `keyed_digest`: HMAC-SHA256 with the signing key, upper-case hex, for codes and refresh tokens (`docs/07-auth.md` section 1) | anything else |
| `infra/clock.py` | `SystemClock` (tests use `ManualClock` from `tests/support`) | |
| `infra/mail.py` | the verification message, `SmtpMailer`, `LogMailer`, `MailQueue` (enqueue with a failure callback, drain on shutdown), `VerificationMailer` (the `CodeMailer` port: send before the reply within the mail timeout, or queue after it) | template logic beyond the two messages |
| `infra/logging.py` | structlog configuration, stdlib bridge, redaction processor | |
| `infra/rate_limit.py` | `MemoryRateLimiter`, `PostgresRateLimiter` (through `OpsRepository.rate_limit_hit`) | |

### Composition root

| Module | Responsibility |
|---|---|
| `settings.py` | `Settings` (pydantic-settings, `XCODE_` prefix), `Environment`, cross-field validation, `Settings.for_tests()` |
| `container.py` | `Container`: frozen dataclass of adapters and use cases; `build_container(settings, pool, *, clock=None, mailer=None, rate_limiter=None, ...)` builds the real adapters and lets tests substitute any port |
| `main.py` | `create_app(settings, container=None) -> FastAPI`: lifespan (pool open/close, startup checks, mail drain), middleware order, router list, exception handlers; stores the container on `app.state` |
| `cli/main.py` | `xcode-api serve|db ...|provision-user|remove-user|clear-pause|revoke-sessions|seed-demo|openapi` (argparse); builds a container and calls use cases; never contains rules |

## 4. The data layer owns its machinery

Mirroring "repositories own DB caches and API clients":

- A repository implementation owns the pool handle it is given, the per-call transaction,
  the retry policy, SQLSTATE translation and the statement counter. Use cases never see a
  connection.
- Any cache, if one is ever justified, lives inside the adapter that implements the port,
  with explicit invalidation and a test that a stale read is impossible after the write
  that should invalidate it. Use cases and routers never cache. Today there is no cache:
  the .NET session cache accepted revoked tokens and was removed, and the .NET
  history-count cache is replaced by a routine that returns the count.
- The SMTP client is owned by `SmtpMailer`; the JWT library by `JwtTokenIssuer`. No other
  module imports them.
- A repository method maps one routine. Composing two routine calls in a repository method
  is forbidden; composition happens in the use case so the transaction boundaries stay
  visible.

## 5. Request lifecycle

1. Middleware assigns the request id, resolves the client address (peer, or the last
   untrusted hop of `X-Forwarded-For` when the peer is in `XCODE_TRUSTED_PROXIES`), binds
   structlog context, rejects oversized bodies.
2. Router dependency `auth_rate_limit` (auth surface only) asks the `RateLimiter`; a refusal
   is 429 with an empty body and `Retry-After` (`docs/06-http-contract.md` section 1.8).
3. Dependency `current_principal` verifies the JWT (algorithm pinned, `iss`/`aud`/`exp`,
   zero leeway) and runs the `ResolveSession` use case, which calls
   `api.auth_resolve_session(sub, version, device, now)`. Any failure is the uniform 401.
   The principal carries `user_id`, `device_id`, `security_version` and the memberships the
   routine returned. Nothing is cached between requests.
4. The organization in scope comes from the route or header the contract defines
   (`docs/06-http-contract.md`); the router passes it into the command untouched. The
   routine decides whether the actor may act there (`tenancy.enter_organization`). Today
   the organization is the token's `org` claim: every `/setup/**` route acts in it.
5. The use case calls the repository; the repository runs one transaction. Outcome returns.
6. The router maps the outcome to the response model and status; exception handlers map
   refusals to the contract's status codes and bodies.
7. The middleware writes one log line: `route`, `method`, `status`, `duration_ms`,
   `request_id`, `actor_id`, `organization_id`, `statements`.

## 6. Error model (HTTP)

- Default body is RFC 9457 problem details (`application/problem+json`) with `type`,
  `title`, `status`, `detail`, `instance`, plus `requestId` and `traceId` extensions.
  Where the .NET contract returns a specific body (the seven-property auth envelope with
  `status`, a 409 body with the current record, the plain `{detail}` of the organization
  section save), `docs/06-http-contract.md` names it and the
  router returns exactly that; the exception handler is the fallback, not a second
  contract.
- 401 and sign-in refusals never say why. 404 vs 403 follows the contract per endpoint.
- Validation failures return the status the contract pins per endpoint (the .NET contract
  uses 400 with `Results.ValidationProblem` in most places) with the field list in `errors`.
- 500 bodies carry `requestId` only; the exception type goes to the log.

## 7. Concurrency and idempotency

- Every row update carries `expectedVersion` from the client (header or body, per contract)
  into `p_expected_version`; the routine raises `XC409`; the router returns 409 with the
  body the contract specifies.
- Revenue capture: the natural key (vehicle, day) is the unique key; there are no
  client-supplied ids and no idempotency keys (the one exception in the whole contract is
  the petty-cash entry create, whose optional `id` is the phone's replay key). The routine
  returns `outcome = 'replayed'`
  with the stored record when the same key arrives again with an identical payload, and
  otherwise follows the step order of `docs/06-http-contract.md` section 2 (row R03).
- The change log is append-only. Every logged change (settings, setup, people, revenue)
  takes the next `tenancy.organizations.settings_version` in the same transaction, as the
  .NET API does: history versions, `nextBefore` and the dashboard cache key depend on it.
  The hot row is accepted knowingly (`docs/04-schema.md` section 4.1).
- Transient retry: `db/session.py` retries `40001`, `40P01`, class `08` up to 3 times with
  jittered backoff, only for calls the repository marks idempotent (reads and keyed
  commands).

## 8. Locality: bugs local, changes cheap

Each kind of knowledge has one home and one test that pins it. A change of one kind touches
the files in its row and nothing else; a pull request that touches more explains why.

| Kind of knowledge | Home | Pinned by |
|---|---|---|
| A status code, header or JSON shape | `http/schemas`, `http/routers`, `http/errors.py` | `tests/api/test_<feature>.py` |
| A business rule or invariant | one routine in `db/routines/` plus a constraint | `tests/db/test_<area>_routines.py` |
| Authorization and tenant scope | `tenancy.require_permission`, `tenancy.enter_organization`, RLS policies | `tests/db/test_tenancy_isolation.py`, `test_structure.py` |
| Vocabulary (names, enum values, record fields) | `domain/` | enum/CHECK parity test, mypy |
| Orchestration (order of port calls, after-commit effects, uniform refusals) | one use case module | `tests/unit/test_use_case_<name>.py` with fakes |
| Cryptographic parameters | `security/` | `tests/unit/test_pin_hasher.py`, `test_digests.py`, `test_tokens.py` with fixed vectors |
| Configuration and safety switches | `settings.py` | `tests/unit/test_settings.py` matrix |
| Routine call shape and SQLSTATE translation | `db/session.py`, `db/errors.py`, `db/routines/*.py` | `tests/db/test_gateway.py` |
| Schema | `db/migrations/` | `tests/db/test_structure.py`, `db verify` |
| Wiring | `container.py`, `main.py` | `tests/api/test_operability.py` startup tests |

Consequences implementers can rely on: a wrong HTTP answer is a bug in `http/`; a wrong
decision is a bug in one routine; a tenant leak is impossible from Python because the
policy sits in the database; swapping SMTP, rate-limit storage or the clock is one adapter
file; a new permission is one row in the permissions seed, one enum member and the routine
that requires it; a new endpoint is the checklist in section 9 and nothing outside it.

## 9. How to add an endpoint (checklist)

1. Contract first: add the endpoint row to `docs/06-http-contract.md` (status codes, bodies,
   permission, statement budget).
2. Schema: if a table or column changes, add `db/migrations/NNNN_*.sql` and `.down.sql`,
   update `docs/04-schema.md` including indexes.
3. Routine: add `db/routines/<area>/<name>.sql` following section 4 of
   `docs/03-database.md`; add its catalogue entry to `docs/05-routines.md`.
4. Routine test: `tests/db/test_<area>_routines.py` covering happy path, each `XC` error,
   tenant isolation, and version conflict if it writes.
5. Domain: add or extend the record, enum or value object in `domain/`.
6. Port: add the method to the repository Protocol in `application/repositories.py`; add the
   fake's implementation in `tests/support/fakes.py`.
7. Repository: one typed method in `db/routines/<area>.py`.
8. Use case: `application/<area>/<verb>_<noun>.py` with its command; a unit test only when it
   orchestrates more than one port.
9. Pydantic request/response models; router handler; include the router in `main.py`; wire
   the use case in `container.py`.
10. HTTP test in `tests/api/test_<feature>.py`: status codes, body shape, auth and permission
    refusals, statement budget.
11. Operability: no new setting without `.env.example` and `docs/08-operability.md`.
12. Run `ruff`, `mypy`, the tests, and `xcode-api db verify` against the test database.

## 10. What is deliberately not here

- No in-process caches of users, sessions or permissions (see section 4).
- No background scheduler inside the API process beyond the mail queue. Recurring-item due
  date generation is computed by routines on read (as the .NET `DueDateGenerator` does) or
  by an explicit CLI command if a materialised form is ever needed.
- No ORM, no SQLite, no reflection-based repository, no generic CRUD base class.
- No second copy of a rule in Python "for a quick check". Shape and normalisation happen at
  the edges; decisions happen in routines.
