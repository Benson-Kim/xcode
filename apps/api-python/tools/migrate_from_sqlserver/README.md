# migrate_from_sqlserver

The one-off, re-runnable copy of existing data into the PostgreSQL schema of `apps/api-python`
(`docs/10-data-migration.md`). It reads two kinds of source: the .NET API's SQL Server
(sections 1 to 6) and the legacy PostgreSQL database of the older single-organization
application that holds the production data (section 7, [below](#the-legacy-database)). A DBA
runs it, dry run first, and reads the printed report. It is not part of the API package and
imports nothing from `xcode_api`; the only API piece it uses is the `xcode-api db verify`
command, as a subprocess.

The cutover night runbook is [REHEARSAL.md](REHEARSAL.md): part E for the legacy database,
which is the night that will run (question 99: nothing is imported from SQL Server).

## Install

Python 3.13, from this directory:

```
python -m venv .venv
.venv/Scripts/activate            # Windows; `. .venv/bin/activate` elsewhere
pip install --require-hashes -r requirements.lock.txt
```

`extract` also needs Microsoft's ODBC Driver 17 or 18 for SQL Server on the machine.
`transform` and `load` need the API's CLI (`pip install -e ../..`, which provides `xcode-api`)
or `XCODE_API_CLI` set to its path.

## Settings (environment only, never arguments)

| Variable | For | Value |
|---|---|---|
| `XCODE_MIGRATION_SOURCE_URL` | `extract` | the SQL Server connection string, ODBC or ADO.NET form (`Server=...;Database=...;User Id=...;Password=...`). Encryption is on unless the string says `Encrypt=no`; keep `TrustServerCertificate` off outside a local machine |
| `XCODE_MIGRATION_LEGACY_URL` | `extract --source legacy` | a PostgreSQL URL of a restored, read-only copy of the legacy database (never the running application's database: the extract refuses a database that answers a write) |
| `XCODE_MIGRATION_DATABASE_URL` | `transform`, `load`, and the `xcode-api db verify` they run | the PostgreSQL target as `xcode_owner` (the tool refuses any other role) |
| `XCODE_ENV` | every command, and `xcode-api db verify` | `production` on the real target: the tool then refuses a remote PostgreSQL URL without `sslmode=verify-full` (read by libpq's own parser) and a SQL Server string that is unencrypted or sets `TrustServerCertificate` |
| `XCODE_OPERATOR` | `load --apply` | the DBA's name, written to `ops.operator_actions` |
| `XCODE_API_CLI` | optional | the path of `xcode-api` when it is not on `PATH` |

## The four commands

```
python -m migrate_from_sqlserver extract   --output <extract-dir> [--source sqlserver|legacy] [--frozen]
python -m migrate_from_sqlserver transform --input <extract-dir> --output <work-dir> [--fleet-numbers <csv>] [legacy options]
python -m migrate_from_sqlserver load      --dry-run | --apply --input <work-dir> [--accept-rejected N] [legacy options]
python -m migrate_from_sqlserver report    --input <work-dir> [--all]
```

`transform`, `load` and `report` take the source kind from the extract's `manifest.json`.
The legacy options are described [below](#the-legacy-database).

- **extract** reads every mapped table in one transaction: `SNAPSHOT` isolation when the
  database allows it; otherwise `--frozen` states that the .NET API is in maintenance and the
  read runs under `READ COMMITTED`. It writes one CSV per table, ordered by key, and
  `manifest.json` (row counts, SHA-256 of each file, the extraction instant, the server
  version, the snapshot mode, the latest EF migration). Tables that are not copied
  (`VerificationCodes`, `RolePermissions`, the lookup tables, `__EFMigrationsHistory`) are
  counted only. It writes into a new directory and never into an old extract.
- **transform** checks every file against the manifest, maps every row through the table
  map (`migrate_from_sqlserver/tablemap.py`), runs the conversions
  (`conversions.py`), and validates every row against the target's own constraints by copying
  everything into the target inside a transaction that is always rolled back. A refused row is
  reported with its source key (`Table=...|Id=...`, the GUIDs as SQL Server prints them) and
  does not move; rows that reference it are refused by their foreign key in turn. When the
  refused rows break a deferred rule (a refused vehicle takes its allocations with it, so a
  scheduled item's allocations no longer add up), the transform still writes its files,
  marks the rule as blocking and exits 1; the load then refuses. It writes
  `load/*.csv` (PostgreSQL's own export of the accepted rows), `transform.json` (every
  refused row, every row dropped by a documented rule, every changed value with its key and
  reason, every row it made) and `permission_old_sets.csv`.
- **load** copies the load files in one transaction as `xcode_owner`, under the migration
  runner's advisory lock, then runs the verifications: rows per table, each table's ordered
  rows equal to its load file byte for byte, the ledger (source + made = loaded + dropped +
  refused, table by table), deferred constraints, every tenant row's organization,
  `api.auth_resolve_session` for people on live devices, revenue per organization and month
  against the source, the grant translation reproduced in SQL, and `xcode-api db verify`.
  `--dry-run` always rolls back. `--apply` commits only when every verification passes and
  records an `ops.operator_actions` row (`data_migration_load`). Refused rows must be
  acknowledged with `--accept-rejected N` (N = their count); a refused person or organization
  can never be accepted. `--input` may also be an extract directory: it is transformed first,
  into `--output` or a new temporary directory.
- **report** prints what moved, what did not and why, every changed value, the rights of every
  person before and after, the revenue sums, and every verification. `--all` lifts the
  50-line cap per group.

Exit status: 0 when the command did what it says and every verification passed, 1 when it
stopped or a verification failed (nothing written), 2 for a usage error.

## DBA procedure

1. Restore a copy of production SQL Server onto a rehearsal server; provision a fresh
   PostgreSQL target (`db/roles`, `xcode-api db migrate`, `xcode-api db verify`).
2. `extract`, `transform`, `report`. Fix in SQL Server what the report refuses, or decide
   with the owner to accept it. Repeat until the report is clean.
3. `load --dry-run` on the fresh target; every verification must pass.
4. On the cutover night follow [REHEARSAL.md](REHEARSAL.md): freeze, `extract`, `transform`,
   `load --dry-run`, `load --apply`, switch the clients.
5. Keep the work directory with the report until the retention period ends
   (`docs/13-open-questions.md` question 13), then destroy it.

The target must be empty: the load never merges and refuses a database that already holds
rows. To run again, drop and re-create the target and migrate it.

## Handling the files

The extract and the work directory hold every person's name, phone number and e-mail, the PIN
hashes and the refresh-token digests. They are as sensitive as the database: keep them on an
encrypted disk of the migration host, never in a ticket, chat or repository, and destroy them
with the SQL Server copy. The hashes are copied byte for byte and never re-computed; a refresh
digest is keyed with the signing key, so sessions survive only if the Python API runs with the
.NET API's signing key (`docs/07-auth.md` section 1).

## What the tool changes, and why

Every change is listed in `transform.json` and printed by `report`; the rules are in
`docs/10-data-migration.md` sections 2, 3, 3.1 and 3.2. In short: GUIDs lower case; instants in
UTC with the 100 ns digit rounded half to even (counted per column); e-mails lower case; phone
numbers normalised; security-policy values clamped into bounds; Windows time-zone ids mapped
to IANA names; a running pause becomes the five-try lock; weekly targets become dated day
sets; buckets become main categories; every person's rights go through the grant translation;
a sent-back petty-cash expense waits with its note; cash given and credit notes lose any
review; audit events get identity ids in occurrence order, and the reason sentence .NET stored
as an access change's `After` becomes a JSON string; trusted devices get their trust and
last-use dates from their refresh tokens; revoked and expired refresh tokens stay behind.

## The legacy database

`docs/10-data-migration.md` section 7: the production data lives in the PostgreSQL database
of an older, single-organization application (alembic `d8e1a4f9c220`). The same four commands
move it, with these differences.

```
python -m migrate_from_sqlserver extract   --source legacy --output <extract-dir>
python -m migrate_from_sqlserver transform --input <extract-dir> --output <work-dir> --migrated-by <e-mail> --people <people.csv> [--organization-name <name>] [--organization-slug <slug>] [--fleet-numbers <csv>]
python -m migrate_from_sqlserver report    --input <work-dir>
python -m migrate_from_sqlserver load      --dry-run | --apply --input <work-dir> --accept-rejected <N>
```

- **The source is a copy.** Restore the dump (`pg_restore --no-owner --no-acl`) into a
  scratch database, then mark it read-only:
  `ALTER DATABASE <copy> SET default_transaction_read_only = on`. The extract refuses a
  database that answers a write (a read-only option in the URL or `PGOPTIONS` does not
  count: the database itself must be marked, or be a standby), any alembic version but `d8e1a4f9c220` (the map was checked
  against it), and any soft-deleted row (the map does not cover one). It reads in one
  `REPEATABLE READ READ ONLY` transaction, one query per target table, never the password
  hashes, and records in `manifest.json` the source kind, the alembic version, every legacy
  table's count and the source figures the load checks (revenue per vehicle and month, vehicle
  costs, petty cash per kind and status, the float, the people, the stored daily balance).
  Every amount is exported as the shortest decimal that reads back as the same
  `double precision`, so an amount that would round is refused, never rounded.
- **`--people <csv>`** (`legacy_email,email,phone,role`): one row per legacy user, from the
  owner's letter. `email` and `phone` are what the person signs in with; `role` is `Owner`,
  `Fleet manager` or empty (an Administrator becomes an Owner, anyone else a Fleet manager).
  A legacy user without a row, or without a valid number, is refused and stops the load. The
  file holds personal details: write it on the migration host, keep it off the repository and
  out of tickets, and destroy it with the work directory. A problem in it is reported by line
  number, never by value.
- **`--migrated-by <e-mail>`** (old or new e-mail) names the Administrator who becomes the
  author of every value the source never stored (who captured revenue, recorded expenses,
  gave cash, approved petty cash). They must move as an Owner.
- **`--organization-name`, `--organization-slug`**: the one organization, made as
  `api.ops_provision_user` makes it (defaults `My fleet`, `my-fleet`), with its four roles.
- **Held-back rows** (the deductions on items without a category, the expense without a
  vehicle, a day with two different revenue amounts, an amount that does not divide by its
  quantity or would round) are refused rows: acknowledge them with `--accept-rejected N`
  (180 on the dump of 13 October 2026).
- **`report`** also writes `exceptions.csv` into the work directory: one row per held-back,
  left-out or dropped row, possible double moved and petty-cash balance day, with the legacy
  day, vehicle, item, amount, entry time, reason, legacy table and id, and empty Decision and
  Note columns for the owner. No name, e-mail, number or payee appears in it, in the report
  or in `transform.json`/`load.json`: people are named by role and legacy creation date.
- **`load`** runs the checks of section 4 and of 7.5 (every legacy row loaded, dropped by a
  named rule, refused or replaced; the people, their roles, scopes and rights; revenue,
  vehicle costs and petty cash against the source figures; the vehicle report's postings
  through `setup.fleet_postings`; every person reaching "Not signed in yet" through
  `api.auth_start`), all inside the load's transaction.

The rules (7.3, 7.4) are in `migrate_from_sqlserver/legacy_tablemap.py` (the map, the rights
table) and `legacy_conversions.py` (the conversions); `legacy_checks.py` holds the 7.5
checks and `legacy_report.py` the report and the exceptions list.

## Tests

```
pip install --require-hashes -r requirements.lock.txt -r requirements-dev.txt
pytest -q
```

They need no SQL Server: the fixture extract (`tests/fixtures/extract`, built by
`python -m tests.fixture_data`) is loaded into PostgreSQL targets cloned from a template that
`xcode-api db migrate` builds. The legacy tests (`tests/test_legacy.py`) build a legacy
database from the dump's schema (`tests/fixtures/legacy/legacy_schema.sql`, from
`pg_restore -s` without owners, grants and `\restrict` lines) and synthetic rows that go in
through the old application's own triggers (`tests/fixtures/legacy/legacy_rows.sql`; no
production row); they need the `uuid-ossp` extension on the test server. Set `XCODE_TEST_DATABASE_URL` (a role with CREATEDB and
CREATEROLE) and have `xcode-api` installed; `XCODE_MIGRATION_TEST_TEMPLATE` names a private
template. `tests/test_extract.py` runs only when `SQLSERVER_TEST_CONNECTION` is set, and only
reads.
