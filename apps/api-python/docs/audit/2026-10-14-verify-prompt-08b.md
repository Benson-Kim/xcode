# Verify: prompt 08b (central expenses, reports, exports, day capture, scheduled runs)

`docs/prompts/verify.md` with `SCOPE: prompt:08b`, `MODE: fix`, `DEPTH: standard`, run 14 Oct 2026 by
revenue-59 [cb8561], a session that wrote none of 08b. It supersedes the 13 Oct draft
(`docs/audit/2026-10-13-verify-prompt-08b.md`, revenue-90 [ca8ec1], verdict pending), which was read only
after this session's own pass. Security focus: W2-E (`docs/prompts/security-waves.md`), clusters SC3
and SC4 (`docs/16-security-matrix.md`).

## 1. Verdict

**Pass with findings.** No blocker survives and the full suite completed: 6572 passed, 3 failed,
0 errors, 0 skipped in 1:50:49 (shared run, section 8). The 3 failures are the D1 `test_gateway`
drift (section 9), not 08b's.

- Findings that survive: 0 blocker, 3 major, 5 minor, 4 notes.
  - Fixed with a failing-first test: 1 major (V-D6-1), 1 minor (V-D10-2).
  - Documents corrected: 2 minor (V-D11-1, V-D3-1).
  - Recorded: 2 major as residual risks with an owner and an open question (V-D7-1, V-D7-2); 1 minor
    as open question 102 (V-D3-2); 1 minor for the user (V-D6-2).
- Claims: 27 in the table of section 2: 22 holds, 2 fails (both fixed or recorded), 2 unproven,
  1 not checked. Counts per claim are in its last column.
- The 13 Oct draft's items: V-D3-1 survives (doc corrected), V-D3-2 survives (question 102), V-D10-1
  closed (the tests exist and each fails without its call), V-D4-1 conceded, N-1 holds as documented,
  N-2 superseded by V-D7-2, N-3 measured and became V-D7-1.

## 2. Thesis and claims

Steelmanned thesis: prompt 08b brings the Python API level with what the .NET API gained on 9 and
10 October (drift rows 1 to 6, 8, 12): migration `0013` with RLS and grants; central expenses,
scheduled-item pause, resume, runs and summary, day capture, reports and the four Excel/PDF exports,
all computed in SQL through one posting function; every export cut to the caller's organization and
visible vehicles, audited, bounded and free of live formulas; the saving model B18 decided by every
write that completes a window; and the owed items of 13 Oct 20:50 (the `next_run` fix, the vehicle
update and restore decisions, the writer-failure test, `0014`, the 10x rewrites) keep every answer
the same.

Grades: `docs/14-verification.md` section 5. "Baseline" is this session's one-module-per-process run
(section 8); "full run" is the shared run of section 8.

