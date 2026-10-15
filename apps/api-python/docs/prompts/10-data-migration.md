# Prompt 10: data migration tool and cutover rehearsal

Paste everything below the line into a fresh Claude Code session running Sonnet, started in
the repository root, after prompts 00 to 09. Skip this prompt entirely if the owners decided
(`docs/13-open-questions.md`) that no SQL Server database needs to move.

---

You are building the one-off, re-runnable tool that copies data from the .NET API's SQL
Server database into the PostgreSQL schema of `apps/api-python`, and the rehearsal script
for the cutover. The tool is separate from the API package; it is run by a DBA with a
printed report, in dry-run mode first.

## Read first

1. `CLAUDE.md`; `apps/api-python/README.md`.
2. `docs/10-data-migration.md` (all), `docs/04-schema.md` (all), `docs/03-database.md`
   sections 2, 6, 7, `docs/07-auth.md` section "Parameters" and the hash formats,
   `docs/11-naming.md`, `docs/13-open-questions.md` (the decisions recorded for this phase).
3. `docs/inventory/inventory-persistence.md` sections 1, 7, 9 (source schema, raw SQL
   history, SQL Server specific features) and `docs/inventory/inventory-auth.md` (hash and
   token storage formats).
4. The current PostgreSQL schema as applied: `db/migrations/*.sql`.

## Deliverables

### D1 Package `apps/api-python/tools/migrate_from_sqlserver/`

- Own `requirements.txt` (`pyodbc` or `pymssql`, `psycopg[binary]`, nothing else) and
  `requirements.lock.txt`; its own `README.md` with the four commands and the DBA
  procedure; no imports from `xcode_api`.
- Commands (`python -m migrate_from_sqlserver <command>`): `extract`, `transform`,
  `load --dry-run | --apply`, `report`, exactly as `docs/10-data-migration.md` section 1.
  Connection strings come from `XCODE_MIGRATION_SOURCE_URL` (SQL Server) and
  `XCODE_MIGRATION_DATABASE_URL` (PostgreSQL, as `xcode_owner`); never from arguments.
- Table map: implement section 3 of `docs/10-data-migration.md` as data (one record per
  table: source name, target `schema.table`, column renames, enum value maps, dropped-row
  predicates, FK load order). The code iterates over the map; adding a table is adding a
  record.
- Type mapping per section 2, including lower-casing GUIDs, `datetime2` as UTC, `bit` to
  boolean, enums stored as integers to their wire strings, JSON validated into `jsonb`.
- Hashes copy byte for byte; the tool never re-hashes anything.
- `extract` writes one CSV per table plus `manifest.json` (row counts, per-table SHA-256
  over the canonical ordered CSV, source server version, extraction time, snapshot mode).
- `transform` validates every row against the PostgreSQL constraints before load and
  reports violations with the source key, then writes load files and a `transform.json`
  listing every value it changed (normalised phone numbers, clamped values) with its key.
- `load` runs in one transaction as `xcode_owner`, `COPY` in FK order, then the
  verification queries of section 4; `--dry-run` loads into a scratch schema and rolls
  back; `--apply` commits only when every verification passes. It writes an
  `ops.operator_actions` row (`data_migration_load`) with `XCODE_OPERATOR`.
- `report` prints source versus target counts, checksum matches, verification results,
  and the transformed-value list.

### D2 Tests (`apps/api-python/tools/migrate_from_sqlserver/tests/`)

- Transform and load are tested without SQL Server: fixture CSVs in the extract format
  (a small organization with users, memberships, vehicles, recurring items and revenue
  records, including one row per enum value and one deliberately invalid row) loaded into
  a PostgreSQL test database built with the API's migration runner (reuse the harness's
  template approach; do not import the API package, invoke `xcode-api db migrate` as a
  subprocess).
- Assertions: counts and checksums match the manifest; the invalid row is reported with
  its key and nothing is loaded in dry-run; `--apply` loads everything else; after the
  load, `api.auth_resolve_session` succeeds for a user whose hash and token digest were
  copied unchanged (sign in through the API's routines with a PIN whose hash is in the
  fixture); revenue sums per organization and month match; every tenant row's
  `organization_id` exists; `xcode-api db verify` passes.
- Extract is tested only when `SQLSERVER_TEST_CONNECTION` is set (same convention as the
  .NET `SqlServerTests`); otherwise the test is skipped with that reason.

### D3 Rehearsal script

- `docs/10-data-migration.md` section 5 turned into `tools/migrate_from_sqlserver/REHEARSAL.md`:
  a numbered, copy-paste runbook with the exact commands, expected outputs, the freeze
  step for the .NET API, the `API_URL` switch for the web proxy and mobile configuration,
  the watch list, and the rollback steps. Include the decision points from
  `docs/13-open-questions.md` as explicit checkboxes at the top.

### D4 Documentation

- Fill any gap you found in `docs/10-data-migration.md` section 3 (table map) from the
  actual schema, including the tables 08 and 08b added (petty cash, central expenses,
  scheduled-item pauses) and any table the drift register in `docs/prompts/README.md`
  lists since, and the data changes of design register row B20 (weekly
  targets into dated target sets, people without a PIN, fleet numbers, petty-cash and
  savings rights copied from the old ones, categories without a main category); record in `docs/13-open-questions.md` anything the owners still have to
  decide (retention period, whether verification codes move).

## Invariants at the end

- No write to the target without `--apply`; `--apply` refuses when any verification fails.
- The tool never re-hashes, never fabricates ids, never drops rows outside the documented
  predicates, and prints every value it changed.
- The tool's tests run in CI without SQL Server (extract skipped with a reason).

## Verify

```
cd apps/api-python/tools/migrate_from_sqlserver
pip install -r requirements.lock.txt -r requirements-dev.txt
pytest -q
python -m migrate_from_sqlserver load --dry-run --input tests/fixtures/extract ; echo "exit=$?"
```

## Challenge pass (before the report)

Apply `docs/14-verification.md` to your own work as if nobody, including you earlier in
this session, had reviewed it:
1. Steelman: list every deliverable bullet and invariant above as a claim, with the code
   that carries it.
2. Falsify: for each claim, name the observation that would disprove it and look for it;
   grade the evidence (section 5). Tenancy, security and integrity claims need grade A.
3. Run the five modes over D3 (no row lost, duplicated or altered), D5 (dates, time zones, normalisation), D6 and D9 (credentials), starting with a pre-mortem of the cutover night, plus D10 (tests as evidence) and D11 (documents);
   give every probe of section 4 for those domains a verdict.
4. Try to refute each finding; fix the survivors with a test that fails first, or record
   them (corrected document, open question, residual risk).
5. Report the findings table (section 7), the conceded challenges with the guard that
   defeated each, and the three hardest attacks for any domain without findings.

This pass does not replace the separate `verify.md` run on this prompt; it makes that run
cheaper.

## Report format

1. Checklist per deliverable and bullet with `file:symbol` and test names.
2. Verify outputs; the dry-run report for the fixture set.
3. Table map decisions and anything not derivable from the documents.
4. Open questions added.

Add the challenge-pass results and the drift-check corrections as the last section of
the report.

## House rules

- Shared tree: `git status` first; write only under `apps/api-python/tools/` and the two
  documents named above; never revert others' changes; never bare `git stash`.
- No commits unless asked; no AI attribution; no plan or prompt identifiers in code; no
  credentials in files; connection strings only from the environment.
