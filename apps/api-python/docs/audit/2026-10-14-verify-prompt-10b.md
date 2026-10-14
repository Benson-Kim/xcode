# Verify: prompt 10b (the legacy PostgreSQL migration), 2026-10-14

`verify.md` with `SCOPE: prompt:10b`, `MODE: fix`, `DEPTH: standard`. Session revenue-da [9afdd6],
fresh eyes: it wrote none of 10b and read the build report (`docs/audit/2026-10-14-build-10b.md`)
only after its own pass. In the same pass, at the user's request, it took two risks the 08b verify
had recorded: the 500-row day save past the 5 s statement timeout (question 101, 08b:V-D7-1) and the
year-long Net report at 10x past it (08b:V-D7-2). The dump `docs/xcode_20261013T0836Z.dump` was
restored only into a private cluster in the scratchpad (port 5461). This report carries counts and
sums, never a row or a personal value.

## 1. Verdict

<<VERDICT>>

| Severity | Survived | Fixed here | Conceded |
|---|---:|---:|---:|
| Blocker | 0 | 0 | |
| Major | 4 | 4 | |
| Minor | 3 | 1 | |
| Note | 3 | 0 | |
| Conceded challenges | | | 8 |

The majors: two in 10b (V-D8-1 the read-only gate passes a writable database; V-D10-1 no test shows
a check of 7.5 failing), and the two 08b risks the user added (V-D7-1, V-D7-2), all fixed with a
test that failed first or, for the Net report, measured before and after on one clone with answers
byte-identical. The `xcode` checksum repair named in the brief was refused by the permission system
at first and done at 16:43 at the user's go-ahead, with one statement more than the 08b steps
(V-D6-1; sections 8 and 10).

## 2. Thesis and claims

Steelmanned thesis: the tool reads the legacy database only from a read-only copy, moves every
legacy row into one new organization or accounts for it by a named rule, a refusal with its key,
or a replacement, keeps every amount exact, gives each person exactly the rights 7.4 lists, and
`--apply` commits only when every figure of 7.5 matches; nothing personal leaves the operator's
machine.

| # | Claim (where stated) | Verdict | Grade |
|---|---|---|---|
| 1 | The extract refuses a database that answers a write (prompt D1; `docs/10` 7.2; build 8.1 row 3, 8.4) | **failed, fixed**: a URL asking for read-only sessions passed a writable database (V-D8-1); now the database itself must be marked or be a standby | A (new test) |
| 2 | `--apply` commits only when every check of 7.5 passes (prompt D1; build 8.3 graded A) | held in code (`load.py:run`), **unproven** by the tests: each check stubbed to pass left the suite green (V-D10-1); now one test breaks each check on an applied target | A (new test) |
| 3 | Every legacy row is loaded, dropped by a named rule, refused with its key, or replaced (7.5 ledger) | holds on the fixture and the dump; `source_ledger` fails on a summary one row short (new test) | A |
| 4 | Money moves exactly (prompt invariants; 7.3 rows 12 to 14) | holds: every 7.5 sum equal on the dump; no amount on the dump with scale above 2, no quantity above 3 decimals, no `plus`/`minus` on the wrong side (measured) | A |
| 5 | Each person gets exactly the rights of 7.4 (7.4; question 98) | holds: `test_the_rights_of_each_person`; all 43 legacy permission names are in the table, every value is in the 59-right catalogue | A |
| 6 | The people move with the numbers and e-mails of the letter, no PIN, "Not signed in yet" (7.3 row 1; 7.5) | holds: `test_people_move_...` asserts each person; 7 of 7 got a first-setup code on the dump | A |
| 7 | No name, e-mail or number in any output (prompt invariants) | holds on the fixture (`test_no_name_...`) and on the dump (token scan of every output, section 8); one gap: `load --input` without `--output` leaves the load files in `%TEMP%` (V-D9-1) | A, minor gap |
| 8 | The SQL Server path is unchanged (prompt D2) | holds: SQL Server tests unchanged, green in the baseline and after | A |
| 9 | The rehearsal figures of 7.5 hold on the dump (prompt D3) | holds: re-run independently, every figure equal (section 8) | A |
| 10 | A 500-row day save fits the 5 s statement timeout (`docs/06` 2.13 day save, 500 rows) | **failed, fixed**: 18.9 s measured by the 08b verify (V-D7-1); 1.4 s now, held by a test under the role's own timeout | A (new test) |
| 11 | The year Net report fits the timeout at 10x (`docs/perf/reports.md` budgets) | **failed, fixed within the timeout**: 3.7 s before, 2.8 s (3.4 s max) after on one clone; the 2.0 s budget is still missed (V-D7-2) | B (measured, no test at 10x) |

