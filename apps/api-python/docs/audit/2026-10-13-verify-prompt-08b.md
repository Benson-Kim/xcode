Superseded by docs/audit/2026-10-14-verify-prompt-08b.md

# Verify: prompt 08b (expenses, reports, exports, day capture, scheduled runs)

`docs/prompts/verify.md` with `SCOPE: prompt:08b`, `MODE: fix`, `DEPTH: standard`; session revenue-90 [ca8ec1], which
wrote none of 08b. Started 14:17 on 2026-10-13 under the FREEZE of queue row 9 (the coordinator's 08b full run): read
and prepare only until that run ended. **Draft: sections marked "pending" fill in after the freeze.**

## 1. Verdict

Pending (the full run and the prepared tests). Read-only pass so far: no blocker, no major; 3 minor, 3 notes.

## 2. Thesis and claims

Thesis: 08b's D1 to D7 carry the .NET behaviour of drift rows 1 to 5, 8 and 14 and the B18 saving model; tenancy,
money and concurrency invariants hold; no posting is summed outside SQL; exports never hold a row the caller cannot
see and each leaves an audit row.

| Claim (where stated) | Code | Verdict | Grade |
|---|---|---|---|
| Routes of drift rows 1-5, 8 with .NET method, path, tag, operation id (08b invariants) | `http/routers/{expenses,reports,revenue,setup_recurring,pettycash}.py` | holds | A (sweep against `apps/api/Api/*.cs` and `docs/06` 2.13; the route tests `test_every_*_operation_id*`) |
| Every new `api.*` routine has the tenant guard and a `docs/05` entry | 18 routines in `57_expenses`, `58_reports`, `40_setup`, `50_revenue`, `55_pettycash` | holds | A (sweep; `db verify` tenant-guard check) |
| Split purchases never lose or invent a cent | `expenses.check_purchase` | holds | A (read: equal shares only when exact to 3 dp and each line rounds to the typed amount, else one line per allocation; sum checked against `round(units * unit_amount, 2)`; `test_a_split_never_loses_or_invents_a_cent`) |
| A retried purchase answers its rows, also under two connections | `api.expenses_entry_create`, `expenses.retried` | holds | A (advisory lock, then `retried` in a later statement; `uq_entries_group_vehicle`; `test_two_connections_recording_one_purchase_make_one_set_of_rows`) |
| A held run is decided once, whichever writer completes its window | `setup.decide_saving_runs` | holds | A (advisory lock per vehicle, then the insert as a new READ COMMITTED statement; `test_two_connections_deciding_one_run_store_one_row` proves the late writer blocks and the run is decided) |
| Vehicle update and restore decide the runs they complete (`docs/05` 11, row of `api.setup_vehicle_update`/`_restore`) | `setup_vehicle_update.sql:151`, `setup_vehicle_restore.sql:71` | unproven until the prepared tests run | pending |
| Day save: all or none, 500 limit, visibility before any row, re-raise with code and detail, 409 names the vehicle | `api.revenue_day_save` | holds | A (read; `tenancy.refuse` is the only raise site and always writes JSON detail; `test_revenue_day*.py`) |
| Day save of 500 rows fits the 5 s statement timeout at 10x | same | unproven | pending (measurement) |
| Exports: no hidden vehicle, cap before the file, formula text stays text, audit row | `58_reports/*_export_get.sql`, `infra/exports/*` | holds | A (`write_string` path with every `strings_to_*` off and a quote prefix; PDF by `drawString`, no markup; `test_a_scoped_viewers_export_holds_no_hidden_vehicle`, `test_an_export_past_the_row_bound_*`) |
| File names and content types as .NET | `reports.document`, `http/responses.py:file_response` | holds | A (`ReportUseCases.cs:80`; header name sanitised, `filename*` percent-encoded) |
| Reports cut to the viewer's vehicles and floats | `reports.build`, `reports.vehicles`, `pettycash.visible_holders`, `pettycash.entry_visible` | holds | A (every fleet builder reads `reports.vehicles`; `test_a_scoped_viewer_sees_no_hidden_vehicle_in_any_figure`, `test_petty_cash_reports_follow_the_floats_a_person_may_see`) |
| Search text cannot widen a match | `expenses_ledger_get`, `ledger_rows`, `entry_matches`, `reports.row_matches` | holds | A (backslash, `%`, `_` escaped; reports use `position()`) |

## 3. Findings

| id | mode | claim attacked | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| V-D3-1 | pre-mortem | "a decision is stored once and never changes", `setup.saving_runs.version_id` is "the version in charge on run_on" (`docs/04` 14.3) | a saving's run due today is decided, then the item is revised today: the new version is in charge of today, `setup.scheduled_runs` posts its share amount with the old decision; the stored `amount` and `version_id` disagree with what every screen shows | `scheduled_runs.sql` (state from `saving_runs`, amount from the current share); no reader reads `saving_runs.amount` | savings never backdate (`save_recurring` effective from the business date), so only the run of the revise day is exposed; every screen reads the same helper, so they agree with each other | survives, minor | for the user: keep (the posted amount follows the version in charge) and say so in `docs/04` 14.3, or post `saving_runs.amount` for a decided run |
| V-D3-2 | dialectic | an opening balance belongs to the share vehicles (`recurring_opening_vehicle`) | a revise that drops vehicle V and sends no opening keeps V's opening in the balance; the same revise sending the opening it read is refused unless V's amount is dropped, which removes it from the balance | `save_recurring.sql` (validation only when `p_opening` is an object); `saving_balance.sql` | the balance keeping a departed vehicle's opening matches how its past saved runs stay; the defect is only that the outcome depends on what the client sends | survives, minor | open question with default: keep the opening of a departed vehicle in both cases (accept it in the validation when it is stored already) |
| V-D10-1 | falsification | vehicle update and restore decide runs (stream C report 9 lists the missing test) | no test at any level fails if either call is removed | grep of `tests/` | none found | survives, minor | tests prepared (section 7) |
| V-D4-1 | Socratic | `docs/06` 2.13: "lists its 400, 403, 404 in the OpenAPI document" | `GET /setup/recurring/{id}/runs` declares 403 and 404; a malformed `{id}` answers 400 | `setup_recurring.py:158` | the other routes the sweep named take no id and never answer 404, so they list what they answer | pending | check against the generated document after the freeze |
| N-1 | note | audit row per export | the routine commits the audit row before the writer builds the file; a writer failure leaves "Exported ..." in history with a 500 | R's report finding 2 | owned by the coordinator after the run (plan Part D) | note | residual risk, coordinator |
| N-2 | note | performance at 10x | the year ledger and `fleet_postings` (1.1 to 1.4 s quiet) | `docs/perf/*.md` | measured by the build; not re-measured here | note | residual risk recorded by the build |
| N-3 | note | the 500-row day save runs one `BEGIN ... EXCEPTION` block per row | 1,000 subtransactions per call; past 64 per transaction other sessions' snapshots consult `pg_subtrans` | `revenue_day_save.sql` (two loops with handlers) | pending the measurement | note | pending |

## 4. Per domain

- D1 tenancy and authorization: no finding. Hardest attacks: another organization's vehicle id in a day save (404
  before any row, `setup.fleet_vehicles` cut by organization, API test 284); a scoped viewer's export and report
  figures (every builder reads `reports.vehicles`); a purchase id another organization uses (`pk_entries` is
  `(organization_id, id)`, test 727). Parity conceded: the ledger lists approved petty-cash purchases with holder names
  to `expenses.view`, as .NET does (`CentralExpenseRepository.cs:37-47`).