| # | Claim | Where stated | Carried by | Verdict (grade) |
|---|---|---|---|---|
| 1 | `0013` tables with code tables, RLS, `tenant_isolation`, grants (I only on append-only), reviewed `.down.sql` | prompt D1; `docs/04` 14 | `db/migrations/0013_expenses{,.down}.sql`; `schema_spec.py` 165-168, 256-263 | holds (A: structure, constraints, grants, enum parity, migrate modules in the full run) |
| 2 | every `api.*` routine of 08b enters its organization first | prompt D2; `docs/05` | `tenancy.enter_organization` first in each; `db verify` "tenant routines enter their organization" | holds (A: `db verify` ok on `xcode`, 14 Oct) |
| 3 | every posting source read through one SQL function; none summed in Python | prompt D2 and invariants | `setup.fleet_postings`; `setup.fleet_totals` sums the same rows; `expenses.ledger_rows` reads `fleet_postings` (`ledger_rows.sql:65`) | holds (A: `test_recurring_pause_routines.py::test_the_kind_and_item_filters_and_the_totals_agree_with_the_full_postings`; Python grep: only layout arithmetic in `pdf.py`) |
| 4 | split expenses never lose or invent a cent | prompt invariants | `57_expenses/check_purchase.sql` | holds (A: `test_a_split_never_loses_or_invents_a_cent`, baseline) |
| 5 | (schedule, run date, vehicle) unique under two racing connections | prompt D2 | `pk_saving_runs` | holds (A: `test_two_connections_deciding_one_run_store_one_row`) |
| 6 | scoped viewers' totals, reports and exports leave hidden vehicles out | prompt D2, D5; `docs/12` | `reports.vehicles`, `setup.visible_vehicles()` in every export | holds (A: `test_a_scoped_viewer_sees_no_hidden_vehicle_in_any_figure`, `test_a_scoped_viewers_export_holds_no_hidden_vehicle` (db and api), `test_the_ledger_figures_of_a_scoped_viewer_leave_out_hidden_vehicles`, `test_a_scoped_person_sees_nothing_outside_their_vehicles_change_log_included`) |
| 7 | another organization's rows and ids stay its own | W2-E; SC4 | `current_organization()` in every builder; `visible_holders` | holds (A for expenses and petty-cash reports: `test_another_organizations_rows_and_ids_stay_its_own`, `test_a_petty_cash_report_of_another_float_is_not_found`; B for the fleet report exports: code read) |
| 8 | the back-dating limit applies to central-expense record, change and remove | W2-E; B12 | `tenancy.check_writable` in `expenses_entry_{create,update,remove}.sql` (create :65, update :83 and :102, remove :59) | holds (A: `test_a_central_expense_before_the_limit_is_refused_on_record_change_and_remove`) |
| 9 | the ledger of record agrees across central, petty-cash and scheduled sources | W2-E; SC4 | as claim 3 | holds (A, as claim 3) |
| 10 | stale writers get the 409 with `current` on a second connection | `docs/14` D3 | `expenses.entries.version` | holds (A: `test_the_stale_writer_on_a_second_connection_gets_the_version_conflict_with_current`, `test_a_stale_row_is_a_day_conflict_naming_the_vehicle_with_its_current_cell`) |
| 11 | domain records, one port per area, gateways (reads and exports idempotent), fakes with parity | prompt D3 | `domain/{expenses,reports}.py`, `db/routines/{expenses,reports}.py`, `tests/support/fakes.py` | holds (B: `test_fakes_match_routines.py` in the full run) |
| 12 | every route of drift rows 1 to 5 and 8 with the .NET method, path, tag and operation id | prompt invariants, D4 | routers `expenses.py`, `reports.py`, `revenue.py`, `setup_recurring.py`, `pettycash.py` | holds (A: .NET `WithName`/`ProducesExport` names equal the Python `operation_id`s; the generated document lists them; `test_openapi.py`) |
| 13 | every `{id}` route lists what it answers | `docs/06` 2.13 | `problem_responses(...)`; `{id:uuid}` convertors | holds (A: draft V-D4-1 conceded, section 6) |
| 14 | export content types and `Content-Disposition` names as .NET sends them | prompt D5 | `http/responses.py` `file_response` | holds (A: `file_ok(...)` in `test_reports.py`, `test_expenses.py`) |
| 15 | one audit row per export, also when the writer fails afterwards | prompt D5; `docs/12` 2.8 | `reports.log_export` in the four export routines | holds (A: `reasons(world)` asserts; `test_a_writer_that_fails_after_the_audit_row_leaves_the_row_and_a_retry_writes_one`) |
| 16 | an export past 10,000 rows is refused with its sentence before any byte | prompt D5 | `reports.check_export` | holds (A: `test_an_export_past_the_row_bound_is_refused_with_its_sentence`) |
| 17 | no export cell is a live formula; a text starting `=`, `+`, `-`, `@`, tab or CR keeps the quote prefix | prompt D5; `docs/12` 2.8; `xlsx.py` docstring; SC3 | `infra/exports/xlsx.py` | **fails** before this session (bands, figure labels and headers had no quote prefix: V-D6-1); holds after the fix (A: `tests/api/test_export_injection.py`) |
| 18 | PDF text cannot carry markup | ADR-16 | `pdf.py` draws with `drawString` only | holds (B: code read; no `Paragraph` anywhere) |
| 19 | pause and resume rules; a stop stays final | prompt D6 | `setup_recurring_{pause,resume}.sql` | holds (A: `test_recurring_pause_routines.py`, 29 passed in the baseline) |
| 20 | runs are decided by every write that completes a window (capture, day save, saving save, vehicle update, vehicle restore) | prompt D6; B18 | the five `setup.decide_saving_runs` calls | holds (A: each of the five covering tests fails with its call removed, section 8) |
| 21 | day capture: each row through `revenue.capture_entry`, 500 limit, all or none, the vehicle in a 400, `vehicleId` in a 409 | prompt D6 | `revenue_day_save.sql` | holds functionally (A: `test_revenue_day_routines.py`, `test_revenue_day.py`) |
| 22 | a 500-row day save completes within the role's statement timeout | the 500-row contract (`docs/06`) with `statement_timeout` 5 s (`db/roles/010_roles.sql:24`) | `revenue_day_save.sql` | **fails** (V-D7-1: 18.9 s measured) |
| 23 | released clients' raw JSON rows for the new screens | prompt D7 | `tests/api/test_contract_released_clients.py` | holds (A: the module, baseline) |
| 24 | `next_run` needs a share vehicle still in the fleet | board 20:50 | `setup_recurring_list.sql:177-192` | unproven (B: `test_the_next_run_needs_a_share_vehicle_still_in_the_fleet` passes; not shown to fail without the fix) |
| 25 | `0014` drops exactly the orphan overloads, and no stale overload survives | board 20:50; `docs/14` D6 | `0014_orphan_routines.sql` | holds (B: on `xcode`, no function has two overloads and none is executable by PUBLIC); its checksum on `xcode` drifted (V-D6-2) |
| 26 | the 10x rewrites changed no answer | board 20:50; `docs/audit/2026-10-13-build-08b.md` 11 | the rewritten routines | unproven (D: fingerprint comparison reported by the build, not repeated); every module that reads them passed in the baseline (A for the test data) |
| 27 | reports and exports within their budgets at 10x | `docs/perf/reports.md` | the report builders | not checked (the build's 22:15 run stands: `net`, `gaps`, `savings`, `moneyOut`, `target`, the petty-cash reports and the Petty cash export over budget; V-D7-2 adds that `net` passes the statement timeout) |

Counts: holds 22 (1-16, 18-21, 23, 25), fails 2 (17, 22), unproven 2 (24, 26), not checked 1 (27).

## 3. Findings

Ids carry the scope prefix `08b:` in cross-references (`docs/14` section 7).

| id | mode | claim attacked | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| V-D6-1 | red team (persona 8, the gamer) | claim 17: "a text starting with `=`, `+`, `-`, `@`, a tab or a carriage return also gets the `quote_prefix` format" (`docs/12` 2.8; `xlsx.py` docstring) | a main category named `-Running` becomes the money-out export's figure label `-RUNNING (KES)` (B5); the display name opens every subtitle (A2); report titles and column labels are band cells. Expected the quote prefix; actual none (only data cells had it) | `infra/exports/xlsx.py` `_Formats` (title, subtitle, stamp, figure_label, header, totals_text had no `quote_prefix`); the new test failed on `('B5', '-RUNNING (KES)')` and on `A1 '=Net'` | every cell is still a string cell (`write_string`, `strings_to_formulas` off), so nothing is live when opened; but editing such a cell (F2, Enter) makes it a formula, which is what the rule exists to stop | survives, **major** (a stated security rule wrong on a reachable path) | fixed: quote prefix on the band, label, header and totals formats; `tests/api/test_export_injection.py` (two tests, both failed before) |
| V-D7-1 | pre-mortem / falsification | claim 22: the day save accepts 500 rows | a fleet of 500 vehicles saves its day: 18.9 s for 500 new records, 7.6 s for an identical replay, 15.7 s for 500 corrections, against the role's 5 s timeout; the statement is cancelled (57014), translated as an unexpected database error, and the client gets a 500; all or none, so nothing is saved | section 8, "The day save at 500 rows"; per function: `capture_entry` 7.0 s own, `decide_saving_runs` 2.1 s, `record_change` 1.4 s, `check_writable` 1.0 s, `business_date` 0.9 s (three calls a row) | measured with no scheduled items at all and with the decision call removed (17.4 s): the cost is the per-row steps, not one statement; the machine was loaded, but even half of 18.9 s is past 5 s; the only tenant today has 9 vehicles (legacy copy, port 5455: `count(*)` of `public.vehicles`), about 0.3 s | survives, **major** (a 5xx on a valid request past about 130 rows) | residual risk in `docs/12` section 7 with an owner; question 101 (default: a set-based batch path before a fleet passes 100 vehicles); measurement in `docs/perf/scheduled-and-day.md`. Not fixed here: the fix moves per-day work out of `revenue.capture_entry`, which the single capture and the offline replay share, which is a build, not a verify change |
| V-D7-2 | pre-mortem | claim 27: reports "bounded by the role's statement timeout" (`docs/12` 2.8 "Bounded exports") | at 10x (500 vehicles, 13 months) `net` over 367 days takes 5.6 s median, 6.3 s max (export as long): cancelled at 5 s, so the report and its export answer 500 rather than a slow answer | `docs/perf/reports.md` "The 10x run"; `db/roles/010_roles.sql:24` | the 10x seed is a worst case (daily saving on every vehicle); the real tenant is 9 vehicles; the document called these "over budget" but never said that `net` passes the hard timeout | survives, **major** (5xx on a valid request at that size) | residual risk in `docs/12` section 7, owner the reports follow-up; a note under the 10x table of `docs/perf/reports.md` |
| V-D10-2 | falsification | "the save logs each record" (`test_the_save_answers_each_row_in_the_order_sent_and_logs_each_record`) | the routine captures in ascending vehicle id (DEC-42, `docs/05` 11.5, `revenue_day_save.sql:7-9`); the test expected KDA's log row before KDC's; ids are `gen_random_uuid()`, so it fails about half the runs | baseline: `1 failed, 17 passed` (`'Recorded revenue for KDC 200B ...' != '... KDA 482M ...'`) | the routine's order is the documented lock order, so the expectation is what is wrong (not weakened: it now asserts that order exactly) | survives, minor | fixed: the expected order is the ascending-id order; 4 of 4 runs pass |
| V-D11-1 | Socratic | `docs/12` 2.8 names its evidence | `tests/api/test_expenses.py::test_an_exported_note_starting_with_equals_stays_text` does not exist | grep: the test is `test_an_exported_item_starting_with_equals_stays_text` | none | survives, minor | doc corrected (the row names the real tests and the new module) |
| V-D6-2 | red team (persona 6, hurried DBA) | migrations are forward-only and checksummed (`docs/14` D6) | `0014_orphan_routines.sql` was edited after it was applied to the CLI database `xcode` (applied 13 Oct 20:29:44, file written 20:35): `db status` shows "migration checksum drift: [14]", and `db migrate` there refuses until it is repaired | stored `5073d714...`, file `9848c7d5...`; `Runner.migrate` calls `_verify_no_drift` | the file is four `DROP FUNCTION IF EXISTS` statements, so re-running it is harmless; no other database holds `0014` (the test templates are rebuilt from files; production has none); `xcode` has no stale overload | survives, minor | for the user (section 10): repair `xcode` |
| V-D3-1 | pre-mortem (draft's) | `setup.saving_runs.version_id` "the version in charge on `run_on`" (`docs/04` 14.3) | a run decided today, then the saving revised today: screens post the new share amount (`scheduled_runs.sql:70`) with the stored state (`:77`); the row's `amount` and `version_id` keep the old version | as stated; no reader reads `saving_runs.amount` | the decision depends on the window's revenue, not on the amount, so the state stays right; every screen reads the same helper, so they agree | survives, minor | doc corrected: `docs/04` 14.3 says the row keeps what was decided and readers post the share of the version in charge |
| V-D3-2 | dialectic (draft's) | an opening belongs to the share vehicles (`recurring_opening_vehicle`) | a revise that drops vehicle V: with no opening sent (SQL NULL keeps it), V's opening stays in the balance; with the opening the client read sent back, it is refused unless V's amount is removed, which removes it | `save_recurring.sql:60, 247-275`; `saving_balance.sql:31` | either outcome is defensible; the defect is that it depends on what the client sends | survives, minor | open question 102 (default: keep V's opening in both cases) |
| N-1 | note | a statement timeout is an "unexpected database error" | 57014 is not transient (`db/errors.py:45-46`), so it becomes `IntegrityBug` and a generic 500, logged as a database fault rather than a slow request | `db/errors.py` `translate` | parity with nothing in .NET; affects every route | note | for verify-09 (operability): consider 503 with the transient title |
| N-2 | note | subtransactions | a 500-row save opens 1,000 subtransactions (two loops with handlers) | `revenue_day_save.sql:88-136` | measured cost is the per-row steps (V-D7-1); the snapshot overflow cost to other sessions is unmeasured | note | folded into question 101's design |
| N-3 | note | the filters words of a report export | a `companyId` of another organization, or of a company the viewer cannot see, gives an empty file headed "All companies" | `report_export_get.sql:57-65` | no row leaks (`reports.vehicles` filters both); only the label misleads | note | none (no failure scenario beyond the label) |
| N-4 | note | exports run off the loop | the file is built on the 4 default worker threads (`main.py:74, 232-234`); the wait has no bound, so a burst of exports by signed-in people queues their documents in memory | `application/reports/files.py:21` | authenticated and rate-limited; 10,000 rows at most per document | note | none |

## 4. Per domain

- **D1 tenancy and authorization.** Probes: tenant guard first in every 08b `api.*` routine, holds
  (A, `db verify`); RLS and `tenant_isolation` on the new tables, holds (A, structure test in the full
  run; `schema_spec.py` 165-168); scoped viewers in totals, reports, exports, ledger, change log, holds
  (A, claim 6); foreign ids answer 404, holds (A, claim 7); anti-escalation and catalogue parity, n/a
  (08b adds no grant path). Hardest attacks tried, all failed: (1) a petty-cash report or export with
  another float's `holderId` (filtered through `pettycash.visible_holders`, not found); (2) a company of
  another organization in a fleet report export (`reports.vehicles` filters organization and
  visibility; empty file, N-3); (3) the Revenue export calling `api.revenue_week_get` inside another
  definer routine (it enters the same organization with the same actor; no widening).
- **D3 integrity and concurrency.** Version compare and 409 with `current` (A, claim 10); replay by a
  unique key (A, `test_two_connections_recording_one_purchase_make_one_set_of_rows`); append-only
  `saving_runs` (I only, `schema_spec.py:168`); money `numeric(14,2)`, units `numeric(12,3)`
  (`0013_expenses.sql:30, 37`); lock order of the day save, ascending vehicle id (documented, V-D10-2).
  Findings V-D3-1, V-D3-2.
- **D4 contract parity.** Routes, methods, tags and operation ids equal .NET for the 08b routes
  (claim 12); errors per route listed (claim 13). The 400 of a malformed `{id}` does not exist
  (`{id:uuid}`, empty 404 as .NET's `{id:guid}`). No finding; hardest attacks: the export operation id
  .NET sets with `ProducesExport` rather than `WithName` (matched); `GET /setup/recurring/{id}/runs`
  without 400 (conceded, section 6); `GET /setup/reports` with no suffix (`GetReportsAccess`, present).
- **D5 domain rules and time.** No `now()`, `current_date`, `clock_timestamp()` or `random()` in
  `db/routines` (sweep); business dates through `tenancy.business_date` with `p_now`. The period and
  window rules are carried by the 08b modules (baseline green). No finding; hardest attacks: a saving's
  run on a vehicle's day away after a restore (decided skipped, `test_a_restore_decides_the_held_runs_of_the_days_away`);
  `next_run` with every share vehicle retired (none); a join date moved earlier completing held windows
  (decided, mutation-proven).
- **D6 database craft.** No `EXECUTE` or `format(` in routines; every `SECURITY DEFINER` pins
  `search_path`; no non-extension function executable by PUBLIC; no overloads on `xcode` (catalogue
  queries, section 8). Findings V-D6-1 (exports, SC3), V-D6-2.
- **D7 performance.** Statement budgets of 2 on every export (`statements=2` in the request log of the
  injection test; `count <= 2` in `test_reports.py`). Findings V-D7-1, V-D7-2; N-2, N-4.
- **D8 operability.** No log call in the 08b source (grep); N-1.
- **D9 hosting and supply chain.** Not checked beyond the build: XlsxWriter and ReportLab come from
  the hashed lock files (`requirements*.lock.txt`); `pip-audit` not run here (verify-09 owns SC5/SC8).
- **D10 tests as evidence.** Sweep: no `skip`, `xfail` or `sleep` in the 08b tests; one broad
  `except Exception` in `tests/support/fakes.py:5235`, which restores state and re-raises (conceded).
  Wrong implementations the tests catch: a routine that skipped the visibility cut (claim 6 tests); a
  writer that dropped the quote prefix anywhere (new module); a capture or vehicle write that skipped
  the run decision (five mutations, section 8); a split that rounded each share (claim 4); a stale
  writer accepted (claim 10). Finding V-D10-2; the draft's V-D10-1 closed.
- **D11 documents.** Finding V-D11-1; `docs/04` 14.3 corrected (V-D3-1); questions 101 and 102 added;
  `docs/12` section 7 two residual risks; `docs/perf` two measurements appended.

## 5. Per mode

- **Assumptions (Socratic).** "Every text goes through `write_string` ... a text that begins like a
  formula also gets the quote prefix" (true for data cells only: V-D6-1). "The role's statement timeout
  bounds the routine" (true, and the bound turns into a 500 at scale: V-D7-1, V-D7-2). "The day save
  runs the single capture's steps" (true, and their cost is per row). "Vehicle ids sort KDA before KDC"
  (false: V-D10-2). "An applied migration never changes" (false on `xcode`: V-D6-2).
- **Falsification.** Claim 20 (decided by every completing write): would a test fail without each of
  the five calls? Yes, each (section 8). Claim 9 (ledgers agree): would a summing helper that missed a
  source pass? No: totals are compared with the full postings per vehicle. Claim 22: would 500 rows fit
  in 5 s? No (18.9 s). Claim 17: would a missing prefix on a non-data cell pass? It did, until the new
  test.
- **Pre-mortem.** (1) Three months after cutover a 150-vehicle tenant joins; the day screen's save
  answers 500 every evening and the clerks fall back to single cells; noticed as "Save failed" reports
  (V-D7-1). Inversion: guaranteed by any fleet past about 130 rows on this hardware. (2) The owner runs
  Net by vehicle for the year at 500 vehicles and gets an error page (V-D7-2). (3) An office admin opens
  the money-out export, fixes a typo in a main-category label cell and the cell turns into a formula
  (V-D6-1, fixed). (4) The next migration cannot reach the shared `xcode` database (V-D6-2).
- **Red team.** Persona 8 (the gamer): a catalogue name, note or holder name of `=cmd|' /C calc'!A0`,
  `=HYPERLINK(...)`, `@SUM`, `+`, `-`, tab or CR in every export: no `<f>` element anywhere; the band
  and label cells lacked the prefix (fixed). Persona 1 (clerk in tenant A): foreign `holderId`,
  `companyId`, vehicle ids in the ledger, report and export routes: nothing leaks (D1). Persona 6
  (hurried DBA): the edited applied migration (V-D6-2). Persona 7 (the calendar): restore and join-date
  changes deciding runs over away days (holds).
- **Dialectic.** ADR-16 (XlsxWriter, string cells plus a format prefix, not a leading apostrophe in the
  value): the rejected option (prefix the value with `'`, as OWASP suggests for CSV) would survive a
  "save as CSV" round trip but changes what the cell holds; the chosen option is right for `.xlsx`, with
  the CSV round trip a user action outside the API. DEC-42 (ascending-id lock order in the day save):
  the other side (log in the order sent) would read better in history but invites deadlocks between
  two overlapping day saves; the decision holds, and the test now follows it. Per-row capture through
  `revenue.capture_entry` (one helper for single and batch saves): the other side (a set-based batch)
  wins at scale (question 101).

## 6. Conceded

- Draft V-D4-1 (a malformed `{id}` on `GET /setup/recurring/{id}/runs` answers an unlisted 400): the
  route is `/recurring/{id:uuid}/runs` (`setup_recurring.py:155`), so a malformed id does not match and
  answers an empty 404, as .NET's `{id:guid}`; `test_setup_recurring.py::test_a_malformed_item_id_is_an_empty_not_found`
  pins it, and the generated document lists 200, 401, 403, 404.
- A live formula in any export: every text is `write_string` with `strings_to_formulas` off; the new
  test finds no `<f>` element in any of the four exports.
- A Python sum of postings: only layout arithmetic in `pdf.py`.
- The broad `except Exception` in `fakes.py:5235`: it restores the fake's state and re-raises.
- Statement timeout retried as transient (amplifying V-D7-1): 57014 is not in `_TRANSIENT_SQLSTATES`,
  so idempotent reads are not retried (N-1 records the status code instead).
- `fleet_totals` diverging from `fleet_postings` after the 10x rewrite: same filters line for line
  (`fleet_totals.sql:36-60` against `fleet_postings.sql:81-136`), compared by a test per vehicle.

## 7. Fixes

| Finding | Files | Test that failed before and passes now |
|---|---|---|
| V-D6-1 | `src/xcode_api/infra/exports/xlsx.py` (`_Formats`: the band, figure-label, header and totals formats carry `quote_prefix`; docstring) | `tests/api/test_export_injection.py::test_no_export_turns_a_leading_formula_character_into_a_formula` (failed on `('B5', '-RUNNING (KES)')`) and `::test_the_bands_figure_labels_and_headers_keep_a_leading_formula_character_as_text` (failed on `A1 '=Net'`); re-proved by switching the prefix off (2 failed), then on (2 passed) |
| V-D10-2 | `tests/db/test_revenue_day_routines.py` (expected log order = ascending vehicle id) | `test_the_save_answers_each_row_in_the_order_sent_and_logs_each_record`: failed in the baseline, 4 of 4 runs pass |
| V-D11-1, V-D3-1, V-D7-1, V-D7-2, V-D3-2 | `docs/12-security.md` (2.8 row; two section 7 risks), `docs/04-schema.md` 14.3, `docs/13-open-questions.md` 101 and 102, `docs/perf/scheduled-and-day.md`, `docs/perf/reports.md` | documents |

## 8. Commands and outputs

Environment (measured 14 Oct): PostgreSQL 16.15 on the 5433 test cluster (started by this session at
08:13); Python 3.13.2; CI image `postgres:18` (`.github/workflows/xcode-api.yml:71`).

Baseline, one module per process, `-n 0`, template `xcode_template_v08b` (built from the tree at 08:13):

| Module | Result |
|---|---|
| `tests/unit` | 1118 passed |
| `tests/db/test_expense_routines.py` | 62 passed |
| `tests/db/test_recurring_pause_routines.py` | 29 passed |
| `tests/db/test_report_routines.py` | 23 passed |
| `tests/db/test_revenue_day_routines.py` | 1 failed (V-D10-2), 17 passed |
| `tests/db/test_setup_recurring_routines.py` | 54 passed |
| `tests/db/test_setup_vehicle_routines.py` | 64 passed |
| `tests/db/test_setup_investment_routines.py` | 33 passed |
| `tests/db/test_setup_helpers.py` | 93 passed |
| `tests/db/test_pettycash_routines.py` | 82 passed |
| `tests/db/test_pettycash_helpers.py` | 64 passed |
| `tests/db/test_history_routines.py` | 61 passed |
| `tests/db/test_revenue_routines.py` | 92 passed |
| `tests/api/test_expenses.py` | 30 passed |
| `tests/api/test_reports.py` | 9 passed |
| `tests/api/test_recurring_pause.py` | 9 passed |
| `tests/api/test_revenue_day.py` | 8 passed |
| `tests/api/test_petty_cash.py` | 18 passed |
| `tests/api/test_setup_recurring.py` | 35 passed |
| `tests/api/test_contract_released_clients.py` | 36 passed |
| `tests/api/test_openapi.py` | 13 passed |
| `tests/api/test_export_injection.py` (new) | 2 passed (2 failed before the fix) |

The API modules ran after the `xlsx.py` fix landed (08:35), so for `test_reports.py` and
`test_expenses.py` they are also the regression run of that fix.

Mutation runs (a copy of `db/` in the scratchpad through `XCODE_DB_DIR`, template
`xcode_template_v08bm`; the live tree untouched), each call replaced by `NULL;`:

| Call removed | Covering test | Result |
|---|---|---|
| `setup_vehicle_update.sql:152` | `tests/api/test_recurring_pause.py::test_a_later_join_date_decides_the_held_runs_whose_window_it_completes` | failed (`[] == [('2026-10-05', 1), ...]`); the restore test passed |
| `setup_vehicle_restore.sql:71` | `::test_a_restore_decides_the_held_runs_of_the_days_away` | failed (`[] == [..., 2)]`); the join-date test passed |
| `capture_entry.sql:195` | `test_recurring_pause_routines.py::test_a_held_run_is_saved_once_its_day_reaches_the_minimum`, `test_revenue_day_routines.py::test_a_day_save_that_completes_a_window_decides_the_saving_run` | both failed |
| `save_recurring.sql:437` | `test_recurring_pause_routines.py::test_a_saving_saved_with_a_rule_decides_its_runs_from_its_start` | failed |

The day save at 500 rows (scratch module outside the tree, `yard` x `seed_10x` = 600 vehicles, no
scheduled items, `xcode_app` with its 5 s timeout, then lifted to 120 s): cancelled at 5 s; lifted:
capture 18.9 s, replay 7.6 s, correction 15.7 s; with the decision call removed, capture 17.4 s. Profile
(`track_functions = 'pl'`): `capture_entry` 7.0 s own of 13.7 s, `decide_saving_runs` 2.1 s,
`record_change` 1.4 s, `check_writable` 1.0 s, `business_date` 0.9 s over 1,500 calls.

Checks: `ruff check .` all passed; `ruff format --check .` 494 files formatted; `mypy` no issues in 227
source files. CLI database `xcode`: `db status` applied 0001-0014, routine drift in
`40_setup/{saving_balance,scheduled_runs,setup_recurring_list,setup_recurring_runs}.sql`, migration
checksum drift `[14]`; `db verify` exit 0. `db routines` was not run there (shared database, drift
left for the user, section 10). Catalogue on `xcode`: no function executable by PUBLIC outside
extensions; no `SECURITY DEFINER` without `search_path`; no name with two overloads. OpenAPI generated
with `XCODE_ENV=development XCODE_MAIL_BACKEND=log` (exit 0; the scratch copy is in this session's
scratchpad).

Full run: one run shared with verify-09 (revenue-81 [4ac8ce]), launched by it at 09:16 under a board FREEZE
on `src/`, `db/` and `tests/`, from this tree with a fresh template `xcode_template_v09full`, `-n 0`;
this session's changes (08:36 to 08:38) were in it and no file under those folders changed since.
Ended 11:07, exit 1: **6572 passed, 3 failed, 0 errors, 0 skipped**, 2 warnings (PyJWT
`InsecureKeyLengthWarning` for the 36-byte test HMAC key) in 6649.8 s (1:50:49). Read by this session
from its `full.log` and `full.xml` (revenue-81's scratchpad `full/`, path in the board's 09:16 entry).
08b modules in that run, all green: unit `test_export_files` 8; db `test_expense_routines` 62,
`test_report_routines` 23, `test_revenue_day_routines` 18, `test_recurring_pause_routines` 29,
`test_setup_recurring_routines` 54, `test_setup_vehicle_routines` 64, `test_pettycash_routines` 82,
`test_pettycash_helpers` 64, `test_revenue_routines` 92, `test_history_routines` 61; api
`test_expenses` 30, `test_reports` 9, `test_revenue_day` 8, `test_recurring_pause` 9,
`test_setup_recurring` 35, `test_setup_vehicles` 79, `test_petty_cash` 18, `test_export_injection` 2.
The only failures are the three of section 9.

## 9. Regressions and misses against earlier reports

Read after this session's own pass: the 13 Oct draft and the three build reports.

- No finding recorded as fixed is broken again.
- Missed by the draft and the builds: V-D6-1 (both reports cite the unit test of data cells only),
  V-D7-1 (the draft named the 500-row save as unmeasured; the builds did not measure it), V-D7-2 (the
  build lists `net` over budget, not past the timeout), V-D10-2, V-D11-1, V-D6-2.
- The draft's items, as section 1 says: V-D3-1 and V-D3-2 confirmed and synthesised; V-D10-1 closed by
  tests that each fail without their call; V-D4-1 conceded; N-1 holds as documented
  (`docs/12` 2.8; pinned by the writer-failure test); N-2 superseded by V-D7-2; N-3 measured (V-D7-1).
- Pre-existing failures that are not 08b's: the three `tests/db/test_gateway.py` drift tests (D1 gateway:
  `CodeCheck` and `DeviceVerification` need `now`; `ClearedPause` has no `was_paused`). In the full run they are the only failures: `test_identity_routines_map_every_outcome_with_one_statement_each`
and `test_verify_device_maps_through_the_gateway` (`TypeError: CodeCheck.__init__()` /
`DeviceVerification.__init__() missing 1 required positional argument: 'now'`),
`test_ops_routines_map_the_operator_routines` (`AttributeError: 'ClearedPause' object has no
attribute 'was_paused'`); the other 16 tests of the module pass. Reported, not fixed.

## 10. For the user

- **The shared CLI database `xcode` (V-D6-2).** `db migrate` refuses there until `0014`'s checksum is
  repaired. Recommendation: since the file is four `DROP FUNCTION IF EXISTS` statements, run it once
  more against `xcode` as `xcode_owner` and set `ops.schema_migrations.checksum` for version 14 to
  `9848c7d5762a6aa27de3c55ea5073d6b52802f1f80bb3a962616551389b75728`, then `db routines`; or rebuild
  `xcode` from the files. Either is reversible; I did not touch it because other sessions use it.
- **Fleet size (questions 101 and the V-D7-2 risk).** Before a tenant with more than about 100
  vehicles is onboarded, the day save needs a set-based batch path and the year-long Net report a
  summing form of the day series. Today's only tenant has 9 vehicles, so nothing blocks the cutover.