## 3. Findings

| id | mode | claim attacked | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| V-D8-1 | red team (hurried DBA) | the extract refuses a database that answers a write (`docs/10` 7.2; build 8.1 row 3, graded A) | the gate read `current_setting('transaction_read_only')` of its own session, so a URL ending in `?options=-c default_transaction_read_only=on` (or `PGOPTIONS`) passes against the live, writable database | before the fix, on the restored copy before it was marked: extract exit 0, then `CREATE TABLE` in a plain session succeeded; `legacy_extract.py` (the session check) | the copy the runbook makes is marked with `ALTER DATABASE`, so the runbook path is safe; but the guard's purpose is to stop the hurried path, and it did not | survives, **major** (the live database could be read mid-write; the tool still only reads, so no data loss) | **fixed**: `_READ_ONLY` (`legacy_extract.py:50`) also requires the database-level setting (`pg_db_role_setting`, database-wide, `on`/`true`/`yes`/`1`) or `pg_is_in_recovery()`; `test_a_url_that_only_asks_for_read_only_sessions_does_not_pass_a_writable_database` (`tests/test_legacy.py:361`) failed first (exit 0), passes now; `docs/10` 7.2 and the README say a URL or `PGOPTIONS` does not count |
| V-D10-1 | Socratic | `--apply` refuses when a verification fails (build 8.3, graded A) | which test shows any check of 7.5 failing? | with all nine checks (`source_ledger`, `_people`, `_rights`, `_holder`, `_revenue`, `_costs`, `_petty_cash`, `_postings`, `_not_signed_in`) stubbed to answer ok, the 36 legacy tests still passed (50.9 s, a scratch copy) | the acknowledgement and people-refusal tests show `--apply` stopping, but on a refusal, not on a failed check | survives, **major** (a missing test for an integrity claim) | **fixed**: `test_each_check_of_7_5_fails_on_a_target_that_breaks_it` (`tests/test_legacy.py:1135`) breaks the applied target once per check in a rolled-back transaction (a revenue amount, a central expense of the last full month, a cash amount, the float holder, `all_companies`, a denied `revenue.view`, a PIN set) and a ledger one row short, and asserts each named check fails; it kills each of the 9 single stubs (one run per stub) |
| V-D7-1 | falsification | a day save of up to 500 rows succeeds (`docs/06` 2.13; question 101) | 500 rows on a 600-vehicle fleet | 08b verify: 18.9 s capture under load; here before the fix, quiet: 7.7 to 8.5 s; `test_a_500_row_save_at_ten_times_the_fleet_fits_the_role_s_statement_timeout` failed with `QueryCanceled` | the only tenant has 9 vehicles; but the contract accepts 500 rows and answers 500 past about 130 | survives, **major** (a 5xx on a valid request) | **fixed**: per-call context (rights, threshold, business date, earliest writable date) read once; one subtransaction per call, not two per row; one decision of saving runs per call (`revenue.capture_row`, `setup.decide_fleet_saving_runs`); capture 1.4 s, replay 0.4 s, correct 1.2 to 1.7 s; the 500-row test and `test_a_day_save_reads_the_rights_and_decides_the_saving_runs_once_per_call` (failed first: 4 calls of `effective_permissions` for 3 rows) pass |
| V-D7-2 | falsification | the year reports fit the statement timeout at 10x (`docs/perf/reports.md`) | `net` over 367 days on 500 vehicles | 13 Oct: 5.6 s median, 6.3 s max; here, same script and seed, before: 3.7 s median, 4.2 s max | the run-to-run spread is large (13 Oct versus 14 Oct on the same seed), so a single before figure proves little; both days are compared within one clone | survives, **major** (a 5xx on a valid request at the measured size) | **fixed within the timeout**: `reports.vehicle_figures` sums the day figures inside each window without building the day series; `setup.scheduled_runs` reads the organization once per statement; `net` 2.8 s median, 3.4 s max, `gaps` 1.9 s, `savings` 1.9 s, answers byte-identical; equality held by `test_the_report_figures_sum_the_day_series_inside_each_vehicle_s_window`; the 2.0 s budget is still missed: residual in `docs/12` section 7 with the next levers measured |
| V-D3-1 | falsification | every legacy row is on the ledger or the exceptions list (7.5) | a value the parser refuses (a `double precision` `NaN` or `Infinity`) | `formats.py:87-117` raises; the row is in no `excluded` count and not in `exceptions.csv` | it fails closed: the row is missing from the target, so the ledger and the sums fail and `--apply` refuses; none on the dump | survives, minor | report: the refusal should be listed with its key like the others |
| V-D9-1 | red team (compromised neighbour) | no personal value is left behind (README, REHEARSAL) | `load --input <extract>` without `--output` | `cli.py:215` `tempfile.mkdtemp(prefix="xcode-migration-")`: the transform files (people, notes) stay in `%TEMP%`, never deleted | REHEARSAL always passes `--output` on the encrypted disk | survives, minor | report: refuse a legacy load without `--output`, or delete the temporary directory |
| V-D6-1 | pre-mortem | the 08b repair of `xcode` (its report, section 10) | run `0014` again, set the checksum, `db routines` | read-only on `xcode`: none of `0014`'s four targets exists there; `setup.scheduled_runs(uuid[], date, date, date, smallint[])` does, while the files define six arguments; `db routines` adds the new overload beside it (non-`api` overloads are not reported) and every five-argument call (`fleet_totals`, `fleet_postings`) becomes ambiguous | 0013 and 0014 were never committed or deployed, so only `xcode` went through the five-argument version | survives, minor (a development database) | **fixed on `xcode`** (16:43, the user's go-ahead): the overload dropped in the same transaction as `0014` and the checksum; `db verify` 21 of 21, `db status` clean (section 8) |
| V-D11-1 | Socratic | the provision balance listed for the owner (question 97) | the report sums the provision rows; the legacy table also stores a carried balance (`provision_cf`) | `legacy_conversions.py:1179-1183` | equal on the dump (2,000) | survives, note | none needed now |
| V-D11-2 | Socratic | the brief's environment (`XCODE_TEST_TEMPLATE`) | the tool's tests read `XCODE_MIGRATION_TEST_TEMPLATE` (`tests/conftest.py:28`) | the baseline used the latter | | survives, note | the next brief should name the tool's variable |
| V-D10-2 | falsification | the tool suite proves the legacy path | run it without `xcode-api` on `PATH` and without `XCODE_API_CLI` | 42 passed, 49 skipped, exit 0 (here, 14:57) | CI installs the API (`pip install -e .`), so CI runs them | survives, note | a run should fail, not skip, when `XCODE_TEST_DATABASE_URL` is set but the CLI is missing |

