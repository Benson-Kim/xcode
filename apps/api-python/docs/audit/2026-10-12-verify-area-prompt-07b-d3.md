# Verify `area:prompt 07b D3` (setup), fix mode, standard depth

Session revenue-17 [60bb7c], 2026-10-12 16:53 onward. Not the D3 builder (revenue-0c [5d50a4]).
Method: `docs/14-verification.md`; prompt `docs/prompts/verify.md`.

## 1. Verdict

**pass with findings**. The full suite ran once on a fresh template holding D3 and D4 (D4's shared
run, board queue row 7, 17:35-19:31): 5733 passed, 3 failed, 0 errors, 0 skipped. Every D3 module
is green. The 3 failures are in `tests/db/test_gateway.py` (the identity and operator gateway; D1
drift since `domain/identity.py` of 11 Oct 22:36, attributed on the board), not in D3's code. No
blocker or major survives.

- Claims (23): holds 22, fails 1, unproven 0, not checked 0. (The provisional tally of 17:15 said "holds 19, unproven 3"; it counted the D10 full-run probe as a claim. Corrected here.)
- Findings that survive (5): blocker 0, major 0, minor 1, note 3, for the user 1.
- Fixes: none. The procedure fixes blockers and majors only; the minor is in prompt 08's files.

## 2. Thesis and claims

Thesis: 07b D3 delivers target sets (B9), the fleet number (B10), the optional initial investment
(B11), main categories (B16) and the split scheduled and savings rights (B17) on the prompt-06
routes. Its rules hold under concurrent writes and for every scope and tenant. The released
clients keep working, apart from the changes the design made on purpose. D3 is built ahead of
.NET: for the register rows, the notes decide (question 46).

