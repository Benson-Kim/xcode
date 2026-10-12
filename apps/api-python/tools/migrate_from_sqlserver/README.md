# migrate_from_sqlserver

The one-off, re-runnable copy of the .NET API's SQL Server data into the PostgreSQL schema of
`apps/api-python` (`docs/10-data-migration.md`). A DBA runs it, dry run first, and reads the
printed report. It is not part of the API package and imports nothing from `xcode_api`; the
only API piece it uses is the `xcode-api db verify` command, as a subprocess.

The cutover night runbook is [REHEARSAL.md](REHEARSAL.md).

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
| `XCODE_MIGRATION_DATABASE_URL` | `transform`, `load`, and the `xcode-api db verify` they run | the PostgreSQL target as `xcode_owner` (the tool refuses any other role) |
| `XCODE_ENV` | `xcode-api db verify` | `production` on the real target (its TLS rules apply) |
| `XCODE_OPERATOR` | `load --apply` | the DBA's name, written to `ops.operator_actions` |
| `XCODE_API_CLI` | optional | the path of `xcode-api` when it is not on `PATH` |

## The four commands

```
python -m migrate_from_sqlserver extract   --output <extract-dir> [--frozen]
python -m migrate_from_sqlserver transform --input <extract-dir> --output <work-dir> [--fleet-numbers <csv>]
python -m migrate_from_sqlserver load      --dry-run | --apply --input <work-dir> [--accept-rejected N]
python -m migrate_from_sqlserver report    --input <work-dir> [--all]
```

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
  does not move; rows that reference it are refused by their foreign key in turn. It writes
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
review; audit events get identity ids in occurrence order; trusted devices get their trust and
last-use dates from their refresh tokens; revoked and expired refresh tokens stay behind.

## Tests

```
pip install --require-hashes -r requirements.lock.txt -r requirements-dev.txt
pytest -q
```

They need no SQL Server: the fixture extract (`tests/fixtures/extract`, built by
`python -m tests.fixture_data`) is loaded into PostgreSQL targets cloned from a template that
`xcode-api db migrate` builds. Set `XCODE_TEST_DATABASE_URL` (a role with CREATEDB and
CREATEROLE) and have `xcode-api` installed; `XCODE_MIGRATION_TEST_TEMPLATE` names a private
template. `tests/test_extract.py` runs only when `SQLSERVER_TEST_CONNECTION` is set, and only
reads.
