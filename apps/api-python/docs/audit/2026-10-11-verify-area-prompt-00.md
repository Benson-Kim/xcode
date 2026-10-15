# Verify: prompt 00 (application bootstrap), 2026-10-11

`SCOPE: area:prompt 00` · `MODE: fix` · `DEPTH: standard` · method `docs/14-verification.md`.
Run by a session that did not write the code. Edits only under `apps/api-python/`.

## 1. Verdict

**fail**: the full suite did not run to completion. Claude Code stopped it at about 36% because
the machine was low on memory (section 8). No blocker survives, and every major is fixed with
a test. Rerun the full suite to turn this into `pass with findings`.

- Claims (section 2): 44. holds 34, fails 7, unproven 3, n/a 0, not checked 0.
- Surviving findings (section 3): blocker 0, major 3, minor 14, note 5.
- Fixed in this run: the 3 majors and 5 minors, each with a test that failed first. Of the
  other 9 minors, 3 have a corrected document, 5 a named owner and 1 is for the user. Notes
  are recorded only.
- Probes (section 4): 27. holds 18, fails 7 (6 fixed, corrected or owned; 1 is the
  incomplete full run), unproven 1, n/a 1.

## 2. Thesis and claims

Thesis (steelmanned): prompt 00 delivers D1 to D12. The settings refuse every unsafe
combination at once, and nothing they print or log carries a secret. The domain and
application rings import only the standard library, and `test_layers.py` proves it. Logs are
structured and redacted. The HTTP plumbing (request id, forwarded address, security headers,
body cap, problem details, rate-limit refusal, health, OpenAPI switch, CORS, allowed hosts)
behaves as `docs/06-http-contract.md` section 1 and the .NET `Program.cs` pipeline say. The
container, compose file and CI build, run and check what `docs/08-operability.md` section 9
describes.