| # | Claim (where stated) | Code | Verdict | Grade | Evidence |
|---|---|---|---|---|---|
| C1 | A set starts today or later (DN-B9-3) | `setup_target_set_save.sql` `target_start_past` | holds | A | `test_setup_target_routines::test_a_set_cannot_start_in_the_past` |
| C2 | A started set cannot be edited or removed (DN-B9-4) | `setup_target_set_remove.sql` (`starts_on <= today`) | holds | A | `::test_a_set_that_has_started_cannot_be_removed`, `::test_a_set_starting_today_is_in_force_and_cannot_be_removed` |
| C3 | A set not started yet is replaced or removed (DN-B9-5) | save `UPDATE ... starts_on = p_starts_on`; remove | holds | A | `::test_saving_again_on_the_same_date_replaces_the_set_that_has_not_started`, `::test_a_set_that_has_not_started_is_removed_and_logged` |
| C4 | A set equal to the one in force is refused (DN-B9-6) | save `target_set_unchanged` | holds | A | `::test_a_set_equal_to_the_one_in_force_on_its_date_is_refused` |
| C5 | Logged "Target set, [registration]" with before, after and the start date (DN-B9-7) | save `record_setup_change`, `vehicle_snapshot` | holds | A | `::test_a_future_set_is_added_and_logged_with_the_figures_before_and_after` |
| C6 | The right `vehicles.target` alone (DN-B9-8) | `enter_organization(..., 'vehicles.target')` | holds | A | `::test_saving_and_removing_need_vehicles_target_alone`; api `test_reading_needs_vehicles_view_and_writing_vehicles_target` |
| C7 | A new vehicle's seven figures, the first set from the join date (DN-B9-10 as `DEC-13` decided) | `setup_vehicle_create.sql:96` | holds | A | vehicle routines module, 63 passed (baseline) |
| C8 | Editing a vehicle no longer carries targets (`DEC-15`) | `api.setup_vehicle_update` has no target parameter | holds | B | structural; the api ignore test was not re-read |
| C9 | The list shows the set in force and the next set (DN-B9-9) | `setup_vehicle_list.sql:108-135` (`day_targets`, `next_target`, gated by `v_manages`) | holds | B | read; vehicle modules green in the baseline |
| C10 | The vehicle report uses day targets (DN-B9-2, the setup part) | `setup_vehicle_report.sql:71` sums `setup.day_target` | holds | B | read; the revenue part is D4's |
| C11 | Fleet number required, unique within the company whatever the case, editable, logged (DN-B10-1, -2) | `fleet_number.sql`, create/update `vehicle_fleet_taken`, `uq_fleet_vehicles_fleet_number` | holds | A | `test_setup_vehicle_routines::test_a_fleet_number_is_unique_in_its_company_whatever_the_case` (the same number in another company is created), `::test_an_update_refuses_a_fleet_number_another_vehicle_of_the_company_uses`; race `test_setup_races::test_two_vehicles_with_one_fleet_number_racing_...` |
| C12 | Every vehicle drop-down shows the fleet number (DN-B10-3) | S03 `access_scope_options.sql:39`, S25 `setup_vehicle_options.sql:37` | **fails** | A | `55_pettycash/pettycash_options_get.sql:48` has no fleet number (V-D4-1) |
| C13 | Initial investment optional, empty not zero, cleared on edit (DN-B11-1) | `nullif(p_initial_investment, 0)`, `ck_fleet_vehicles_initial_investment` (> 0) | holds | A | vehicle routines tests at `test_setup_vehicle_routines.py:363-378` |
| C14 | Main categories: unique name, a category under one or none, rights of the expense items (DN-B16-1, -3, -4, -7) | `setup_expense_main_category_*.sql`, `fk_expense_categories_main_category` | holds | A | `test_setup_main_category_routines.py` 18 passed (baseline), incl. `::test_a_rename_checks_the_name_then_the_record_then_uniqueness`, `::test_adding_needs_catalog_add_and_renaming_catalog_edit` |
| C15 | "Counts as" goes; existing groups become ordinary main categories (DN-B16-2, question 63) | `0010_setup.sql` backfill and its `DO` check | holds | B | read; `test_migrate`'s backfill test not re-run by me (D4's full run) |
| C16 | Rights split by kind; revise needs the edit right of both kinds (DN-B17-1) | `recurring_kind_right.sql`; `save_recurring.sql:92,103`; `recurring_visible.sql:16` | holds | A | `test_setup_recurring_routines::test_the_rights_of_one_kind_reach_no_item_of_the_other`, `::test_switching_the_kind_needs_the_edit_right_of_both_kinds` |
| C17 | Change log reads "Saving, [name]" / "Scheduled expense, [name]" (DN-B17-3) | `recurring_change_reason.sql` | holds | A | `::test_every_revise_names_the_kind_and_the_item_as_it_ends` |
| C18 | The visibility and tenancy tests extend to every new route (prompt evidence) | — | holds | A | `test_setup_object_authorization.py:109-121` (foreign ids), `:228-231`, `:320` (`test_target_sets_of_a_vehicle_outside_the_scope_are_not_found`) |
| C19 | Target writes serialise on the vehicle row | save/remove lock the vehicle `FOR UPDATE` first | holds | A | `test_setup_races.py` (one date at once, a save while the vehicle leaves, a removal while replaced), 11 passed (baseline) |
| C20 | Backfill: each week total kept; a target too small to split is left, not aborting | `0010_setup.sql` split (Sunday takes the remainder) and `DO` check | holds | B | read; the abort recorded for B20 (`docs/10` 3.1) is avoided here |
| C21 | Released clients keep working apart from the changes listed on purpose (invariant) | `tests/api/test_contract_released_clients.py` | holds | A | full run: 32 passed (the rows the design changed on purpose are the builder's, `DEC-15`) |
| C22 | Lint, types, all tests green (invariant) | — | holds | A | lint, format and mypy clean at 17:15; full run: every D3 module green (section 8); the 3 suite failures are D1's gateway tests |
| C23 | `db verify` exit 0 (invariant) and no TODO or plan ids | — | holds | A | section 8: 21 of 21 on `xcode` at 17:11; the sweep of every D3 file is empty |

C21 and C22 were unproven until the full run; both hold (section 8).

## 3. Findings

| id | mode | claim attacked | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| 07b-d3:V-D4-1 | falsification | DN-B10-3: every vehicle drop-down shows registration and fleet number (`docs/15` row, docs location `docs/06` 2.12) | The petty-cash entry form's vehicle list (P03 `GET /setup/pettycash/options`) serves `{id, registration, ...}` without the fleet number, and `docs/06` 2.12 names only S03 and S25 as option bodies that add `fleetNumber` | `db/routines/55_pettycash/pettycash_options_get.sql:48`; `docs/06-http-contract.md:551,568` | Looked for a client fallback: the notes say "the registration alone until a number is set", so a client degrades to the registration rather than breaking. No released client reads the field. Prompt 08 landed `0012` before D3 added the number, so neither prompt's checklist asked for it | survives, **minor** | Recorded on the board (17:10) for the next verify-08 or 08b: add `fleet_number` to the routine, the options DTO, the fake and a test, plus the P03 row in `docs/06` 2.12. Not fixed here: it's a minor, in 08's files, and `tests/support/fakes.py` is in D4's landing set |
| 07b-d3:V-D11-1 | Socratic | `docs/05` matches the code | `docs/05` section 4 rows (`api.setup_recurring_list` to `_cancel_stop`, `docs/05-routines.md:360-365`; the expense lists `:395-396`) still name `commitments.*` and `expenses.setup`. Section 10.4 restates them as "(changed)" further down, so a reader of section 4 alone builds the old gate | `docs/05-routines.md:360-365, 395-396` versus `:10.4` rows 38-40 | The appended "(changed)" sections are the documents' convention for 07b (`docs/15` D0) | survives, **note** | For the next docs pass: mark the superseded section-4 rows "see 10.4" (docs/05 is in D4's landing set now) |
| 07b-d3:V-D1-1 | red team (clerk) | a scoped viewer learns nothing about hidden vehicles | A member scoped to some vehicles of a company, with `vehicles.edit`, saves a visible vehicle with fleet number "14": `vehicle_fleet_taken` tells them a vehicle they can't see in that company holds "14" | `setup_vehicle_update.sql:89-96`, `setup_vehicle_create.sql:77-79` | The registration check of 06 and .NET reveals hidden registrations across the whole organisation the same way, and a fleet number isn't secret. The unique constraint must refuse anyway | survives, **note** | Residual risk, owner: 08b/security wave (SC2). Accepted as parity with the registration check |
| 07b-d3:V-D5-1 | red team (calendar) | a set starts today or later (DN-B9-3) | `startsOn` 9999-12-31 is accepted; the far-future set shows as `nextTarget` | `setup_target_set_save.sql:51-53` (lower bound only) | No rule in the notes bounds it, and it changes no figure until that day; it can be removed (not started) | survives, **note** | None needed; a client may cap the date picker |
| 07b-d3:V-D5-2 | dialectic | DN-B10-1: a fleet number is unique within a PSV company | A retired vehicle keeps its fleet number, so a replacement bus cannot take number 14 in that company until the old one is renumbered (retired vehicles cannot be edited: `vehicle_retired_edit`) | `uq_fleet_vehicles_fleet_number` covers retired rows; `setup_vehicle_update.sql:74-76` | Restoring a retired vehicle would otherwise collide; the notes don't say | survives, **for the user** | Decided by the owner at 20:46: keep. Question 81 in `docs/13` (decided). Pinned by the new `test_setup_vehicle_routines::test_a_retired_vehicle_keeps_its_fleet_number_in_its_company`: it failed first when a scratch plugin let the per-test copy of `api.setup_vehicle_create` skip retired vehicles (the constraint then answered 23505, not `vehicle_fleet_taken`), and it passes as is |

