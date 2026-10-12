# Prompt 02: schema

Paste everything below the line into a fresh Claude Code session running Sonnet, started in
the repository root. Requires prompts 00 and 01 to be complete.

---

You are building the PostgreSQL schema of `apps/api-python`: every `identity`, `tenancy`,
`setup` and `revenue` table, the code tables and the permission catalogue with their rows,
row-level security, indexes, triggers and schema-level functions, as migrations 0002 to
0007; the Python domain vocabulary that mirrors it; the structure, parity, isolation,
constraint and grant tests; and the `db verify` checks that prove the schema on a live
database. No `api.*` routine is written here (prompts 03 to 09). The petty-cash tables are
added by prompt 08.

## Read first, in this order

1. `CLAUDE.md`; `apps/api-python/README.md`.
2. `docs/00-principles.md` sections 3 and 4; `docs/01-architecture.md` sections 2, 3
   (`domain/`), 8; `docs/03-database.md` (all); `docs/04-schema.md` (all: it is the
   specification you implement table by table); `docs/11-naming.md`; `docs/12-security.md`
   sections 2.3 and 4; `docs/13-open-questions.md` "Before prompt 02" (build the defaults).
3. `docs/05-routines.md` sections 1.4 and 2 (so that trigger errors use the same SQLSTATE
   and code protocol as the routines) and section 6.2 (the snapshot keys are not needed
   here, but the code-table names are).