## 4. Per domain

| Domain | Probe verdicts |
|---|---|
| D1 Tenancy | every migrated tenant row carries the one organization (generic check, every load); the per-check test runs as the owner inside one target; the new routines take the organization from the caller and filter every read by it (`capture_row`, `decide_fleet_saving_runs`), and `vehicle_figures` filters each joined table by `(SELECT tenancy.current_organization())` |
| D2 Identity | people move without a PIN, counters 0, `not_signed_in`; the 7.5 check reaches `api.auth_start` per person inside a rolled-back savepoint (conceded below); the PIN check of V-D10-1 now fails when a PIN is set |
| D3 Integrity and concurrency | ledger per file (A); exact money (A); the copies rule stops on disagreement (A); V-D3-1 (minor); the day save's locks: records in ascending vehicle id, then the advisory locks in ascending id after the loop; every other decider takes its row locks before its advisory lock, so no cycle; the two race tests pin the two refusals (conceded, section 6) |
| D5 Rules and time | dates in the business time zone; "the last full month" across midnight on the 1st (build R2, residual); back-dating: a row past the limit names the earliest day and the vehicle (`test_a_row_past_the_back_dating_limit_names_the_earliest_day_and_the_vehicle`) |
| D6 Database craft | `db verify` before and after in every legacy load (generic checks); the new routines have headers, grants to the executor only, no `EXECUTE`/`format(`, `revenue_day_save` keeps `SET search_path` with `SECURITY DEFINER`; features: `ON CONFLICT ON CONSTRAINT`, `SKIP LOCKED` (9.5), `hashtextextended` (11), all older than the oldest supported; versions measured: 16.15 local and on the private cluster, 18 in CI; V-D6-1 |
| D7 Performance | V-D7-1, V-D7-2; rehearsal times on the dump: extract 5 s, transform 5 s, dry-run load 15 s |
| D8 Reliability | V-D8-1; exit codes 0/1 asserted; refusals name the line or key, never a value (`test_a_people_file_problem_names_the_line_and_never_a_value`) |
| D9 Supply chain | the tool's lock file has hashes and CI installs it with `--require-hashes`; V-D9-1 |
| D10 Tests | V-D10-1, V-D10-2; mutation evidence in section 7; no `xfail`, `sleep` or bare `except` in the tool or my tests; the tool's skips are environment skips and two migration-version guards |
| D11 Documents | `docs/10` 7.2, the tool README, `docs/05`, `docs/12`, `docs/13` (101), both perf notes updated; V-D11-1, V-D11-2 |

