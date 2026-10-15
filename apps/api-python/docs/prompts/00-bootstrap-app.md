# Prompt 00: application bootstrap (no database)

Paste everything below the line into a fresh Claude Code session running Sonnet, started in
the repository root. Prompt 01 (database foundation) follows it.

Since it ran, later prompts changed some of its clauses; the code and `docs/01` to `docs/08`
decide, not the text below (verify run of 2026-10-11, `docs/audit/2026-10-11-verify-area-prompt-00.md`):
- D3: `Money` is positive (no `allow_negative`); `Version` starts at 0 for users and refresh
  tokens; `PageRequest` refuses `page` outside 1 to 100 000 and `page_size` outside 1 to 100
  instead of clamping (.NET `SetupContracts.cs`, `docs/06-http-contract.md` section 1.7);
  `DeviceId` is 1 to 128 code points without U+0000; `Email` allows 320 characters.
- D6: the `console` log format is allowed in development and testing (`docs/08` section 1).
- D8: the health routes skip the allowed-hosts check (`docs/06` section 1.10); every
  `X-Forwarded-For` line is read, as one list; `serve` leaves forwarded headers to
  `XCODE_TRUSTED_PROXIES` alone.

---

You are implementing the first slice of `apps/api-python`, the Python rewrite of the .NET
API in `apps/api`. This slice does not touch PostgreSQL. It produces the package skeleton,
settings, logging, HTTP plumbing, the composition root, the CLI skeleton, the container
image and CI, each with tests. The next prompt adds the database foundation on top of it.

## Read first, in this order

1. `CLAUDE.md` in the repository root (shared-tree rules, house rules).
2. `apps/api-python/README.md`.
3. `apps/api-python/docs/00-principles.md`.
4. `apps/api-python/docs/01-architecture.md` (all sections; section 2 is the import rule you
   will encode in a test).
5. `apps/api-python/docs/02-stack.md`.
6. `apps/api-python/docs/08-operability.md` sections 1, 2, 3, 4, 6, 7, 8, 9, 11.
7. `apps/api-python/docs/09-testing.md`.
8. `apps/api-python/docs/11-naming.md`.
9. `apps/api-python/docs/12-security.md` sections 2.4, 2.5, 2.6, 3.
10. `apps/api-python/docs/07-auth.md` section "Parameters" (defaults for the token-lifetime
    and PBKDF2 settings).
11. `apps/api-python/pyproject.toml`, `requirements.txt`, `requirements-dev.txt`,
    `.env.example`, `docker-compose.yml`, `deploy/README.md`, and every `README.md` under
    `src/` and `tests/`.

## Environment check, before any change

- `python --version` is 3.13 or newer; otherwise stop and report (do not install Python).
- `git status` in the repository root: note files other sessions are editing. You write only
  under `apps/api-python/` plus one new file `.github/workflows/xcode-api.yml`.
- In `apps/api-python`: create `.venv` (git-ignored), activate it,
  `pip install -e . -r requirements-dev.txt`.

## Deliverables

Each deliverable names its evidence: the module and the test that fails without it. No
TODO or FIXME comments; if a piece cannot be finished, the report says so.

### D1 Dependency lock files

- `uv pip compile requirements.txt -o requirements.lock.txt` and
  `uv pip compile requirements-dev.txt -o requirements-dev.lock.txt`. Generated files, never
  edited by hand.
- Evidence: CI job `lint` recompiles both and fails on a diff (D12).

### D2 `settings.py`

- `Environment` (`development`, `testing`, `production`) and `Settings` (pydantic-settings,
  `env_prefix="XCODE_"`): one field per row of the table in `docs/08-operability.md`
  section 1, with that table's types, defaults and validations.
- `load_settings() -> Settings` collects every violation and raises
  `SettingsError(messages)`; the CLI prints one message per line and exits 2 (D9).
- `.env` is read only when `XCODE_ENV=development`. In any other environment a present
  `.env` is ignored and a warning is logged once logging is configured.
- `Settings.for_tests(**overrides)`: `XCODE_ENV=testing`, random 32-byte signing key,
  `mail_backend=log`, `log_format=console`, auth rate limit 10000, `openapi_enabled=True`.
- `Settings.summary() -> dict` for the startup log: secrets shown as `"<set>"` or
  `"<unset>"`, the previous-keys list shown as a count.
- Evidence: `tests/unit/test_settings.py`, a parametrised matrix with one case per rule in
  the settings table and per row of the safety-switches table (section 11), each asserting
  the variable name is in the error; one case proving several violations are reported at
  once; `.env` loaded in development only; `summary()` never contains a secret value.