| # | Claim (where stated) | Carried by | Verdict | Grade |
|---|---|---|---|---|
| C1 | D1 lock files compiled by `uv pip compile` | `requirements*.lock.txt` headers | holds | B |
| C2 | D1 CI fails on lock drift | `.github/workflows/xcode-api.yml` `lint` | unproven: CI never ran (workflow untracked) | D |
| C3 | D2 one field per row of `docs/08` section 1 | `settings.py` `Settings` | holds (sweep, section 8) | A |
| C4 | D2 every violation at once, exit 2 | `load_settings`, `settings_check.run` | holds: production run listed 5 violations, exit 2 | A |
| C5 | D2 `.env` read in development only, warning elsewhere | `_should_read_env_file`, `main.build_default_app` | holds | A |
| C6 | D2 `Settings.for_tests()` values | `settings.py` `for_tests` | holds | B |
| C7 | D2 `summary()` never contains a secret (also an invariant) | `settings.py` `_redact_url` | **fails** → fixed (V-D8-1) | A |
| C8 | D3 `DomainRefusal` and subclasses, nothing HTTP | `domain/errors.py` | holds | A |
| C9 | D3 value objects as the prompt words them | `domain/values.py` | **fails** as text: prompt 04 changed them to match .NET; prompt corrected (V-D11-2) | A |
| C10 | D4 ports are Protocols with contract docstrings | `application/ports.py` | holds | B |
| C11 | D4 `OpsRepository` methods | `application/repositories.py` | holds | B |
| C12 | D4 `CheckReadiness` within 10 s, never raises | `application/ops/check_readiness.py` | holds (`test_use_case_check_readiness.py`: healthy, failing, slow) | A |
| C13 | D5 the six rules as data, proven by `test_layers.py` | `tests/unit/test_layers.py` | **fails**: `from .. import x` was skipped (V-D10-1, fixed); rule 4 weaker than the doc (V-D10-2) | A |
| C14 | D5 SQL literals in `db/routines/*.py` are routine calls; only `db` imports psycopg | `test_layers.py` | holds | A |
| C15 | D5 the mutation `import fastapi` in `domain/values.py` fails the test | scratch copy of `src` | holds (section 8) | A |
| C16 | D6 JSON or console, UTC ISO time, stdlib bridge, access log off | `infra/logging.py` | holds | B |
| C17 | D6 redaction at any depth | `redact_processor` | holds (`test_logging.py`); over-redaction of `code` (V-D8-5) | A |
| C18 | D6 `bind_request_context` / `clear_request_context` | `infra/logging.py` | holds | B |
| C19 | D7 `MemoryRateLimiter` fixed window and eviction | `infra/rate_limit.py` | holds (contract cases); cost per hit (V-D7-1) | A |
| C20 | D7 `PostgresRateLimiter` delegates | `infra/rate_limit.py` | holds (contract cases, `tests/db/test_rate_limit_postgres.py`) | A |
| C21 | D7 log and SMTP mailers, queue order, isolation, drain, full queue | `infra/mail.py` | holds (`test_mail_queue.py`, `test_smtp_mailer.py`); port refusal outside settings (V-D8-6) | A |
| C22 | D8 request id accepted, generated, replaced, echoed | `RequestContextMiddleware` | holds | A |
| C23 | D8 client address per `docs/12` section 2.6 | `middleware.client_address`, `serve` | **fails** → fixed (V-D2-1, V-D2-2) | A |
| C24 | D8 security headers on 200, 404, 500; no `Server` | middleware, `errors.py` | holds | A |
| C25 | D8 body cap 1 MiB, 413 problem (declared and chunked) | `BodyCapMiddleware` | holds | A |
| C26 | D8 one `request.completed` line with the route template | `RequestContextMiddleware` | **fails** → fixed (V-D8-2) | A |
| C27 | D8 problem details; 400 not 422; 503 with `Retry-After: 1`; 500 with `requestId` only | `http/errors.py` | holds | A |
| C28 | D8 auth rate limit: 429, empty body, `Retry-After` | `dependencies.auth_rate_limit` | holds | A |
| C29 | D8 `ApiModel`, `Page[T]`, `Money` as a JSON number with at most two decimals | `http/schemas/common.py` | holds; float-literal note (N1) | A |
| C30 | D8 health bodies and types; no auth, no rate limit | `routers/health.py` | holds; host check now skipped (V-D9-1) | A |
| C31 | D8 OpenAPI at `/openapi/v1.json` only when enabled; docs and redoc off | `main.create_app` | holds | A |
| C32 | D9 `Container` and `build_container` | `container.py` | holds | B |
| C33 | D9 middleware order of `docs/01` section 5 and `docs/06` 1.5 | `main.create_app` | holds (read; host check sits between request context and CORS) | B |
| C34 | D9 lifespan starts the queue and drains it for `shutdown_grace_seconds` | `main.create_app` | holds | B |
| C35 | D9 CORS: exact origins, no credentials, any method and header | `main.create_app` | unproven before this run (no test sent `Origin`); now holds, see section 7 | A |
| C36 | D9 CLI registry, `serve`, `openapi`, `settings-check` | `cli/` | holds (`test_cli.py`, new `serve` test) | A |
| C37 | D10 image: base pinned by digest, healthcheck on `/health/live` | `deploy/Dockerfile` | **fails**: tag, not digest (V-D9-2); the healthcheck was refused under production hosts (V-D9-1, fixed) | D |
| C38 | D11 compose: `postgres` superuser for initdb, roles mounted, `mail` profile | `docker-compose.yml` | holds | B |
| C39 | D12 CI jobs lint, typecheck, test (PG 18), audit, db-verify, image (scan, push on tags) | workflow | unproven: never ran; push is an `echo` stub (V-D9-2) | D |
| C40 | Invariant: ruff, format, mypy clean; unit and api tests green without a database | commands, section 8 | holds | A |
| C41 | Invariant: `domain` and `application` import only the standard library (and `domain`) | `test_layers.py` | holds (after V-D10-1) | A |
| C42 | Invariant: no secret in any log line or in the summary | settings, logging | **fails** → fixed (V-D8-1); residual note N3 | A |
| C43 | Invariant: every setting in `Settings`, `.env.example`, the test matrix | sweep | holds | A |
| C44 | Invariant: no TODO or FIXME, no plan identifiers, `xcode` naming | grep | holds | A |

## 3. Findings

Format of `docs/14-verification.md` section 7. Line numbers are from before the fix unless
the row says otherwise.

