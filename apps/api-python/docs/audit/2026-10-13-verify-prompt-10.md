# Verify: prompt 10 (data migration), fix mode, standard depth, 2026-10-13

Session revenue-e7 [344b4b], fresh eyes (wrote none of prompt 10). At the user's request the
focus moved from the .NET source to the real production data: the dump
`docs/xcode_20261013T0836Z.dump`, mapped straight onto the api-python schema ("consult the
api-python and the dump, not .NET"). The board's freeze on `src/`, `db/`, `tests/` (queue row 9,
the 08b full run) held for the whole session, so nothing under those paths changed and no test
ran on the shared cluster; the dump was restored into a private cluster in the scratchpad.

## 1. Verdict

**fail**: one blocker survives (the production data cannot be moved by the tool prompt 10
built), and the full suite was not run by this session (the shared run of queue row 9 was in
progress, 12% at 14:44).

| | count |
|---|---|
| Claims | 9: holds 3, fails 2, unproven 2, not checked 2 |
| Findings | 10: blocker 1, major 6, minor 2, note 1 |
| Fixed here (documents) | 5 (V-D11-1, V-D11-2, V-D12-1 locally, and the specification of V-D3-1/V-D2-1 in `docs/10` 7) |
| Owed to prompt 10b (code) | V-D3-1 to V-D3-5, V-D2-1, V-D9-1 |

## 2. Thesis and claims

Steelmanned thesis: "Prompt 10 delivers a re-runnable, verified copy of the production data into
the PostgreSQL schema: the tool reads the source, refuses nothing silently, moves money exactly,
and the cutover runbook gets the owner from the old system to the new one without losing a row."

| # | Claim (where stated) | Carried by | Verdict | Grade |
|---|---|---|---|---|
| C1 | The tool copies the data that must survive (`docs/10` intro, prompt 10 preamble) | `extract.py` reads SQL Server only (`SOURCE_ENV`, `pyodbc`) | **fails**: production is a legacy PostgreSQL database (V-D3-1) | A (dump TOC, `pg_restore -l`) |
| C2 | `docs/13` question 11 frames the decision ("whether any SQL Server database is worth migrating") | `docs/13` row 11 | **fails** as a framing: the real source was never named (V-D11-1) | A |
| C3 | No write without `--apply`; `--apply` refuses on a failed check (prompt 10 invariant) | `load.py` `run`, `_verify` | holds by reading; the strategy is kept for the legacy source (`docs/10` 7.2) | C (read, not run here) |
| C4 | Every value changed or made is listed (prompt 10 invariant) | `records.Ledger` | holds by reading; the legacy rules of 7.3 each name their listing | C |
| C5 | Money moves exactly | SQL Server: `formats.py` decimals | holds for the legacy data: every stored `double precision` amount has at most 2 decimals and every quantity at most 3 (measured), so `numeric(14,2)`/`numeric(12,3)` take them without rounding | A (SQL on the dump) |
| C6 | The tool runs against the current target (`0013`, contract 6) | `tablemap.py` `since=13` records | **unproven** on 2026-10-13 (freeze); **proven 2026-10-14** (section 11): the suite, a test with both tables' rows and an `XCodeTest` apply against `0014` | A |
| C7 | The tool's tests run in CI without SQL Server | `.github/workflows/xcode-api.yml` | not checked (no CI run inspected) | - |
| C8 | Ruff and format are clean on the tool | `tools/migrate_from_sqlserver` | holds: `ruff check .` all passed; `ruff format --check .` 22 files formatted (15:05) | A |
| C9 | The cutover runbook covers the real cutover (`REHEARSAL.md`) | `REHEARSAL.md` | not checked in detail: it is a SQL Server runbook, superseded for production by V-D3-1 | - |

## 3. Findings

