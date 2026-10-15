# Build report part: prompt 08b, stream E, central expenses and shared purchases (2026-10-13)

Session revenue-a8 [c5ed4b], stream E of the 08b build (Part C of the approved plan
`~/.claude/plans/cached-baking-blanket.md`); coordinator revenue-17 [60bb7c], who consolidates
this part into `docs/audit/2026-10-13-build-08b.md` after the shared full run. Scope: B2.2
(`57_expenses`), B2.5 (`55_pettycash` shared purchases), B2.6 (`history_list`), the stream's
parts of B3, B4 and B7, and the ledger's EXPLAIN evidence of B8. No helper agents; every file was
written here. Stream R reuses `expenses.ledger_rows` and `expenses.check_ledger` for E02.

## 1. Drift check against .NET

The D0 inventory (`docs/inventory/inventory-expenses-reports.md`, 2026-10-12) read `HEAD` 493bf82
plus the working tree. Re-checked at 10:05 today: no central-expense file changed since.

| File | Modified |
|---|---|
| `apps/api/Domain/CentralExpense.cs` | 2026-10-09 18:26:59 |
| `apps/api/Application/CentralExpenseUseCases.cs` | 2026-10-10 22:29:31 |
| `apps/api/Application/CentralExpenseContracts.cs` | 2026-10-09 18:59:27 |
| `apps/api/Api/CentralExpenseEndpoints.cs` | 2026-10-10 22:30:44 |
| `apps/api/Infrastructure/CentralExpenseRepository.cs` | 2026-10-09 19:00:38 |
| `tests/api/CentralExpenseTests.cs` (both classes) | 2026-10-09 19:11:50 |
| `packages/shared/src/expenses.ts` | 2026-10-09 18:38:24 |

.NET has no petty-cash group: the shared purchase of B2.5 is a v2.3 design addition, so
`docs/05` 11.6 and `docs/06` 2.12 are its only source.

## 2. Checklist

### D2 Routines