| id | mode | claim attacked | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| V-D8-1 | red team (compromised neighbour reading logs) | C7, C42 | `XCODE_DATABASE_URL=postgresql://xcode_app@db/xcode?sslmode=verify-full&password=…` passes the production TLS rule. `summary()` printed the URL with `password=…` (libpq reads any keyword from the query, keys percent-decoded, so `pass%77ord` too), and a key/value string came back unchanged. `settings-check` prints the summary. | `settings.py:430-438` `_redact_url` kept the query; `test_summary_hides_secrets` covered only userinfo | Looked for another filter between `summary()` and stdout: none. A `/` inside the userinfo is already stripped (the case passed before the fix). | survives, **major** | fixed: query `password`/`sslpassword` values shown as `<set>`; any non-URL form shown as `<set>` (`settings.py:440`) |
| V-D9-1 | pre-mortem | C30, C37 | In production `XCODE_ALLOWED_HOSTS` must list real hosts. The image's HEALTHCHECK calls `http://127.0.0.1:5000/health/live`, so Host is `127.0.0.1:5000` and Starlette's `TrustedHostMiddleware` answers 400. The container stays "unhealthy" for ever, and a load balancer probing by address gets the same 400. | `Dockerfile:49-50`, `main.py:75-76`, `settings.py:268` | Could the operator add `127.0.0.1` to the hosts? Yes, but nothing tells them, and a valid production configuration fails. .NET had no container healthcheck. | survives, **major** | fixed: `HostCheckMiddleware` (`middleware.py:194`) checks hosts on every path except the three health paths, which answer constant bodies. `test_a_host_outside_the_allowed_hosts_is_refused` probed `/health/live`; its two assertions (200 for the listed host, 400 for a foreign one) now run against `/openapi/v1.json`. Exact-path test: `/health/live/` is still checked. `docs/06` 1.10 and `docs/12` 2.6 updated |
| V-D2-1 | red team (outsider guessing PINs) | C23 | A trusted proxy that adds its own `X-Forwarded-For` line instead of appending: the request carries `[client: 203.0.113.9]` then `[proxy: 198.51.100.7]`. `client_address` read only the first line, so the attacker chose the rate-limit key on every request and the 30-per-minute `/auth` limit stopped working. RFC 9110 section 5.3 makes the lines one list. .NET (`GetCommaSeparatedValues`) and uvicorn 0.54 (`b", ".join`) both join them. | `middleware.py:75,104-109`; `.venv/.../uvicorn/middleware/proxy_headers.py:38-52` | Behind a loopback proxy under `serve`, uvicorn rewrote the peer first and hid this. Behind a non-loopback trusted proxy nothing hid it. | survives, **major** | fixed: every line is read, joined in order (`middleware.py:78`); `tests/unit/test_client_address.py` |
| V-D2-2 | Socratic | C23 | "Client address is believed only from `XCODE_TRUSTED_PROXIES`" (`docs/12` 2.6). uvicorn's `proxy_headers=True` default also believes `FORWARDED_ALLOW_IPS` (`127.0.0.1,::1`), so there were two trust lists. With the setting set to a remote proxy only, a local process could still forge addresses through uvicorn. | `serve.py:77-86`; uvicorn `config.py:225,363` | Both defaults trust loopback, so the defaults agree. Only a narrowed setting diverges. | survives, minor | fixed: `serve` passes `proxy_headers=False` (`serve.py:44`); test in `test_client_address.py` |
| V-D8-2 | falsification | C26 | `request.completed` should carry the route template, but `route_template` was set nowhere, so every line logged the raw path (ids included; high cardinality for the future metrics label). | `middleware.py:162`; grep: no writer of `route_template` | FastAPI sets `scope["route"]` on a match (`fastapi/routing.py:869`), so the template was available but unused. | survives, minor | fixed: `_route_template` uses `path_format`, else the raw path for an unmatched request (`middleware.py:116`); 2 tests |
| V-D8-3 | falsification | `docs/08` s4 "the reason is logged", s10 runbook `health.ready.failed` | `/health/ready` dropped `ReadinessReport.reason`, so a failing probe left no log line, although the runbook tells the operator to look for one | `routers/health.py:24-28` | Searched for another logger of the reason: none | survives, minor | fixed: `health.ready.failed` with `reason` at WARNING (`health.py:31`); the reply stays `Unhealthy` |
| V-D4-1 | falsification | `docs/06` 1.8 and `docs/08` s1 "30 (testing: 10000)" | `XCODE_ENV=testing` without the variable gave 30. .NET gives 10000 in Testing (`Program.cs:93`). Only `for_tests()` set 10000. | `settings.py:93` | none | survives, minor | fixed: the testing default applies when the variable is unset (`settings.py:161-166`); 3 tests |
| V-D10-1 | falsification | C13, C41 | `from .. import container` inside `domain/` passed `test_layers.py`, because an `ImportFrom` with `module=None` was skipped | `test_layers.py:120-121` | grep: no such import in `src` today, so the claim held in fact but its test did not prove it | survives, minor | fixed; new `test_relative_package_imports_are_checked`; the scratch-copy mutation (section 8) now reports both `fastapi` and `container` |
| V-D10-2 | Socratic | C13 | `docs/01` rule 4 lets `db`, `security` and `infra` import only `application.ports`, `.repositories` and `.errors`. The test allows any `application` module, so an adapter importing a use case would pass. | `test_layers.py:30-63` | grep: no adapter imports a use-case module today | survives, minor | open; owner: the next change to `test_layers.py` (prompt 09's structure work). Recommendation: track the second path part for adapters |
| V-D8-4 | falsification | `docs/08` s1 "the startup settings summary" | `serve` never logs `summary()`; only `settings-check` prints it. If it were logged as is, the redaction processor would hide `email_*`, `development_codes` and `auth_pin_iterations` (keys containing `email`, `code`, `pin`). | grep `summary()` in `src` | none | survives, minor | owner prompt 09 (startup and readiness): log the summary under keys the processor leaves alone, or change `docs/08` to name `settings-check` as the place to read it |
| V-D8-5 | falsification | C17 | `request.refusal_without_message` logs `code=exc.code`, and the redaction processor replaces it with `[redacted]` in real output, so the line loses its only payload. Tests cannot see this: `structlog.testing.capture_logs` skips the processors. | `http/errors.py:112`; `logging.py:17-26` | none | survives, minor | owner: the next change to `http/errors.py` (another session was editing it at 15:00): rename the key (for example `refusal=`) |
| V-D8-6 | pre-mortem | `docs/08` s1 "checked at startup, not first send" | `XCODE_EMAIL_PORT=25` outside development passes `settings-check` (exit 0). `serve` then fails building the container with a `MailDeliveryError` traceback, not an exit-2 violation naming the variable. | `infra/mail.py:98-101`; `settings.py` `_check_mail` has no port rule | none | survives, minor | owner prompt 09 D2 with drift-register row 10 (loopback relay): move the port rule into settings |
| V-D7-1 | pre-mortem | C19 | `MemoryRateLimiter._evict` scans every bucket on every hit. Rotating source addresses (an IPv6 /64 gives 2^64 keys, and the key is the full address, as in .NET's partition) grows the map with the request rate, and each hit costs O(keys) on the event loop: about 36 000 entries at 200 requests a second, so about 7 million iterations a second. | `infra/rate_limit.py:35-52` | The `postgres` backend has no such loop. Fixed-window parity with .NET holds. | survives, minor | owner prompt 09 (performance): evict once per window change; decide on /64 keying for IPv6 (business call, section 10) |
| V-D9-2 | red team (supply chain) | C37, C39 | Base image is a tag (`python:3.13-slim-bookworm`, `Dockerfile:9,31`), not a digest. Lock files carry no hashes and the build installs without `--require-hashes`. Actions are pinned by tag, not SHA (`actions/*@v4/v5`, `trivy-action@0.28.0`). The workflow has no `permissions:` block. The push step is an `echo`. No step asserts uid 10001. CI has never run (workflow untracked). | files named | Docker is not installed here, so the digest cannot be resolved in this session (the Dockerfile says so) | survives, minor | CI is outside this run's edit scope. For the user (section 10); `docs/12` 2.5 corrected to say what is not yet proven |
| V-D11-1 | falsification | `docs/12` 2.4, 2.5 | The doc named proofs that do not exist: a `test_layers.py` grep for f-strings next to `execute(`, a CI uid assertion, and readiness "ok/failed per check". | grep of `tests/`, workflow | Found the real guards: the regex in `db/session.py` `call` and `_quote_ident` in `db/migrate.py`, so the injection claim holds in code | survives, minor | doc corrected (`docs/12` 2.4, 2.5) |
| V-D11-2 | falsification | C9 | Prompt 00 D3 and D6 text (non-negative `Money` with `allow_negative`, `Version` at least 1, clamped paging, ASCII `DeviceId`, 254-character `Email`, console log only in development) no longer describe the code, which follows .NET and later prompts | `domain/values.py`; `SetupContracts.cs:140` | The code is right (.NET parity) | survives, minor | doc corrected: a "since it ran" note at the top of `docs/prompts/00-bootstrap-app.md` |
| V-D11-3 | falsification | `docs/01` s2 rule 3 | `http` imports `structlog` and the `Container` type, and `test_layers.py` allows both, but rule 3 listed neither | `http/middleware.py:11`, `http/dependencies.py:15` | none | survives, minor | doc corrected |

Notes (no failure scenario that justifies a change now):
- N1: a JSON number such as `12.340000000000000001` reaches `Money` as the float `12.34` (FastAPI parses with `json.loads`), so it is accepted rather than refused. No client sends such literals.
- N2: Money is written as `100` where .NET wrote `100.00`. The values are equal, and both clients parse JSON numbers.
- N3: an unhandled exception is logged by uvicorn with its message (`exc_info`). A database error message can carry a `DETAIL` with personal data. The gateway translates the known SQLSTATEs first (prompt 01 scope). Residual.
- N4: an IPv4-mapped peer (`::ffff:127.0.0.1`, a dual-stack bind) does not match an IPv4 trusted network. `serve` binds `0.0.0.0`.
- N5: a 500 built by Starlette's outermost `ServerErrorMiddleware` carries no CORS headers. .NET's exception handler behaves the same way, and no client is a browser origin (`docs/06` 1.9).

## 4. Per domain

Domains the scope touches: D2 (sign-in surface throttle and client address only), D4, D7, D8,
D9, D10, D11. D1, D3, D5 and D6 are `n/a` for prompt 00: no routine, table or tenant code.

| Domain | Probe | Verdict | Evidence |
|---|---|---|---|
| D2 | the rate limit runs before body validation and is charged once | holds | `dependencies.auth_rate_limit` flag; `tests/api/test_auth_contract.py` rate-limit tests ran in the full run |
| D2 | client address believed only from trusted hops | fails → fixed | V-D2-1, V-D2-2 |
| D4 | routes: .NET, `docs/06`, routers and OpenAPI agree for the scope's routes | holds | `/health/live`, `/health/ready`, `/health` (`Program.cs:179-181`), `/openapi/v1.json` (`Program.cs:184`); the global differences are drift-register rows 1 to 5 and 7 plus prompts 07 and 08 not yet built |
| D4 | error shapes, empty 404/405/415/429, `WWW-Authenticate` on envelope 401 | holds | `test_http_plumbing.py`, `http/errors.py:90-97` |
| D4 | drift of the .NET pipeline since the inventories | holds | `git log -- apps/api/Program.cs`: only route registrations (9276c51, rows 1 and 2) |
| D4 | `useGroupping`, client reads | n/a | prompt 05 |
| D7 | threads: event loop, mail task, executor | holds for 00 | one mail task; the PIN pool is prompt 04 |
| D7 | paging capped | holds | `PageRequest` refuses page sizes over 100 |
| D7 | rate-limiter cost under key rotation | fails (minor) | V-D7-1 |
| D8 | startup order, contract version, readiness semantics, shutdown drain | holds | `main.build_default_app`, `_verify_contract_version`, `test_readiness_unhealthy_when_the_contract_version_moved` |
| D8 | every timeout set: SMTP, body read, readiness | holds | `SmtpMailer` timeout; body cap; readiness 10 s |
| D8 | logs never carry bodies, PINs, codes, tokens, phones, emails | holds; N3 residual | log-call sweep (section 8): `mail.body` only with `reveal_body` (development and testing) |
| D8 | `X-Request-ID` everywhere, problem `requestId` | holds | middleware and handlers |
| D8 | CLI exit codes | holds | settings-check 0/2 measured |
| D8 | every `XCODE_*` in `settings.py`, `.env.example`, `docs/08`, `test_settings.py` | holds | sweep; `EMAIL_PORT/USERNAME/PASSWORD` sit in `docs/08` as `XCODE_EMAIL_HOST/PORT/...` and have no rule to test |
| D8 | the readiness reason is logged | fails → fixed | V-D8-3 |
| D8 | request log route template | fails → fixed | V-D8-2 |
| D9 | the documented deployment matches the real host | unproven | open questions 39 to 45; the container healthcheck defect is fixed (V-D9-1) |
| D9 | lock files with hashes; `pip-audit`; actions pinned; minimal permissions | fails (minor) | V-D9-2 |
| D9 | no secret or `.env` committed | holds | `.gitignore`, `.dockerignore` exclude `.env` |
| D9 | production TLS rule read as libpq reads it | holds | `test_settings.py` holds it against `psycopg.conninfo`; tried `u:p@ss@evil.com`, `%2F` sockets, `hostaddr` overrides, repeated `sslmode` |
| D10 | no fake of the capability under test | holds | plumbing tests use `FakeOpsRepository` only for the database port |
| D10 | `skip`, `xfail`, `importorskip`, `sleep`, bare `except` in the scope's tests | holds | two `asyncio.sleep` in `test_mail_queue.py` model a slow mailer and yield once; not timing-dependent |
| D10 | five invariants against a wrong implementation | holds after fixes | a summary that echoed the query, a first-line-only XFF reader, a health route refused by host, a raw-path route log, a domain `from .. import` now each fail a test |
| D10 | full suite on a fresh template with counts | fails | the run stopped at 36% (section 8) |
| D11 | doc clauses the scope touches match the code | fails → corrected | V-D11-1 to V-D11-3 |
| D11 | memory and earlier reports re-measured | holds | versions, file times and test counts measured here |

D2, D4, D7, D8 and D9 have findings. The probes above stand for the "hardest attacks" of
the domains that have none in scope.

## 5. Per mode

**Assumptions (Socratic).**

| Assumption | Where | Enforced by |
|---|---|---|
| Only `XCODE_TRUSTED_PROXIES` decides forwarded addresses | `docs/12` 2.6 | nothing until `proxy_headers=False` (V-D2-2) |
| A proxy appends to one `X-Forwarded-For` line | implicit in `client_address` | nothing (V-D2-1) |
| Probes reach `/health/live` with a listed host | `Dockerfile:49` | nothing (V-D9-1) |
| A database URL keeps its password in the userinfo | `_redact_url` | nothing (V-D8-1) |
| Redaction keys never hide what an operator needs | `logging.py:17` | nothing (V-D8-4, V-D8-5) |
| Python 3.13 and PostgreSQL 16 locally, 18 in CI | memory, README | measured 3.13.2 and 16.15; CI 18 never ran |

**Falsification:** the claims table in section 2 (44 claims with falsifier, result and grade).

**Pre-mortem** (ranked by likelihood × impact):
1. Week one on a container platform: every replica is "unhealthy" because production hosts
   refuse the healthcheck's Host, so the orchestrator restarts them in a loop (V-D9-1). Early
   sign: health status flapping. Fixed.
2. A credential-stuffing burst through a proxy that adds `X-Forwarded-For` lines: each request
   names a new address, the 30-per-minute limit never fires, and the PIN pool saturates into
   503s for real users (V-D2-1). Early sign: many distinct auth keys from one proxy. Fixed.
3. A support engineer pastes `settings-check` output into a ticket, and the database password
   is in it (V-D8-1). Fixed.
4. An IPv6 attacker rotates addresses. The memory limiter's map grows and every hit scans it,
   so event-loop latency climbs and readiness times out (V-D7-1). Open, owner 09.
5. Readiness fails at 3 a.m. and the runbook's log line does not exist (V-D8-3). Fixed.

Inversion: to guarantee failure, trust whatever address the client sends, print secrets on
demand, and make probes fail closed. Before this run, the first three conditions existed in
reachable configurations.

**Red team.**

| Persona | Vector | Defence | Result |
|---|---|---|---|
| Outsider with numbers | extra `X-Forwarded-For` line to rotate rate-limit keys | lines joined (V-D2-1) | gap closed |
| Outsider | forged `X-Forwarded-For` from an untrusted peer | peer untrusted, header ignored | holds |
| Outsider | oversized or chunked body to exhaust memory | 1 MiB cap, declared and streamed | holds |
| Outsider | odd `X-Request-ID` (newline, 200 characters) | regex refuses; h11 refuses raw newlines | holds |
| Compromised neighbour | reads logs or `settings-check` output for the database password | redaction (V-D8-1) | gap closed |
| Compromised neighbour | connects from loopback with a forged address after the operator narrowed the trusted proxies | `proxy_headers=False` (V-D2-2) | gap closed |
| Outsider | DNS rebinding to a health route | constant bodies, `no-store` | accepted (exemption is safe) |
| Supply chain | swapped wheel at a pinned version, or a moved action tag | none (no hashes, tag pins) | open (V-D9-2) |

**Dialectic.**

| Decision | Strongest counter | Verdict |
|---|---|---|
| Fixed window per address, in memory by default (ADR, .NET parity) | a sliding window or token bucket keyed by /64 resists rotation | keep for parity; /64 keying is a business call (section 10) |
| Host checking on every route | probes by address need an exemption, or a Host header injected into every probe | exempt the three health paths (constant bodies), keep the check elsewhere |
| JSON numbers parsed as floats by FastAPI | parse JSON with `Decimal` to refuse long literals exactly | keep (N1): no client sends them, and the cost is a custom body parser |
| Over-redacting by substring | an allow-list per event would keep operator data | keep for safety; fix the two lines that lose data (V-D8-4, V-D8-5) |
| `PageRequest` refuses rather than clamps (contrary to prompt 00) | clamping is friendlier | refuse, as .NET does (`SetupContracts.cs:140`); prompt corrected |

## 6. Conceded

- The production TLS parser and libpq disagree on `u:p@ss@evil.com` (first `@` against last).
  Conceded: when ours reads "local", libpq's host contains `@` and does not resolve, so no
  unprotected connection results.
- Injection through the routine gateway's f-string: conceded, because `call` validates the name
  against `_ROUTINE_NAME` and binds every argument; the runner quotes catalogue names
  (`db/migrate.py` `_quote_ident`). Only the documentation's "proven by" was wrong (V-D11-1).
- `X-Request-ID` regex `$` allows a trailing newline: conceded, because h11 refuses newlines in
  header values.
- `MailQueue` task death stopping all mail: conceded, because `_deliver` catches every exception
  from the send and the callback.
- Fixed-window bursts of twice the limit at a boundary: conceded as parity with .NET's
  `FixedWindowRateLimiter`.
- A password containing `/` in the userinfo: already stripped (the case passed before the fix).

## 7. Fixes

| Finding | Files | Test that failed before and passes now |
|---|---|---|
| V-D8-1 | `src/xcode_api/settings.py` (`_redact_url`) | `tests/unit/test_settings.py`: `test_summary_hides_a_password_in_the_query_of_a_database_url` (3 of 4 cases failed), `test_summary_keeps_the_host_and_sslmode_of_a_database_url`, `test_summary_hides_a_key_value_connection_string` |
| V-D9-1 | `src/xcode_api/http/middleware.py` (`HostCheckMiddleware`, `HEALTH_PATHS`), `src/xcode_api/main.py` | `tests/api/test_health_hosts_and_request_log.py::test_a_probe_by_address_reaches_the_health_routes` (3 cases); guards `test_every_other_route_still_checks_the_host`, `test_a_health_lookalike_path_still_checks_the_host`; `tests/api/test_http_plumbing.py::test_a_host_outside_the_allowed_hosts_is_refused` moved from `/health/live` to `/openapi/v1.json` with both assertions kept |
| V-D2-1 | `src/xcode_api/http/middleware.py` (`client_address`, `_header_values`) | `tests/unit/test_client_address.py::test_a_second_forwarded_line_is_read_after_the_first` |
| V-D2-2 | `src/xcode_api/cli/commands/serve.py` | `tests/unit/test_client_address.py::test_serve_leaves_forwarded_headers_to_the_trusted_proxies_setting` |
| V-D8-2 | `src/xcode_api/http/middleware.py` (`_route_template`) | `test_the_request_log_names_the_route_template_not_the_path`; guard `test_the_request_log_keeps_the_path_when_no_route_matched` |
| V-D8-3 | `src/xcode_api/http/routers/health.py` | `test_a_failed_readiness_probe_logs_its_reason_and_answers_without_it` |
| V-D4-1 | `src/xcode_api/settings.py` (`RATE_LIMIT_AUTH_PER_MINUTE_TESTING`) | `test_testing_environment_defaults_the_auth_rate_limit_to_10000`; guards for an explicit value and for production |
| V-D10-1 | `tests/unit/test_layers.py` (`_import_roots`) | `test_relative_package_imports_are_checked` |
| C35 coverage | none | `test_cors_answers_only_the_listed_origin_and_never_allows_credentials` (passed first time: evidence, not a fix) |
| documents | `docs/12-security.md` 2.4, 2.5, 2.6; `docs/06-http-contract.md` 1.10; `docs/01-architecture.md` s2 rule 3; `docs/prompts/00-bootstrap-app.md` (note) | none |

## 8. Commands and outputs

- Environment, measured: Python 3.13.2; PostgreSQL 16.15 (local cluster, port 5433);
  uvicorn 0.54.0, FastAPI 0.142.4, Starlette 1.7.0, pydantic 2.13.5, structlog 26.1.0,
  psycopg 3.3.6. CI image `postgres:18`, never run: `.github/workflows/xcode-api.yml` and
  `apps/api-python/` are untracked.
- Shared tree: another session was writing prompt 07 (revenue) files. `main.py`, `container.py`,
  `http/errors.py`, `tests/conftest.py` and `test_http_plumbing.py` changed between 14:58 and
  15:00. I edited `main.py` and `test_http_plumbing.py` only after 15:30, with one exact
  replacement each, and left `http/errors.py` alone (V-D8-5).
- Baseline before any change: 10 modules (`test_settings`, `test_domain_values`, `test_layers`,
  `test_logging`, `test_rate_limiter_contract`, `test_mail_queue`, `test_smtp_mailer`,
  `test_use_case_check_readiness`, unit `test_cli`, `test_http_plumbing`): **283 passed in
  13.48 s**.
- After the fixes: `pytest tests/unit tests/api/test_http_plumbing.py
  tests/api/test_health_hosts_and_request_log.py`: 844 passed (before the CORS test), then the
  new file 10 passed.
- `ruff check .`: All checks passed. `ruff format --check .`: 320 files already formatted.
  `mypy`: no issues in 153 source files.
- `settings-check`: development with `.env.example` as `.env` gave exit 0 and a summary.
  `XCODE_ENV=production` gave exit 2 and listed `XCODE_DATABASE_URL`, `XCODE_AUTH_SIGNING_KEY`,
  `XCODE_ALLOWED_HOSTS`, `XCODE_EMAIL_HOST` and `XCODE_EMAIL_FROM` at once (the `.env` was
  ignored).
- `xcode-api openapi` exit 0; written to the session scratchpad, not `/tmp`.
- D5 mutation on a scratch copy of `src` (the live file untouched): appending `import fastapi`
  to `domain/values.py` and `from .. import container` to `domain/errors.py` made
  `test_dependency_rule_holds` and `test_domain_imports_only_stdlib` fail, naming
  `values.py:231 … 'fastapi'` and `errors.py:58 … 'container'`.
- CLI database (`xcode`, as `xcode_owner`): `db routines` applied 184 routine files; `db status`
  reported nothing pending and no drift; `db verify` exit 0 with 21 `ok` lines.
- Template: `xcode_template` dated 15:22:11, older than `db/routines/50_revenue/cell.sql`
  (15:41:58, the revenue session's in-flight change). With no connection on the cluster
  (`pg_stat_activity` 0), I dropped it at 15:42:33. My run rebuilt it at 15:45:43. Three idle
  `test_gw*` databases from a 13:47 run belong to another session and were left alone.
- Full run: `pytest -n 3 -q -p no:cacheprovider` started 15:42:39 and was stopped at
  about 16:27 by Claude Code because the machine was low on memory (other sessions' suites and
  an `EXPLAIN` workload ran at the same time; the CPU was at 100%). Progress at the stop: 36%.
  Counted from the progress lines: 1 463 passed, 46 errors and 3 failures; the last failure is
  worker `gw0` going down ("node down: Not properly terminated"). `-q` prints names only at
  the end, so these are **unattributed**. The revenue session (revenue-6c) said its `EXPLAIN`
  script rebuilt `xcode_template` from its unfinished `db/routines/50_revenue` files at about
  15:45:52 and again at 16:05. So the run's databases were cloned from in-flight files, and
  the errors most likely belong there; I reported them to that session instead of fixing them.
  Every prompt-00 module passed in the targeted runs above. Not restarted: it should run again
  when the machine is quiet, on a template built from settled files. My run's two orphaned
  databases (`test_gw1_3972fbf088cc`, `test_gw2_3b67faa272f8`) were dropped after a minute
  with no connections or locks.

## 9. Regressions and misses against earlier audits

Read only after the pass above: `docs/audit/README.md` and
`docs/audit/2026-10-11-verify-area-docs.md` (no earlier report covers prompt 00; the
2026-10-08 validation left none).
- Regressions: none. That report's V-D9-1 (no test sent a foreign `Host`) is still covered:
  its test keeps both assertions on a routed endpoint.
- Missed by it: V-D8-1, V-D9-1 (this report), V-D2-1, V-D2-2, V-D8-2 to V-D8-6, V-D4-1,
  V-D10-1, V-D10-2, V-D7-1, V-D9-2, V-D11-1 (its V-D11-7 corrected other rows of the same
  table), V-D11-2, V-D11-3.

## 10. For the user

1. **Rate-limit key for IPv6 (business and security).** Recommendation: key `/auth` limits by
   the /64 prefix for IPv6 and the full address for IPv4. One home or mobile customer gets one
   /64, so the limit then counts people, not addresses. It differs from .NET, so it needs your
   yes.
2. **CI and supply chain (irreversible once the repository is public).** Recommendation, before
   the first push of the workflow: add `permissions: contents: read`, pin actions by commit SHA,
   generate both lock files with `--generate-hashes` and install with `--require-hashes`, pin
   the base image by digest from a machine with Docker, and either wire the push step or remove
   it. These are outside this run's edit scope (the workflow lives outside `apps/api-python/`).
3. **Commit.** The fixes are uncommitted, like the rest of `apps/api-python/`.

Resume points: the five minors with owners (V-D10-2, V-D8-4, V-D8-5, V-D8-6, V-D7-1).
`docs/prompts/README.md` was changed by another session at 16:19, so I did not edit it. Its
status row for 00 should gain: "verify `area:prompt 00` 2026-10-11
(`docs/audit/2026-10-11-verify-area-prompt-00.md`): 3 majors and 5 minors fixed; verdict
`fail` until a full run completes". Next step: one full run on a quiet machine.