### D3 `domain/` skeleton

- `domain/errors.py`: `DomainRefusal(Exception)` with `code: str` (stable snake_case) and
  `detail: Mapping[str, object]`; subclasses `SessionInvalid`, `Forbidden`, `NotFound`,
  `Conflict`, `RuleViolation`, `CapExceeded`. Nothing HTTP in this module.
- `domain/values.py`: `Money` (Decimal, two places, non-negative unless constructed with
  `allow_negative=True`), `Version` (integer, at least 1), `PageRequest` (`page` at least 1,
  `page_size` at least 1 and clamped to `MAX_PAGE_SIZE = 100`), `DeviceId` (1 to 128
  printable ASCII characters), `Email` (trimmed, lower-cased, at most 254 characters,
  exactly one `@`). `PhoneNumber` and `Pin` arrive with prompt 04.
- Evidence: `tests/unit/test_values.py` boundary cases; `tests/unit/test_layers.py` (D5).

### D4 `application/` skeleton

- `application/ports.py`: Protocols `Clock` (`now() -> datetime`, tz-aware UTC),
  `TokenIssuer`, `PinHasher`, `CodeHasher`, `Mailer` (`send(message: MailMessage) -> None`),
  `RateLimiter` (`hit(key, limit, window_seconds, now) -> RateLimitDecision` with
  `allowed`, `remaining`, `retry_after_seconds`). Each Protocol has a docstring stating its
  contract including failure behaviour. `MailMessage` is a frozen dataclass (`to`,
  `subject`, `text`).
- `application/repositories.py`: `OpsRepository` Protocol with `ping()`,
  `contract_version() -> int`, `rate_limit_hit(key, limit, window_seconds, now)`,
  `record_operator_action(operator, action, target, detail)`. Other repositories arrive
  with later prompts.
- `application/errors.py`: `TransientFailure`, `IntegrityBug`.
- Use case `application/ops/check_readiness.py`: `CheckReadiness.execute() ->
  ReadinessReport` calls `ping()` within a 10 s budget and never raises.
- Evidence: `tests/unit/test_use_case_check_readiness.py` with `FakeOpsRepository`
  (healthy, failing, slow).

### D5 Layer rule test

- `tests/unit/test_layers.py` walks every module under `src/xcode_api` with `ast`, collects
  imports and asserts the six rules of `docs/01-architecture.md` section 2, written as data
  (a mapping from package to its allowed first-party and third-party import roots). It also
  asserts that modules in `db/routines/` contain no SQL literal other than ones matching
  `^SELECT \* FROM api\.[a-z_]+\(`, and that nothing outside `db/` and `tests/` imports
  `psycopg`.
- Evidence: temporarily add `import fastapi` to `domain/values.py`, show the failing test
  output in the report, revert.

### D6 Logging (`infra/logging.py`)

- `configure_logging(settings)`: structlog with `contextvars` merging, ISO-8601 UTC
  timestamps, level from settings, JSON renderer unless `console` in development, stdlib
  bridge so that `uvicorn`, `uvicorn.error` and `psycopg` go through the same processors;
  uvicorn access log disabled.
- Redaction processor: any key whose lower-cased name contains `pin`, `code`, `token`,
  `authorization`, `password`, `phone`, `email` or `secret`, at any depth of the event
  dict, is replaced by `"[redacted]"`.
- `bind_request_context(request_id, actor_id=None, organization_id=None)` and
  `clear_request_context()`.
- Evidence: `tests/unit/test_logging.py` using `structlog.testing`: redaction at depth,
  JSON line keys, console mode accepted only in development.

### D7 Infra adapters that need no database

- `infra/clock.py`: `SystemClock`.
- `infra/rate_limit.py`: `MemoryRateLimiter` (fixed window, `window_start =
  floor(now / window_seconds) * window_seconds`, per-process dict, eviction of windows
  older than two windows) and `PostgresRateLimiter` delegating to
  `OpsRepository.rate_limit_hit` (its routine is prompt 01).
- `infra/mail.py`: `LogMailer` (logs `mail.sent` with `recipient_hash`, the first 12 hex
  characters of SHA-256 of the lower-cased address, and the subject; body only at DEBUG),
  `SmtpMailer` (aiosmtplib; STARTTLS on 587, implicit TLS on 465, plaintext refused unless
  development; timeout from settings; failures raise `MailDeliveryError`), and
  `MailQueue(mailer, max_pending=1000)`: `enqueue()` never blocks (a full queue drops the
  message and logs `mail.dropped` at ERROR), a background task drains in order, failures
  are isolated per message, `drain(timeout_seconds)` for shutdown, `depth` property, log
  events `mail.queued`, `mail.sent`, `mail.failed` carry `recipient_hash` only.
