# Technology decisions

Each decision is recorded in the ADR style: context, decision, consequences, and what would
make us revisit it. Implementers do not re-open these without a new ADR appended here.

Versions below were checked against PyPI in October 2026. `requirements.txt` carries
floors; `requirements.lock.txt` (generated, committed) carries the exact pins.

## ADR-1 Python 3.13, src layout, one distribution `xcode-api`

Context: a long-lived service maintained by several people and by model-driven agents.
Decision: Python 3.13 minimum (3.14 allowed), `src/xcode_api/` package layout, console
script `xcode-api`, `pyproject.toml` for metadata and tool configuration, `requirements*.txt`
for dependencies because that is what the user asked for and what the deployment image
installs.
Consequences: tests import the installed package (`pip install -e .`), never the working
directory, so import mistakes surface early.

## ADR-2 FastAPI + uvicorn

Context: the HTTP contract is small (about 50 endpoints), JSON only, bearer tokens, OpenAPI
document asserted by tests.
Decision: FastAPI 0.136+ on uvicorn 0.47+ (`uvicorn[standard]`). One process per container;
replicas scale horizontally. No gunicorn.
Consequences: Pydantic models are the contract; dependency injection carries the principal,
the settings and the gateways; the OpenAPI document is generated. Access logging is disabled
in uvicorn and done by our middleware so every line has the request id.
Revisit if: streaming or websockets are needed (they are not in the contract).

## ADR-3 Pydantic v2 for contracts, pydantic-settings for configuration

Decision: every request and response body is a Pydantic model with `alias_generator` to
camelCase and `populate_by_name=True`; strictness is on for identifiers and money.
Settings are a single `Settings` class with `env_prefix="XCODE_"`, validated at import of
the app factory; a bad production value stops the process with a clear message.
Consequences: no hand-written JSON shaping; the OpenAPI document matches reality.

## ADR-4 psycopg 3 (async) with psycopg_pool; no ORM

Context: business rules live in PostgreSQL routines; the application needs a thin, correct
driver with excellent SQLSTATE handling, composite type mapping and a production pool.
Decision: `psycopg[binary,pool]` 3.3+, `AsyncConnectionPool`, server-side binding, dict row
factory into typed records. No SQLAlchemy, no ORM, no query builder.
Consequences: SQL in Python is limited to `SELECT * FROM api.<routine>(%s, ...)` calls in
`src/xcode_api/db/routines/`. Errors raised by routines (`RAISE ... USING ERRCODE`) are
translated by SQLSTATE in one place. `psycopg[c]` may replace `binary` in the image build
for a small speed gain; behaviour is identical.
Revisit if: a workload appears that routines cannot express well; the escape hatch is a
`SECURITY INVOKER` view granted to `xcode_app`, documented in `docs/05-routines.md`.

## ADR-5 Plain-SQL migrations and repeatable routine files, applied by our own runner

Context: DBAs review SQL files, not Python migration scripts; routines must be readable as
whole definitions in one file each, and their current definition must be diffable in a PR.
Decision:
- `db/migrations/NNNN_name.sql` (+ `NNNN_name.down.sql`): versioned, forward-only schema
  and data changes, each applied in its own transaction.
- `db/routines/<order>_<area>/<name>.sql`: one routine (or type) per file, written as
  `CREATE OR REPLACE`, all applied on every deploy in one transaction, in lexical path order.
- `db/roles/*.sql`: roles and grants; idempotent; applied by DBAs or the local compose init.
- Runner: `xcode-api db migrate|routines|status|verify`, specified in `docs/03-database.md`.
  It records versions and checksums in `ops.schema_migrations` and `ops.routine_versions`,
  holds a transaction-level advisory lock, and refuses to run when an applied file changed.
Alternatives considered: Alembic (Python migration scripts, raw SQL awkward, routines
scattered through history), sqitch (closest to the DBA workflow but a Perl toolchain in the
image), dbmate/yoyo (no repeatable migrations). The runner is about 200 lines with tests,
has no dependencies and gives the exact behaviour we want.
Consequences: a routine signature change is a versioned migration that drops the old
signature plus the edited routine file; `db verify` is the structural self-test.