| Id | Sev | Domain | Finding | Evidence | Synthesis |
|---|---|---|---|---|---|
| 10:V-D3-1 | blocker | D3 | The production data is in a legacy PostgreSQL database (alembic `d8e1a4f9c220`; `users`, `vehicles`, `entries`, `records`, `petty_cash`, …), not in the .NET SQL Server the tool reads; nothing in the repository referred to it | `pg_restore -l docs/xcode_20261013T0836Z.dump`: 13 tables in `public`, owner `doadmin`; `extract.py` (`XCODE_MIGRATION_SOURCE_URL`, `pyodbc`); a repository-wide grep for the legacy table names found nothing | Specified: `docs/10` section 7 (source facts, parameters, table map, rights, verifications, owner view), questions 90 to 99, build prompt `docs/prompts/10b-legacy-migration.md` (a second source in the same tool, the SQL Server path unchanged). Code owed by 10b |
| 10:V-D3-2 | major | D3 | `records` holds 1,198 trigger copies of committed petty-cash expenses beside 1,407 direct expenses; moving every `minus` record as a central expense would count those 3,895,300 twice on the vehicles (petty cash posts approved expenses itself) | `after_insert_update_petty_cash()` inserts into `records`; all 1,198 match their original (amount, day, vehicle, item), 0 copies of uncommitted rows | `docs/10` 7.3: copies not moved, matched to their originals (a mismatch stops the transform); 7.5 checks vehicle costs = central + approved petty cash (30,383,042 = 26,487,742 + 3,895,300) |
| 10:V-D3-3 | major | D3 | The legacy float's stored daily balances diverge from its own entries since 2026-09-17 (14 days; on 2026-10-09 stored −2,580,518, entries −619,557), and 2 balance rows have no entry. The new system computes the float from entries, so the owner will see a different balance from the old screen | window sum over `petty_cash` against `petty_cash_daily_balances`: equal through 2026-09-16, differ from 2026-09-17 | Not a tool defect: `docs/10` 7.5 prints the stored figure beside the checked one; 7.6 tells the owner; section 10 below |
| 10:V-D3-4 | major | D3 | Five vehicle-days hold the same revenue twice (38,450); the target allows one record per vehicle and day | 3,527 `Earnings` rows over 3,522 vehicle-days; each pair has the same amount, entered 0 s to 40 min apart | `docs/10` 7.3 row 12 (keep the earliest, list the other), question 92 |
| 10:V-D3-5 | minor | D3 | Rows the target refuses as they stand: 2 zero revenue days, 3 zero petty-cash rows, 1 petty-cash expense without a vehicle (30,000), 2 repeated item names in one category, 5 items without a category (179 records, 1,031,025), 8 registrations without the space | SQL on the dump (counts in `docs/10` 7.1, 7.3) | A rule each in 7.3; questions 93, 95, 96 |
| 10:V-D9-1 | major | D6, D9 | No credential can move: people sign in with e-mail and bcrypt passwords, the target with phone, code and PIN. Everyone starts "Not signed in yet"; one Administrator has no phone, and a person without one stops the load | `users.password` `$2b$12$` on 7 of 7; `phone` empty on 1; `docs/04` 3.1 `phone_number NOT NULL` | `docs/10` 7.3 row 1 (`pin_hash` null), 7.2 `--people`, 7.6 (code delivery must work on the night), question 90 |
| 10:V-D2-1 | major | D2 | The legacy app has no data scopes (everyone sees every vehicle). Made as `api.ops_provision_user` makes them, the four Fleet managers would get no `tenancy.data_scopes` row and see no vehicle after cutover | `ops_provision_user.sql:178-182` gives a scope to Owner and Office admin only | `docs/10` 7.3 row 6: `all_companies` true for every migrated person, checked in 7.5 |
| 10:V-D12-1 | major | D12 | The dump (production names, e-mails, phone numbers, bcrypt hashes) sat untracked and not ignored in `apps/api-python/docs/`, one `git add -A` from a commit | `git status --short` showed `?? apps/api-python/docs/xcode_20261013T0836Z.dump`; `git check-ignore` found no rule | Fixed locally: `apps/api-python/docs/*.dump` added to the repository's `.git/info/exclude` (not shared with other clones); the user should move the file out of the repository tree |
| 10:V-D11-1 | major | D11 | `docs/10` and `docs/13` question 11 treat the migration as SQL Server or nothing; the real source is absent from every document | `docs/10` lines 3-5; `docs/13` row 11 | Fixed: a sentence in the `docs/10` intro, section 7, question 99 (default: the SQL Server path leaves the runbook) |
| 10:V-D11-2 | minor | D11 | `docs/prompts/README.md` listed prompt 10 as "not started" although it was built 2026-10-13; prompt 10 has no build report in `docs/audit` (only board entries 06:40 and 06:55) | README status row `10, 11` | Fixed: rows 10, 10b, 11 and a prompt-list row 10b |

## 4. Per domain

