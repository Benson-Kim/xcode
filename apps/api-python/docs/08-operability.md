# Operability, deployment and safety switches

## 1. Settings (`XCODE_*`)

All configuration is environment variables read by `Settings` (pydantic-settings). In
`development` a `.env` file in the project directory is loaded; in any other environment
`.env` is ignored and its presence is logged as a warning (the .NET `DotNetEnv` behaviour of
loading `.env` everywhere is not carried over).

| Variable | Type | Default | Validation / notes |
|---|---|---|---|
| `XCODE_ENV` | `development` \| `testing` \| `production` | required | drives every safety switch below |
| `XCODE_DATABASE_URL` | libpq URL | required | role `xcode_app`; in production `sslmode` must be `verify-full` (or `require` with `XCODE_DATABASE_ALLOW_REQUIRE_SSLMODE=true` and a logged warning), unless every address the URL reaches is a Unix socket or the loopback interface (a database beside the API on one host, where TLS protects nothing; read as libpq reads it, with `PGHOST`/`PGHOSTADDR` for what the URL leaves out and a named service never counting as local); development and testing run against local or throwaway servers |
| `XCODE_MIGRATION_DATABASE_URL` | libpq URL | unset | role `xcode_owner`; needed only by `db` commands, the test harness and, in development, `XCODE_AUTO_MIGRATE` (required then) |
| `XCODE_DATABASE_OPERATOR_URL` | libpq URL | unset | role `xcode_operator`; needed only by the CLI's user and seed commands (`provision-user`, `remove-user`, `clear-pause`, `revoke-sessions`, `seed-demo`) and, in development, `XCODE_DEMO_SEED` (required then); outside development the API process never reads it |
| `XCODE_DATABASE_ALLOW_REQUIRE_SSLMODE` | bool | false | production only: accept `sslmode=require` instead of `verify-full`, with a logged warning |
| `XCODE_DATABASE_POOL_MIN` | int | 2 | at least 1 |
| `XCODE_DATABASE_POOL_MAX` | int | 10 | at least `_MIN`; below the role's connection limit (`deploy/README.md`); documented sizing: `max = 2 x vCPU` per replica |
| `XCODE_AUTH_SIGNING_KEY` | string | required outside development/testing | at least 32 bytes UTF-8; development/testing generate a random key per process when empty (tokens do not survive restarts, as in .NET); the startup summary then shows `<generated>` and a warning is logged |
| `XCODE_AUTH_PREVIOUS_SIGNING_KEYS` | comma-separated strings | empty | verify-only keys accepted during a rotation; each at least 32 bytes; never used to sign; the startup summary logs only their count |
| `XCODE_AUTH_ISSUER` | string | `xcode-api` | |
| `XCODE_AUTH_AUDIENCE` | string | `xcode-clients` | |
| `XCODE_AUTH_TRUST_LIFETIME_DAYS` | int or empty | empty | positive or empty (empty = no expiry) |
| `XCODE_AUTH_PIN_ITERATIONS` | int | value from `Security.cs` (210 000) | must equal the .NET value until all hashes are upgraded; changing it is a documented migration; `Settings.for_tests()` uses `PIN_ITERATIONS_TESTING` (1 000) |
| `XCODE_RATE_LIMIT_BACKEND` | `memory` \| `postgres` | `memory` | production with more than one replica must use `postgres` (documented, and the readiness log line states the backend) |
| `XCODE_RATE_LIMIT_AUTH_PER_MINUTE` | int | 30 (testing: 10000) | positive |
| `XCODE_RATE_LIMIT_PIN_PER_ADDRESS` | int | 20 (testing: 10000) | positive; PIN checks (A01, A02, N02, N07) per client address in ten minutes |
| `XCODE_RATE_LIMIT_PIN_PER_DEVICE` | int | 10 (testing: 10000) | positive; PIN checks per `deviceId` in ten minutes |
| `XCODE_TRUSTED_PROXIES` | list of IP addresses | `127.0.0.1,::1` | each must parse as an IP address; CIDR ranges allowed |
| `XCODE_CORS_ORIGINS` | list of origins | empty | exact origins; `*` refused outside development |
| `XCODE_ALLOWED_HOSTS` | list | `*` | production must list hosts; `*` refused in production (development and testing keep it); the health probes and `/metrics` are exempt (callers use the address) |
| `XCODE_MAIL_BACKEND` | `log` \| `smtp` | `smtp` | `log` refused in production |
| `XCODE_EMAIL_HOST` | string | empty | required when the backend is `smtp`; checked at startup, not first send |
| `XCODE_EMAIL_PORT` | int | 587 | outside development 465 or 587, unless `XCODE_EMAIL_TLS=false` to a relay on this machine |
| `XCODE_EMAIL_FROM` | string | empty | required when the backend is `smtp` |
| `XCODE_EMAIL_USERNAME` | string | empty | SMTP login, optional |
| `XCODE_EMAIL_PASSWORD` | string | empty | secret; the summary shows only set or unset |
| `XCODE_EMAIL_TIMEOUT_SECONDS` | int | 10 | positive; bounds the SMTP operations and the new-device mail awaited before the reply (`docs/07-auth.md` section 7) |
| `XCODE_EMAIL_TLS` | bool | true | port 465 is implicit TLS, any other port requires STARTTLS; `false` sends without TLS and is refused outside development unless `XCODE_EMAIL_HOST` is `localhost` or a loopback address literal (a relay on the same machine, as .NET's `Email:EnableSsl=false`, `Infrastructure/Security.cs` `SmtpEmailSender.UsesTls`); a host name is never resolved for this, so one that only resolves to the loopback interface still needs TLS |
| `XCODE_LOG_FORMAT` | `console` \| `json` | `json` | `console` allowed in development and testing, refused in production |
| `XCODE_LOG_LEVEL` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` \| `CRITICAL` | `INFO` | case-insensitive |
| `XCODE_DEVELOPMENT_CODES` | bool | false | returns verification codes in responses and skips the resend cooldown; refused unless `XCODE_ENV=development` (in testing the codes are always absent, as in .NET) |
| `XCODE_DEMO_SEED` | bool | false | startup demo seed (as `xcode_operator`, so `XCODE_DATABASE_OPERATOR_URL` is required); refused unless `XCODE_ENV=development` |
| `XCODE_AUTO_MIGRATE` | bool | false | migrate at startup (as `xcode_owner`, so `XCODE_MIGRATION_DATABASE_URL` is required); refused unless `XCODE_ENV=development` |
| `XCODE_OPENAPI_ENABLED` | bool | true in development/testing, false in production | the document route `/openapi/v1.json` |
| `XCODE_METRICS_ENABLED` | bool | false | exposes `/metrics` (Prometheus text) on the same port; no authentication, so the proxy must never forward it (section 5) |
| `XCODE_SHUTDOWN_GRACE_SECONDS` | int | 10 | mail queue drain budget; not negative |
| `XCODE_OPERATOR` | string | OS user name | recorded in `ops.operator_actions` by every CLI command; printable, at most 128 characters |

Two variables are read outside `Settings`: `XCODE_DB_DIR` (where the runner finds `db/`; by
default the first `db` folder above the working directory) and, for the test harness only,
`XCODE_TEST_DATABASE_URL` and `XCODE_TEST_TEMPLATE` (`docs/09-testing.md` section 5).

Rules: validation errors list every bad variable at once and exit with code 2 before any
network socket opens. Secrets are never logged, including in the startup settings summary
(which logs key names and non-secret values).

The `db` and operator commands of section 8 validate only `CliSettings`: `XCODE_ENV`, the
URL they connect with (`XCODE_MIGRATION_DATABASE_URL` for `db`, `XCODE_DATABASE_OPERATOR_URL`
for the user and seed commands) and `XCODE_OPERATOR`. A migration job therefore carries the
owner URL and nothing of the API's own configuration or secrets.

## 2. Logging

- structlog, JSON lines outside development, UTC timestamps, keys: `timestamp`, `level`,
  `event`, `logger`, `request_id`, `actor_id`, `organization_id`, `route`, `method`,
  `status`, `duration_ms`, `statements`, `client` (address only when a log line is about
  rate limiting or auth refusal; never otherwise).
- Redaction processor drops any key named like `pin`, `code`, `token`, `authorization`,
  `password`, `phone`, `email` anywhere in the event dict, as a last line of defence.
- One request log line per request at INFO; 5xx at ERROR with the exception type; 4xx at
  INFO without bodies.
- Routine calls log at DEBUG with routine name and duration (no arguments).
- Mail: `mail.queued`, `mail.sent`, `mail.failed` (and `mail.withdraw_failed`) with recipient
  hash (SHA-256 prefix) and, for verification codes, `purpose`, `code_id` and `request_id`;
  never the address or the code (the development log mailer's `mail.body` is the exception).

## 3. Request id and tracing

- Inbound `X-Request-ID` is accepted when it is at most 128 printable ASCII characters,
  otherwise replaced; outbound header always set; `requestId` and `traceId` included in
  problem details (`traceId` is the W3C trace id when OpenTelemetry is enabled, else the
  request id).
- OpenTelemetry is optional: when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, the FastAPI and
  psycopg instrumentations are enabled (packages added to `requirements.txt` by the
  operability phase only if adopted).

## 4. Health

| Route | Checks | Success | Failure |
|---|---|---|---|
| `GET /health/live` | none | 200 `text/plain` `Healthy` | process not running |
| `GET /health/ready` | the startup checks have passed (section 6); `SELECT 1` via the pool and the contract version within 10 s; the shared limiter answers when the backend is `postgres` (a hit on its own window `health:ready`) | 200 `text/plain` `Healthy` | 503 `text/plain` `Unhealthy`, no detail; the reason in `health.ready.failed` |
| `GET /health` | none (legacy; staging `start.js` depends on it) | 200 `application/json` `{"status":"ok"}` | |

Bodies and content types are those of `docs/06-http-contract.md` section 1.10 (parity with
the ASP.NET health endpoints). Readiness never returns details that reveal infrastructure;
the reason is logged.

## 5. Metrics (when enabled)

`http_requests_total{route,method,status}`, `http_request_duration_seconds{route}`,
`db_routine_duration_seconds{routine}`, `db_pool_connections{state}`,
`auth_refusals_total{reason}` (reason is internal: `unknown`, `paused`, `capped`,
`wrong_pin`; never exposed per account), `mail_queue_depth`, `rate_limit_rejections_total`.

- `route` is the route template (`/setup/people/{id}`); a request no route matched is counted
  as `unmatched`, so a scanner's paths never become label values. `state` is `idle`, `busy`
  or `waiting`, read from the pool at scrape time.
- Each app has its own registry (`infra/metrics.py`); the HTTP middleware binds it to the
  request (`application/observability.py`), so the gateway reports routine durations and the
  auth routines' refusals without importing the client library. A 429 counts as a rate-limit
  rejection.
- `/metrics` has no authentication: the proxy must never forward it, and it is exempt from
  `XCODE_ALLOWED_HOSTS` because the scraper calls by address. Tests: `tests/api/test_metrics.py`.
- Whoever can both send a sign-in and read `/metrics` learns from `auth_refusals_total{reason}`
  whether a number exists (`unknown` against `wrong_pin`, `paused` or `capped`), which the
  identical answers of section 1.6 of `docs/06-http-contract.md` otherwise hide. So `/metrics`
  must be reachable by the operators' scraper alone: never through the proxy, never on a host
  where other accounts share the loopback interface (`docs/13-open-questions.md` question 86).

## 6. Startup sequence

1. Parse and validate settings (exit 2 on failure).
2. Configure logging.
3. Cap the worker threads (anyio's limiter for synchronous dependencies and the loop's
   default executor, 4 each; the PIN pool keeps its own 2), open the pool (fail after 30 s:
   `startup.database_unreachable`, exit 1), run `SELECT 1`, check that the connected role is
   `xcode_app` (`db.role_unexpected` warning if it is not: least privilege is being bypassed).
4. Optionally (development only) auto-migrate as `xcode_owner` and demo-seed as
   `xcode_operator`, each through its own URL; outside development the process never reads
   `XCODE_MIGRATION_DATABASE_URL` or `XCODE_DATABASE_OPERATOR_URL`.
5. Verify routine compatibility: call `api.meta_contract_version()` and compare with the
   version the package expects; refuse to start on mismatch (prevents a new API against an
   old database or the reverse).
6. Log the number of active users without an organization membership (parity with the .NET
   startup warning), via `api.meta_unassigned_user_count` (granted to `xcode_app` like
   every `api.meta_*` routine): `startup.unassigned_users`, message
   `{n} active users have no organization membership and cannot sign in`, only when n > 0.
7. Start the mail queue and serve. Readiness becomes true only after steps 5 and 6 and turns
   false again when shutdown starts.

A failure in steps 3 to 6 ends the lifespan; uvicorn's startup-failure code 3 becomes exit 1
(`cli/commands/serve.py`). Tests: `tests/api/test_operability.py`,
`tests/unit/test_production_startup.py`.

## 7. Shutdown sequence

SIGTERM: stop accepting; in-flight requests finish (uvicorn timeout 30 s); mail queue
drains for at most `XCODE_SHUTDOWN_GRACE_SECONDS`; pool closes; exit 0.

## 8. CLI (`xcode-api`)

| Command | Purpose | Connects as |
|---|---|---|
| `serve [--host] [--port]` | run the API (default 0.0.0.0:5000, to match `API_URL` defaults in the web proxy) | `xcode_app` |
| `db migrate|routines|status|verify|down` | see `docs/03-database.md` section 7 | `xcode_owner` |
| `provision-user --email --phone [--role] [--first-name] [--last-name] [--organization-name]` | parity with `--provision-user`: creates or re-activates a user and membership; prints that they can now set a PIN with an email code | `xcode_operator` (routine `api.ops_provision_user`) |
| `remove-user --email` | parity with `--remove-user`: marks the user removed and revokes refresh tokens | `xcode_operator` (routine `api.ops_remove_user`) |
| `clear-pause --email` | clears a sign-in pause (never the untrusted-device cap) | `xcode_operator` (routine `api.ops_clear_pause`) |
| `revoke-sessions --email` | bumps `security_version`, revokes refresh tokens and device trust; the user signs in again with a code | `xcode_operator` (routine `api.ops_revoke_sessions`) |
| `account-state --email` | prints status, pause, attempt counters, trusted-device and live-token counts for a support call; never a hash | `xcode_operator` (routine `api.ops_account_state`) |
| `seed-demo` | development only; refuses otherwise; idempotent | `xcode_operator` (routine `api.ops_seed_demo`; `docs/13-open-questions.md` question 7) |
| `openapi > file` | prints the OpenAPI document for contract comparison | none |
| `settings-check` | validates the `XCODE_*` settings of the API process and prints the startup summary (secrets shown only as set or unset); exit 2 naming every bad variable | none |

Every command logs to stderr at INFO in the console form; stdout carries only the
command's own output (ids, counts, the verify lines, the OpenAPI document), so it can be
piped or parsed.

## 9. Deployment

The intended host is the shared cPanel account `priori`, not a container platform. The
container below stays as the CI build and a portable fallback, but several of its
assumptions (five roles, `pg_hba`, a secret store, a read-only root filesystem, replicas)
may not exist on that host. Questions 39 to 45 of `docs/13-open-questions.md` list the facts
to measure there first; until they are answered, nothing in this section is proven for
the real host.

Container (`deploy/Dockerfile`; the base image pinned by digest, recorded in `deploy/README.md`):
- `python:3.13-slim-bookworm` builder installs `requirements.lock.txt` into a venv; runtime stage
  copies the venv and `db/` (the runner needs the SQL files), creates user `xcode` (uid
  10001), sets `PYTHONDONTWRITEBYTECODE=1`, `PYTHONUNBUFFERED=1`, read-only root filesystem
  with `/tmp` as tmpfs, `ENTRYPOINT ["xcode-api"]`, `CMD ["serve"]`, healthcheck on
  `/health/live`.
- Release procedure: run `xcode-api db migrate` as a one-off job with the owner URL; when it
  exits 0, roll the replicas. Rollback: roll replicas back; run `db down` only if the
  release notes say the migration is reversible without data loss.
- Behind a reverse proxy that terminates TLS and sets `X-Forwarded-For`; the proxy's address
  is in `XCODE_TRUSTED_PROXIES`; HSTS and HTTPS redirection are the proxy's job.

CI (`.github/workflows/xcode-api.yml`; every action pinned by commit, its tag in a comment):
- jobs: `lint` (ruff check, ruff format --check, lock drift), `typecheck` (mypy), `test`
  (PostgreSQL 18 service container, `XCODE_TEST_DATABASE_URL` set, `pytest -n auto`), `audit`
  (pip-audit on the lock file), `db-verify` (a fresh database: `db migrate`, `db status`,
  `db verify`, then `seed-demo` twice and `db verify` again), `migration-tool` (the data
  migration tool's lint, types and tests), `image` (build, vulnerability scan failing on
  critical and high findings that have a fix, run read-only as uid 10001, push to GHCR on
  tags `xcode-api-v*`). Dependencies install from the lock files.
- The lock file is checked for drift: `uv pip compile` output must equal the committed file.

Release checklist (platform controls the API cannot verify itself; see `docs/12-security.md`):
- TLS terminated at the proxy with HSTS; the API port is not reachable from outside.
- PostgreSQL accepts `scram-sha-256` over TLS only; `pg_hba` denies `xcode_owner` from the
  application network; volumes and backups are encrypted; a restore drill is on record.
- The image is pinned by digest and passed the CI vulnerability scan.
- Secrets come from the platform's secret store; no `.env` file is mounted.
- `XCODE_TRUSTED_PROXIES` names the proxy; `XCODE_ALLOWED_HOSTS` and `XCODE_CORS_ORIGINS`
  are explicit; `XCODE_RATE_LIMIT_BACKEND=postgres` when more than one replica runs.

## 10. Runbook entries (minimum)

The procedures, with commands and log event names, are `deploy/runbook.md`.

- "Readiness is failing": check pool saturation (`db_pool_connections`), PostgreSQL
  availability, role timeouts; the log line `health.ready.failed` carries the exception
  type.
- "A user cannot sign in": `xcode-api account-state --email <email>` (status, pause,
  attempt counters, trusted-device and live-token counts; never a hash); clearing a pause
  is `xcode-api clear-pause`; the untrusted-device cap is lifted only by a PIN reset or a
  verified new device (`docs/07-auth.md` section 4).
- "Rate limit hits from one address": confirm `XCODE_TRUSTED_PROXIES` includes the proxy;
  otherwise every client shares the proxy's address.
- "Migration failed mid-way": each file is its own transaction; `db status` shows which
  applied; fix forward with a new migration, never edit an applied file.
- "Routine drift": `db status` lists files whose checksum differs from the database;
  re-run `db routines` (idempotent).
- "Rotate the signing key": set the new `XCODE_AUTH_SIGNING_KEY`, move the old value into
  `XCODE_AUTH_PREVIOUS_SIGNING_KEYS`, roll replicas, remove it after the access-token
  lifetime. Sessions survive; forged tokens die with the old key.
- "Suspected account compromise": `xcode-api revoke-sessions --email <email>`; the user
  signs in again with an email code and re-trusts devices. The action is recorded in
  `ops.operator_actions`.
- "Who did what": `tenancy.change_log` for organization changes, `ops.operator_actions`
  for CLI and migration actions, `identity.sign_in_attempts` for sign-in history; all
  append-only.

## 11. Safety switches summary

| Feature | Flag | Allowed in |
|---|---|---|
| Log mailer | `XCODE_MAIL_BACKEND=log` | development, testing |
| Development codes in responses | `XCODE_DEVELOPMENT_CODES=true` | development |
| Demo seed at startup | `XCODE_DEMO_SEED=true` | development |
| Auto-migrate at startup | `XCODE_AUTO_MIGRATE=true` | development |
| OpenAPI route | `XCODE_OPENAPI_ENABLED=true` | development, testing (default on), production (explicit) |
| Console log format | `XCODE_LOG_FORMAT=console` | development, testing |
| Wildcard CORS | `XCODE_CORS_ORIGINS=*` | development |
| Wildcard hosts | `XCODE_ALLOWED_HOSTS=*` | development, testing |
| `db down` | `--i-know-this-destroys-data` | any, logged at WARNING with the operator name from `XCODE_OPERATOR` if set |

A flag set outside its allowed environments is a startup failure with the variable named,
never a silent downgrade.
