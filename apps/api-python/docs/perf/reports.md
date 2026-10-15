# Reports and exports at 10x

Budgets and the measuring command for `api.report_get` (`net`, `gaps`, `moneyOut`), the other
builders and the three screen exports (`docs/05-routines.md` 11.4), written on 2026-10-13 by the
08b build (stream R, reports and exports). The 10x `EXPLAIN (ANALYZE, BUFFERS)` run itself was
time-boxed out of the build session and is the first "left for later" item of
`docs/audit/2026-10-13-build-08b-reports.md`, done the same evening (section "The 10x run"); the command below reproduces it on a clone of the
test template seeded as `docs/perf/expenses.md` and `docs/perf/revenue.md` describe (one
organization, 10 companies, 500 vehicles, 13 months of records, central and petty-cash expenses,
scheduled costs and savings), as `xcode_owner`, after `VACUUM ANALYZE`.

## Shape of the cost

Every report is one statement: `api.report_get` enters the organization, checks the query and the
period, builds the whole table for the actor's visible vehicles (or floats), then searches and
pages it in `reports.page`. Nothing is read per vehicle:

- `net`, `target`, `gaps`: one `reports.vehicle_figures` over `ARRAY[every visible vehicle]`, which
  is one `revenue.vehicle_days` (the day series, cut to each vehicle's `setup.report_window`) and
  one `setup.fleet_postings`; `net` adds one `reports.money_out_by_main` (the same
  `fleet_postings`, grouped by main category). The day series is the dominant term: vehicles x
  days of the period (500 x 367 = 183,500 rows for the longest period).
- `moneyOut`: one `setup.fleet_postings`, grouped by item.
- `savings`: two `setup.scheduled_runs` (the period's runs; the runs since each saving began, for
  the balances) plus the opening amounts, grouped by vehicle. No `setup.saving_balance` per
  vehicle (the 10:38 note of the coordinator: `setup.vehicle_net` costs about 28 ms per call at
  10x, so a per-vehicle helper would cost 14 s for 500 vehicles).
- `investment`: money in from `revenue.records` inside each vehicle's window and one
  `setup.fleet_postings` from the earliest join date, grouped by vehicle. No `setup.vehicle_net`
  per vehicle, for the same reason.
- The petty-cash reports: one `reports.pettycash_entries` over the chosen floats (the entries with
  their names), grouped in SQL.
- The exports read the same builders without paging, cap the matching rows at 10,000
  (`reports.check_export`), and write one change-log row and one audit event in the same
  transaction. The Revenue export reads `api.revenue_week_get` itself (the legacy page of 500
  vehicles); the Central expenses export `expenses.ledger_rows` (`docs/perf/expenses.md` has its
  cost); the Petty cash export `pettycash.entry_matches`, the list's own query.

## Budgets (as `xcode_app`, the Owner, every company, one statement each)

| Call | Rows | Budget | Why |
|---|---:|---:|---|
| `api.report_get` `net`, 367 days | 500 | 2.0 s | one day series of 183,500 rows plus one postings read; the same reads the vehicle report makes for one vehicle, done once |
| `api.report_get` `gaps`, 367 days, page 1 | 500 (about 10,000 missing days) | 2.0 s | the same day series; the rows are the unnest of each vehicle's missing days |
| `api.report_get` `moneyOut`, 367 days | about 60 items | 1.5 s | one postings read grouped twice (items, main categories) |
| `api.report_get` `target`, 30 days | 500 | 0.5 s | a 30-day series |
| `api.report_get` `savings`, 367 days | 500 | 2.0 s | two `scheduled_runs` reads |
| `api.report_get` `investment` | 500 | 1.5 s | records since joining plus one postings read |
| a petty-cash report, 367 days, every float | 50 floats | 0.5 s | one entries read |
| `api.revenue_export_get`, one week | 500 | 1.0 s | the week grid's own cost plus the document |
| `api.expenses_export_get`, 30 days | about 7,800 | 2.0 s | `expenses.ledger_rows` (1.4 s at 10x, `docs/perf/expenses.md`) plus the document |
| `api.pettycash_export_get`, 367 days, every float | at most 10,000 | 1.5 s | the list's query without a page |

The HTTP route adds the file: XlsxWriter writes 10,000 rows of 10 columns in about 0.4 s and
ReportLab draws them in about 1.5 s on this laptop (`tests/unit/test_export_files.py` builds 60
rows in under 0.1 s); both run in a worker thread (`asyncio.to_thread`), so they never hold the
event loop. The role's statement timeout bounds the routine; the row cap bounds the file.

## The command

On a disposable clone of the test template (`CREATE DATABASE xcode_perf_08br TEMPLATE
xcode_template_08br`), seeded by the scratch script of `docs/perf/expenses.md` with the savings
of `docs/perf/scheduled-and-day.md` added, then `VACUUM ANALYZE`:

```sql
SET ROLE xcode_app;
SELECT tenancy.enter_organization(:actor, :org, 'perf', 'reports.view');
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT api.report_get(:actor, :org, 'perf', 'fleet', 'net', :today - 366, :today,
                      NULL, NULL, NULL, 1, 50, now());
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT api.report_get(:actor, :org, 'perf', 'fleet', 'gaps', :today - 366, :today,
                      NULL, NULL, NULL, 1, 50, now());
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT api.report_get(:actor, :org, 'perf', 'fleet', 'moneyOut', :today - 366, :today,
                      NULL, NULL, NULL, 1, 50, now());
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT api.revenue_export_get(:actor, :org, 'perf', :today - 6, NULL, 'xlsx', now());
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT api.expenses_export_get(:actor, :org, 'perf', :today - 29, :today, NULL, NULL, 'xlsx', now());
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT api.pettycash_export_get(:actor, :org, 'perf', :today - 366, :today, NULL, 'expenses',
                                NULL, NULL, 'xlsx', now());
```

`:actor` is the Owner's user id, `:org` the organization, `:today` its business date. The plans
of the helpers inside a plpgsql routine do not show in the outer plan: for them, run the same
statements with `auto_explain` (`LOAD 'auto_explain'; SET auto_explain.log_min_duration = 0;
SET auto_explain.log_nested_statements = on; SET auto_explain.log_analyze = on;`) and read the
server log, as `docs/perf/revenue.md` did. Record the median of five calls per row of the budget
table, and the plan of the day series and of `setup.fleet_postings` once.

## The 10x run (2026-10-13)

Run at 22:15 on a quiet test cluster (no other connections) against `xcode_perf_08bo`: a clone of the
08b template at `0014`, seeded as above (500 vehicles, 184,193 revenue records, 65,951 central and
28,322 petty-cash entries, 1,500 saving shares, 44,640 decided runs), then `VACUUM ANALYZE`. One
connection as `xcode_app`, six calls per row, the first dropped; the median and max are of the other
five. Buffers are of one `EXPLAIN (ANALYZE, BUFFERS)` of the same call (the outer plan only).

| Call | Rows | Median ms | Max ms | Buffers (shared hit / read) | Budget | Before the 20:38 fixes (median ms) |
|---|---:|---:|---:|---|---:|---:|
| `api.report_get` `net`, 367 days | 500 | 5,641 | 6,308 | 396,626 / 0 | 2,000 | 13,648 |
| `api.report_get` `gaps`, 367 days, page 1 | 12,031 | 4,205 | 4,332 | 293,926 / 0 | 2,000 | 5,189 |
| `api.report_get` `moneyOut`, 367 days | 20 | 1,944 | 2,088 | 102,743 / 0 | 1,500 | 8,922 |
| `api.report_get` `target`, 30 days | 490 | 791 | 888 | 41,700 / 0 | 500 | 608 |
| `api.report_get` `savings`, 367 days | 408 | 3,689 | 3,894 | 556,935 / 0 | 2,000 | 5,448 |
| `api.report_get` `investment`, as at today | 500 | 776 | 842 | 20,275 / 0 | 1,500 | 3,313 |
| `api.report_get` `cashBook`, 367 days, every float | 362 | 783 | 819 | 923 / 0 | 500 | 3,244 |
| `api.report_get` `managers`, 367 days, every float | 1 | 838 | 849 | 923 / 0 | 500 | 3,326 |
| `api.report_get` `items`, 367 days, every float | 20 | 681 | 786 | 923 / 0 | 500 | 3,235 |
| `api.report_export_get` `net`, 367 days | 500 | 5,660 | 5,730 | 396,674 / 0 | (as `net`) | 13,374 |
| `api.report_export_get` `gaps`, 367 days | refused: `export_too_many_rows` | 4,314 | 4,366 | refused | (as `gaps`) | 5,088 |
| `api.revenue_export_get`, one week | 490 | 316 | 333 | 6,060 / 0 | 1,000 | 355 |
| `api.expenses_export_get`, 30 days | 7,749 | 531 | 556 | 21,891 / 0 | 2,000 | 1,037 |
| `api.pettycash_export_get`, 367 days, every float | refused: `export_too_many_rows` | 1,877 | 1,959 | refused | 1,500 | 4,216 |

The "before" column is the same script on the same clone at 20:24, before the fixes of
`docs/audit/2026-10-13-build-08b.md` section 11. Every answer was fingerprint-equal before and after.

Within budget: `investment` and the three screen exports apart from Petty cash. Over budget:
`net`, `gaps`, `savings`, `moneyOut`, `target`, the petty-cash reports and the Petty cash export
(which refuses past the row cap only after counting the year's entries). This seed is a worst case:
a daily saving on every vehicle and 13 months of records, so the day series and the scheduled runs
are both at their largest. `target` (30 days) got about 180 ms slower: it now reads `setup.fleet_totals`
as well as the day series. The next lever for `net`, `gaps` and `savings` is a summing form of the day
series (totals per vehicle without building 183,500 day rows) or stored daily totals.

Against the role's 5 s statement timeout (noted by the 08b verify, 14 Oct): `net` over 367 days at this
size (5.6 s median, 6.3 s max, and its export as long) is cancelled, so that request answers 500;
`gaps` (4.2 s) and `savings` (3.7 s) are within 1.3 s of it. `docs/12-security.md` section 7.

## 14 Oct: the day figures summed in place

Built at the user's request in the 10b verify (`docs/audit/2026-10-14-verify-prompt-10b.md`). The
script and seed are the 10x run's (`xcode_perf_vnet`: 500 vehicles, 184,106 revenue records, the
same expense, petty-cash and saving shapes). It ran as `xcode_app` on a quiet cluster: six calls
each, the first dropped. The answers before and after are byte-identical.

| Call | Before median ms | Before max ms | After median ms | After max ms |
|---|---:|---:|---:|---:|
| `api.report_get` `net`, 367 days | 3,669 | 4,170 | 2,822 | 3,385 |
| `api.report_get` `gaps`, 367 days, page 1 | 2,656 | | 1,923 | 1,965 |
| `api.report_get` `savings`, 367 days | 2,884 | | 1,933 | 2,057 |

The "before" is the tree of 14 Oct, run the same afternoon. It is faster than the 13 Oct run above
on the same seed: the load on the laptop differs between the two days, so compare within a row,
not across days.

The changes:

- **`reports.vehicle_figures` no longer builds the day series.** Inside a vehicle's report window
  a day is in the fleet unless away. So the day figures come straight from the away periods, the
  target set in force and the record: a `generate_series` per window, with one LEFT JOIN each.
  `revenue.vehicle_days` built every day of the period, with its rules, then cut it to the window.
  `tests/db/test_revenue_helpers.py::test_the_report_figures_sum_the_day_series_inside_each_vehicle_s_window`
  holds the two forms equal on a seeded random fleet.
- **`setup.scheduled_runs` reads the organization once per statement.** It used the inlined
  `tenancy.current_organization()` as a filter, which is evaluated per row; it now uses a scalar
  subquery. Its four filters are unchanged otherwise.

What is left in `net` (as the executor, one transaction):

| Part | ms |
|---|---:|
| `reports.vehicle_figures` | 1,740 |
| `setup.fleet_totals` (inside it) | 730 |
| `reports.money_out_by_main` | 900 |

`setup.scheduled_runs` is read twice, once through `fleet_totals` and once through
`money_out_by_main`. A version of `money_out_by_main` that summed per item before joining the
names gave 2,888 ms against 2,822 ms, so it was not kept.

Next levers:

- **The row-level-security policies.** They read `tenancy.current_organization()` per row.
  Written as `(SELECT tenancy.current_organization())`, they read it once per statement. On the
  clone the records scan fell from 662 ms to 66 ms and `savings` to about 1.6 s. This needs a
  migration and a change to `db verify`'s expected policy text.
- **One `scheduled_runs` read for `net`.**
- **Stored daily totals.**