- Evidence: `tests/unit/test_rate_limiter_contract.py` parametrised over
  `MemoryRateLimiter` and `PostgresRateLimiter(FakeOpsRepository)` (window boundaries,
  remaining, retry_after; export the case list so prompt 01 can reuse it);
  `tests/unit/test_mail_queue.py` (ordering, failure isolation, drain timeout, full queue);
  `tests/unit/test_smtp_mailer.py` testing configuration decisions only (port to TLS mode,
  plaintext refusal), no network.

### D8 HTTP plumbing (`http/`)

- `http/middleware.py`: request id (inbound `X-Request-ID` accepted when 1 to 128
  printable ASCII characters, else replaced by UUID4; always echoed); client address per
  `docs/12-security.md` section 2.6 (trusted proxies as IPv4/IPv6 addresses or networks;
  `X-Forwarded-For` walked right to left starting from the peer; the first untrusted hop
  wins; the header is ignored when the peer is untrusted); security headers
  `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: no-referrer`; no `Server` header; body cap 1 MiB answered with a 413
  problem (`docs/06-http-contract.md` section 1.5); one log line `request.completed` per request (route template, method, status,
  duration_ms, request_id, actor_id, organization_id, statements) at INFO, ERROR for 5xx
  with the exception type.
- `http/errors.py`: `problem(status, title, detail=None, **extensions)` producing RFC 9457
  bodies as `application/problem+json` with `requestId` and `traceId`; handlers:
  `DomainRefusal` subclasses to the default statuses of `docs/03-database.md` section 5
  (`RuleViolation` 400 by default; later prompts override per endpoint),
  `RequestValidationError` to 400 (never FastAPI's default 422) with the `/setup` problem
  shape of `docs/06-http-contract.md` section 1 (`title` `Invalid setup change`, `detail`
  the first message, `errors` field path to messages); the auth router's own
  pre-validation answers the auth envelope `invalid_request` instead (prompt 04),
  `TransientFailure` to 503 with `Retry-After: 1`,
  `IntegrityBug` and unexpected exceptions to 500 with `requestId` only plus an ERROR log
  carrying the exception type.
- `http/dependencies.py`: `container(request) -> Container`, `client_address(request)`,
  `auth_rate_limit` (key `auth:<address>`, limit and window from settings; refusal is a 429
  with an empty body and `Retry-After`, `docs/06-http-contract.md` section 1.8).
- `http/schemas/common.py`: `ApiModel` base (camelCase alias generator,
  `populate_by_name=True`, `extra="ignore"`: unknown properties are ignored, as in .NET),
  `Page[T]` (`items`, `pageNumber`, `pageSize`, `total`), `Problem`, `Money` (a JSON
  number with at most two decimals, parsed to `Decimal`, never a float; serialized as a
  number).
- `http/routers/health.py`: `GET /health/live`, `GET /health/ready` (through
  `CheckReadiness`), `GET /health` legacy; bodies and content types exactly as
  `docs/06-http-contract.md` section 1.10 (`text/plain` `Healthy` or `Unhealthy` for live
  and ready, `application/json` `{"status":"ok"}` for `/health`); these routes bypass authentication and rate limiting and still receive the
  security headers and the request id.
- OpenAPI: `openapi_url="/openapi/v1.json"` when `settings.openapi_enabled`, else `None`;
  `docs_url=None`, `redoc_url=None`.
- Evidence: `tests/api/test_http_plumbing.py` using `FakeOpsRepository` (the one fake
  permitted under `tests/api`, because these tests exercise middleware and handlers, not
  the database): request id echo, generation and replacement of bad ids; forwarded-address
  matrix (peer trusted or not, one hop, chained hops, IPv6, CIDR); security headers on 200,
  404 and 500; 413; problem-details shape with `requestId`; 429 with an empty body and
  `Retry-After` from the auth rate-limit dependency; health bodies and content types;
  OpenAPI route present in testing and absent when disabled, and the document facts of
  `docs/06-http-contract.md` section 1.11; unknown JSON properties ignored; a decimal
  field refusing a float literal with more than two decimals; no `Server` header.

### D9 Composition root and CLI

- `container.py`: `Container` frozen dataclass (`settings`, `clock`, `mail_queue`,
  `rate_limiter`, `ops`, `check_readiness`) and `build_container(settings, *, ops,
  clock=None, mailer=None, rate_limiter=None)`. Prompt 01 adds the pool and the real
  `OpsRoutines`.
- `main.py`: `create_app(settings, container) -> FastAPI`: `configure_logging`, middleware
  in the order of `docs/01-architecture.md` section 5, routers, handlers, lifespan (start
  the mail queue; on shutdown drain it for `shutdown_grace_seconds`), container stored on
  `app.state`. CORS with exact origins from settings, credentials not allowed, any method and any
  request header (`docs/06-http-contract.md` section 1.9). Trusted hosts from
  settings.
- `cli/main.py`: argparse with a subcommand registry (a command is a module in
  `cli/commands/`); commands now: `serve [--host 0.0.0.0] [--port 5000]` (uvicorn
  programmatic run, access log off, `timeout_graceful_shutdown=30`), `openapi` (prints the
  document), `settings-check` (loads settings, prints the summary, exit 2 on violations).
  Database commands arrive with prompt 01, user commands with prompts 03 and 08.
- Evidence: `tests/unit/test_cli.py` (registry, `settings-check` exit codes and output);
  `tests/api/test_http_plumbing.py` goes through `create_app`.

### D10 Container image

- `deploy/Dockerfile` per `docs/08-operability.md` section 9 and `deploy/README.md`:
  builder installs `requirements.lock.txt` into `/opt/venv`; runtime `python:3.13-slim`
  pinned by digest (record digest and date in `deploy/README.md`); copies the venv and
  `db/`; user `xcode` uid 10001; `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`;
  `ENTRYPOINT ["xcode-api"]`, `CMD ["serve"]`; `HEALTHCHECK` on `/health/live`.
  `.dockerignore` excludes tests, docs, `.venv`, `.env`.
- Evidence: `docker build` succeeds locally when Docker is available (report if not); CI
  `image` job (D12).

### D11 Compose check

- `docker-compose.yml`: the PostgreSQL service must use `POSTGRES_USER=postgres`
  (superuser for initdb only) and mount `db/roles` as init scripts, so that `xcode_owner`,
  `xcode_api_executor`, `xcode_app`, `xcode_operator` and `xcode_readonly` are created as non-superuser roles
  by `010_roles.sql` (written in prompt 01). Fix the file if it says otherwise; keep the
  `mail` profile.

### D12 CI

- `.github/workflows/xcode-api.yml`, triggered by changes under `apps/api-python/**` and to
  the workflow itself; jobs: `lint` (ruff check, ruff format --check, lock drift: recompile
  both lock files and `git diff --exit-code`), `typecheck` (mypy), `test` (PostgreSQL 18
  service container; `XCODE_TEST_DATABASE_URL` pointing at it as superuser;
  `pytest -n auto`), `audit` (`pip-audit -r requirements.lock.txt`), `db-verify` (runs
  `xcode-api settings-check` until prompt 01 replaces it with `db migrate && db verify`),
  `image` (build; vulnerability scan; push on tags only). Do not modify other workflows.

## Invariants at the end

- `ruff check .`, `ruff format --check .`, `mypy` clean; `pytest tests/unit tests/api -q`
  green with no database running.
- Nothing in `domain/` or `application/` imports anything outside the standard library
  (and `domain`), proven by `test_layers.py`.
- No secret appears in any log line or in the settings summary.
- Every setting in `docs/08-operability.md` exists in `Settings`, `.env.example` and the
  settings test matrix; anything you had to add goes into all three and into the report.
- No TODO or FIXME; no plan or prompt identifiers in code or comments; names per
  `docs/11-naming.md` (`xcode`, never `Auth`).

## Verify (paste the outputs into the report)

```
cd apps/api-python
ruff check . && ruff format --check . && mypy
pytest tests/unit tests/api -q
cp .env.example .env && xcode-api settings-check ; echo "exit=$?"          # 0 and a summary
XCODE_ENV=production xcode-api settings-check ; echo "exit=$?"             # 2, every missing production setting listed
xcode-api openapi | head -c 400
docker build -f deploy/Dockerfile -t xcode-api:dev .                       # when Docker is available
```

## Report format

1. Checklist: one row per deliverable D1 to D12 and per bullet inside it: done or not,
   `file:symbol`, test name.
2. Verify outputs, trimmed.
3. Deviations from the documents, with the document section and the reason, and any
   document you changed.
4. Items left for the next prompt (expected: pool, `OpsRoutines`, `db` commands, readiness
   against PostgreSQL).

## House rules

- Shared tree: `git status` first; edit only under `apps/api-python/` and the one workflow
  file; never revert or reformat others' changes; never kill processes you did not start;
  never bare `git stash`.
- No commits unless the user asks. No AI attribution anywhere.
- No comments unless needed; no plan or prompt identifiers in code.
- Never weaken a test to make it pass. If a document is wrong, fix the document and report
  it.