## ADR-6 Row-level security plus SECURITY DEFINER routines plus a privilege-less app role

Context: the .NET service relied on EF global query filters and write guards for tenant
isolation. The equivalent must survive a forgotten `WHERE`.
Decision: described in `docs/03-database.md`: `xcode_app` can only execute `api.*`;
routines run as `xcode_api_executor`, which is not the table owner and is subject to RLS
policies keyed by a transaction-local setting that `tenancy.enter_organization` sets after
verifying membership and permission.
Consequences: a routine that forgets to enter the organization sees no tenant rows;
cross-tenant reads are impossible for the API role by construction; migrations and DBA
maintenance run as the owner and are unaffected.

## ADR-7 PyJWT (HS256), hashlib PBKDF2, `secrets` for codes and refresh tokens

Decision: PyJWT 2.13+ with `algorithms=["HS256"]` pinned, `issuer`/`audience` required,
`leeway=0`. PIN hashing with `hashlib.pbkdf2_hmac` using the parameters recorded in
`docs/07-auth.md` (taken from the .NET `Security.cs`), run in a worker thread. Refresh
tokens and verification codes are generated with `secrets` and stored as SHA-256 digests.
Alternatives: python-jose (unmaintained periods), passlib (unmaintained). Argon2 is not used
because migrated hashes must verify unchanged; a hash-upgrade-on-login path is documented
as a future extension, not built now.

## ADR-8 structlog for logging; stdlib `logging` bridged

Decision: structlog 26.1+ with `contextvars` binding of `request_id`, `actor_id`,
`organization_id`; JSON renderer outside development, console renderer in development;
uvicorn and psycopg loggers routed through the same processor chain. No print statements.

## ADR-9 aiosmtplib behind a `Mailer` port, with a drained background queue

Decision: `SmtpMailer` (production) and `LogMailer` (development/testing, explicitly
enabled). Sending is queued after the database transaction commits and drained at shutdown
for at most 10 s, matching the .NET `VerificationMailer.Idle()` behaviour. Delivery
failures are logged with the request id, never surfaced to the client (enumeration safety).

## ADR-10 Rate limiting behind a `RateLimiter` port

Decision: fixed window per client address on the auth surface, 30 per minute by default.
Two adapters: `MemoryRateLimiter` (per process, parity with .NET, default) and
`PostgresRateLimiter` (routine `api.rate_limit_hit` over an `UNLOGGED` table, correct across
replicas). Selected by `XCODE_RATE_LIMIT_BACKEND`. Both pass the same contract tests.
Not chosen: Redis (another stateful dependency for one counter).

## ADR-11 Tests on real PostgreSQL only