- **D3 integrity** (the focus): probes run on the dump: row counts per table; soft deletes (none);
  derived-column agreement (registration, name, category on `records`: 0 differences; petty-cash
  copies: 0 mismatches); money precision (holds, C5); uniqueness against target keys (V-D3-4,
  repeated item names); orphan references (none: every FK of the dump is enforced); balances
  (V-D3-3). Verdicts: V-D3-1 to V-D3-5.
- **D5 dates and normalisation**: every legacy instant is `timestamptz` (no zone guess needed);
  `date` columns are business dates; no record is in the future of the dump (latest 2026-10-09);
  `records.week` is consistent (0 rows differ) and not moved. `joined_on` uses the Nairobi date of
  `created_at` (7.3 row 8). Phones: 6 of 6 present numbers are `07` + 8 digits and normalise to the
  target pattern. No finding beyond V-D3-5.
- **D6/D9 credentials**: V-D9-1. Hardest attacks tried: reusing bcrypt hashes as PIN hashes
  (refused: different scheme and secret; the target CHECK rejects the form); carrying
  `password_reset_codes` (0 rows; not moved); a migrated person signing in without a code (the
  target has no PIN for them, so the code step is mandatory).
- **D2 tenancy and access**: V-D2-1; the rights translation (7.4) keeps every legacy ability
  that has a right and adds none the legacy role lacked except the needs the resolver adds; on the
  dump the Manager 101 people get 29 rights and still cannot approve, issue cash or manage people.
- **D10 tests as evidence**: not checked: the tool's suite needs the shared cluster (freeze).
- **D11 documents**: V-D11-1, V-D11-2.

## 5. Per mode (condensed)

- **Assumptions inventory**: (a) the source is the .NET database (false, V-D3-1); (b) every
  source table has an organization (false: single-tenant); (c) the source stores authors (false:
  no `created_by` anywhere, question 91); (d) stored balances are trustworthy (false, V-D3-3);
  (e) `records` holds only first-hand rows (false, V-D3-2).
- **Falsification**: C1 and C2 fell to the dump's TOC; C5 survived a direct test on every amount
  and quantity; C6 could not be tested.
- **Pre-mortem, cutover night**: (1) the load refuses at 02:00 for the admin without a phone
  (q90: give the number before the night); (2) everyone is locked out because codes do not
  arrive (7.6: test delivery in the rehearsal); (3) the owner sees −619,557 and calls it a loss
  (7.6 and the printed comparison); (4) managers see no vehicles (V-D2-1); (5) vehicle costs
  double (V-D3-2). Inversion: each now has a rule, a check or a decision with a default.