| Item | Done | Where | Test |
|---|---|---|---|
| B2.2 `check_date` (future; more than 3 650 days back) | yes | `57_expenses/check_date.sql` | `test_the_record_steps_answer_in_their_order` |
| B2.2 `check_purchase`: rows of CE-5 in sent order; one vehicle as typed; equal amounts take `units / n` when the share has at most three decimals and costs the amount exactly, else one unit at each amount; amounts read from the jsonb as text (a third decimal refused, not rounded) | yes | `check_purchase.sql` (`expenses.check_purchase`, plpgsql STABLE, the casts guarded by `CASE`) | `test_a_split_never_loses_or_invents_a_cent` (table incl. 100 / 3 and refunds), `test_a_purchase_amount_sent_as_a_json_number_is_read_exactly`, `test_the_purchase_checks_run_in_their_order`, `test_fifty_vehicles_share_one_purchase_and_fifty_one_are_refused` |
| B2.2 `row_document` (the row as the ledger lists it, or null) | yes | `row_document.sql` | `test_the_stale_writer_on_a_second_connection_gets_the_version_conflict_with_current`, `test_a_conflict_on_a_row_the_ledger_cannot_list_carries_a_null_current` |
| B2.2 `describe`, `entry_snapshot`; reasons of CE-15 byte for byte through `tenancy.fmt_money`; audit `expenses.recorded`; section `centralexpenses`, the row's vehicle | yes | `describe.sql`, `entry_snapshot.sql`, `log.sql` | `test_the_snapshot_keeps_the_dotnet_keys_in_their_order`, `test_a_change_is_logged_with_the_values_after_it`, `test_removing_takes_the_row_out_of_every_list_and_logs_the_reason`; API `test_one_vehicle_records_one_row_and_its_log` |
| B2.2 `expenses_entry_create`: the advisory lock on `hashtextextended('xcode.expense_purchase:' \|\| org \|\| ':' \|\| id, 0)` before the retry lookup; lookup by `group_id = p_id OR id = p_id`; `unique_violation` only a backstop | yes | `expenses_entry_create.sql`, `retried.sql` | `test_two_connections_recording_one_purchase_make_one_set_of_rows`, `test_a_retried_record_answers_the_rows_it_made_whatever_the_body`, `test_a_purchase_id_another_purchase_or_person_holds_is_a_conflict`, `test_an_id_another_organization_uses_is_a_new_purchase_here` |
| B2.2 `expenses_entry_update` (CE-10, CE-11, CE-12) | yes | `expenses_entry_update.sql`, `check_vehicle.sql`, `check_item.sql` | `test_the_change_steps_answer_in_their_order`, `test_a_new_item_units_or_amount_leaves_the_group_and_a_new_date_vehicle_or_note_keeps_it`, `test_capture_alone_changes_only_its_own_rows_of_the_day_and_correct_any` |
| B2.2 `expenses_entry_remove` (CE-13) | yes | `expenses_entry_remove.sql` | `test_the_remove_steps_answer_in_their_order`, `test_removing_takes_the_row_out_of_every_list_and_logs_the_reason` |
| B2.2 the ledger: one statement over central rows, approved petty-cash expenses and `scheduled_runs` state 0, each inside its window; figures over all; `total`, `amount` and the page over the `source` and `q` matches; ILIKE with `%`, `_` and `\` escaped; order day desc, source, registration `COLLATE "C"`, id; `LIMIT`/`OFFSET` in SQL | yes | `expenses_ledger_get.sql` (figures, count and page cut from `setup.fleet_postings` keys; the page's rows built through `ledger_rows.sql`, since the E-4 fix), `check_ledger.sql` | `test_the_ledger_lists_three_sources_newest_first_and_never_savings`, `test_every_page_is_the_ledger_rows_helper_cut_in_the_ledgers_order`, `test_source_and_search_narrow_the_rows_not_the_figures`, `test_pages_are_cut_in_the_ledgers_order`, `test_nothing_counts_after_the_business_date_or_outside_a_vehicles_days`, `test_the_ledger_figures_of_a_scoped_viewer_leave_out_hidden_vehicles`, `test_the_ledger_checks_its_query_in_order` |
| B2.2 `expenses_options_get` (CE-22) | yes | `expenses_options_get.sql` | `test_the_options_follow_the_rights_the_scope_and_the_date` |
| Part C: the ledger's row query as a helper R reuses; signature on the board as soon as it compiled | yes | `expenses.ledger_rows(...)`, posted 08:42; `expenses.check_ledger(...)` shared at R's request | R's `api.expenses_export_get` |
| B2.5 `pettycash_entry_create` + `p_allocations jsonb`: 2 to 50 allocations make one waiting entry per vehicle sharing the group, through `expenses.check_purchase`; the retry key is the group; the float lock before the vehicle and item checks | yes | `55_pettycash/pettycash_entry_create.sql` | `test_a_shared_purchase_is_one_entry_per_vehicle_and_recounts`, `test_a_shared_purchase_follows_the_purchase_rules_and_only_an_expense_takes_one` |
| B2.5 `pettycash_entry_update`: a new item, units or unit amount nulls the four group columns | yes | `pettycash_entry_update.sql` (also refuses a part moving onto a vehicle its purchase has) | `test_a_shared_purchase_is_one_entry_per_vehicle_and_recounts` |
| B2.5 `entry_document`: `group {id, size, total, units, unit_amount}`, `size` counted live over parts not removed and not rejected | yes | `entry_document.sql` | the same test (size 3, 2 after a reject, 1 after a removal; a rejected part keeps its group) |
| B2.5 `pettycash_options_get`: vehicles gain `fleet_number` | yes | `pettycash_options_get.sql` | API `test_a_shared_expense_is_one_entry_per_vehicle_on_the_wire`, `test_the_options_and_dashboard_follow_the_rights` |
| B2.6 `history_list`: `centralexpenses` by vehicle, `reports` for whoever sees everything | yes | `30_tenancy/history_list.sql` | `test_central_expense_and_export_rows_follow_the_scope` |

### D3 Domain, ports, gateway, fakes

| Item | Done | Where | Test |
|---|---|---|---|
| `domain/expenses.py`: source, ledger row (id `str`), group, figures, ledger, options, allocation, the three commands, `ExpenseRecorded`, `ExpenseSaved`, the two queries | yes | `src/xcode_api/domain/expenses.py` | mypy; the parity test |
| `ExpenseExportQuery` | R's | R keeps every export query in `domain/reports.py` (its 08:51 board note) | R's tests |
| `domain/pettycash.py`: `PettyCashCreate.allocations`, `PettyCashEntry.group`, `PettyCashGroup`, `PettyCashVehicleOption.fleet_number` | yes | `domain/pettycash.py` | parity; API tests |
| `ExpensesRepository` (appended block) | yes | `application/repositories.py` | `test_the_expenses_fake_is_an_expenses_repository` |
| gateway `ExpensesRoutines` (only `SELECT * FROM api.<name>(` literals); petty-cash `create` sends the allocations | yes | `db/routines/expenses.py` (`allocations_argument` sends amounts as decimal strings), `db/routines/pettycash.py` | `tests/unit/test_layers.py`; the routine and API tests |
| `FakeExpensesRepository` (full CE rules), `FakePettyCashRepository` allocations and group | yes | `tests/support/fakes.py` (appended block; petty-cash additions in place) | `test_the_expenses_fake_answers_as_the_routines_do` (3 runs out of 3 green) |
| `tests/support/expenses_cases.py` (one world, 08's shape) | yes | `ExpensesWorld`, case `keep_the_ledger` | the same |

### D4 Messages, use cases, HTTP

| Item | Done | Where | Test |
|---|---|---|---|
| the central-expenses message block (21 codes); `docs/06` section 3 block; 2.13.6 rows moved with a note | yes | `http/messages.py`, `docs/06-http-contract.md` | `tests/unit/test_messages.py`, `tests/db/test_message_codes.py` |
| `http/errors.py`: `("expense_version_conflict", "current"): ExpenseLedgerRowDto` | yes | `http/errors.py` | API `test_a_change_replays_an_identical_line_and_a_stale_one_is_a_409_with_the_row` |
| use cases `get_ledger`, `get_options`, `record_expense`, `change_expense`, `remove_expense` | yes | `application/expenses/` | the API tests |
| container and `main.py` (`expenses` port with its own fallback) | yes | `container.py`, `main.py` | `tests/api/test_http_plumbing.py` |
| schemas in the wire order of `docs/06` 2.13.1; petty-cash `allocations`, `group`, `fleetNumber` | yes | `http/schemas/expenses.py`, `http/schemas/pettycash.py` | key-order assertions in both API modules |
| router: E01, E03 to E06, `/setup/expenses`, tag `Central expenses`, `SetupRoute`, `{id}` as UUID, page bounds as petty cash | yes | `http/routers/expenses.py` (R appended E02) | `test_every_central_expense_route_has_its_operation_id_and_tag`, `test_the_routes_refuse_a_bad_id_no_bearer_and_a_person_without_the_rights`, `tests/api/test_openapi.py` |
| `tests/api/test_expenses.py`: every `CentralExpenseTests` scenario, budget 2 on every route, key orders, 401/403/404, reasons verbatim, `current` on the 409 | yes | 19 test functions | section 4 |
| `tests/api/test_petty_cash.py` additions: allocations, `group`, `fleetNumber` | yes | `ENTRY_KEYS` + `group`, `GROUP_KEYS`, two new tests, the options vehicle | the module |
| `tests/support/operations.json`: E01, E03 to E06 no longer planned | yes | | `tests/unit/test_endpoint_catalogue.py` |

### D7 Released clients and B8 evidence

| Item | Done | Where | Test |
|---|---|---|---|
| raw-JSON rows for the ledger and the options as `packages/shared/src/expenses.ts` reads them | yes | `tests/api/test_contract_released_clients.py` | `test_the_expense_ledger_and_options_read_as_the_web_does` |
| EXPLAIN at 10x for the ledger (5, 150, 300 rows by budget; 1 to 367 days by time) | yes | `docs/perf/expenses.md` | `test_the_ledger_reads_with_two_statements_however_many_rows` |
| `docs/05` 11 built notes, `docs/06` built notes, `docs/09` 4.2 test names as built | yes | the three documents | `test_routine_catalogue`, `test_endpoint_catalogue`, `test_messages` |

## 3. Rule id to test

`R` = `tests/db/test_expense_routines.py`, `A` = `tests/api/test_expenses.py`, `P` =
`tests/db/test_pettycash_routines.py`.

| Rule | Tests |
|---|---|
| CE-1 vehicles 1 to 50, distinct, first | R `test_the_purchase_checks_run_in_their_order`, `test_fifty_vehicles_share_one_purchase_and_fifty_one_are_refused`; A `test_a_bad_purchase_is_refused_with_its_sentence` |
| CE-2 the line as a petty-cash expense line, with the first vehicle | R `test_the_purchase_checks_run_in_their_order`; A `test_a_bad_purchase_is_refused_with_its_sentence` |
| CE-3 each amount: non-zero, two decimals, the total's sign, the sum | R `test_the_purchase_checks_run_in_their_order`, `test_a_purchase_amount_sent_as_a_json_number_is_read_exactly`; A `test_each_vehicles_amount_is_checked_exactly` |
| CE-4 total rounded half away from zero | R `test_a_split_never_loses_or_invents_a_cent` |
| CE-5 the rows of a split | R `test_a_split_never_loses_or_invents_a_cent`, `test_one_vehicle_takes_the_purchase_as_typed_and_its_id`; A `test_even_and_uneven_splits_keep_the_purchase_on_every_row` |
| CE-6 the group and the ids | R `test_one_vehicle_takes_the_purchase_as_typed_and_its_id`; A `test_even_and_uneven_splits_keep_the_purchase_on_every_row` |
| CE-7 note trimmed, blank null | R `test_one_vehicle_takes_the_purchase_as_typed_and_its_id` (`"  Two tyres "`) |
| CE-8 the retried record | R `test_a_retried_record_answers_the_rows_it_made_whatever_the_body`, `test_a_purchase_id_another_purchase_or_person_holds_is_a_conflict`, `test_two_connections_recording_one_purchase_make_one_set_of_rows`; A `test_a_retried_purchase_answers_its_rows_and_a_stolen_id_is_a_conflict` |
| CE-9 the record's order | R `test_the_record_steps_answer_in_their_order`; A `test_vehicles_dates_and_items_are_checked_and_the_options_follow_the_date`, `test_a_scoped_person_sees_nothing_outside_their_vehicles_change_log_included` |
| CE-10 the change's order, the replay | R `test_the_change_steps_answer_in_their_order`; A `test_a_change_replays_an_identical_line_and_a_stale_one_is_a_409_with_the_row` |
| CE-11 detachment | R `test_a_new_item_units_or_amount_leaves_the_group_and_a_new_date_vehicle_or_note_keeps_it`; A `test_a_new_item_units_or_amount_takes_a_row_out_of_its_group_and_keeps_the_key` |
| CE-12 capture alone versus correct | R `test_capture_alone_changes_only_its_own_rows_of_the_day_and_correct_any`; A `test_recording_alone_changes_only_its_own_rows_of_the_day` |
| CE-13 remove | R `test_the_remove_steps_answer_in_their_order`, `test_removing_takes_the_row_out_of_every_list_and_logs_the_reason`; A `test_removing_needs_a_reason_and_takes_the_row_out_of_the_ledger_and_the_report` |
| CE-14 the version and the lost race (substituted: the row lock) | R `test_the_stale_writer_on_a_second_connection_gets_the_version_conflict_with_current` |
| CE-15 the change log | R `test_a_change_is_logged_with_the_values_after_it`; A `test_one_vehicle_records_one_row_and_its_log` |
| CE-16 the snapshot keys | R `test_the_snapshot_keeps_the_dotnet_keys_in_their_order` |
| CE-17 the ledger's query checks | R `test_the_ledger_checks_its_query_in_order`, `test_the_ledger_needs_its_view_right_and_takes_any_source_word_case` |
| CE-18 the ledger's rows and figures | R `test_the_ledger_lists_three_sources_newest_first_and_never_savings`, `test_nothing_counts_after_the_business_date_or_outside_a_vehicles_days`, `test_the_ledger_figures_of_a_scoped_viewer_leave_out_hidden_vehicles`; A `test_the_ledger_lists_three_sources_newest_first_and_never_savings` |
| CE-19 the order | R `test_pages_are_cut_in_the_ledgers_order`; A `test_source_and_search_narrow_the_rows_not_the_figures_and_pages_are_cut` |
| CE-20 the search | R `test_source_and_search_narrow_the_rows_not_the_figures` |
| CE-21 the flags and permissions | R `test_capture_alone_changes_only_its_own_rows_of_the_day_and_correct_any`, `test_a_central_expense_before_the_limit_is_refused_on_record_change_and_remove` |
| CE-22 the options | R `test_the_options_follow_the_rights_the_scope_and_the_date`; A `test_vehicles_dates_and_items_are_checked_and_the_options_follow_the_date` |
| CE-23 `current` on the 409 | R `test_the_stale_writer_on_a_second_connection_gets_the_version_conflict_with_current`, `test_a_conflict_on_a_row_the_ledger_cannot_list_carries_a_null_current` |
| CE-24 instants UTC; a removed row is not found | R `test_the_snapshot_keeps_the_dotnet_keys_in_their_order` (`+00:00`), `test_the_change_steps_answer_in_their_order` (404 on a removed row) |
| CE-25 organizations apart | R `test_an_id_another_organization_uses_is_a_new_purchase_here`; A `test_another_organizations_rows_and_ids_stay_its_own` |
| B12 the back-dating limit | R `test_a_central_expense_before_the_limit_is_refused_on_record_change_and_remove` |
| shared purchases (`docs/05` 11.6) | P `test_a_shared_purchase_is_one_entry_per_vehicle_and_recounts`, `test_a_shared_purchase_follows_the_purchase_rules_and_only_an_expense_takes_one`; `tests/api/test_petty_cash.py::test_a_shared_expense_is_one_entry_per_vehicle_on_the_wire`, `::test_a_shared_expense_follows_the_purchase_rules_and_only_an_expense_takes_one` |

## 4. .NET fact to Python test

| .NET method | Python test |
|---|---|
| `RecordingOnOneVehicleSavesOneRowThatTheLedgerShowsAndTheChangeLogNames` | A `test_one_vehicle_records_one_row_and_its_log` |
| `ASplitSavesOneRowPerVehicleAndAnEvenSplitKeepsTheUnitCost` | A `test_even_and_uneven_splits_keep_the_purchase_on_every_row` |
| `BadAllocationsAndLinesAreRefusedWithTheirReason` | A `test_a_bad_purchase_is_refused_with_its_sentence`, `test_each_vehicles_amount_is_checked_exactly` |
| `VehiclesDatesAndItemsAreCheckedWhereTheExpenseIsRecorded` | A `test_vehicles_dates_and_items_are_checked_and_the_options_follow_the_date` |
| `ARetriedSaveAnswersWithTheRowsItMadeAndAnotherPersonCannotTakeTheId` | A `test_a_retried_purchase_answers_its_rows_and_a_stolen_id_is_a_conflict` |
| `ChangingBumpsTheVersionAnUnchangedSaveIsAReplayAndAStaleVersionConflictsWithTheCurrentRow` | A `test_a_change_replays_an_identical_line_and_a_stale_one_is_a_409_with_the_row` |
| `ASaveThatLosesARaceOnTheVersionIsAConflictNotAnOverwrite` | R `test_the_stale_writer_on_a_second_connection_gets_the_version_conflict_with_current` (the row lock replaces EF's token, `docs/09` 4.2) |
| `ChangingTheItemUnitsOrPriceTakesARowOutOfItsGroupButTheNoteAndVehicleDoNot` | A `test_a_new_item_units_or_amount_takes_a_row_out_of_its_group_and_keeps_the_key` |
| `RemovingNeedsAReasonAndTakesTheRowOutOfTheLedgerTheFiguresAndTheVehicleReport` | A `test_removing_needs_a_reason_and_takes_the_row_out_of_the_ledger_and_the_report` |
| `ViewersCannotRecordCapturersChangeOnlyTheirOwnRowsOfTheDayAndCorrectorsChangeAny` | A `test_recording_alone_changes_only_its_own_rows_of_the_day`, `test_the_routes_refuse_a_bad_id_no_bearer_and_a_person_without_the_rights` |
| `TheLedgerHoldsApprovedPettyCashScheduledRunsAndCentralRowsButNeverSavings` | A `test_the_ledger_lists_three_sources_newest_first_and_never_savings` |
| `SourceAndSearchNarrowTheRowsButNotTheFiguresAndPagingCountsEveryMatch` | A `test_source_and_search_narrow_the_rows_not_the_figures_and_pages_are_cut` |
| `APersonSeesNoRowsFiguresOptionsOrLogForVehiclesOutsideTheirScope` | A `test_a_scoped_person_sees_nothing_outside_their_vehicles_change_log_included` |
| `AnotherOrganizationsRowsAreNeverSeenOrChanged` | A `test_another_organizations_rows_and_ids_stay_its_own` |
| `TheOpenApiDocumentDescribesTheCentralExpenseRoutes` | A `test_every_central_expense_route_has_its_operation_id_and_tag`; `tests/api/test_openapi.py` |
| `PagesAreCutInTheDatabaseAndKeepTheOrderAcrossADayWhereAllThreeSourcesMeet` | A `test_source_and_search_narrow_the_rows_not_the_figures_and_pages_are_cut`; R `test_pages_are_cut_in_the_ledgers_order` |
| `TheLedgerReadsTheSameNumberOfTimesHoweverManyRowsThePeriodHolds` | A `test_the_ledger_reads_with_two_statements_however_many_rows` (5, 150, 300 rows) and `docs/perf/expenses.md` |
| `OneVehicleTakesThePurchaseAsBoughtAndKeepsItsId` | R `test_one_vehicle_takes_the_purchase_as_typed_and_its_id` |
| `AnEvenSplitKeepsTheUnitCostOnlyWhileUnitsDivideIntoThreeDecimals` | R `test_a_split_never_loses_or_invents_a_cent` |
| `AnUnevenSplitStoresOneUnitAtEachAmountAndTheRowsAddUpToTheTotal` | R `test_a_split_never_loses_or_invents_a_cent` |
| `ThePurchaseIsCheckedBeforeAnyRowIsMade` | R `test_the_purchase_checks_run_in_their_order` |
| `EveryChangeAndRemovalBumpsTheVersionAndTheItemUnitsOrPriceLeaveTheGroup` | R `test_a_new_item_units_or_amount_leaves_the_group_and_a_new_date_vehicle_or_note_keeps_it`, `test_the_change_steps_answer_in_their_order`, `test_removing_takes_the_row_out_of_every_list_and_logs_the_reason` |

## 5. Secure-coding checks

Skills consulted before writing: `testing-for-business-logic-vulnerabilities`,
`exploiting-race-condition-vulnerabilities`, `exploiting-sql-injection-vulnerabilities` (the
plan's gate for this stream). The new routes were also checked against the endpoint rows of the
gate (object- and function-level authorization, mass assignment) by reading and by the tests
below. Nothing offensive was run against any host; every probe ran on the 5433 test cluster.

| Check | Applied | Evidence |
|---|---|---|
| money computed by the server only; the client's total never trusted | the routine computes every total; the answer's `total` is the stored one | R `test_a_split_never_loses_or_invents_a_cent`; A `test_a_retried_purchase_answers_its_rows_and_a_stolen_id_is_a_conflict` |
| exact amounts: no float, no rounding of a third decimal | amounts travel as decimal strings and are cast from the jsonb text | R `test_a_purchase_amount_sent_as_a_json_number_is_read_exactly`; A `test_each_vehicles_amount_is_checked_exactly` |
| sign and sum tampering (a refund split into a charge, parts adding up to more) | `expense_allocation_sign`, `expense_allocation_sum` | the same, and P `test_a_shared_purchase_follows_the_purchase_rules_and_only_an_expense_takes_one` |
| workflow bypass: back-dating, other people's rows, another day | `tenancy.check_writable` on the stored and the new date; CE-12 | R `test_a_central_expense_before_the_limit_is_refused_on_record_change_and_remove`, `test_capture_alone_changes_only_its_own_rows_of_the_day_and_correct_any` |
| object-level authorization: hidden vehicles, other organizations | 404 for a hidden row, refusal for a hidden vehicle, figures without hidden vehicles, history by vehicle | A `test_a_scoped_person_sees_nothing_outside_their_vehicles_change_log_included`, `test_another_organizations_rows_and_ids_stay_its_own`; R `test_the_ledger_figures_of_a_scoped_viewer_leave_out_hidden_vehicles` |
| function-level authorization | each routine checks its right before anything else | A `test_the_routes_refuse_a_bad_id_no_bearer_and_a_person_without_the_rights`; R `test_the_ledger_needs_its_view_right_and_takes_any_source_word_case` |
| mass assignment | bodies list their fields; unknown properties are ignored; version, recorder and totals are the routine's | A `test_unknown_properties_never_reach_the_stored_purchase` |
| race: one purchase id from two connections | advisory lock before the lookup; unique index backstop | R `test_two_connections_recording_one_purchase_make_one_set_of_rows` |
| race: a stale writer | `FOR UPDATE` on the row, then the version | R `test_the_stale_writer_on_a_second_connection_gets_the_version_conflict_with_current` |
| race: a vehicle retired or an item stopped under a purchase | vehicles `FOR SHARE` in id order, item and category `FOR SHARE` | `expenses_entry_create.sql`, `check_item.sql` (reading; 08's race tests prove the same locks for petty cash) |
| SQL injection through `q`, `source` or ids | every value a bound parameter; no `EXECUTE` or `format()` in `57_expenses`; `q` escaped for ILIKE | R `test_source_and_search_narrow_the_rows_not_the_figures` (`' OR 1=1 --`, `%`, `_`, `\`) |
| the E-4 fix keeps the same guards | the page-only route still checks rights, the query and the page before it reads, reads only `setup.visible_vehicles()`' vehicles, and binds `q` as one escaped ILIKE pattern (no `EXECUTE`, no `format()`). The page's rows are built by `expenses.ledger_rows` over a subset of the same vehicles, so a hidden vehicle never enters either pass | R `test_every_page_is_the_ledger_rows_helper_cut_in_the_ledgers_order` (the clerk's scoped view under seven filters, searches included); R `test_source_and_search_narrow_the_rows_not_the_figures` (`' OR 1=1 --`, `%`, `_`, `\`) and `test_the_ledger_figures_of_a_scoped_viewer_leave_out_hidden_vehicles` rerun after the fix |

## 6. Verify outputs

One module per process, `-n 0`, template `xcode_template_08be`, each started at 0.6 GB free or
more.

| Module or check | Result |
|---|---|
| `tests/db/test_expense_routines.py` | 61 passed (10:27, after the E-1 fix; 61 before it too) |
| `tests/db/test_pettycash_routines.py` | 82 passed (the 16-argument create, the two shared-purchase tests) |
| `tests/db/test_pettycash_helpers.py` | 63 passed |
| `tests/db/test_history_routines.py -k central_expense` | 1 passed |
| `tests/db/test_message_codes.py` | 6 passed |
| `tests/db/test_routine_headers.py` | 1711 passed, 6 failed: the six are R's `58_reports` files, whose `Tests:` lines name `tests/db/test_report_routines.py` before R has written it (R told); every stream E file passes |
| `tests/db/test_fakes_match_routines.py -k expenses` | 2 passed (three runs before E-1, one after) |
| `tests/api/test_expenses.py` | 28 passed; `test_unknown_properties_never_reach_the_stored_purchase`, written after that run, 1 passed alone |
| `tests/api/test_petty_cash.py` | 18 passed (R's export row in `OPERATIONS` included) |
| `tests/api/test_contract_released_clients.py -k expense` | 1 passed |
| `tests/api/test_openapi.py` | 12 passed |
| `tests/unit` | 1116 passed (`test_messages`, `test_routine_catalogue`, `test_endpoint_catalogue`, `test_layers` included) |
| `ruff check .`, `ruff format --check .` | clean on every stream E file; at 10:31 one finding each in R's new `tests/support/export_files.py` (in flight, R's) |
| `mypy` | no issues in 227 source files |

After the E-4 fix (11:55 to 12:00; the template rebuilt from the live tree at 11:38; one module
per process, `-n 0`, at 1.9 GB free or more):

| Module or check | Result |
|---|---|
| `tests/db/test_expense_routines.py` | 62 passed (the page-parity test new; fail-first: it failed, and the older page test passed, with a page cut lacking the registration) |
| `tests/api/test_expenses.py` | 30 passed (stream R's appended export test included) |
| `tests/db/test_routine_headers.py` | 1717 passed |
| `tests/unit/test_routine_catalogue.py` | 2 passed |
| `tests/db/test_fakes_match_routines.py -k expense` | 2 passed |
| `tests/db/test_message_codes.py` | 6 passed |
| `ruff check .`, `ruff format --check .`, `mypy` | clean; 488 files formatted; no issues in 227 source files |

The route is the one in the live tree since 11:06; the single-call variant measured after it was
dropped (section 7). The coordinator's shared full run (queue row 9) started at 11:35 with that
route but before the parity test and these reruns. At the user's request it was stopped at 11:40
so they could land first, and it restarts from a fresh template after them.

The shared full run and `xcode-api db verify` are the coordinator's, after the three streams.

## 7. Deviations and decisions

- The ledger's SQL column is `entry_date` and its document keys `from_date`/`to_date`
  (`db/types.document()` maps exact keys onto dataclass fields, and `date`, `from`, `to` cannot be
  field names); the wire keeps `date`, `from`, `to`. Agreed with R before R used the helper.
- The source word is `pettycash`, as `packages/shared/src/expenses.ts` and `docs/06` 2.13.1 have it;
  the plan's B3 bullet wrote `pettyCash` (that is the figures member only).
- `expenses.check_ledger(p_from, p_to, p_source, p_q) RETURNS text` exists so R's export checks
  the query exactly as the ledger does (R asked for it).
- A shared petty-cash purchase: the first part's id is the purchase id and the group id; one
  allocation makes a plain entry on that vehicle; cash and credit notes refuse allocations
  (`pettycash_line_cash_shape`, `pettycash_line_credit_vehicle`); a payee or the reimbursable flag
  on a shared expense is `pettycash_line_expense_payee`. A part moved onto a vehicle its purchase
  already has reuses `expense_purchase_has_vehicle` (no new code).
- A rejected part keeps its group (it can be reopened) and its `size` counts the live parts, so a
  rejected part whose siblings are gone shows `size` 0; only an entry alone has `group` null
  (`docs/05` 11.6, `docs/06` 2.12).
- The purchase checks run before the retry lookup (CE-9 for central expenses, 08's order for a
  petty-cash line), so a retry must send a valid body; it then answers the stored rows whatever
  the body says.
- A retried purchase answers the first row's (by id) stored `group_total`; after a detachment
  that row may carry its own total. .NET answers `existing[0].GroupTotal`, the same rule.
- Allocation amounts accept a JSON number or a decimal string; both are read as text.
- `build_container` gained an `expenses` port with its own fallback, so a pool-less container
  needs `expenses=FakeExpensesRepository()` (`tests/api/test_http_plumbing.py` updated).
- The race test's second connection waits on the advisory lock; the unique index is only the
  backstop the handler covers.
- The parity observation sorts ledger rows by a tie-free key and names the parts, because a
  split's ids are random and the ledger breaks ties by id.
- SQLSTATE 57014 (statement timeout) is answered 500, not 503: `db/errors.py` treats it as neither
  a refusal nor transient (`docs/perf/expenses.md` finding 1).

- The year ledger (E-4's residual) is fixed by the page-only route. The other option listed,
  per-day sums, would still read every posting through the same helper. Over the narrow keys it
  could save only part of their cost: the key pass, figures and top-100 sort take about 0.26 s
  over the helper's 1.24 s at 367 days. A single-call variant (the postings read once and kept whole,
  only the page's rows built in the route) was measured. It was dropped: no gain at 367 days
  (2,356 ms), and it would repeat `expenses.ledger_rows`' row formulas in the route. The price
  of the page-only route is a second, small `setup.fleet_postings` call over the page's vehicles
  and days, 50 to 100 ms at 10x on 1 to 30 days. The page cut orders by the row id as a uuid,
  then the vehicle. This is the documented `id COLLATE "C"` order: a uuid's text is fixed-width
  lowercase hex, and a scheduled row's id is its item, day and vehicle. The parity test pins it.

## 8. Challenge pass

Run as `docs/14` asks, over D1 (tenancy and authorization), D2 (money), D3 (concurrency), D4
(search and reads), D10 (tests and evidence); the gamer persona first.

### 8.1 Steelman and falsification

| Claim | What would disprove it | Looked for | Grade |
|---|---|---|---|
| one purchase id makes one set of rows, even under a race | two sets, or a second change-log set | R `test_two_connections_recording_one_purchase_make_one_set_of_rows` (two connections) | A, holds |
| no cent is lost or invented by a split | rows not adding up to the total; a rounded third decimal | R `test_a_split_never_loses_or_invents_a_cent`, `test_a_purchase_amount_sent_as_a_json_number_is_read_exactly` | A, holds |
| a stale writer gets 409 with `current` | a stale save accepted | R `test_the_stale_writer_on_a_second_connection_gets_the_version_conflict_with_current` | A, holds |
| a scoped viewer learns nothing about hidden vehicles | a figure, row, option, log line or 403 where 404 is due | A `test_a_scoped_person_sees_nothing_outside_their_vehicles_change_log_included`; R `test_the_ledger_figures_of_a_scoped_viewer_leave_out_hidden_vehicles` | A, holds |
| the search matches text only, never pattern syntax | `%`, `_` or `\` acting as a wildcard or escape | R `test_source_and_search_narrow_the_rows_not_the_figures` | was C (E-1); A after the fix |
| the ledger answers inside the statement timeout | a period that times out | `docs/perf/expenses.md` | B: 367 days over 500 vehicles answers in 1.7 s on a quiet machine after the E-4 fix, but can still come near the timeout under heavy load (E-4) |

### 8.2 Probes and verdicts

- Gamer clerk with `expenses.capture` only: changing another's row, an earlier day's row, or
  moving the date is refused (CE-12); recording on a hidden vehicle is refused; recording before
  the back-dating limit is refused. Conceded.
- Gamer clerk splitting a purchase so one part lands on a hidden vehicle: every vehicle is checked
  in scope (`expense_vehicle_not_yours`). Conceded.
- Stealing a purchase id (another person's, another purchase's, or one row's id of a split): 409
  `expense_saved_by_other` without `current`. Conceded.
- A part moved onto a vehicle its purchase already has, in either module: refused by name before
  the unique index. Conceded.
- Searching with `%`, `_`, `\` or `' OR 1=1 --`: matched as text once E-1 was fixed.
- Refunds: a negative purchase with negative parts is allowed (as .NET); mixed signs are refused.
  Conceded.
- Pre-mortem on the year ledger: E-4.

### 8.3 Findings

| id | mode | claim attacked | challenge | evidence | verdict | synthesis |
|---|---|---|---|---|---|---|
| E-1 | falsification | the ledger's search escapes `\` | `ledger_rows.sql:57` read `replace(v_text, '\', '\')`, a no-op: the file tool had collapsed the doubled backslash. `q=\` matched rows holding `%`. The test passed because its one row held both `%` and `\` | re-reading every backslash of my SQL files; R's `entry_matches.sql` has `'\\'` | major, fixed | line fixed; the test gained a row with `%` and no `\` and asserts `q="\\"` and `q="0%"`; R told (it reuses the helper) |
| E-2 | falsification | the API tests carry the .NET assertions | the retry test sent an invalid body (refused by CE-1 before the lookup) and lacked the single-vehicle retry and the row-id case; the scoped test lacked the `audit.view` grant, the figures, `q`, options, the 404s and the refusal | first API run: 2 failed | minor, fixed | both rewritten to the .NET assertions |
| E-3 | Socratic | a rejected part shows no group | my routine test expected `group` null on a rejected part | `docs/05` 11.6 says only an entry alone has none | expectation wrong, fixed | the test asserts the group with `size` 0 |
| E-4 | pre-mortem | the ledger serves a year | 367 days over 500 vehicles takes about 5.2 s, past `xcode_app`'s 5 s | `docs/perf/expenses.md` | major; fixed: the helpers' part by C, the residual by E | C rewrote `setup.fleet_postings` and `setup.scheduled_runs` (C's helpers; 10:38): at 367 days, loaded, the postings went from 5,506 to 1,795 ms and the route from 12,100 to 6,924 ms. E's residual was fixed on the user's request the same day by the page-only route: the figures, count and page are cut from the postings' keys and only the page's rows are built through `expenses.ledger_rows`. Quiet, at 367 days: 2,138 to 1,706 ms; page 900: 2,779 to 1,836 ms. Short periods pay 50 to 100 ms. Answers are unchanged (9 cases on the clone; A `test_every_page_is_the_ledger_rows_helper_cut_in_the_ledgers_order`, fail-first with a page cut lacking the registration). `docs/perf/expenses.md`, section "The page-only route" |
| E-5 | falsification | mass assignment cannot set stored columns | no test sent `version`, `total` or a recorder | reading `ApiModel` (`extra="ignore"`) | minor, fixed (test) | A `test_unknown_properties_never_reach_the_stored_purchase` |

## 9. Left for later

- E-4's residual was fixed the same day (sections 6 and 8.3). What is left: under heavy load a
  367-day ledger over 500 vehicles can still come near `xcode_app`'s 5 s timeout. Most of the
  remaining cost is in `setup.fleet_postings`, C's helper (about 1.1 to 1.4 s quiet for 96,000
  postings), and in spilling wide rows at the server's `work_mem`. Neither is stream E's to change.
- The coordinator's: the shared full run and `db verify` on `xcode`.