## 5. Per mode

**Assumptions.** A1 the runbook's copy is marked read-only (enforced now by the gate itself, A).
A2 `users.permissions` is the person's real set (build R1: not checked; the 43 names on the dump all
translate). A3 the people file is complete (blocking refusal, A). A4 no amount on the dump rounds
(measured, and refused if one does, A). A5 the day save's 500-row contract is what the web sends
(`docs/06` 2.13, unchanged). A6 the 10x seed is representative (a daily saving on every vehicle:
the worst case for the scheduled runs).

**Falsification.** Claims 1, 2, 10 and 11 of section 2 fell and were fixed; 3 to 9 held with the
evidence named there.

**Pre-mortem** (the morning after the cutover): (1) the DBA, in a hurry, points the extract at the
live database with a read-only URL option: refused now (V-D8-1); (2) a figure is off and
`--apply` commits anyway because a check was weakened later: each check now has a failing test
(V-D10-1); (3) a fleet of 150 vehicles is onboarded and the first day save answers 500: fixed
(V-D7-1); (4) the owner opens the year Net report on a busy morning and it is cancelled: within the
timeout now, 1.6 s of margin on a quiet machine (V-D7-2, residual). Inversion: running the load
without the acknowledgement, without the people file or against a target at another migration is
refused (A, unchanged).

**Red team.** Hurried DBA: V-D8-1. Compromised neighbour: V-D9-1. The gamer: a typed label run as
a formula in `exceptions.csv` (fixed by the build, `_cell`, A). Insider: the float holder approving
their own spending after the move (a Fleet manager holds no approval right, A).

**Dialectic.** Keep `name` as the cash note (build, kept). `SKIP LOCKED` plus a plain read against
a per-row subtransaction: kept (section 6), the same answers for 1 s less at 500 rows. Ship the
row-level-security change now or later: later, because it changes every policy, needs a migration
and `db verify`'s expected text, and helps `gaps` and `savings` more than `net`.

## 6. Conceded

| Challenge | Guard that defeats it |
|---|---|
| A legacy permission value outside the 59-right catalogue | `test_the_rights_of_each_person` (last assertion) and the dump: all 43 names translate, every value in the catalogue |
| A number or e-mail moved to the wrong person | `test_people_move_...` asserts each person's e-mail and number |
| A `plus`/`minus` value on the wrong side lost silently | none on the dump (measured); cash with both would fail the float check |
| The holder's role ("Petty Cash Manager" in the letter, Fleet manager in the tool) | question 98 records the decision and its reason |
| Placeholder numbers in the letter reach real phones | codes go by e-mail (`CodeMailer`), not SMS |
| `api.auth_start` writes during `--apply` | each call runs in a savepoint rolled back at once (`legacy_checks.py:363`); the routine sends no mail itself |
| The extract reads a moving database | one `REPEATABLE READ READ ONLY` transaction, and now only a read-only copy |
| `capture_row`'s `FOR UPDATE SKIP LOCKED` and a plain read change the answer of a save that meets another (`docs/05` 10.5: `revenue_concurrent_save` at once) | a skipped row is one another transaction has locked, and the plain read still sees its committed version, so the answer is `NOWAIT`'s; an uncommitted first insert is invisible to both reads, and `ON CONFLICT DO NOTHING` waits for it as the plain insert did, then answers `unique_conflict`; `test_a_save_of_a_day_another_save_holds_is_refused_at_once` and `test_two_first_captures_of_a_day_race_to_one_record_and_a_unique_conflict` pass on the new code |