- D3 integrity and concurrency: V-D3-1, V-D3-2. Lock orders: the day save (vehicle `FOR SHARE`, record `NOWAIT`,
  advisory lock, by ascending vehicle id), `save_recurring` (item `FOR UPDATE`, vehicles `FOR SHARE` in id order,
  advisory locks in id order), vehicle update and restore (vehicle `FOR UPDATE`, then one advisory lock) take no pair
  in opposite orders. A concurrent move of two group rows to one vehicle hits `uq_entries_group_vehicle`, mapped to
  409 (`db/errors.py:38`).
- D4 contract parity: V-D4-1 (pending). Drift: `apps/api` and `tests/api` unchanged since `ac2f9a0`, whose .NET content
  the inventory lists (`20261010194310_RecurringPauses`, `ScreenExports.cs`, `RecurringPauseTests.cs`).
- D5 domain and time: no clock call in the scope routines (sweep); savings never backdate.
- D6 database craft: no dynamic SQL; every `SECURITY DEFINER` routine pins `search_path` (sweep).
- D7 performance: pending (day save at 10x).
- D9 supply chain: not re-checked; the build ran `pip-audit --require-hashes` on both locks.
- D10 tests as evidence: V-D10-1; no skip, xfail or sleep in the scope tests (sweep). Some `Raises:` codes are tested
  in their helper's module only (`not_member`, `time_zone_invalid`, the petty-cash period codes on
  `api.pettycash_export_get`).
- D11 documents: pending with the fixes.

## 5. Per mode

Pending (written with the results).

## 6. Conceded

- Header injection through an export name: `file_response` replaces every character outside printable ASCII, `"` and
  `\` and percent-encodes `filename*`.
- Formula injection: xlsx cells are strings with `strings_to_formulas` off and a quote prefix on formula-leading text;
  the PDF draws plain strings.
- Lost saving decisions under two writers: the advisory lock and the per-statement snapshot (test above).
- Non-JSON detail breaking the day save's re-raise: `tenancy.refuse` is the only raise site.
- ILIKE escaping: correct in all three places.

## 7. Fixes

Pending. Prepared in a scratchpad snapshot: `test_a_restore_decides_the_runs_its_away_days_complete`,
`test_a_later_joining_date_decides_the_runs_it_completes` (`tests/db/test_recurring_pause_routines.py`).

## 8. Commands and outputs

Pending.

## 9. Regressions and misses against the build reports

Read after this session's own pass: no fixed finding found broken again. The build reports listed V-D10-1 (stream C,
section 9) and N-1 (stream R, finding 2); they did not list V-D3-1, V-D3-2 or the unmeasured 500-row day save.

## 10. For the user

Pending (V-D3-1 and V-D3-2 carry a recommendation each).
