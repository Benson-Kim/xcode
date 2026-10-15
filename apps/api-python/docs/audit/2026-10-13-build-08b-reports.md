# Build report part: prompt 08b, stream R, reports and every export (2026-10-13)

Session expenses-reports-design-build [9fea06], stream R of the 08b build (Part C of the approved
plan `~/.claude/plans/cached-baking-blanket.md`); coordinator revenue-17 [60bb7c], who
consolidates this part into `docs/audit/2026-10-13-build-08b.md` after the shared full run.
Scope: B2.3 (`58_reports`, the three screen exports included), the stream's parts of B3 and B4,
all of B5 (the two export adapters and their dependencies), the D7 rows of B7, and the reports
part of B8. No helper agents; every file was written here. The Central expenses export reuses
stream E's `expenses.check_ledger` and `expenses.ledger_rows`; the Petty cash export reuses
`pettycash.entry_matches`, the list's query extracted into a set-returning helper so the export
and the screen read one query.

## 1. Drift check against .NET

The D0 inventory (`docs/inventory/inventory-expenses-reports.md`, 2026-10-12) read `HEAD` 493bf82
plus the working tree. Re-checked at 10:58 today by file times: no report file of `apps/api` or
`tests/api/ReportTests.cs` changed since (newest 2026-10-10 22:35, `packages/shared/src/reports.ts`);
the working-tree changes under `packages/shared/src` are the web v2.3 session's, not .NET's.

| File | Modified |
|---|---|
| `apps/api/Api/ReportEndpoints.cs` | 2026-10-10 22:30 |
| `apps/api/Application/ReportUseCases.cs`, `ScreenExports.cs`, `PettyCashReports.cs` | 2026-10-10 22:29, 22:30, 22:20 |
| `apps/api/Application/FleetReports.cs`, `Tables.cs`, `ReportContracts.cs`, `ReportFormat.cs`, `ReportWorkbook.cs` | 2026-10-09 |
| `apps/api/Infrastructure/ReportRepository.cs`, `ReportPdf.cs` | 2026-10-09 22:22, 22:24 |
| `tests/api/ReportTests.cs` | 2026-10-10 22:32 |

## 2. Checklist

### D2 Routines (B2.3)