4. `docs/inventory/inventory-http-contract.md` section 3.2 (the permission catalogue rows:
   group, key, label, dependencies, role defaults) and `apps/api/Domain/PermissionKeys.cs`
   (the 40 keys; the C# file is the source of truth for the key list). Do not read other
   C# files.
5. `docs/inventory/inventory-persistence.md` section 1 only where `docs/04-schema.md` cites
   it for a column detail you need.
6. `db/README.md`, `db/migrations/README.md`, `db/roles/README.md`, `tests/README.md`,
   `tests/support/README.md`, and the code from prompts 00 and 01: `db/migrate.py`,
   `db/verify.py`, `tests/support/database.py`, `tests/conftest.py`,
   `tests/db/test_structure.py`, `domain/errors.py`, `domain/values.py`.

## Environment

PostgreSQL 18 as in prompt 01 (`docker compose up -d postgres` or `XCODE_TEST_DATABASE_URL`).
Run `git status` first; you write only under `apps/api-python/`.

## Deliverables

### D1 Migrations `0002_identity.sql` to `0007_readonly.sql`

- Exactly the files and contents of `docs/04-schema.md` section 11, every table of section
  1 with the columns, types, defaults, `CHECK` constraints (named `ck_<table>_<rule>`),
  unique constraints, foreign keys (composite ones starting with `organization_id`),
  indexes, `ENABLE ROW LEVEL SECURITY` and the `tenant_isolation` policy of
  `docs/03-database.md` section 2 on every tenant table (`tenancy.organizations` on `id`).
- Each file is one transaction, starts with `SET LOCAL lock_timeout = '10s'`, contains no
  data except code-table rows and the catalogue (D2), and no `api.*` routine.
- Grants per table per `docs/04-schema.md` section 1 ("Writes" column) to
  `xcode_api_executor`; append-only tables get `INSERT` only; audit tables revoke `UPDATE`
  and `DELETE` explicitly; code tables and the catalogue grant `SELECT` to
  `xcode_api_executor` and `xcode_readonly`; nothing else to `xcode_readonly`
  (`0007_readonly.sql` holds the DBA checklist as comments and no grant).
- `CREATE EXTENSION IF NOT EXISTS btree_gist` in `0005_setup.sql` (the only extension; add
  it to the allow-list in `db/verify.py`).
- `db/migrations/README.md`: one line per file.
- Evidence: `tests/db/test_migrate.py` still passes (fresh apply, re-run applies nothing);
  `tests/db/test_schema_structure.py` (D6).

### D2 Seed rows inside the migrations

- Code tables (`docs/04-schema.md` section 2): `setup.recurring_kinds`,
  `setup.recurrence_frequencies`, `setup.expense_buckets`, `revenue.no_earnings_reasons`
  with `code`, `name`, `label` exactly as listed.
- `tenancy.permissions` (40 rows: key, group name, label, group order, item order, in the
  order of `inventory-http-contract.md` section 3.2 and `PermissionKeys.cs`),
  `tenancy.permission_dependencies` (the `needs` column of that table),
  `tenancy.role_defaults` (the role table of section 3.2; `Owner` is every key except
  `dash.capture`). Petty-cash and office-bills keys are part of the catalogue and are
  seeded now even though their features arrive later.
- Evidence: `tests/db/test_enum_parity.py` (D6) and a test that the catalogue rows equal the
  table in the inventory (read from a fixture file you write under `tests/support/`, not
  from the inventory markdown).

### D3 Schema-level functions and triggers (`docs/04-schema.md` section 10)

- `ops.touch_updated_at()` attached to every table with `updated_at`;
  `setup.forbid_registration_change()`, `revenue.forbid_date_change()`,
  `setup.check_allocation_sum()` (constraint trigger, deferred), each raising with
  `ERRCODE = 'XC422'`, `MESSAGE = '<code>'` and a JSON `DETAIL`, the same protocol as
  `docs/05-routines.md` section 1.4 (`registration_immutable`,
  `business_date_immutable`, `allocation_sum_mismatch`).
- `tenancy.check_contrast(text, text)` (immutable; WCAG relative luminance, sRGB
  linearisation, ratio to two decimals) and the `CHECK` on the three colour columns.
- `tenancy.current_organization()`, `tenancy.current_actor()`, `tenancy.current_request()`
  reading the transaction-local settings `xcode.organization_id`, `xcode.actor_id`,
  `xcode.request_id` (`current_setting(name, true)`, `NULL` when unset).
- Evidence: `tests/db/test_constraints.py` (D6) with a contrast table of at least six
  colours whose ratios you compute by hand in the test file.

### D4 Domain vocabulary (`src/xcode_api/domain/`)

- `identity.py`, `tenancy.py`, `setup.py`, `revenue.py`, `values.py` per
  `docs/01-architecture.md` section 3: frozen dataclasses for every record a routine
  returns (fields in snake_case matching the columns and the `jsonb` keys of
  `docs/05-routines.md` section 1.3), `StrEnum`s for text-coded enumerations (`UserStatus`,
  `CodePurpose`, `ChangeLogSection`, `SignInOperation`, `SignInOutcome`, `SignInRefusal`,
  `ScopeMode`, `ThemeMode`, `DatePattern`, `WeekNumbering`, `DashboardPeriod`), `IntEnum`s
  for the code tables (`RecurringKind`, `RecurrenceFrequency`, `ExpenseBucket`,
  `NoEarningsReason` with a `label` property giving `Garage`, `Arrest`, `No Crew`, `Other`
  and a `snapshot_name` giving the .NET names `Garage`, `Arrest`, `NoCrew`, `Other`),
  `Money` (`Decimal`, two decimals, positive, below `10^12`), `Version` (`int`),
  `PageRequest` (1..100000, 1..100).
- Nothing imports anything outside the standard library (`tests/unit/test_layers.py`).
- Evidence: `tests/unit/test_domain_values.py` (normalisation and refusals of each value
  object); `tests/db/test_enum_parity.py`.

### D5 `db verify` and the shared structure module

- Extend `db/verify.py` (and the module `tests/db/test_structure.py` shares with it) with:
  every table of `docs/04-schema.md` section 1 exists with the listed primary key; every
  tenant table has RLS enabled and exactly the `tenant_isolation` policy for
  `xcode_api_executor`; every index named in `docs/04-schema.md` exists; privileges per
  table per role match section 1 and section 9 (`xcode_app` and `xcode_operator` hold
  nothing on any table or sequence; `xcode_readonly` holds `SELECT` only on code tables
  and the catalogue); audit tables carry no `UPDATE`/`DELETE` grant; no column named `pin`,
  `code`, `token`, `secret` or `password` exists unless its name ends in `_hash` or
  `_digest`; installed extensions are within the allow-list; `public` is empty.
- Evidence: `xcode-api db verify` exit 0 after `db migrate`; `tests/db/test_structure.py`
  fails when you drop one index or disable RLS on one table in a scratch copy (do this
  once, report it, restore).

### D6 Tests (`tests/db/`)

- `test_schema_structure.py`: the D5 assertions through the shared module.
- `test_enum_parity.py`: every code table holds exactly the members of its `IntEnum`
  (code and name); every `CHECK (col IN (...))` list of section 2 of `docs/04-schema.md`
  equals its `StrEnum`'s values (read the constraint definition from `pg_constraint`).
- `test_tenancy_isolation.py`: as `xcode_owner` with `SET ROLE xcode_api_executor` (the
  owner is a member of the executor role) and `set_config('xcode.organization_id', ...)`
  set directly: rows of organization A are invisible with B's id set, invisible with no id
  set, and an `INSERT`/`UPDATE` naming another organization fails with `42501`; for every
  tenant table. Add a `tests/support/database.py` helper that yields an executor-role
  connection.
- `test_constraints.py`: for every `CHECK`, unique constraint, `EXCLUDE`, foreign key and
  trigger in `docs/04-schema.md` section 7, one insert or update that must fail, asserting
  the SQLSTATE (`23514`, `23505`, `23P01`, `23503`, `XC422`) and, for triggers, the code
  in `MESSAGE`; plus one that must pass.
- `test_grants.py`: `UPDATE` and `DELETE` on each append-only table as the executor role
  fail with `42501`; `xcode_app` and `xcode_operator` cannot `SELECT` any table.
- Every test uses its own database from the template (`tests/conftest.py`), never the
  template itself.

### D7 Documentation touch-ups

- `docs/04-schema.md`: any deviation you had to make (a type, a constraint PostgreSQL
  cannot express, an index you added) is written into the document in the same change and
  listed in the report. `db/migrations/README.md` and `tests/README.md` updated.

## Invariants at the end

- `db migrate` on a fresh database applies 0001 to 0007 in order; a second run applies
  nothing; `db verify` exits 0.
- No tenant table lacks RLS; no table is reachable by `xcode_app` or `xcode_operator`;
  `xcode_readonly` sees only code tables and the catalogue.
- The `domain/` package imports only the standard library; every enumeration has exactly
  one parity test against the database.
- No `api.*` routine exists yet; nothing in Python contains SQL outside `db/migrate.py`,
  `db/verify.py`, `db/pool.py`, `db/session.py` and the test helpers.
- Lint, types and all tests green; no TODO or FIXME; no plan or prompt identifiers.

## Verify (paste the outputs into the report)

```
cd apps/api-python
docker compose up -d postgres
ruff check . && ruff format --check . && mypy
pytest -n auto -q
xcode-api db migrate && xcode-api db status && xcode-api db verify ; echo "exit=$?"
psql "$XCODE_MIGRATION_DATABASE_URL" -c "\dt identity.* tenancy.* setup.* revenue.*"
psql "$XCODE_MIGRATION_DATABASE_URL" -c "select count(*) from tenancy.permissions"   # 40
```

## Report format

1. Checklist: one row per deliverable D1 to D7 and per bullet: done or not, `file:symbol`,
   test name.
2. Verify outputs, trimmed, including the full `db verify` output and the table list.
3. Deviations from `docs/04-schema.md` with reasons; the document lines you changed.
4. Open questions you built the default for (`docs/13-open-questions.md` numbers).
5. Items left for later prompts.

## House rules

- Shared tree: `git status` first; edit only under `apps/api-python/`; never revert or
  reformat others' changes; never kill processes you did not start; never bare `git stash`.
- No commits unless the user asks. No AI attribution anywhere.
- No comments unless needed; migration files carry a one-line header naming the tables
  they create and nothing decorative; no plan or prompt identifiers anywhere.
- Never weaken a test to make it pass. If a document is wrong, fix the document and report
  it.