- **Red team**: the insider with the dump (V-D12-1); a manager who gains rights through the
  translation (7.4: none beyond the resolver's needs); a refused row silently left behind
  (prevented by `--accept-rejected N` as today).
- **Dialectic**: one tool with a second source versus a separate tool: one tool keeps the
  verified load, ledger and report machinery and one runbook (chosen, 10b D1); the cost is
  making transform/load take a profile, guarded by the unchanged SQL Server tests.

## 6. Conceded

- "Gaps block capture after migration": conceded. The Python capture has no earlier-day rule
  (`db/routines/50_revenue/*`, no such refusal); 619 missing days only show as Missing days.
- "Duplicate Earnings break the revenue sum check": conceded once the drop rule exists; the check
  compares against the source minus documented drops.
- "Uncommitted petty-cash expenses change the float": conceded. Both systems count every entry
  in the balance whatever its status (legacy trigger sums all rows; PC-4), and only
  committed/approved expenses post to vehicles in either.

## 7. Fixes

Documents only (code is frozen and the code gap is a new deliverable, prompt 10b):

| Finding | Files | Evidence |
|---|---|---|
| V-D3-1, V-D3-2 to V-D3-5, V-D2-1, V-D9-1 (specification) | `docs/10-data-migration.md` (intro sentence, section 7), `docs/13-open-questions.md` (90 to 99), `docs/prompts/10b-legacy-migration.md` (new) | every figure from SQL on the restored dump, this session |
| V-D11-2 | `docs/prompts/README.md` (status rows 10, 10b, 11; prompt list 10b) | |
| V-D12-1 | `.git/info/exclude` (local) | `git check-ignore -v` now names the rule |

No failing-first test was written: the tests 10b needs depend on the legacy profile it builds
(its D2 lists them, each failing first).

## 8. Commands and outputs

- Private cluster: `initdb` into the scratchpad, port 5455, `shared_buffers` 16 MB;
  `SELECT version()`: PostgreSQL 16.15. `pg_restore --no-owner --no-acl` of the dump: 0 errors.
- `pg_restore -l`: archive created 2026-10-13 08:36:25, dumped from 16.15, 123 TOC entries.
- Python 3.13.2 (the API's `.venv`). Tool: `ruff check .` all passed; `ruff format --check .` 22
  files already formatted.
- Not run: the tool's pytest suite, `mypy`, `xcode-api db verify`, the full suite (queue row 9,
  revenue-17 [60bb7c]'s 08b run, was at 12% at 14:44; it is not this session's run).

## 9. Regressions and misses against earlier work

- The 10-build board entries (06:40, 06:55) record "dry run of XCodeTest data green" and open
  items (`0013` untested, CI). They missed V-D3-1: the run used `XCodeTest`, a test database,
  not production data, and no document asked where production data lives.
- No regression found in what was built; C6 stays open.

## 10. For the user

1. **Confirm the legacy database is the only production source** (question 99). Recommendation:
   yes; build prompt 10b next (Opus, one session), and take the SQL Server path off the runbook.
2. **Questions 90, 91, 95 block the load**; give the missing phone number, name the
   migrated-by Administrator, and choose the vehicle of the 30,000 expense in the restored copy.
   Recommendation: decide them before the 10b rehearsal so its dry run can pass end to end.
3. **The petty-cash float** will read −619,557 where the old screen read −2,580,518 (V-D3-3).
   Recommendation: accept the entries' figure (it is what every entry adds up to); the old page's
   carry-forward drifted from 17 September 2026.
4. **Move the dump out of the repository tree** (V-D12-1): the local ignore rule protects only
   this clone.

## 11. Rerun on 2026-10-14 (the user's request): C6 proven

The freeze had lifted (board, 19:23), so the tool was run as prompt 10's Verify section says,
against a target at the head (`0014`, which includes `0013`).

- ruff, `ruff format --check`, mypy (strict, 14 files): clean.
- First suite run: 51 passed, 1 failed, 1 skipped. The failure was the test, not the tool:
  `test_apply_loads_everything_else_and_records_the_operator` counted only the tables of
  migrations up to 12 (`LOADED_TABLES`), so the load's `expenses.entries` row raised a
  `KeyError` while the load itself had committed with every verification passing. Fixed in
  `tests/test_load.py` `_counts`: every mapped table the target has (`to_regclass`).
- The fixture carries no central expense or pause, so a new test puts two parts of a shared
  central expense (a note to trim) and a closed and an open pause through `load --apply`:
  `test_central_expenses_and_recurring_pauses_move_into_a_target_with_migration_0013`. It fails
  with the pause's from/through columns swapped in `tablemap.py` (toggled and restored).
- Final suite: **53 passed, 1 skipped, 0 failed** (5:16), with `SQLSERVER_TEST_CONNECTION` set,
  so `tests/test_extract.py` read `XCodeTest`. The skip is the guard for a target without
  `0013`, which cannot apply to a head target.
- The prompt's verify command (`load --dry-run --input tests/fixtures/extract`): exit 1 as
  designed (one refused away period unacknowledged); with `--accept-rejected 1`, exit 0, every
  verification passed, nothing written.
- Rehearsal on `XCodeTest` (read only; `XCode` untouched; `--frozen`, as the database does not
  allow SNAPSHOT and nothing was writing to it): 13,060 rows extracted; transform 0 refused,
  1,355 dropped by documented rules, 5,169 changed values; `load --dry-run` every verification
  passed. Then `load --apply` into a scratch target: committed, 42 checks ok, `xcode-api db
  verify` ok before and after. 217 central expenses (live total 202,958.61, equal to SQL
  Server's own sum) and all 3,155 change-log rows moved; on the `0012` target the 234
  central-expense change-log rows had been refused. `XCodeTest` holds no recurring pause, so
  pauses are proven by the new test only.
- Operator note: `XCODE_ENV` must be set for every command (README, settings table); without it
  the `db verify` check fails with "XCODE_ENV: Field required" and the load rightly refuses.
- Resources: private template and scratch targets dropped; the 5433 cluster stopped again (it
  was stopped before the run).
