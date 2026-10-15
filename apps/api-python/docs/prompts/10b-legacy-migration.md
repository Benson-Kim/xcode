# Prompt 10b: migrate the legacy PostgreSQL database

Paste everything below the line into a fresh Claude Code session (Opus: data integrity and a
migration are involved), started in the repository root, after prompts 00 to 10 and 08b.

---

You are building the path that moves the production data into `apps/api-python`. That data is
not in the .NET API's SQL Server: it is in the PostgreSQL database of an older, single-organization
application, whose dump is `apps/api-python/docs/xcode_20261013T0836Z.dump`. The specification
is `docs/10-data-migration.md` section 7. Consult the api-python schema and routines and the dump;
the .NET code is not a source for this work.

## Read first

1. `CLAUDE.md`; `apps/api-python/README.md`; `.coordination/board.md` (rules, freezes, claims).
2. `docs/10-data-migration.md` sections 1, 4 and 7 (all of 7); `docs/13-open-questions.md`
   questions 11, 16, 17 and 90 to 100 (90 to 98 decided by the owner on 2026-10-14, in the letter
   `docs/reports/XCODE-Migration-Decisions.pdf` at the repository root: it names people with
   their e-mails and numbers, so read it for the `--people` file of the rehearsal and never copy
   a value of it into the repository); `docs/04-schema.md` sections 3.1, 4.1 to 4.8, 5, 6, 13 and
   14.2; `docs/15-design-v2-3.md` 3.1 and 3.2 (the 59 rights, role defaults).
3. The existing tool, `tools/migrate_from_sqlserver/` (README, `transform.py`, `load.py`,
   `report.py`, `database.py`, `records.py`, `formats.py`, its tests): its strategy is the one
   section 7 keeps.
4. `db/routines/20_identity/ops_provision_user.sql` and `tenancy.seed_roles` (how an
   organization and its roles are made), `identity.normalize_phone`, `setup.fleet_postings`.
5. The dump itself: restore it into a scratch database of your own (`pg_restore --no-owner
   --no-acl`; never into the shared test cluster's templates) and check every figure of section
   7.1 before relying on it.

The dump holds personal details and password hashes. Never copy a row of it into the
repository, a test fixture, a log or a report; reports carry counts and sums only.

## Deliverables

### D1 A second source in the tool

- `python -m migrate_from_sqlserver extract --source legacy --output DIR` reads
  `XCODE_MIGRATION_LEGACY_URL` (a restored copy; refuse a URL whose database answers a write)
  in one `REPEATABLE READ READ ONLY` transaction, one query per target table of section 7.3,
  into the extract format of section 1 with a manifest naming the source kind and its alembic
  version (refuse any version but `d8e1a4f9c220` until the map is checked against it).
- `transform`, `load` and `report` take the source kind from the manifest. Make them work over a
  profile (table map, conversions, drop rules, source figures, verifications) instead of the
  module-level SQL Server map; the SQL Server profile and its tests stay exactly as they are and
  stay green. New modules for the legacy profile (`legacy_*.py`); no import of `xcode_api`.
- Parameters of section 7.2: `--organization-name`, `--organization-slug`, `--migrated-by`,
  `--people` (`legacy_email,email,phone,role`; every legacy user must have a row), `--fleet-numbers`;
  the held-back rows go through the existing `--accept-rejected`.
- Every rule of section 7.3 and the rights of 7.4, each with its listed values (made, changed,
  dropped by a named rule, refused with the legacy key and the constraint).
- The verifications of section 7.5, each a `Check` that `--apply` requires.
- The exceptions list of section 7.2 (`exceptions.csv`, written by `report`): held back, left
  out, dropped double entries, possible doubles moved, petty-cash balance days, each row with
  its reason and empty Decision and Note columns.

### D2 Tests

- A legacy fixture database built from the dump's schema only (`pg_restore -s`, stripped of
  owners, grants and `\restrict` lines, committed as SQL) plus synthetic rows that exercise every
  rule of 7.3 and 7.4: a double-entered revenue day, a zero day, a person without a phone, a
  person whose e-mail and role `--people` change, a legacy user missing from `--people`, a
  one-word name, a duplicate item name, items without a category (their records held back), a
  petty-cash expense without a vehicle, zero petty-cash rows, committed and uncommitted expenses,
  rows with no manager, the default manager and another manager (all three end with the one
  holder), an expense and a cash entry that repeat another of the same day (moved, listed), a
  credit note, a petty-cash copy in `records` (and one that disagrees with its original), a
  registration without its space, a provision and a budget.
- Assertions as prompt 10's D2, plus each figure of 7.5 computed independently in the test, the
  rights of each fixture person, every row of the exceptions list against the fixture (and that
  no user name, e-mail or number appears in it or in any other output), and that a migrated person with a number reaches the
  "Not signed in yet" path of the sign-in routines. Each new rule's test fails first.
- The SQL Server tests unchanged and green.

### D3 Rehearsal on the real dump

- Restore the dump into a scratch database, run `extract --source legacy`, `transform`, `report`,
  `load --dry-run` against an empty target built by `xcode-api db migrate`. Record in the report:
  every count and figure of 7.5 (they must equal the section's, or the section is corrected with
  the reason), the refused and dropped rows by rule (counts only; 180 held back, 3 left out, 5
  double entries dropped, 16 possible doubles moved), the exceptions list's rows by kind,
  the run times.
- Add the legacy commands to `tools/migrate_from_sqlserver/README.md` and a legacy cutover
  runbook to `REHEARSAL.md` (decisions 90 to 100 as checkboxes, 90 to 98 ticked from the letter;
  the `--people` file written from the letter and kept off the repository; freeze of the old application;
  `pg_dump` of production; restore; the four commands; the owner's first steps of 7.6: targets,
  fleet numbers, main categories, approving the waiting expenses, re-entering the provision).

### D4 Documentation

- `docs/10` section 7 follows the code (any rule the build changes); `docs/13` 90 to 100 keep
  their decisions and defaults unless the owner decides again; `docs/prompts/README.md` status row 10b.

## Invariants at the end

- No write to the target without `--apply`; `--apply` refuses when any verification fails.
- No production row in the repository; the fixture is synthetic.
- Every legacy row ends loaded, dropped by a named rule of 7.3, refused with its key, or replaced
  by rows the tool made; the report counts all four per source table.
- Money moves exactly: every legacy amount fits `numeric(14,2)` and every quantity
  `numeric(12,3)` without rounding (the transform refuses a value that would round).

## Verify

```
cd apps/api-python/tools/migrate_from_sqlserver
pytest -q
python -m migrate_from_sqlserver extract --source legacy --output <scratch>/legacy
python -m migrate_from_sqlserver load --dry-run --input <scratch>/legacy --output <scratch>/work --migrated-by <email> --people <scratch>/people.csv --accept-rejected 180 ; echo "exit=$?"
```

Then `ruff check`, `ruff format --check`, `mypy` (strict, as CI runs the tool).

## Report

`docs/audit/<date>-build-10b.md`: checklist per deliverable bullet with `file:symbol` and test
names; the rehearsal's figures against 7.5; the open questions touched; a challenge pass as
prompt 10's (pre-mortem of the cutover night first).

## House rules

As prompt 10: shared tree, `git status` first, write only under `apps/api-python/tools/` and the
documents named above, no commits unless asked, no AI attribution, no plan or prompt identifiers
in code, connection strings only from the environment.
