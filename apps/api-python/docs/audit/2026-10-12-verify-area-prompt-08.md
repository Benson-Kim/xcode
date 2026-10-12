# Verification: prompt 08 (petty cash), 2026-10-12

Session revenue-ff [9fea06], a fresh session with no build context, `SCOPE: area:prompt 08`,
`MODE: fix`, `DEPTH: standard`. Method: `docs/14-verification.md`. The 08 builder's session
(revenue-17 [60bb7c], after `/clear`) had registered the same scope at 16:04 and stood down at
16:09; it kept only the two items of its own 14:20 handoff (the integer-bounds test and the
missing-schema structure test), both done at 16:52 and outside this report's fixes. This
session was cut by a usage limit from 16:15 to 16:52 with nothing changed.

## 1. Verdict

**pass with findings** (changed by the coordinator, revenue-d5 [b49167], at 20:45 under "Where
to resume"): every 08 module passed on the shared full run of queue row 7, which ended at 19:31
(section 12). Before that run, the verdict read: "fail until the shared full run (board queue
row 7) completes; on the targeted modules: pass with findings." The full suite did not run inside this session: the board allows one full
run at a time, and D4's run (shared with verify-08, template built at 17:35 from the tree with
this session's fixes, about 20:05) carries the 08 modules; the coordinator adds section 12
from its log, as for the earlier verify reports. Every 08 module ran one at a time on the
live tree before and after the fixes (section 8).

| Findings | blocker | major | minor | note |
|---|---|---|---|---|
| surviving | 0 | 0 | 2 (both fixed) | 4 (2 documents corrected, 2 recorded) |

One challenge that survived its first run (a deadlock through the vehicle row) was refuted
by its own fail-first run and is recorded in section 6 with what defeated it.

Claims: 41 (`holds` 36, `fails` 2 both fixed, `unproven` 2, `n/a` 1). Probes: D1 6 (holds
5, n/a 1), D3 6 (holds 5, fails 1 fixed), D4 5 (holds 4, fails 1 fixed), D5 4 (holds 3, n/a
1), D6 7 (holds 6, unproven 1), D7 6 (holds 3, unproven 1, note 2), D8 5 (holds 3, n/a 2), D9
3 (n/a 3), D10 5 (holds 5: the full run since section 12), D11 2 (holds 2 after the corrections).
D2 is out of scope (08 changes nothing in identity or sessions).

## 2. Thesis and claims

Thesis (steelmanned): prompt 08 delivers D0 to D4 of `docs/prompts/08-petty-cash.md`; its
invariants hold; the behaviour equals the .NET petty-cash feature at `HEAD` 493bf82 plus the
working tree of 10 October 22:31 (`apps/api/Application/PettyCashUseCases.cs`,
`Domain/PettyCash.cs`, `Api/PettyCashEndpoints.cs`, `tests/api/PettyCashTests.cs`; no commit
to `apps/api` or `tests/api` since 2026-10-11, so nothing drifted since the inventory was
corrected on 2026-10-12), except where the design notes' B19 rules
(`docs/15-design-v2-3.md`, DN-B19-1 to 13, DEC-21 to DEC-29) deliberately change it: twenty
rights instead of six, "sent back" as a note on a waiting expense, rejected and reopened
expenses, credit notes and cash never reviewed or edited, the back-dating limit on every
write of a record, new wire fields appended last.