## 4. Per domain

**D1 Tenancy and authorization.**
- Tenant guard: every new `api.*` routine calls `tenancy.enter_organization` first. `db verify` "tenant routines enter their organization" is ok on `xcode`. holds.
- RLS and the `tenant_isolation` policy on `setup.vehicle_target_sets` and `setup.expense_main_categories`: holds (`0010_setup.sql`, `db verify`).
- Scoped viewers: target sets of a hidden vehicle are `not_found` (C18). Day targets and the next set are hidden from investment-only viewers (`v_manages`). Savings reach `vehicles.view` holders through the report and `recurringItems` (the builder's V-D1-1, question 73, for 08b). Fleet-number refusal: V-D1-1 (note). holds, with the note.
- Foreign ids answer `not_found`: holds (C18).
- Anti-escalation and catalogue: n/a (D2's).

**D3 Data integrity and concurrency.**
- Version bump and compare: the D3 writes return `api.write_result`; the version is the change-log version from `record_setup_change`; no client version is sent to S48/S49. holds.
- Lock order: vehicle `FOR UPDATE` then the organization row (through `record_setup_change`). Capture takes the vehicle `FOR SHARE` then the organization row, the same order (builder's V-D3-4, conceded). holds.
- Replays: an identical target save answers 400 (DN-B9-6; builder's V-D3-3, by design). Two first writes on one date race to one row (C19). holds.
- Money: day figures `numeric(14,2)`, positive by `ck_vehicle_target_sets_days`; the week total is never stored (builder's V-D3-2). holds.

Three hardest attacks that failed:
1. A removal racing a replacement on the same date: the vehicle lock serialises them and the test pins the outcome.
2. A target save racing a retirement: refused after the wait.
3. A future set left on a vehicle whose join date moves earlier: only the first set is copied to the new join date.

**D4 Contract parity.**
- Routes S47-S52: `docs/06` matches the routers (`setup_vehicles.py:165,176,191`, `setup_expenses.py:206,229,244`). The S48 body is `{startsOn, days}` in both. holds.
- Bodies and the released-client changes (`DEC-15`): holds (`test_contract_released_clients` 32 passed in the full run).
- Drift: no `.NET` file under `apps/api` or `tests/api` changed on 2026-10-12 (`find -newermt`). n/a for drift.
- Drop-downs: V-D4-1.

**D5 Domain rules and time.**
- The business date comes from the organization's zone through `tenancy.business_date`.
- No `now()`, `current_date`, `clock_timestamp()` or `random()` in `40_setup` (sweep). Table defaults in `0010` are never used by the routines, which pass `p_now`.
- The `touch_updated_at` trigger writes `now()` only when a routine leaves `updated_at` unchanged.
- holds. V-D5-1 and V-D5-2 are notes.

**D6 Database craft.**
- `db verify` 21 of 21 on `xcode` (section 8). No dynamic SQL. Every `SECURITY DEFINER` routine in `40_setup` sets `search_path` (sweep).
- `0010` has a `.down.sql`.
- Features: generated stored columns (PostgreSQL 12).
- holds. The fingerprint and template probe: not checked by me (D4's run builds its own template).

**D7 Performance.** Statement budgets are asserted in `tests/api/test_setup_{targets,vehicles,expenses}.py` (`statements(`). holds (read, not re-run).

**D10 Tests as evidence.**
- No `skip`, `xfail`, `sleep(` or broad `except` in the setup tests (sweep).
- Every new refusal code has at least one test file (`target_start_required` to `expense_main_taken`, all 4 to 8 files).
- Wrong implementations the tests catch:
  - removal allowed on the start day;
  - the fleet check across the organisation instead of the company;
  - a kind right reaching the other kind;
  - an equal set not refused;
  - a save without the vehicle lock (the race tests).
- The full suite on a tree holding D3: holds (5733 passed, 3 failed outside D3; section 8).

**D11 Documents.**
- `docs/06` S47-S52 and S17-S19 match the code.
- `docs/05` 10.4 matches the code; the older section-4 rows don't (V-D11-1, note).
- The `docs/05` 4.9 row records the null-bucket rule ("2, charges").
- Questions 63 and 73 are current.

## 5. Per mode

**Assumptions:**

| Assumption | Where stated | Enforced by |
|---|---|---|
| "a set that has started cannot be edited" | DN-B9-4 | `setup_target_set_remove.sql` `<=`; save replaces a set starting today, which DN-B9-4 allows ("corrected by a new set from today") |
| "only one set per vehicle and date" | docs/04 13.4 | `uq_vehicle_target_sets_start` |
| "fleet numbers are unique per company" | DN-B10-1 | own check plus `uq_fleet_vehicles_fleet_number` (also over retired vehicles: V-D5-2) |
| "vehicles work every day" (no zero day) | notes v2.3 line 157 | `ck_vehicle_target_sets_days`, `check_day_targets` |
| "a category without a group counts as a charge in the old report" | docs/05 4.9 row | `coalesce(bucket, 2)` in both posting sources |

**Falsification:** the claims table in section 2, with its grades.

**Pre-mortem:**
1. A depot replaces bus 14 after a crash; the new bus can't be numbered 14, so staff type "14A" and reports split the history (V-D5-2). Early sign: requests to renumber. Inversion: uniqueness ignoring retired rows would let a restore collide. The condition exists today: question for the user.
2. A clerk enters next week's set on Sunday night in Nairobi while the server clock is UTC. Inversion: the start check uses the organization's business date, so it holds.

**Red team:**
- Clerk: the fleet-number probe (V-D1-1, note).
- Foreign set id: `not_found` (C18).
- Kind rights: holds (C16).
- Calendar: a far-future set (V-D5-1, note).
- Hurried DBA: the backfill `DO` block stops the migration on a lost week total. holds.

**Dialectic:**
- The first set from the join date (`DEC-13`) rather than today: kept. A back-dated join needs targets for its past days.
- Retired vehicles keeping their number: open to the owner (section 10).

## 6. Conceded

- Replacing a set that starts today contradicts "started is fixed": no. DN-B9-4 corrects a started set "by a new set from today", which is that same date.
- The first set should start today (DN-B9-10): `DEC-13` decided the join date, and the code and docs/05 10.4 follow it.
- A day figure of 0 is refused: the notes say all seven are required "because vehicles work every day".
- New categories land in "recurring charges" in the v2.11 vehicle report: documented in `docs/05` 4.9, the same as the scheduled source; 08b's per-main-category report replaces it.
- `touch_updated_at` overwrites `p_now` with the wall clock: it fires only when the routine left `updated_at` unchanged.
- Removing a future set of a retired vehicle is allowed: cleanup only, it changes no figure.
- The S48 field `days` versus `dayTargets`: `docs/06` names `days` for S48 and `dayTargets` for the vehicle bodies, and the code follows.

## 7. Fixes

None in D3's scope; no blocker or major survived.

Outside this scope, in the same session and before this verify started (prompt 08's two handoff items, board 16:52):
- `tests/db/test_structure.py::test_verify_reports_a_missing_schema` renames the schema instead of dropping it.
- `tests/api/test_petty_cash.py::test_integers_beyond_their_column_types_are_refused_before_the_routine` is new. With each bound removed, it failed with a 500.

## 8. Commands and outputs

- PostgreSQL 16.15 (local cluster, port 5433); Python 3.13.2. CI pins `postgres:18`, and `.github/workflows/xcode-api.yml` is untracked, so CI has never run.
- Baseline, `-n 0`, one module at a time, private template, pre-D4 tree (16:55-17:09):
  - target routines 15, main category routines 18, vehicle routines 63, expense routines 36, recurring routines 54, helpers 93, races 11: all passed.
  - Object authorization: 1 passed and 25 errors, which I caused: I dropped the template under the run while stopping it before D4's landing. Not a finding.
  - The remaining modules were not run here; the agreement with the coordinator is to read them from D4's full run.
- `xcode-api db status` on `xcode` (17:11): applied 0001-0010 and 0012, pending none, no routine or checksum drift. `db verify`: 21 of 21 ok, exit 0.
- After D4 landed (17:15): `ruff check .` all checks passed; `ruff format --check .` 397 files already formatted; `mypy` no issues in 189 source files.
- Sweeps over the D3 files (`40_setup`, `0010`, the setup src and tests): clock, dynamic SQL, definer without `search_path`, skip/sleep/except, TODO and plan ids: no hits.
- **Full run** (D4's shared run, `pytest -n 2`, fresh template, freeze on `src/`, `db/`, `tests/`): started 17:35:41,
  `3 failed, 5733 passed, 4 warnings in 6920.82s (1:55:20)`; 0 errors, 0 skipped (`full.xml` suite totals).
  Failures: `tests/db/test_gateway.py::{test_identity_routines_map_every_outcome_with_one_statement_each,
  test_verify_device_maps_through_the_gateway, test_ops_routines_map_the_operator_routines}`, D1 drift, not D3.
  Measured by me from `full.xml` (per-module tally), the D3 modules, all green:
  - db: setup target routines 15, main category routines 18, vehicle routines 63, expense routines 36,
    recurring routines 54, company routines 35, investment routines 33, helpers 93, races 11, object authorization 26;
  - api: setup targets 17, vehicles 79, expenses 34, recurring 35, investment 34, companies 33;
  - shared rows: released clients 32, constraints 59, grants 77, schema structure 39, tenancy isolation 97,
    migrate 18, routine headers 1342.
  No D3 file changed between my reading and the run except D4's announced edit to
  `tests/db/test_setup_object_authorization.py` (the dropped `setup.vehicle_targets` left its table list;
  every target-set and main-category case is still there).

## 9. Regressions and misses against earlier audits

Earlier audit: `docs/audit/2026-10-12-build-07b-d3.md` section 4 (read after this pass).
- Regressions: none. Its fixes still hold in the code: V-D3-1 (the first set copied to an earlier join date, `setup_vehicle_update.sql:131-145`), V-D5-1 (`dayTargets` while away), V-D11-1 (the joined change-log sentence).
- Its misses: V-D4-1 (petty-cash drop-down), V-D11-1 (stale section-4 rights), V-D1-1, V-D5-1, V-D5-2.
- Agreed independently: its V-D1-1 (savings on vehicle screens, question 73) and V-D3-4 (lock order).

## 10. For the user

- **Fleet numbers of retired vehicles: decided by the owner on 2026-10-12 (20:46): a retired vehicle keeps its fleet number.** Recorded as question 81 (decided) in `docs/13-open-questions.md`, pinned by a test (section 3, V-D5-2). Nothing else is open for the user.