## 7. Fixes

| Finding | Files | Test that failed before and passes now |
|---|---|---|
| V-D8-1 | `tools/migrate_from_sqlserver/migrate_from_sqlserver/legacy_extract.py`; `tools/migrate_from_sqlserver/README.md`; `docs/10-data-migration.md` 7.2 | `tests/test_legacy.py::test_a_url_that_only_asks_for_read_only_sessions_does_not_pass_a_writable_database` (exit 0 before) |
| V-D10-1 | `tools/migrate_from_sqlserver/tests/test_legacy.py` | the test itself is the fix; mutation proof: all 7.5 checks stubbed to pass, the 36 earlier legacy tests passed; each of the 9 single stubs makes the new test fail |
| V-D7-1 | new `db/routines/50_revenue/capture_row.sql`, new `db/routines/40_setup/decide_fleet_saving_runs.sql`; `db/routines/50_revenue/{capture_entry,revenue_day_save}.sql`, `db/routines/40_setup/decide_saving_runs.sql`; `tests/db/test_revenue_day_routines.py` (three tests); `docs/05`, `docs/12`, `docs/13` 101, `docs/perf/scheduled-and-day.md` | `test_a_500_row_save_at_ten_times_the_fleet_fits_the_role_s_statement_timeout` (`QueryCanceled` before); `test_a_day_save_reads_the_rights_and_decides_the_saving_runs_once_per_call` (4 calls before); `test_a_row_past_the_back_dating_limit_names_the_earliest_day_and_the_vehicle` (guards the `-infinity` sentinel: a NULL earliest date means no limit) |
| V-D7-2 | `db/routines/58_reports/vehicle_figures.sql`, `db/routines/40_setup/scheduled_runs.sql`; `tests/db/test_revenue_helpers.py` (one test); `docs/05`, `docs/12`, `docs/perf/reports.md` | a refactor for time: `test_the_report_figures_sum_the_day_series_inside_each_vehicle_s_window` passes before and after (it guards the equality); the time is measured (section 8), not asserted, because a 10x seed takes minutes |
| V-D6-1 | none in the tree: the database `xcode` (5433), at the user's go-ahead | a database repair, no test: before, `db status` showed checksum drift `[14]` and the five-argument overload; after, `db status` clean, `db verify` 21 of 21, one `setup.scheduled_runs` (section 8) |

Day save, 500 rows on 600 vehicles, quiet cluster, timeout lifted for the measurement:

| Call | Before (s) | After (s) |
|---|---:|---:|
| capture | 7.7, 8.5 | 1.46, 1.39 |
| replay | 5.3, 2.8 | 0.44, 0.40 |
| correct | 9.4, 5.6 | 1.69, 1.22 |

Net at 10x (500 vehicles, 184,106 records; the 08b script and seed; `xcode_app`; six calls, the
first dropped):

| Report | Before median / max (ms) | After median / max (ms) |
|---|---|---|
| `net` | 3,669 / 4,170 | 2,822 / 3,385 |
| `gaps` | 2,656 | 1,923 / 1,965 |
| `savings` | 2,884 | 1,933 / 2,057 |