Decision: pytest 8 + pytest-asyncio 1.3 + httpx ASGI transport. The database comes from
`XCODE_TEST_DATABASE_URL` when set (CI service container, local compose), otherwise from
`testcontainers[postgres]`. Migrations and routines are applied once into a template
database; each test gets `CREATE DATABASE ... TEMPLATE xcode_template` and drops it after.
Tests connect as `xcode_app` for behaviour and as `xcode_owner` for structure, which is how
grant mistakes are caught. pytest-xdist parallelism is safe because every test owns a
database.
Not chosen: SQLite (the .NET suite's main source of divergence from production), mocked
gateways for behaviour tests (allowed only for unit tests of pure Python).

## ADR-12 ruff + mypy strict + pip-audit

Decision: ruff for lint and format with the `S` (bandit) rules enabled; mypy `strict = true`
on `src/`; `pip-audit` on the lock file in CI. No other linters.

## ADR-13 Container and CI (specified in `docs/08-operability.md`)

Decision: multi-stage image on `python:3.13-slim`, non-root user, read-only root
filesystem, `xcode-api serve` as the entrypoint, `xcode-api db migrate` as a separate job.
CI runs lint, type-check, tests against a PostgreSQL 18 service, `pip-audit`, and builds
the image. No CI YAML is written in this planning folder; the prompt for the bootstrap phase
specifies it.

## ADR-14 Rings: pure domain, use cases with ports, adapters outside, one composition root

Context: the domain must be testable without any framework, and dependencies must point
inwards (UI -> Domain <- Data) so that a bug is local to one ring and a change is cheap.
Decision: `domain/` (standard library only), `application/` (use cases, ports including
repository Protocols; imports `domain` only), inbound adapter `http/`, outbound adapters
`db/`, `security/`, `infra/`, and a composition root (`container.py`, `main.py`, `cli/`).
Repository implementations own connections, transactions, retries and any cache; use cases
own orchestration; routines own rules. `tests/unit/test_layers.py` enforces the import
graph; `tests/support/fakes.py` provides in-memory ports so use cases run in plain unit
tests.
Consequences: more small files than a service-per-area design; in exchange every endpoint
has one use case, one routine, one repository method and one router handler, and nothing
in `application/` or `domain/` can import FastAPI, psycopg or PyJWT by construction.
Revisit if: the repository Protocols grow past one method per routine (that would mean
rules are leaking into Python).

## ADR-15 Zero-trust posture

Decision: the controls in `docs/12-security.md` are requirements, not aspirations: every
request verified against the database, every routine re-verifying the actor, a
privilege-less application role under RLS, hashes only at rest, TLS `verify-full` to the
database outside development (unless it is reached over a Unix socket or loopback), signing-key rotation with a verify-only previous-keys list,
an audit trail for operator actions, non-root read-only containers, and startup refusal of
unsafe configuration. Each control has a named test or `db verify` check.

## ADR-16 Excel and PDF exports: XlsxWriter and ReportLab, built in the API process

Context: the notes (v2.28 section 4) ask for Excel and PDF files of every report and of the Revenue, Central expenses
and Petty cash screens, built on the server with Figtree and Fraunces embedded, A4 landscape PDF with the brand header,
tiles, banded rows, bars and a totals row, and Excel with numbers as numbers, a frozen header and a totals row. .NET
writes the `.xlsx` by hand (`ReportWorkbook.cs`, about 300 lines over `System.IO.Compression`) and the PDF with PDFsharp
(MIT) and the three OFL fonts in `apps/api/Assets/Fonts` (`docs/inventory/inventory-expenses-reports.md` RP-16, RP-17).
The host may offer no system libraries (questions 41 and 42: a shared cPanel account, no root, no package manager), so
anything that needs Cairo, Pango, HarfBuzz or a headless browser may not exist there.

Candidates, measured on 2026-10-12 from the wheels' metadata (`pip download --only-binary=:all: --python-version 3.13
--platform manylinux2014_x86_64`):

| Candidate | Licence | What it needs | Fonts | Large file | Determinism for tests |
|---|---|---|---|---|---|
| XlsxWriter 3.2.9 (Excel) | BSD-2-Clause | pure Python, no dependency | not applicable | `constant_memory` writes row by row | every part's zip time is fixed at 1980-01-01 by the library; the created date comes from `set_properties({"created": ...})`, so two runs give the same bytes |
| openpyxl 3.1.5 (Excel) | MIT | pure Python, `et-xmlfile` | not applicable | `write_only` mode streams; the default mode keeps every cell object | zip times are the wall clock; needs patching to be byte-stable |
| hand-written `.xlsx` (stdlib `zipfile` + XML, as .NET) | ours | nothing | not applicable | streams | full control |
| ReportLab 5.0.1 (PDF) | BSD | pure Python (no compiled module in the wheel); depends on Pillow (compiled wheel bundling its own image libraries; MIT-CMU) and `charset-normalizer` | TrueType embedding and subsetting built in (`pdfbase.ttfonts`) | the canvas writes page by page; a 10 000-row table is about 450 pages | `rl_config.invariant = 1` fixes dates and the document id ("produces repeatable, identical PDFs") |
| fpdf2 2.8.9 (PDF) | LGPL-3.0-only | pure Python; depends on Pillow, fontTools (compiled speed-ups, pure fallback), `defusedxml` | TrueType subsetting through fontTools | page by page | creation date settable; the file id must be fixed by hand |
| WeasyPrint (PDF from HTML) | BSD | Pango, HarfBuzz, Fontconfig system libraries | system font machinery | renders the whole document | stable once fonts are pinned |
| hand-written PDF (stdlib + fontTools for metrics and subsetting) | ours (fontTools MIT) | fontTools | our own `CIDFontType2` + `ToUnicode` code | streams | full control |

Decision:
- Excel with **XlsxWriter**, through one adapter `infra/exports/xlsx.py` implementing the port `ReportFileWriter`
  (`application/ports.py`: `write(document) -> bytes`), with `Workbook(..., {"in_memory": True,
  "strings_to_formulas": False, "strings_to_numbers": False, "strings_to_urls": False})`, `write_string` /
  `write_number` / `write_datetime` per cell kind (never `write`, which turns a text beginning with `=` into a formula
  and a text that looks like a URL into a hyperlink), and the `quote_prefix` cell format on every text cell beginning
  with `=`, `+`, `-`, `@`, a tab or a carriage return (`docs/12-security.md` 2.8). The layout is RP-16's, cell for cell.
- PDF with **ReportLab** (canvas API, no Platypus), adapter `infra/exports/pdf.py`, registering Figtree Regular,
  Figtree Bold and Fraunces Bold from a copy of the OFL fonts and their licences under
  `src/xcode_api/infra/exports/fonts/` (package data; never read from the system). `invariant` is set in tests only.
  The layout is RP-17's.
- Test-only: `pypdf` (BSD) to open a produced PDF and read its pages, text and embedded fonts; Excel files are read
  with the standard library (`zipfile` + `xml.etree`), as the .NET tests read theirs.
- Both libraries go into `requirements.txt` with a reason and into the hashed lock; `pip-audit` covers them; the
  container and the cPanel install need no system package.

The rejected options at full strength:
- **A hand-written `.xlsx`, as .NET does.** No dependency at all, so no supply chain to audit and no library update to
  track; byte-for-byte control; the .NET code is a working 300-line reference. Against it: the OOXML details .NET had to
  get right (shared versus inline strings, style indices, print titles, defined names, column widths, the frozen pane
  and auto-filter references, XML-illegal characters) are exactly what XlsxWriter has handled and tested for a decade,
  and a Python port would carry the port's own bugs with no test corpus but ours. XlsxWriter is a single pure-Python
  package without dependencies, so the supply-chain cost is one pinned, hashed wheel. Kept as the fallback if
  XlsxWriter is ever withdrawn: the adapter is the only module that imports it.
- **A hand-written PDF.** The same zero-dependency argument, stronger here because ReportLab brings Pillow. Against it:
  embedding TrueType fonts so that text is selectable and searchable needs a `CIDFontType2` font with `Identity-H`
  encoding, a width array, a `ToUnicode` map and, to keep files small, subsetting; that is several hundred lines of
  subtle code that ReportLab already has and that a reviewer cannot check by eye. Pillow is a manylinux wheel that
  bundles its own libraries, so it needs nothing from the host beyond a glibc the wheel tags allow.
- **fpdf2.** Comparable features and a smaller API. Against it: LGPL-3.0, which obliges us to let a recipient of the
  image replace the library; acceptable for a service, but BSD and MIT need nothing. It also pulls fontTools' compiled
  wheel.
- **WeasyPrint or a headless browser.** HTML templates would reuse the web's CSS. Against them: system libraries the
  host may not have (questions 41 and 42), and a renderer far larger than the problem.

Consequences: two runtime dependencies (`XlsxWriter`, `reportlab` with `pillow` and `charset-normalizer`) and one
test dependency (`pypdf`). Memory: the files are built in memory (`in_memory`), bounded by the 10 000-row cap; a
10 000-row workbook is a few megabytes, the PDF about 450 pages, built in a worker thread (`asyncio.to_thread`) so the
event loop is never blocked, as PIN hashing is. Determinism: tests pin the creation date (XlsxWriter) and `invariant`
(ReportLab), so a golden-bytes test is possible, though the export tests assert content, not bytes.

Revisit if: the host cannot install the Pillow wheel (then the hand-written PDF writer above, behind the same port), or
exports must exceed the 10 000-row cap (then XlsxWriter's `constant_memory` with a streamed response).