| Item | Done | Where | Test |
|---|---|---|---|
| Helpers `check_period`, `check_query`, `cell_text`, `page`, `matching_rows`, `document`, `log_export`, `check_export`, `vehicles`, `vehicle_figures`, `money_out_by_main` | yes | `db/routines/58_reports/<name>.sql`; plus `figure`, `heading`, `build_table`, `ratio`, `row_matches`, `totals`, `build`, `pettycash_entries` (named in `docs/05` 11.4's built note) | `test_the_period_checks_answer_in_order_and_cut_the_last_day_to_today`, `test_check_query_skips_the_page_only_when_both_are_null`, `test_cell_text_shows_dates_numbers_and_texts_as_the_search_sees_them`, `test_the_page_cuts_the_matching_rows_and_the_totals_cover_every_match`, `test_check_export_reads_the_format_in_any_case_and_caps_the_rows`, `test_ratio_rounds_half_away_from_zero_and_has_no_answer_for_an_empty_whole` (all `tests/db/test_report_routines.py`) |
| Builders `fleet_net`, `fleet_target`, `fleet_gaps`, `fleet_money_out`, `fleet_savings`, `fleet_investment` | yes | one file each; `vehicle_figures` and `money_out_by_main` are one `revenue.vehicle_days` and one `setup.fleet_postings` over every visible vehicle; `fleet_savings` and `fleet_investment` set-based (no `setup.saving_balance` or `setup.vehicle_net` per vehicle, the coordinator's 10:38 note) | `test_net_by_vehicle_agrees_with_each_vehicle_report_and_splits_money_out_by_main_category`, `test_revenue_against_target_counts_captured_no_revenue_and_missing_days`, `test_capture_gaps_lists_each_missing_day_in_order`, `test_money_out_groups_every_source_by_item_at_the_true_unit_cost`, `test_savings_count_runs_in_the_period_and_the_balance_since_each_saving_began`, `test_investment_shows_what_came_back_since_joining_and_needs_its_permission` |
| Builders `pettycash_cash_book`, `pettycash_managers`, `pettycash_vehicles`, `pettycash_items`, `pettycash_waiting`, `pettycash_sent_back`, `pettycash_rejected` | yes | one file each over `reports.pettycash_entries(holder ids, view_all, visible vehicles)` | `test_petty_cash_reports_follow_the_floats_a_person_may_see`, `test_a_petty_cash_report_of_another_float_is_not_found` |
| `api.report_catalog_get` (RP-1 with DEC-40's rights) | yes | `report_catalog_get.sql` | `test_the_catalogue_lists_what_the_actor_may_open`, `test_a_holder_with_the_reports_right_sees_their_own_float_only`; HTTP `test_the_catalogue_reads_in_wire_order_by_right` |
| `api.report_get`: query checks, `reports.build` (404, the report's right, the holder, the period cut to today), search, page, totals | yes | `report_get.sql`, `build.sql`, `page.sql` | `test_the_report_checks_run_in_their_order`, `test_a_dated_report_is_cut_to_the_business_date_and_an_undated_one_has_no_period`, `test_each_report_and_export_refuses_without_its_right`, `test_a_scoped_viewer_sees_no_hidden_vehicle_in_any_figure` |
| `api.report_export_get`: format first, then the search, the report, every matching row, the 10,000 cap, `reports.document`, `reports.log_export` in one transaction | yes | `report_export_get.sql`, `document.sql`, `log_export.sql`, `check_export.sql` | `test_an_export_writes_one_change_log_row_with_its_count`, `test_a_scoped_viewers_export_holds_no_hidden_vehicle`; HTTP `test_an_export_past_the_row_bound_is_refused_with_its_sentence` |
| `api.revenue_export_get` (reads `api.revenue_week_get` itself), `api.expenses_export_get` (E's `check_ledger` + `ledger_rows`), `api.pettycash_export_get` (`pettycash.entry_matches`, `reports.pettycash_entries`, `pettycash.tallies`) | yes | the three files; `55_pettycash/entry_matches.sql` new, `pettycash_entry_list.sql` reads it | `test_the_screen_exports_list_what_their_screens_list`; HTTP `test_screens_export_what_they_list` |
| Table shape (RP-13) and the document's keys | yes | `build_table.sql` (`from_date`, `to_date`: see deviation 3), `page.sql`, `document.sql` | the shape asserted in every test above; DTO orders in `tests/api/test_reports.py` |
| `tests/db/test_report_routines.py` with the names the documents cite | yes | 23 tests | `docs/12` 2.8 and `docs/09` 4.2 name four of them; all exist |

### D3 Domain, ports, gateway, fakes (B3)

| Item | Done | Where | Test |
|---|---|---|---|
| `domain/reports.py` | yes | `ReportGroup`, `CellKind`, `ExportFormat`, `ReportColumn`, `ReportFigure`, `ReportTable`, `ReportsAccess`, `ReportHolder`, `ReportQuery`, `ReportExportQuery`, `ReportDocument`, `ExportFile`, and the three screen export queries (deviation 2) | `tests/unit/test_use_case_export_report.py`, the parity block |
| `application/repositories.py` `ReportsRepository`; `application/ports.py` `ReportFileWriter` | yes | appended blocks | `test_the_reports_fake_is_a_reports_repository` |
| `db/routines/reports.py` (`ReportsRoutines`, every export `idempotent=True`, float cells to `Decimal`) | yes | one `SELECT * FROM api.<name>(` literal per method | `tests/unit/test_layers.py`; the parity block |
| `FakeReportsRepository` (catalogue rights, period and query checks, `net` and `gaps` from the setup/revenue fakes, export logging with the cap, the other builders empty: said in its docstring) and `tests/support/reports_cases.py` | yes | `tests/support/fakes.py` (appended), `reports_cases.py` | `test_the_reports_fake_answers_as_the_routines_do` (`tests/db/test_fakes_match_routines.py`) |
| `tests/unit/test_use_case_export_report.py` (writer by content type, off the loop, name and type from the document, missing writer an integrity bug) | yes | 4 tests | itself |

### D4 Messages, use cases, HTTP (B4)

| Item | Done | Where | Test |
|---|---|---|---|
| `http/messages.py` reports-and-exports block (10 codes, `export_too_many_rows` with `{count}`); `docs/06` section 3 block; 2.13.6 note; `SAMPLES` gains `count` | yes | `messages.py`, `docs/06-http-contract.md`, `tests/unit/test_messages.py` | `tests/unit/test_messages.py`, `tests/db/test_message_codes.py` |
| `http/responses.py` `file_response` | yes | `responses.py` | `tests/unit/test_file_response.py` (an ASCII name; a name with other letters, a quote and a backslash) |
| Use cases `application/reports/{get_reports_access,get_report,export_report}.py`, `files.py` (`build_file`: the writer by the document's content type, `asyncio.to_thread`), `application/expenses/export_ledger.py`, `application/revenue/export_week.py`, `application/pettycash/export_entries.py` | yes | the files; `container.py` wires `reports`, `export_writers`, the seven use cases; `main.py` includes `reports.router` | `tests/unit/test_use_case_export_report.py`; HTTP tests |
| `http/schemas/reports.py` in wire order (`from`/`to` aliases, cells as JSON numbers) | yes | the file | `test_the_catalogue_reads_in_wire_order_by_right`, `test_a_fleet_report_reads_in_wire_order_with_its_page_and_search`; D7 rows |
| Router `reports.py` (G01 to G04; `{group}` validated as `fleet`/`pettycash`, else an empty 404); `/export` on `revenue.py` before `/{vehicleId}/{date}`, `pettycash.py`, `expenses.py` (E02); budget 2 | yes | the routers; `tests/support/operations.json` planned flags off for G01 to G04, X02, X03, E02 | `test_every_report_route_has_its_operation_id_and_the_reports_tag`, `statements()` in every HTTP test, `tests/unit/test_endpoint_catalogue.py`, `tests/api/test_openapi.py` |
| `tests/api/test_reports.py` (`ReportTests` scenarios, the files opened, the change-log reasons, 401/403/404, the route catalogue) | yes | 8 tests | itself |

### D5 Exports (B5)

| Item | Done | Where | Test |
|---|---|---|---|
| Dependencies and locks: `XlsxWriter>=3.2`, `reportlab>=4.4` (runtime), `pypdf>=6`, `defusedxml>=0.7` (dev); both locks regenerated with `uv pip compile --universal --python-version 3.13 --generate-hashes`; `pip-audit` on both locks: no known vulnerabilities | yes | `requirements*.txt`, `requirements*.lock.txt`; pinned XlsxWriter 3.2.9, reportlab 5.0.1 (pillow 12.3.0, charset-normalizer 3.5.2), pypdf 6.20.1, defusedxml 0.7.1 | section 6 |
| `pyproject.toml` package data for the fonts; mypy overrides for the two untyped libraries | yes | `pyproject.toml` | `mypy src` clean |
| Fonts copied from `apps/api/Assets/Fonts` with the two OFL texts; never a system font | yes | `src/xcode_api/infra/exports/fonts/` | `test_the_pdf_is_a4_landscape_with_the_three_fonts_embedded_and_numbered_pages` (every referenced font embedded; the canvas starts in Figtree, so Helvetica is never referenced) |
| `tests/unit/test_layers.py` and `docs/01` name the two libraries, `infra/exports` only | yes | the test, `docs/01-architecture.md` | `tests/unit/test_layers.py` |
| `infra/exports/xlsx.py` (RP-16: bands, figures, header, banded rows, totals row when a column sums, frozen and repeated header, autofilter, landscape fit-to-width, footer, the number formats, date serials, `quote_prefix`, the three `strings_to_*` options off, XML-illegal characters stripped, 31-character sheet name) | yes | `xlsx.py`, `layout.py` | `tests/unit/test_export_files.py` (6 Excel tests), HTTP `same_rows` cell by cell |
| `infra/exports/pdf.py` (RP-17: A4 landscape, brand band, headline card, figure tiles, header repeated, banded rows, bars beside percents, tinted totals, `Nothing to show for these dates.`, `Page i of n` by a two-pass layout, title/author/creator metadata) | yes | `pdf.py` | `test_the_pdf_is_a4_landscape_with_the_three_fonts_embedded_and_numbered_pages`, `test_an_empty_pdf_says_there_is_nothing_to_show`, `test_two_builds_of_one_document_are_the_same_bytes` |
| `tests/unit/test_export_files.py` on fixed documents; the readers shared with the HTTP tests | yes | the test; `tests/support/export_files.py` (`Workbook`, `embedded_fonts`) | itself |

### D7 Released clients (B7) and B8

| Item | Done | Where | Test |
|---|---|---|---|
| D7 rows: the catalogue, `net`, `cashBook` in `has(...)` style | yes | `tests/api/test_contract_released_clients.py` (appended block) | `test_the_report_catalogue_keeps_the_keys_the_web_reads`, `test_net_by_vehicle_and_the_cash_book_read_as_the_web_does` |
| `docs/perf/reports.md` | budgets and the exact command, no 10x run (time-boxed) | `docs/perf/reports.md` | section 9, item 1 |
| `docs/05` 11.4 built note (the new helpers' names, the signature choices), `docs/06` section 3 block and 2.13.6 note, `docs/09` 4.2 (names as built), `docs/12` 2.8 proven-by cells (names as built, unchanged) | yes | the documents | `tests/unit/test_routine_catalogue.py`, `test_messages.py`, `test_endpoint_catalogue.py` |

## 3. Rule id to test

| Rule | Test |
|---|---|
| RP-1 | `test_the_catalogue_lists_what_the_actor_may_open`, `test_a_holder_with_the_reports_right_sees_their_own_float_only`; HTTP `test_the_catalogue_reads_in_wire_order_by_right` (with DEC-40's rights, deviation 5) |
| RP-2 | `test_the_report_checks_run_in_their_order`, `test_check_query_skips_the_page_only_when_both_are_null`, `test_the_period_checks_answer_in_order_and_cut_the_last_day_to_today`; HTTP `test_refusals_keep_their_status_and_sentence` |
| RP-3 | `test_a_scoped_viewer_sees_no_hidden_vehicle_in_any_figure` (every fleet builder: rows, headline, figures; the company filter); HTTP `test_a_scoped_viewers_export_holds_no_hidden_vehicle` |
| RP-4 | `test_net_by_vehicle_agrees_with_each_vehicle_report_and_splits_money_out_by_main_category` (equal to `api.setup_vehicle_report` per vehicle), `test_revenue_against_target_counts_captured_no_revenue_and_missing_days` (a vehicle joined mid-period, the day before today counted, today not) |
| RP-5 (as DEC-38 changes it) | `test_net_by_vehicle_agrees_with_each_vehicle_report_and_splits_money_out_by_main_category` (one money column per main category with money, `main:none` for none; order by net then registration) |
| RP-6 (DEC-37) | `test_revenue_against_target_counts_captured_no_revenue_and_missing_days` (reached 121.3, 150.0, 175.0; the figure 148.3; order by reached), `test_ratio_rounds_half_away_from_zero_and_has_no_answer_for_an_empty_whole` |
| RP-7 | `test_capture_gaps_lists_each_missing_day_in_order` |
| RP-8 (B18) | `test_savings_count_runs_in_the_period_and_the_balance_since_each_saving_began` (9 runs then 5 in a shorter period, the balance 900 both times; a company without savings gives no rows) |
| RP-9 (DEC-39, DEC-40) | `test_investment_shows_what_came_back_since_joining_and_needs_its_permission` (initial investment plus entries; the vehicles without one last with null recovered), `test_each_report_and_export_refuses_without_its_right` (`report_investment_permission`) |
| RP-10 | `test_money_out_groups_every_source_by_item_at_the_true_unit_cost` (a central purchase of 4 at 1,200 and a petty-cash expense of 2 at 1,500 on one item: 2 entries, 6 units, lowest 1,200, highest 1,500; a scheduled cost by its name with the bucket's label; the share; the figures by main category) |
| RP-11 (DEC-40, B19) | `test_each_report_and_export_refuses_without_its_right` (`report_pettycash_permission`), `test_a_petty_cash_report_of_another_float_is_not_found`, `test_petty_cash_reports_follow_the_floats_a_person_may_see` (a holder outside the viewer's floats is 404; `waiting` undated) |
| RP-12 | `test_petty_cash_reports_follow_the_floats_a_person_may_see` (the cash book's opening carried day to day, waiting counted and shown, the credit note; by manager; waiting with days waiting; by item and by vehicle; sent back and rejected empty), the Petty cash export's `Credit note` row in `test_the_screen_exports_list_what_their_screens_list` |
| RP-13 | `test_the_page_cuts_the_matching_rows_and_the_totals_cover_every_match` (page 2 of size 1; `kda 9,700` with the thousands form; `2026-10-06 kdb`; the totals over every match, the figures over the whole report), `test_cell_text_shows_dates_numbers_and_texts_as_the_search_sees_them`; HTTP `test_a_fleet_report_reads_in_wire_order_with_its_page_and_search` |
| RP-14 | `test_an_export_writes_one_change_log_row_with_its_count` (format in any case, Excel and PDF, the filters text, the file name, the snapshot keys, the reason with the search, the audit event; the company and the holder filters), `test_check_export_reads_the_format_in_any_case_and_caps_the_rows` (`10,001` in the sentence); HTTP `test_an_export_is_a_file_with_its_name_and_one_change_log_row`, `test_an_export_past_the_row_bound_is_refused_with_its_sentence` (10,000-plus gap rows from 28 seeded vehicles over 367 days; the refused export logs nothing; the narrowed one exports) |
| RP-15 | `test_the_screen_exports_list_what_their_screens_list` (the Revenue export equals `api.revenue_week_get` cell by cell, day labels `Mon 5`, `Target to date` for an unfinished week; the Petty cash export's rows are the list's with the status words and the cash view's descriptions; the Central expenses export's rows are the ledger's with `Standing order` and `{recorder}, {holder}'s float`; each export's snapshot and reason); HTTP `test_screens_export_what_they_list` |
| RP-16 | `test_the_bands_figures_header_totals_and_footer_are_laid_out_as_the_rules_say`, `test_numbers_are_numbers_with_their_formats_and_dates_are_serials`, `test_a_cell_starting_with_equals_stays_text`, `test_a_long_title_gives_a_sheet_name_of_at_most_31_characters_without_forbidden_marks`, `test_an_undated_report_reads_as_at_and_an_empty_one_has_only_its_count_row`; HTTP `same_rows` reads every data row of every exported file against the JSON report |
| RP-17 | `test_the_pdf_is_a4_landscape_with_the_three_fonts_embedded_and_numbered_pages`, `test_an_empty_pdf_says_there_is_nothing_to_show`, `test_two_builds_of_one_document_are_the_same_bytes`; HTTP: the PDF's mediabox, fonts, title and `Page 1 of 1` |
| RP-18 | E's `tests/db/test_history_routines.py::test_central_expense_and_export_rows_follow_the_scope` (section `reports` visible to `v_all` only; B2.6 is E's file); the rows written here carry no vehicle, as that filter assumes (`test_an_export_writes_one_change_log_row_with_its_count`) |
| G01 to G04, X02, X03, E02 | `test_every_report_route_has_its_operation_id_and_the_reports_tag`, `tests/unit/test_endpoint_catalogue.py`, `tests/api/test_openapi.py`; the petty-cash and central-expense route catalogues gained their export rows |

## 4. .NET fact to Python test

`ReportTests` (13), `tests/api/ReportTests.cs` lines as the inventory's section 5 cites them.

| .NET fact | Python test |
|---|---|
| Net by vehicle agrees with each vehicle report (41-86) | `test_net_by_vehicle_agrees_with_each_vehicle_report_and_splits_money_out_by_main_category` (equality with `api.setup_vehicle_report` on money in, money out, net and savings for every row; DEC-38's per-main-category columns instead of repairs/charges/loans) |
| Target and gaps count captured, no-revenue and missing days (88-118) | `test_revenue_against_target_counts_captured_no_revenue_and_missing_days`, `test_capture_gaps_lists_each_missing_day_in_order` |
| Money out at the true unit cost (120-142) | `test_money_out_groups_every_source_by_item_at_the_true_unit_cost` (every source: central, petty cash, scheduled; the main category added) |
| Savings runs and balance (144-155) | `test_savings_count_runs_in_the_period_and_the_balance_since_each_saving_began` (saved, skipped and held runs and the opening balance, B18) |
| Investment and its permission (157-180) | `test_investment_shows_what_came_back_since_joining_and_needs_its_permission` (the initial investment and the vehicle without one last, DEC-39), `test_each_report_and_export_refuses_without_its_right` |
| Petty-cash reports follow the floats (182-245) | `test_petty_cash_reports_follow_the_floats_a_person_may_see`, `test_a_petty_cash_report_of_another_float_is_not_found` (B19's statuses, `pettycash.reports`) |
| Scope (247-262) | `test_a_scoped_viewer_sees_no_hidden_vehicle_in_any_figure`; HTTP `test_a_scoped_viewers_export_holds_no_hidden_vehicle` |
| The Excel file's cells and the change log (264-307) | HTTP `test_an_export_is_a_file_with_its_name_and_one_change_log_row` (the file read cell by cell under its header, the totals row, the name in `Content-Disposition`, five change-log reasons verbatim) |
| Screen exports and their log reasons (309-368) | HTTP `test_screens_export_what_they_list`; DB `test_the_screen_exports_list_what_their_screens_list` |
| The PDF's pages, size and fonts (385-416) | `test_the_pdf_is_a4_landscape_with_the_three_fonts_embedded_and_numbered_pages` (3 pages for 60 rows, 842 x 595, the three fonts with `/FontFile2`, the title and `Page i of n` in the text) |
| Paging and search (418-462) | `test_the_page_cuts_the_matching_rows_and_the_totals_cover_every_match`; HTTP `test_a_fleet_report_reads_in_wire_order_with_its_page_and_search` |
| Periods and unknown reports (464-490) | `test_the_report_checks_run_in_their_order`, `test_a_dated_report_is_cut_to_the_business_date_and_an_undated_one_has_no_period`; HTTP `test_refusals_keep_their_status_and_sentence` |
| Search and totals without a database (492-513) | `tests/unit/test_use_case_export_report.py` and the fake's `_rp_matching`/`_rp_totals`, proven equal to the routines by `test_the_reports_fake_answers_as_the_routines_do` (the rules live in SQL: `reports.cell_text`, `reports.totals`) |

## 5. Secure-coding checks

Skills consulted (the gate's rows for dependencies and for new endpoints):
`detecting-dependency-confusion`, `analyzing-sbom-for-supply-chain-vulnerabilities`,
`testing-api-for-broken-object-level-authorization`,
`exploiting-broken-function-level-authorization`. The mass-assignment and property-level rows
were applied by reading the routes: every new route is a `GET` with scalar query parameters,
no body, and answers either a DTO built in the router or a file; nothing a client sends is
written anywhere but the change-log snapshot of its own export.

| Check | Where | Test |
|---|---|---|
| Dependency confusion: no private index, no private package name; every new package is a public PyPI name resolved from the one index; both locks carry hashes (`--generate-hashes`), so a substituted artefact fails the install | `requirements*.lock.txt` | the CI diff of the locks (prompt 09); `pip-audit --require-hashes` on both locks (section 6) |
| SBOM: the locks are the inventory (name, version, hashes, `# via` lines); `pip-audit` ran clean on 2026-10-13 against both; versions recorded in D5 | section 2, D5 | section 6 |
| Function-level authorization: every route's right is checked in SQL before any read (`reports.view`, `reports.investment`, `pettycash.reports`, `reports.export`, `revenue.export`+`revenue.view`, `expenses.export`+`expenses.view`, `pettycash.export`+`pettycash.view`), never in the router | `58_reports/*_get.sql` | `test_each_report_and_export_refuses_without_its_right` (a Revenue clerk on all seven routines, a Fleet manager on the four it lacks); HTTP `test_refusals_keep_their_status_and_sentence`, `test_the_catalogue_reads_in_wire_order_by_right`, `test_screens_export_what_they_list` (403s) |
| Object-level authorization: `holderId` outside the viewer's floats is 404 (never another float's figures); `companyId` only narrows the viewer's visible vehicles (a hidden company gives an empty table, not a leak); every figure, footer and exported row is cut to `setup.visible_vehicles()` in SQL | `build.sql`, `vehicles.sql`, `pettycash_export_get.sql` | `test_a_petty_cash_report_of_another_float_is_not_found`, `test_a_scoped_viewer_sees_no_hidden_vehicle_in_any_figure`, `test_a_scoped_viewers_export_holds_no_hidden_vehicle` (the file and the PDF text), `test_petty_cash_reports_follow_the_floats_a_person_may_see` (a random and a non-holder id) |
| Formula injection in exported cells: `write_string` only, the three `strings_to_*` options off, `quote_prefix` on `=`, `+`, `-`, `@`, tab and carriage return, the value unchanged | `infra/exports/xlsx.py` | `test_a_cell_starting_with_equals_stays_text`; HTTP `test_screens_export_what_they_list` (a petty-cash note `=2+2`); E's module `test_an_exported_item_starting_with_equals_stays_text` (a catalogue name) |
| `q` reaching SQL: matched word by word against `reports.cell_text` with `position(lower(word) in lower(text))`, never `format()`; the Petty cash export's `q` goes through `pettycash.entry_matches`, the list's own escaped ILIKE | `row_matches.sql`, `55_pettycash/entry_matches.sql` | `test_the_page_cuts_the_matching_rows_and_the_totals_cover_every_match` (punctuation and thousands separators as data) |
| Bounded work: the period at most 367 days, the page at most 100 rows, the export at most 10,000 rows (checked on the matching rows before any byte is built), the file built in a worker thread | `check_period.sql`, `check_query.sql`, `check_export.sql`, `application/reports/files.py` | `test_check_export_reads_the_format_in_any_case_and_caps_the_rows`; HTTP `test_an_export_past_the_row_bound_is_refused_with_its_sentence`; `test_the_writer_is_chosen_by_the_documents_content_type_and_runs_off_the_loop` |
| Audit row per export in the export's transaction, `idempotent=True` so a failed transaction leaves no row and a retry writes one | `log_export.sql`, `db/routines/reports.py` | `test_an_export_writes_one_change_log_row_with_its_count` (one row per export, none for a refusal), HTTP: the reasons read back after every export route |
| File name on the wire: non-ASCII, `"` and `\` never reach the quoted form | `http/responses.py` | `tests/unit/test_file_response.py` |

Gaps left: no rate limit on exports beyond the role's statement timeout and the row cap (the
plan did not ask for one; a 10,000-row PDF costs about 1.5 s of a worker thread); the
`reports` change-log rows' scope filter is E's helper and E's test.

## 6. Verify outputs

- `ruff check .`: All checks passed. `ruff format --check .`: 486 files already formatted.
  `mypy src`: Success, no issues found in 227 source files (10:57).
- `pip-audit -r requirements.lock.txt --require-hashes` and the same on
  `requirements-dev.lock.txt`: No known vulnerabilities found (pip-audit 2.10.1, 10:46).
- Modules, one per process, `-n 0`, on `xcode_template_08br` (rebuilt by fingerprint from the
  live tree at each change), the board's Running-now rows of 09:26 and 10:40:

| Module | Result |
|---|---|
| `tests/unit` | 1116 passed (10:49; `test_file_response.py` added after: 2 passed at 11:24, in one process with `test_export_files.py` and `test_use_case_export_report.py`, 14 passed in 1.5 s) |
| `tests/db/test_routine_headers.py` | 1717 passed |
| `tests/db/test_message_codes.py` | 6 passed |
| `tests/db/test_fakes_match_routines.py -k reports` | 6 passed |
| `tests/db/test_pettycash_routines.py` | 82 passed (10:52, 8:28) |
| `tests/api/test_petty_cash.py` | 18 passed (11:01, 2:25) |
| `tests/api/test_revenue.py` | 39 passed (11:03, 5:16) |
| `tests/api/test_http_plumbing.py` | 32 passed (11:09, 0:41) |
| `tests/api/test_openapi.py` | 12 passed (11:10, 1:04) |
| `tests/api/test_contract_released_clients.py` | 36 passed (11:11, 4:22) |
| `tests/api/test_expenses.py` (E's module; my appended test) | 30 passed (11:16, 3:30) |
| `tests/api/test_reports.py` | 8 passed (11:20, 0:56) |
| `tests/db/test_report_routines.py` | 23 passed (11:21, 2:00) |

## 7. Deviations and decisions

1. `api.pettycash_export_get` takes `p_status text[]` (the router splits the comma list, as the
   list's `p_statuses`), not a text. `docs/05` 11.4's built note says so.
2. Every export query lives in `domain/reports.py` (`RevenueExportQuery`, `ExpenseExportQuery`,
   `PettyCashExportQuery` beside `ReportExportQuery`) and every export on `ReportsRepository`,
   as Part C lists them; B3's placement of the screen export queries in `domain/revenue.py` and
   `domain/pettycash.py` is not followed, so the reports gateway is the one caller of
   `reports.document` and `reports.log_export`.
3. The table's period keys are `from_date` and `to_date` in jsonb (`db/types.py`'s `document()`
   adapter needs field names, and `from` cannot be one); the HTTP layer serves `from` and `to`.
   The export snapshot keeps `from` and `to`, as RP-14 lists them.
4. `reports.check_query` skips the page check only when both page arguments are null (the
   export); `api.report_get` passes `coalesce(p_page, 0)` so a missing page is still refused.
5. The catalogue's `holders` are empty, and the petty-cash reports refused, without
   `pettycash.reports` (DEC-40); RP-1's `pettycash.spend or view_all` and RP-11's
   `"View every float"` sentence are replaced by that right and its label
   (`Petty cash reports need the permission "View petty cash reports".`). The investment
   sentence names `"See the investment report"` (`reports.investment`'s label) instead of
   `invest.view`'s. Both sentences are in `docs/06` section 3.
6. `api.revenue_export_get` calls `api.revenue_week_get` itself (an internal `api.*` call, as
   `60_ops` does), so the export and the screen share one query and the legacy page of 500
   vehicles; the Petty cash export reads `pettycash.entry_matches`, extracted from
   `api.pettycash_entry_list` (the list now reads it too; `tests/db/test_pettycash_routines.py`
   proves the list unchanged).
7. The money-out table shows `Not set` for a row without a main category and the figure
   `No main category`; Net by vehicle's extra column for such money is `main:none` labelled
   `No main category`. The petty-cash reports' columns beyond RP-12's words are listed in
   `docs/05` 11.4's built note.
8. `fleet_savings` and `fleet_investment` are set-based (the coordinator's 10:38 perf note);
   `fleet_investment` counts money in and money out exactly as `setup.vehicle_net` does, proven
   row by row against the vehicle report.
9. The planned `test_an_exported_note_starting_with_equals_stays_text` in E's module is named
   `test_an_exported_item_starting_with_equals_stays_text`: the Central expenses export has no
   note column (its columns are the ledger's: date, vehicle, item, category, quantity, unit
   amount, amount, source, recorded by), so a catalogue name carries the formula; a note does
   in the Petty cash export (`test_screens_export_what_they_list`).
10. The Excel adapter writes the totals row only when a column sums (RP-16's words); Capture
    gaps has none, so its file ends with the data. The sheet name drops a trailing space after
    the 31-character cut. The PDF canvas starts in Figtree, so no page references Helvetica.
11. `tests/support/export_files.py` (new, mine) holds the Excel and PDF readers both test
    modules use; `tests/unit/test_file_response.py` holds B4's `file_response` unit test.
12. The Central expenses export's unit-amount column key is `unitAmount` (as the Petty cash
    export's), renamed from `unit` during the build; keys are not on the wire for a file.

## 8. Challenge pass

### 8.1 Steelman and falsification

| Claim | Steelman | Falsified by | Grade |
|---|---|---|---|
| A scoped viewer's export cannot carry a hidden vehicle | every builder reads `reports.vehicles`, which joins `setup.visible_vehicles()`; the export reads the same builder | `test_a_scoped_viewers_export_holds_no_hidden_vehicle` opens the Excel rows and the PDF text; `test_a_scoped_viewer_sees_no_hidden_vehicle_in_any_figure` checks headline, figures, rows and totals of five builders | A |
| A float outside the viewer's is never summed | `reports.build` resolves `p_holder_id` against `pettycash.visible_holders(view_all)`; an id outside it is 404 before any read | `test_a_petty_cash_report_of_another_float_is_not_found` (a second float exists and the own-float viewer asks for it) | A |
| No right, no row | each `api.*` enters with the route's right and requires the screen's read right | `test_each_report_and_export_refuses_without_its_right` (two roles, seven routines) | A |
| The row cap counts the matching rows, not the page | `report_export_get` runs `matching_rows` without paging, then `check_export(format, count)` | HTTP `test_an_export_past_the_row_bound_is_refused_with_its_sentence` (10,000-plus rows refused with the exact count; the narrowed search exports) | A |
| One change-log row per export, none per refusal | `log_export` runs in the routine's transaction after the cap | `test_an_export_writes_one_change_log_row_with_its_count`, the `reasons(world) == []` checks after each refusal in the HTTP tests | A |
| A formula in a cell stays text | `write_string` + `quote_prefix` + the three options off | three tests, one per source of text (fixed document, petty-cash note, catalogue name) | A |
| The screen and its export agree | one SQL per screen | DB and HTTP screen-export tests compare the export with the screen's own answer | A |
| Two builds of one document are byte-equal | `invariant = 1`, the created date pinned, no clock in the adapters | `test_two_builds_of_one_document_are_the_same_bytes` (Excel and PDF) | B (pdf determinism holds under `invariant`; production PDFs carry the real date) |
| 500 vehicles over 367 days answer within budget | set-based builders; one day series | not measured at 10x in this session (section 9) | C |

### 8.2 Probes and verdicts

| Mode | Probe | Verdict |
|---|---|---|
| the attacker | `holderId` of a non-holder member, a random uuid, another float as an own-float viewer | 404 each (`test_a_petty_cash_report_of_another_float_is_not_found`, HTTP `test_refusals_keep_their_status_and_sentence`) |
| the attacker | `/setup/reports/nowhere/net/export` | empty 404 from the router (HTTP) |
| the attacker | `format=csv`, `format=doc` with other errors present | `export_format_invalid` first (DB and HTTP) |
| the attacker | a note or an item named `=2+2` exported | a text cell with the quote prefix, no `<f>` element |
| the attacker | a name with `"` and `\` in `Content-Disposition` | replaced by `_` in the quoted form, percent-encoded in the other (`test_file_response.py`) |
| the auditor | an export that fails after the row count | the whole routine's transaction rolls back (`idempotent=True`); no row, no file (by design; the fault path itself is not simulated: a gap, see 8.3) |
| the clerk | `q` of 201 characters, page 0, page size 101 | `report_search_length`, `page_out_of_range` before the report is built |
| the clerk | a period of 368 days, a future period, `to` before `from`, one day only | the four codes in order; `to` cut to today; a period of 367 days accepted |
| the accountant | Net by vehicle against each vehicle report; the target's reached and against; the cash book's running opening | equal to the cent (DB tests) |
| the accountant | the Revenue export of an unfinished week | `Target to date`, future days blank, `Missing` for passed days |
| the operator | the module chain, `ruff`, `mypy`, `pip-audit` | section 6 |

### 8.3 Findings

| # | Finding | Severity | State |
|---|---|---|---|
| 1 | Search words match any cell containing them: `Oct 2026` matches every dated row, `8` matches `KDA 482M`. The .NET rule (RP-13) says the same (every word must appear in the row), so this is the contract, not a bug; noted because a user searching `6 Oct 2026` gets every row of October. | low | kept; the test asserts the ISO form narrows and the words form does not |
| 2 | The transaction-failure path after the audit row (a writer failure in Python leaves a row for a file never delivered) is by design (`docs/12` 2.8) and not simulated by a test. | low | left for later (a test with a writer that raises, asserting the row stays) |
| 3 | No 10x measurement of the fleet builders. | medium | left for later, section 9 item 1 |

## 9. Left for later

1. `docs/perf/reports.md`'s `EXPLAIN (ANALYZE, BUFFERS)` run at 10x: the exact statements and the
   seeding are in that file; run on a clone of `xcode_template_08br` (or the next template) as
   `xcode_owner`, record the medians into its budget table, and replace the budgets that do not
   hold. The builders are set-based, but `revenue.vehicle_days` over 500 vehicles and 367 days is
   183,500 rows and is the number to confirm.
2. A unit test for the audit-row-without-a-file path (finding 2): a `ReportFileWriter` that
   raises after `ExportReport` ran the routine; assert the change-log row stays and the HTTP
   answer is a 500 problem.
3. The shared full run and the CLI `xcode` database steps (B8 items 2 and 3) are the
   coordinator's after the three parts land.