| # | Claim | Where stated | Code that carries it | Verdict | Grade |
|---|---|---|---|---|---|
| C1 | Schema `pettycash` with `kinds`, `statuses` (1, 2, 4) and `entries` exactly as `docs/04` 6.2 | prompt D1 | `db/migrations/0012_pettycash.sql` | holds | A (`test_schema_structure`, `test_enum_parity`, `test_constraints`) |
| C2 | One failing insert per `CHECK` (kind shape, review, removal, total) | prompt D1 | `0012` constraints | holds | A (`test_constraints` rows; `ck_entries_unit_amount` dropped by the builder as implied by `ck_entries_total`) |
| C3 | `INSERT` and `UPDATE` grants only, no `DELETE`; RLS with `tenant_isolation` | prompt D1, invariant "never deleted" | `0012` lines 106-116 | holds | A (`test_grants`, `test_tenancy_isolation`; `db verify` 21 of 21 on a clone of my template, 17:29) |
| C4 | `total` generated, never written by a routine | invariant | `0012` line 42; no routine sets it | holds | A (a generated column refuses a write; `test_constraints`) |
| C5 | `updated_at` set by the routines, "trigger not used" | prompt D1 | every `UPDATE` sets `updated_at = p_now`; `0012` creates `touch_updated_at` because `db verify` (`check_updated_at_triggers`, `verify.py:597`) requires it on every table with the column | holds for the behaviour; the prompt's wording is stale, `docs/04` 6.2 now says so | B |
| C6 | Every helper and routine of `docs/05` 4.9 with its check order | prompt D2 | 42 files in `db/routines/55_pettycash/` | holds; the create's order is now 6 `lock_float`, 7 `check_expense` (V-D3-1) | A (`test_the_*_steps_answer_in_their_order`, five of them) |
| C7 | The fifteen line checks in the inventory's order with its sentences (14 and 16 gone, DN-B19-10) | prompt D2, invariant | `check_line.sql` | holds | A (`test_the_line_checks_run_in_their_order`) |
| C8 | Replays: create by a known own `id` without reading the body; change with a matching line not sent back; approve, send back, reject by the same reviewer | prompt D2, PC-15, PC-16 | `pettycash_entry_create.sql:57-67, 134-142`; `pettycash_entry_update.sql:70-80`; `approve:37`, `send_back:32`, `reject:32` | holds | A (`test_a_retried_create_answers_with_the_entry_it_made_whatever_the_body`, `test_two_creates_under_one_new_id_race_to_one_entry`, `test_an_unchanged_line_is_a_replay_before_the_rights_and_the_version`, `test_approving_twice_...`) |
| C9 | The client-supplied `id` is accepted only by `api.pettycash_entry_create` | invariant | the other twelve routines take `p_entry_id` of an existing row only | holds | A (`test_an_id_another_organization_uses_is_a_new_entry_here`; grep of `p_id` across `55_pettycash`) |
| C10 | Approved expenses post into the vehicle report through `setup.vehicle_net` and `api.setup_vehicle_report` (`source = pettycash`, bucket from the category, charges when none) | prompt D2, PC-31 | `vehicle_postings.sql`; `vehicle_net.sql:26`; `setup_vehicle_report.sql:106` | holds | A (`test_approved_spending_reaches_the_vehicle_report_and_credit_notes_never`, `test_a_removed_approved_expense_leaves_the_report`, `test_an_approved_expense_whose_category_has_no_bucket_posts_as_a_charge`, api `test_an_approved_expense_reaches_the_vehicle_report_...`) |
| C11 | `api.history_list` admits `pettycash` rows for scoped viewers only with a visible `vehicle_id` | prompt D2, PC-32 | `history_list.sql:99` | holds (= .NET) | A (`test_a_scoped_viewer_sees_petty_cash_history_only_for_their_vehicles`) |
| C12 | Balance, holders, visibility for the three scope kinds, `can_change`/`can_review` truth tables, week bounds, the PC-3 rounding vectors | prompt D2 evidence | `balance`, `holders`, `entry_visible`, `authorize_*`, `flags`, `revenue.week_start` | holds | A (`test_pettycash_helpers.py`, 63 passed 17:14) |
| C13 | One test per numbered step per endpoint, every PC rule, the float guard with and without `issue_negative`, the version conflicts with `current`, approve-day skipping, the reason sentences byte for byte, snapshots with PascalCase keys, the change-log `vehicle_id` | prompt D2 evidence | `tests/db/test_pettycash_routines.py` | holds | A (79 tests before this session, 80 after; `Removed Wanjiru Kamau's petty cash spending on KAA 501A for 9 Oct 2026. Reason: Recorded twice.` at line 1620; `Recorded petty cash given to Wanjiru Kamau` at 961) |
| C14 | The behaviours inventory 5.4 says no .NET test covers (`q` with `%` and `_`, status filter, `from > to`, paging bounds, the 80, 200 and 500 limits, the ten-year window, kind and holder change refusals, audit rows) | prompt D2 evidence | `test_the_list_checks_its_filters_in_order`, `test_the_list_filters_by_kind_status_text_and_days_and_pages_in_order`, the steps tests, `test_recording_logs_the_snapshot_the_reason_the_vehicle_and_an_audit_row` | holds | A |
| C15 | `domain/pettycash.py` records, `PettyCashRepository` port, `PettyCashRoutines` gateway, `FakePettyCashRepository` with parity cases (create, create replay, change conflict, approve, removal under the float guard) | prompt D3 | the files named; `tests/support/pettycash_cases.py` | holds | A (`test_the_pettycash_fake_answers_as_the_routines_do`, 2 passed 17:18) |
| C16 | `http/messages.py` carries every petty-cash sentence; `test_message_codes` green | prompt D4 | `messages.py:335-452` | holds | A (`tests/unit/test_messages.py` pins `docs/06` section 3; `test_message_codes` 6 on the 13:00 run) |
| C17 | DTOs in wire order, `kind`/`status` as words, `bucket` integer, `float` served from `float_`, `from`/`to` aliased | prompt D4 | `http/schemas/pettycash.py` | holds | A (`test_the_overview_answers_in_wire_order_...`, `test_a_create_answers_200_...`, the released-client rows) |
| C18 | Thirteen routes under `/setup/pettycash`, tag `Petty cash`, the .NET operation ids, 200 for create, comma lists parsed, 409 with `current` (null for a foreign id), 400 with `balanceAfter` | prompt D4, `docs/06` 2.11 | `http/routers/pettycash.py`; `http/errors.py:44-48` | holds | A (`xcode-api openapi` 17:01: 13 operations, ids and tag equal to `docs/06` P01-P13 and to .NET's 12 plus reject and reopen; `test_every_petty_cash_route_has_its_operation_id_and_the_petty_cash_tag`, `test_a_stale_version_is_a_409_with_the_entry_as_the_list_serves_it`, `test_cash_taken_below_zero_is_a_400_with_the_balance_after`) |
| C19 | Every `PettyCashTests` row of inventory 5.2 as a scenario with the same assertions, plus the client expectations of section 6 | prompt D4 evidence | `tests/api/test_petty_cash.py` (16 tests after this session) and the routine tests the builder mapped them to (its section 2 fact map; deviation 08:V-D10-2) | holds at the routine level; the HTTP module covers the wire, errors, budget and report | B |
| C20 | Statement budget 2 per request | prompt D4 | `test_every_route_keeps_the_statement_budget_of_two` | holds | A |
| C21 | Lock order: the float(s), then the entry rows, then `record_change` | `docs/05` 4.9; the build report's D3 narrative | the create took the vehicle and item `FOR SHARE` before the float; update takes the float, the entry, then the shares | **fails** as a description of the code (V-D3-1, minor, fixed by aligning the code); no failure was reachable through the pair (section 6) | B for the fix (the new test passes on the old order too); A for the behaviour it pins |
| C22 | Every `version` write bumps and compares with `expected_version`; a stale writer gets `XC409` with `current` | D3 probe | `check_version.sql`; the eight writing routines | holds | A (`test_the_change_steps_answer_in_their_order`, api `test_a_stale_version_is_a_409_...`, `test_two_saves_on_one_float_run_one_after_the_other`) |
| C23 | Two identical first writes under one id produce one row | D3 probe | the `unique_violation` block | holds | A (`test_two_creates_under_one_new_id_race_to_one_entry`) |
| C24 | Money `numeric(14,2)`, rounded once, half away from zero; sums cannot overflow | D3 probe | `0012`; `check_line.sql:49-55` refuses `abs(total) > 999999999999.99` before the column could | holds | A (`test_the_total_is_units_times_amount_rounded_half_away_from_zero`) |
| C25 | One routine call is one transaction; only reads are retried | D3 probe | `db/routines/pettycash.py` (`idempotent=True` on the four reads) | holds | A (the gateway; `test_the_pettycash_fake_is_a_pettycash_repository`) |
| C26 | Every tenant-scoped routine calls `tenancy.enter_organization` first; `db verify` bites | D1 probe | all 13 `api.pettycash_*` files; `verify.py:750` | holds | A (grep: 13 of 13; `db verify` 21 of 21) |
| C27 | Scoped viewers: totals, counts, floats, history, the dashboard, options and 404s never leak a hidden vehicle | D1 probe | `entry_visible`, `tallies`, `visible_holders`, `history_list.sql:99`, `options_get` (visible vehicles) | holds | A (`test_a_holder_sees_only_their_own_float_and_a_scoped_viewer_only_what_they_may`, `test_the_tallies_group_the_visible_entries_by_window`, `test_a_scoped_viewer_sees_petty_cash_history_...`, `test_the_options_follow_the_rights_and_the_date`) |
| C28 | Every `{id}` route answers 404 for a foreign, removed or out-of-scope id | D1 probe | `visible_entry.sql:44-46` | holds | A (`test_an_entry_of_another_organization_is_never_read`; the steps tests) |
| C29 | Business dates from `tenancy.business_date(p_now)`; no `now()` in `55_pettycash` | D5 probe | grep | holds | A (sweep, section 8) |
| C30 | Week start per organization | D5 probe, PC-21 | `revenue.week_start` in `overview_get.sql:53` | holds | A (`test_a_week_starts_on_the_organizations_first_day`) |
| C31 | Reasons and snapshots equal the .NET text (`d MMM yyyy`, PascalCase keys) | D5 probe, PC-25, PC-26 | `describe.sql`, `entry_snapshot.sql` | holds | A (`test_the_subjects_and_the_snapshot`) |
| C32 | `SECURITY DEFINER` only on `api.*`, each with `SET search_path`; `EXECUTE` revoked from `PUBLIC` on every function; no dynamic SQL | D6 probe | the 42 files | holds | A (sweep; `db verify` `check_api_routine_properties`, `check_no_dynamic_sql`) |
| C33 | A reviewed `.down.sql`; forward-only, checksummed | D6 probe | `0012_pettycash.down.sql` | holds | B (`test_migrate` rows; read: the change-log constraints come back `NOT VALID`, as documented) |
| C34 | Every query has its index | D6 probe | `0012` four indexes; `docs/04` 6.2 | holds for the predicates on reading; no `EXPLAIN` at 10x | unproven (C) |
| C35 | No SQL feature newer than PostgreSQL 16 | D6 probe | grep for `MERGE`, `NULLS NOT DISTINCT`, `ANY_VALUE`, `JSON_TABLE`, `uuidv7`, `RETURNING OLD`, `pg_input_is_valid` | holds | A (none; cluster 16.15 measured) |
| C36 | Paging capped in Python and SQL | D7 probe | router bounds; `tenancy.check_page` | holds | A (`test_the_list_checks_its_filters_in_order`; revenue-17's `test_integers_beyond_their_column_types_are_refused_before_the_routine`) |
| C37 | No PII in logs | D8 probe | no log call in the 08 Python files | holds | A (grep) |
| C38 | `POST /approve` with `{"entries": null}` answers as .NET does | D4 probe, PC-33 | `ApprovePettyCashEntries.entries` was not nullable | **fails** (V-D4-1, minor, fixed) | A after the fix |
| C39 | No `skip`, `xfail`, `sleep`, bare `except` in the 08 tests; no `TODO` or plan ids in the 08 code | D10, invariant | grep | holds | A |
| C40 | Every `Raises:` code of the 13 routines has a test | D10 probe | the 08 test modules | holds (71 codes; only `not_member` and `time_zone_invalid`, both `via tenancy.*`, are tested in the tenancy modules) | A |
| C41 | README status row 08, `docs/13` q68 and q72, `docs/04` to `docs/06` current | D11 | as named | holds after this session's corrections (`docs/05` 4.9, `docs/04` 6.2, README row 08) | A |

## 3. Findings

| id | mode | claim attacked | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| V-D3-1 | falsification, pre-mortem | "Writes lock in this order: the float(s), then the entry rows, then whatever `record_change` takes" (`docs/05` 4.9); the build report's "lock order of every write: 1 the float, 2 the vehicle and item `FOR SHARE`, 3 the entry; no pair is taken in opposite orders" | `api.pettycash_entry_create` took the vehicle and item `FOR SHARE` (`check_expense`, old line 114) before `lock_float` (old line 117); `api.pettycash_entry_update` takes the float, the entry, then the same shares (`:59`, `:97`); the code did not have the order both documents describe | the lock sweep (section 8); the new test `test_a_create_a_change_and_a_vehicle_write_on_one_float_never_deadlock` (four connections: the float held, a change waiting on it, a create queued behind the change holding the shares, a retirement of their vehicle waiting on the create) | my first narrative (a vehicle write queued `FOR UPDATE` behind the create's share closes a cycle with the change's later `FOR SHARE`) was refuted by running the test against the old create (`zz_failfirst_check.py`, 17:28, old body installed with `CREATE OR REPLACE` in the test database): the three writes completed with no error, because a `FOR SHARE` compatible with the row's current share lock is granted without taking the tuple lock, so it never queues behind a waiting updater. The first run's `55P03` on the change (17:17) was my harness holding the float past the 2 s `lock_timeout`, not the code | survives, minor (the documented lock order was not the code's; no failure reachable through the pair) | fixed by aligning the code with the documents: `lock_float` moves before `check_expense` in `pettycash_entry_create.sql` (one order on every path); `docs/05` 4.9 create steps renumbered and the lock sentence extended; the test above pins that a create, a change and a vehicle write on one float complete (it passes on the old order too, so it guards the behaviour, not the fix: grade B) |
| V-D4-1 | falsification | "every scenario of `PettyCashTests` with the same assertions" (prompt D4); PC-33 `{entries: null}` -> "Choose the entries to approve." | `ApprovePettyCashEntries.entries` was `list[...]` with an empty default, so `{"entries": null}` was a binding 400 naming the field, where .NET (`input.Entries ?? []`) answers the petty-cash sentence | api `test_a_null_entries_list_asks_for_the_entries_as_an_empty_one_does`: failed first at 17:17 (`detail` was the binding sentence), passes after the fix (16 passed, 17:28) | released clients send a list; only a hand-written body reaches it | survives, minor (wrong message text) | fixed: the field is nullable, the router passes `body.entries or ()`; the test above |
| V-D11-1 | Socratic | "`updated_at` trigger not used" (prompt 08 D1) | `0012` creates `touch_updated_at` on `pettycash.entries`; `docs/04` 6.2 did not say so | `0012_pettycash.sql:103-104`; `src/xcode_api/db/verify.py:597-627` requires it on every table with the column | the routines always set `updated_at = p_now`, so the trigger never fires (it acts only when a write leaves the column unchanged); the prompt's wording predates the verify check | survives, note | `docs/04` 6.2 gains one bullet; the prompt is history |
| V-D11-2 | falsification | the build report's D3 narrative ("no pair is taken in opposite orders") | see V-D3-1: the report described an order the code did not have | `docs/audit/2026-10-12-build-08.md` 6.2 D3 | its conclusion (no deadlock) holds for the reason in section 6, not for the reason it gave | survives, note (a report claim) | recorded in section 9; the code and `docs/05` now match the report's order |
| V-D4-2 | falsification | the same prompt D4 claim for `POST /approve-day` with `to` and no `date` | Python answers `pettycash_range_both`; .NET binds a missing `date` to 0001-01-01 and answers "Choose at most 367 days." | `pettycash_day_approve.sql:47`; `PettyCashUseCases.cs` `Range()` | a body with `to` and no `date` is not one a client sends; both are 400 | survives, note (parity on a nonsense input) | recorded; no change (the Python sentence names the real mistake) |
| V-D4-3 | falsification | the OpenAPI document "lists the same status codes" (D4 probe) | every operation in `xcode-api openapi` carries a 422 entry (84 of 97 operations, app-wide), while validation answers 400 | `openapi.json` in my scratchpad | FastAPI's default response for request validation; not 08's | survives, note (app-wide, outside 08) | for prompt 09 or 11: drop the default 422 in the app factory |

## 4. Per domain

### D1 Tenancy and authorization
- Every tenant routine calls `tenancy.enter_organization` first: holds (13 of 13; `db verify` `check_tenant_routines_enter_organization`).
- RLS and `tenant_isolation` on `pettycash.entries`: holds (`0012:106-110`; `test_tenancy_isolation` 97 and `test_grants` 79 on the 13:00 run).
- Scoped viewers: holds (C27). The hardest attacks: a `view_all` reviewer scoped to one company reading a hidden vehicle's spending through the dashboard's `approvals` card, the overview's figures with `holderId`, and the history list; all three are cut by `entry_visible` or the history CASE line, and the tests named in C27 assert the cut rows.
- `{id}` routes answer 404 for a foreign id: holds (C28).
- Anti-escalation: n/a (no grants in 08).
- Permission catalogue parity: n/a for 08 (D2's `0009`); the 20 petty-cash keys are read by name in the routines and pinned by `tests/unit/test_permission_keys.py`.

### D3 Data integrity and concurrency
- Version bump and compare with `current`, two connections: holds (C22).
- Lock order: **fails** as documented, V-D3-1, fixed by alignment. The list after the fix: create `lock_float` (membership `FOR NO KEY UPDATE`) -> `check_expense` (`FOR SHARE` vehicle; `FOR SHARE OF i, c`) -> `record_change` (organizations `UPDATE`); update, approve, send back, reject, reopen, remove `lock_float` -> entry `FOR UPDATE NOWAIT` -> (update only) the shares -> `record_change`; ticked and day approval: floats `ORDER BY holder_id` -> entries (`FOR UPDATE` by id) -> `record_change`. Setup vehicle and item writes: the row `FOR UPDATE` (after a company `FOR SHARE` in vehicle create, update and restore) -> `record_change`. No pair is taken in opposite orders now; the foreign-key `KEY SHARE` on the membership does not conflict with `NO KEY UPDATE`; the shares `check_expense` takes are compatible with each other, so even the old order could not cycle (section 6).
- Replays by unique constraint, no second change-log row, two racing first writes: holds (C8, C23).
- Append-only by grant: n/a for `entries` (updated by design); `change_log` and `audit_events` are tenancy's.
- Money: holds (C24).
- One call, one transaction; retries for reads only: holds (C25).

### D4 Contract parity
- Routes: holds (C18; .NET 12 routes, `docs/06` 13, routers 13, OpenAPI 13; the export is 08b's by the register).
- Bodies: holds (C17; `rejected`, `rejectReason`, `reopenReason`, `canSendBack`, `canReject`, `canReopen` and the new permission flags appended last, DEC-29).
- Errors: holds for `current`, `balanceAfter`, `earliest`, the titles `This entry has changed.` and `This entry was changed by another save.`; **fails** for `{"entries": null}` (V-D4-1, fixed); a ticked entry without `id` is a binding 400 where .NET answers 404 for `Guid.Empty` (note, no change).
- Clients: holds (`packages/shared/src/pettyCash.ts` words `cash`/`expense`/`credit`, `waiting`/`approved`/`sentBack`; the mobile queue reads `{id, version}`, `current` and `detail`).
- Drift: holds (no commit since 2026-10-11; the .NET files are dated 10-10 22:31; register row 7 closed by 08's D0).

### D5 Domain rules and time
- Business dates and `p_now`: holds (C29).
- Week start, month ends, ten-year window: holds (C30; `date_trunc('month', v_today)` for the float card; `p_today - 3650` as .NET `AddDays(-3650)`; 29 February n/a, nothing in 08 adds months).
- Reasons and snapshots: holds (C31).
- Normalisation: n/a (texts are trimmed by `tenancy.trim_text`, the .NET `Trim()`).
The hardest attacks: a `date` of `0001-01-01` on a change (refused by `check_line` before anything is read), a `period` of `" week "` (trimmed, a week), and a range of exactly 367 days starting 3650 days ago (accepted, as .NET).

### D6 Database craft
- `db verify` exit 0: holds (21 of 21 on `xcode_v08f_verify`, a clone of my template, 17:29, dropped after); each check shown to fail on a database built to break it: unproven for the 21 checks in general (`tests/db/test_structure.py` covers them; revenue-17's rename fix makes the missing-schema case pass again), not re-proven here.
- `SECURITY DEFINER`, `search_path`, `EXECUTE` revoked, no stale overload: holds (C32; no signature changed in 08).
- No dynamic SQL: holds.
- Migrations: holds (C33).
- Indexes: unproven at scale (C34).
- Version: holds (C35).
- Template fingerprint: holds. At 17:25 `template_fingerprint(db/)` gave `4b6cf4cc31b9ff46...9dd314` and the comment on `xcode_template_v08f` read `xcode test template 4b6cf4cc31b9ff46...9dd314`; `pg_stat_activity` showed no other session on the template or on a `test_*` database of mine. The template was first built at 17:11 and rebuilt by the harness at 17:14 and 17:17 as D4's landing (17:11 to 17:13) and my create change (17:16) changed the fingerprint; the helpers module may have run on the pre-D4 build.

### D7 Performance and scale
- Budgets asserted: holds (C20).
- `EXPLAIN` at 10x: unproven (not run; the builder recorded it for prompt 09, 08:V-D7-2).
- No query per row in a loop: note. Ticked approval runs `visible_entry` and `check_version` per id (at most 100) and `pettycash.log` per approved entry; day approval runs `log` per entry; both by design (one change-log row per entry, as .NET) and bounded (100; a period of 367 days, 08:V-D7-1).
- Connections and threads: n/a (nothing new).
- Hot rows: note. Every petty-cash write updates the organization row (`record_change`), as every logged write does; a burst of captures and petty-cash saves in one organization serialises there, the documented serialisation point (`docs/05` 1.5) and .NET's `SettingsVersion`.
- Paging capped: holds (C36).

### D8 Reliability and operability
- Logs: holds (C37). Retries: holds (reads only). `X-Request-ID`: holds (the problem bodies carry `requestId`; `ok()` asserts the header in every api test).
- Settings: n/a (08 adds none). The mandatory `XCODE_*` sweep found names outside 08: `docs/08-operability.md` lacks `XCODE_DATABASE_POOL_MAX`, `XCODE_EMAIL_FROM`, `XCODE_EMAIL_PORT`; `tests/unit/test_settings.py` lacks `XCODE_DATABASE_ALLOW_REQUIRE_SSLMODE`; `.env.example` and `docs/08` name `XCODE_AUTH_AUDIENCE`, `XCODE_AUTH_ISSUER`, `XCODE_METRICS_ENABLED`, `XCODE_OPENAPI_ENABLED`, `XCODE_SHUTDOWN_GRACE_SECONDS` that `settings.py` builds from field names. For the next verify of prompt 00 or 09.
- CLI and audit rows: n/a.

### D9 Hosting and supply chain
n/a: 08 adds no dependency, setting or deployment step. CI (`.github/workflows/xcode-api.yml`, PostgreSQL 18) is untracked and has never run; the cluster here is 16.15.

### D10 Tests as evidence
- No fake of the capability under test: holds (the parity test runs the shared cases against the routines and the fake).
- Sweeps: holds (C39).
- Would a wrong implementation pass? For the five invariants: a visibility check that ignored the vehicle scope fails `test_an_entry_is_visible_by_float_and_by_the_scope_of_its_vehicle` and `test_a_holder_sees_only_their_own_float_...`; a reviewer rule that let the recorder approve fails `test_who_may_review_an_entry` and the approve steps test; a float guard read outside the lock fails `test_two_saves_on_one_float_run_one_after_the_other`; a version check without `current` fails `test_a_stale_version_is_a_409_with_the_entry_as_the_list_serves_it`; a create that skipped `check_expense` fails `test_an_expense_is_checked_against_the_vehicle_and_the_item_vehicle_first`. The new lock test does not distinguish the create's old order (section 6).
- Every `Raises:` code tested: holds (C40).
- Full run: holds (queue row 7, every 08 module green; section 12).

### D11 Documents and prompts
- Doc clauses match the code: holds after `docs/05` 4.9 (create steps, lock sentence) and `docs/04` 6.2 (the trigger) were corrected; `docs/06` 2.11, `docs/15` B19 and the inventory read true against the code.
- README status and `docs/13`: holds (row 08 now records this verification; q68 and q72 current).

## 5. Per mode

### Assumptions inventory

| Assumption | Where stated | Enforced by |
|---|---|---|
| "Every write takes the float before it reads a balance" | `lock_float.sql:2`, `docs/05` 4.9 | `lock_float` before `guard_float` in create and remove; `visible_entry(lock)` in the rest |
| "The holder never changes" (so the unlocked read of the holder in `visible_entry` is safe) | `visible_entry.sql:2` | `pettycash_holder_change` in update; no routine writes `holder_id` |
| "Writes lock in this order" | `docs/05` 4.9 | nothing for the create's shares (V-D3-1); now the code |
| "A null `p_expected_version` is a conflict" | `check_version.sql:21` | `IS DISTINCT FROM` |
| "`round(numeric, 2)` is half away from zero" | `docs/04` 6.2 | PostgreSQL semantics; `test_the_total_is_units_times_amount_rounded_half_away_from_zero` |
| "`total` cannot overflow `numeric(14,2)`" | implicit | `check_line` refuses `abs(total) > 999999999999.99` first |
| "The organization's time zone decides the business date" | `tenancy.business_date` | every routine passes `p_now` |
| "Only approved, non-removed expenses post" | PC-31 | `vehicle_postings.sql:28-30` |
| "`FOR NO KEY UPDATE` does not block the change log's foreign-key check" | `lock_float.sql:2` | PostgreSQL lock modes; `save_person.sql:127` records the same reasoning |
| "A later `FOR SHARE` queues behind a waiting `FOR UPDATE`" (mine, in the first V-D3-1 narrative) | nowhere | false: a compatible share is granted without the tuple lock (the fail-first run, section 6) |

### Falsification table

| Claim | Falsifier looked for | Result | Grade |
|---|---|---|---|
| lock order as documented (C21) | the create's first lock | found (the shares), aligned | B |
| a deadlock through the vehicle row | one of three writes aborted with `40P01` | not found: the scenario against the old create completed | A (refuted) |
| `{entries: null}` parity (C38) | a binding 400 | found, fixed | A |
| self-approval impossible (C27 area) | a path where the recorder or holder approves | none (single, ticked, day all refuse; `flags` agrees) | A |
| foreign id replay (C9) | a create under another organization's id reading its row | none (RLS and the organization filter) | A |
| float guard raced (C22) | two cash removals below zero | none (`test_two_saves_on_one_float_run_one_after_the_other`) | A |
| a rejected expense still posting or counting (DN-B19-7) | `vehicle_postings`, `effect`, the figures | none (`test_a_rejected_expense_leaves_the_balance_the_figures_and_the_report_until_reopened`) | A |
| `q` wildcards (PC-28) | `%` matching everything | none (escaped) | A |
| the trigger stamping `now()` on a write (C5) | an `UPDATE` that leaves `updated_at` unchanged | none; every routine sets it | A |

### Pre-mortem narratives (ranked)
1. An organization with 40 floats approves a 367-day period and the request takes seconds, one change-log row per entry under the organization row lock, while captures queue behind it. Early sign: statement time on `pettycash_day_approve`. Inverted: nothing bounds a period approval but the period; recorded (08:V-D7-1, prompt 09).
2. A holder with `reopen` reopens an approved expense from last quarter and edits it, and the vehicle report changes for a closed month. Inverted: the back-dating limit (`check_writable` on reopen and on both dates of an edit) is what stops it; the organization must set a limit (DEC-11: existing people have none), question 65.
3. The list's `ILIKE` over five columns at 100k entries takes seconds. Inverted: no index serves the text search; the builder recorded the 10x `EXPLAIN` for prompt 09.
4. Three writes on one float and one vehicle at the same moment and one answers 500. Inverted: this needed an opposite-order pair that waits; the pair existed on paper and did not wait (section 6); now it does not exist.

### Red-team vectors
| Persona | Vector | Defence |
|---|---|---|
| Clerk in tenant A | `POST /entries` with an id from tenant B to read or replay it | a new entry in A (`test_an_id_another_organization_uses_is_a_new_entry_here`) |
| Clerk, scoped | `GET /entries?holderId=<other>` and `overview?holderId=` | 404 unless the holder is visible |
| Clerk, scoped with `view_all` | the dashboard approvals card, the figures, history | cut by `entry_visible` and the history line |
| Dismissed employee | replay queued creates | `enter_organization` refuses before the replay check |
| The gamer | approve own spending, by ticking or by day | `authorize_review`; day approval skips own and recorded |
| The gamer | a refund (negative expense) to raise the float | waits for a reviewer; counts, as .NET (DN-B19-11) |
| The gamer | delete an approved expense to drop a cost from the report | needs `delete_approved` and a reason; logged with the snapshot |
| The gamer | edit after approval | refused (`pettycash_change_decided`); reopen needs its right and leaves a reason |
| The gamer | a reviewer edits then approves (q72 a); an issuer funds own float (q72 b); split under the limit (q72 c) | recorded for the owner, parity with .NET |
| The calendar | a range of 367 days ending after today | allowed (the last day may be after today, as .NET) |
| Hurried DBA | `.down.sql` on a filled schema | the change-log constraints come back `NOT VALID`; rows stay |

### Dialectic
| Decision | Strongest counter | Verdict | Confidence |
|---|---|---|---|
| DEC-21 sent back as a note, not a status | a status is what the clients show and .NET stored | keep: the wire word is unchanged and the notes store it on the waiting entry; status 3 stays unused so .NET data cannot be misread | high |
| DEC-23 cash and credit notes never edited | the inventory's PC-16 replay for a cash change is lost | keep: delete and re-record keeps both amounts in the log; the change route refuses them explicitly | high |
| DEC-24 reopen needs only its right | a holder with `reopen` can reopen their own approved expense | keep with the back-dating limit; the owner decides who holds `reopen` | medium (q72 territory) |
| align the create with the documented order (V-D3-1) versus correct the document to the create's order | the old order held the float for less time and could not deadlock either | keep the alignment: one order on every path is what the next reader and `docs/05` assume, and the cost is a share read under the float | high |
| `db verify` requiring the trigger versus the prompt's "not used" | a trigger that never fires is dead weight | keep the trigger: the check is uniform across schemas; the document now says why | high |

## 6. Conceded

| Challenge | Guard that defeated it |
|---|---|
| a deadlock between a create (shares, then the float), a change (the float, the entry, then the shares) and a vehicle write queued `FOR UPDATE` behind the create's share (my first V-D3-1 narrative, 17:05) | the scenario run against the old create completed all three writes (`zz_failfirst_check.py`, 17:28, old body installed by `CREATE OR REPLACE` in the test database; the diagnostic at 17:24 showed the retirement waiting on the create and the create holding the share): PostgreSQL grants a `FOR SHARE` compatible with the row's share lock without taking the tuple lock, so the change never queues behind the waiting updater and no cycle closes; the `55P03` of the 17:17 run was the test harness (its queue check watched the wrong blocker and held the float past the 2 s `lock_timeout`), corrected at 17:28 |
| history hides cash and credit rows from scoped viewers while the list shows them | parity: .NET PC-17 versus PC-32 are the same two rules |
| the float guard on a change (the .NET `CheckFloat(delta)`) is missing | cash and credit notes cannot be changed (DEC-23) and an expense never trips the guard |
| day approval locks floats from a first query and approves from a second, so a float of an entry inserted between them is not locked | approval does not move money (a waiting expense already counts), so the float guard elsewhere reads the same balance |
| `visible_entry` reads the holder without a lock before locking the float | the holder never changes |
| `check_version` before the status checks in ticked approval (a stale rejected entry answers 409 before `not_waiting`) | the documented order and .NET's |
| `guard_float` is `STABLE` while it raises | raising is allowed in a stable function; it reads only |
| `NOT p_permissions && ARRAY[...]` in `authorize_remove` parses as `NOT (a && b)` | PostgreSQL precedence: `NOT` is lower than any other operator |
| the OpenAPI 422 entries | app-wide default, outside 08 (V-D4-3 note) |
| `Guid.Empty` for `holderId` on an expense ("Spending is recorded on your own float." in .NET) | Python answers `pettycash_holder_not_holder`; both 400, no client sends it |

## 7. Fixes

| Finding | Files | Test |
|---|---|---|
| V-D3-1 | `db/routines/55_pettycash/pettycash_entry_create.sql` (`lock_float` before `check_expense`; a header note); `docs/05-routines.md` 4.9 (create steps 6 to 9; the lock-order sentence) | `tests/db/test_pettycash_routines.py::test_a_create_a_change_and_a_vehicle_write_on_one_float_never_deadlock`: passes alone (17:29) and in the module (80 passed, 2:38, 17:31); it also passes against the old order (17:28), so it pins the behaviour and not the alignment (grade B); the alignment itself is read in the file |
| V-D4-1 | `src/xcode_api/http/schemas/pettycash.py` (`ApprovePettyCashEntries.entries` nullable); `src/xcode_api/http/routers/pettycash.py` (`body.entries or ()`) | `tests/api/test_petty_cash.py::test_a_null_entries_list_asks_for_the_entries_as_an_empty_one_does`: 1 failed at 17:17 (`detail` was the binding sentence), 16 passed at 17:28 |
| V-D11-1 | `docs/04-schema.md` 6.2 (one bullet) | document |

## 8. Commands and outputs

Measured in this session:
- `python --version`: 3.13.2; `SELECT version()`: PostgreSQL 16.15 on port 5433; CI image `postgres:18`, workflow untracked (never ran).
- `git log --since=2026-10-11 -- apps/api tests/api`: empty; the .NET petty-cash files are dated 2026-10-10 22:31; the inventory was corrected 2026-10-12.
- Free memory 282 MB at 16:10 (D4's run live), 1 162 MB at 17:05, 1 263 MB at 17:21; one `-n 0` job of mine at a time beside D4's, template `xcode_template_v08f` (private).
- Baseline and fail-first (one module at a time, `-n 0`, live tree; the two new tests were appended at 17:14 before their modules started): `test_pettycash_helpers.py` 63 passed (2:29); `test_pettycash_routines.py` 79 passed, 1 failed (the new lock test, on the harness flaw above, 3:07); `test_petty_cash.py` 15 passed, 1 failed (the new `entries: null` test, 0:49); the petty-cash parity tests 2 passed.
- After the fixes (17:24 to 17:29): a one-test diagnostic module against the old create (removed after; its timeline is quoted in section 6); `test_pettycash_routines.py` with the uncorrected test 79 passed, 1 failed (the same harness flaw, 2:50); `test_petty_cash.py` 16 passed (0:46); `zz_failfirst_check.py` against the old create: the real test did not fail (refutation, 0:04); the corrected lock test alone: 1 passed (0:04); `test_pettycash_routines.py` with the corrected test: 80 passed (2:38, 17:31).
- `ruff check . && ruff format --check . && mypy`: all checks passed, 397 files formatted, no issues in 189 source files (17:26).
- `xcode-api openapi` (with `.env.example` in the environment): 13 petty-cash operations, 97 in all, 84 with a 422 entry.
- `db verify` on `xcode_v08f_verify` (a clone of `xcode_template_v08f`): exit 0, 21 of 21 `ok` (17:29; the clone dropped).
- Template: fingerprint of `db/` equal to the template's comment at 17:25 (section 4 D6).
- Sweeps: `now()`/`current_date`/`clock_timestamp()`/`random()` in `55_pettycash`: none; `EXECUTE`/`format(` in `db/routines`: none; `SECURITY DEFINER` without `search_path`: none (13 files, all `api.*`); `skip`/`xfail`/`importorskip`/`sleep(`/bare `except` in the 08 tests: none (the sweep of `tests/` as a whole hits `test_structure.py:227,263` skips needing a superuser, and sleeps in `test_auth_contract.py`, `test_pin_hasher.py`, `test_mail_queue.py`, `support/client.py`, all outside 08); `TODO`/`FIXME`/`XXX`/`HACK`/plan ids in `src`, `db`, `tests`: none; log calls with bodies, phones, PINs or tokens in the 08 files: none; `XCODE_*`: section 4 D8; row locks across `db/routines`: 44 statements listed (`pg_advisory_xact_lock` in `20_identity`; `FOR UPDATE` in identity, tenancy and setup writes; `FOR NO KEY UPDATE` on memberships in `people_*`, `save_person` and `lock_float`; `FOR SHARE` in vehicle create, update and restore, `revenue_capture` and `check_expense`; `FOR UPDATE NOWAIT` in `revenue_capture` and `visible_entry`; `FOR UPDATE` in `pettycash_day_approve`).
- Full run: queue row 7 (D4's, shared), template built 17:35 from the tree with the fixes; ended 19:31, counts in section 12.

## 9. Regressions and misses against earlier audits

Read after the pass: `docs/audit/2026-10-12-build-08.md` (the builder's challenge pass) and the board's 14:20 and 15:26 entries.
- Regressions: none. Every finding the builder recorded as fixed (08:V-D3-1 `check_expense` locks, 08:V-D5-1 the null bucket, 08:V-D6-1, 08:V-D10-1 to 5, 08:V-D11-1) is still in place and its test still runs.
- Missed: the create's lock order against the documents (V-D3-1). The builder's D3 narrative states the order "the float, then the vehicle and item shares, then the entry" for every write and concludes "no pair is taken in opposite orders"; the create it shipped took the shares first. The conclusion was right for a reason the narrative does not give (compatible shares never queue behind a waiting updater). Also missed: `{entries: null}` (V-D4-1) and the trigger sentence (V-D11-1).
- The builder's open item (`test_structure::test_verify_reports_a_missing_schema`) and the optional bounds test were done by revenue-17 at 16:16 (board 16:52).

## 10. For the user

- Question 72 (separation of duties: a reviewer who edits then approves, an issuer funding their own float, splits under the limit) stays the owner's: the behaviour equals .NET, and the fix is a policy (who holds `pettycash.edit` and `pettycash.issue`, a per-day limit) rather than code. Recommendation: refuse approval by the last editor (cheap, no client change) and leave the other two to the rights.
- Question 65 (the back-dating limit for existing people): without a limit, `reopen` and `delete_approved` reach any past month. Recommendation: 7 days for everyone at cutover, as new people get.

## 11. Where to resume

Open until the shared full run of queue row 7 ends (about 20:05): the coordinator adds section 12 with the 08 modules' counts (`test_pettycash_helpers.py` 63, `test_pettycash_routines.py` 80, `test_petty_cash.py` 16, the petty-cash parity tests, `test_constraints`, `test_schema_structure`, `test_tenancy_isolation`, `test_enum_parity`, `test_message_codes`, `tests/unit`). If they are green, section 1 becomes "pass with findings", C21's full-run clause and D10's full-run probe become `holds`, and README row 08 drops "fail until its modules pass on the shared full run of queue row 7".

## 12. Shared full run (added by the coordinator, revenue-d5 [b49167], 2026-10-12 20:45)

Queue row 7 (D4's full run, shared with this report): `pytest -n 2 -q -p no:cacheprovider -rfE --junitxml` from the live tree on a fresh `xcode_template_d4full` built at 17:35 (this session's fixes in since 17:25), 17:35 to 19:31 (1:55:20): 5733 passed, 3 failed, 0 errors, 0 skipped. Log and JUnit XML are in revenue-d5's scratchpad (`full/full.log`, `full/full.xml`). The 3 failures are all in `tests/db/test_gateway.py` and are 07b D1's (the test lags D1's `domain/identity.py` types); none is 08's.

Section 11's list:
- `tests/db/test_pettycash_helpers.py` 63 passed; `tests/db/test_pettycash_routines.py` 80 passed; `tests/api/test_petty_cash.py` 16 passed.
- The petty-cash parity tests of `tests/db/test_fakes_match_routines.py` (`test_the_pettycash_fake_is_a_pettycash_repository`, `test_the_pettycash_fake_answers_as_the_routines_do[keep_a_float]`) passed; the module 663 passed.
- `test_constraints` 59, `test_schema_structure` 39, `test_tenancy_isolation` 97, `test_enum_parity` 27, `test_message_codes` 6, `tests/unit` 945 passed.
- Also green: `tests/db/test_structure.py` 14 (the builder's open item, `test_verify_reports_a_missing_schema`, passes) and `test_grants` 77.

Every listed module is green, so section 1 is now **pass with findings**, D10's full-run probe is `holds`, and README row 08 no longer says "fail until". C21 has no full-run clause (its verdict rests on the fix and section 6), so it stays as written.