Tried and not kept: `money_out_by_main` summed per item before joining the names (2,888 ms, no
gain); the row-level-security policies with `(SELECT tenancy.current_organization())` on the clone
only (the records scan 662 to 66 ms, `savings` about 1.6 s, `net` unchanged; needs a migration and
`db verify`'s expected text, left as the next lever in `docs/12` section 7).

## 8. Commands and outputs

- Baseline, the whole tool suite before any change (13:29 to 13:35): 87 passed, 2 skipped (SQL
  Server's two), exit 0, 7 min 28 s.
- Rehearsal on the dump (13:37; private cluster 5461, database marked read-only; target cloned
  from the private template; the people file from the letter, kept in the scratchpad and deleted
  at the end): extract 5 s, transform 5 s (180 refused, 1,987 dropped, 1,891 changed), `load
  --dry-run --accept-rejected 180` 15 s, exit 0, every check ok. Revenue 3,522 days, 27,312,770;
  costs 29,352,017; cash 195 (6,788,630); credit notes 6 (120,700); approved 1,196 (3,895,300);
  waiting 1,182 (3,362,187); float −589,557; postings of 2026-09: 9 vehicles, 1,492,817; 7 of 7
  people reach a first-setup code; 54 overrides. Exceptions 209: held back 180, left out 3, double
  entries 5, possible doubles 16, balance days 5. A token scan of every output found no name,
  e-mail or number.
- After the fixes: the whole tool suite (14:58 to 15:02): 89 passed, 2 skipped (the same two), exit 0, 3 min 57 s; the two more than the baseline are the new tests; `ruff check`, `ruff format --check` (30 files),
  `mypy` (20 source files) clean for the tool; `ruff` clean on the two API test modules.
- Targeted API modules on the final code, one process each, `-n 0`: revenue routines 92 (both race
  tests), day routines 21, routine headers 1732, api revenue 39, api revenue day 8, revenue helpers
  64, report routines 23, setup helpers 93, recurring pause routines 29, api reports 9; all passed.
- Full API suite: <<FULLRUN>>
- `xcode-api db status` on `xcode` (5433) before the repair, read only: applied 0001 to 0014,
  checksum drift `[14]`, routine drift in eight files (four of 08b's, four of this pass); the only
  `setup.scheduled_runs` was the five-argument one; no other client connected.
- The `xcode` repair (16:43, the user's go-ahead; refused by the permission system at 14:53), as
  `xcode_owner`, `psql -1 -v ON_ERROR_STOP=1`: `0014` (its four drops skipped, none exists),
  `DROP FUNCTION IF EXISTS setup.scheduled_runs(uuid[], date, date, date, smallint[])`, the
  checksum `UPDATE 1`; committed. Then `db migrate`: `applied: none`, every routine file, exit 0, no
  orphan warning; `db verify`: 21 of 21 ok; `db status`: no pending, routine drift none, checksum
  drift none, exit 0. `setup.scheduled_runs` now has only the six-argument form, and no routine in
  the app schemas has two overloads.
- Versions: PostgreSQL 16.15 (5433 and the private cluster), CI `postgres:18`; Python 3.13.2.

## 9. Regressions and misses against earlier audits

- Build 10b, 8.1 row 3 and 8.4 ("extract from the running application's database: refused", graded
  A): missed V-D8-1; the test it cites marks the database itself, so it never tried the URL option.
- Build 10b, 8.3 ("`--apply` refuses when a verification fails", graded A): the evidence was the
  acknowledgement and people refusals, not a failed check (V-D10-1).
- Build 10b, section 5: the mutation pass stopped before its read-only-gate run; this pass found
  the gate's hole by attack instead.
- 08b verify, section 10: the `xcode` repair steps miss the five-argument `setup.scheduled_runs`
  (V-D6-1).
- Nothing the earlier audits recorded as fixed is broken again: `_exact_total`, `_cell`, the
  one-holder stop and the cash and credit-note rules all hold in the suite and on the dump.

## 10. For the user

- **The shared CLI database `xcode` (08b:V-D6-2, V-D6-1 here).** Repaired at 16:43 at your
  go-ahead; `db migrate` works there again and `db verify` passes (section 8). `xcode` lives on the
  5433 test cluster, not 5432. The 08b steps lacked one statement: `xcode` still held the
  five-argument `setup.scheduled_runs`, so it was dropped in the same transaction as `0014` and the
  checksum; without the drop, `db routines` would have left every five-argument call ambiguous.
  `xcode` now carries this pass's routines, which are still uncommitted, like `0013` and `0014`.
- **The next reports lever.** `net` now fits the timeout with 1.6 s to spare on a quiet machine but
  still misses its 2.0 s budget. The measured next step is the row-level-security policies written
  as `(SELECT tenancy.current_organization())` (a migration touching every tenant policy). I
  recommend it in the reports follow-up, not as a hotfix: today's only tenant has 9 vehicles.
