# Central-expenses ledger at 10x

Timings and plans for `api.expenses_ledger_get` (`docs/05-routines.md` 11.2 and 11.7), measured on
2026-10-13 by the 08b build (central expenses). The route is two statements however many rows the
period holds (`tests/api/test_expenses.py::test_the_ledger_reads_with_two_statements_however_many_rows`,
5, 150 and 300 rows); this file is the cost of that one statement.

## Seed

The demo seed (`api.ops_seed_demo`) has 50 vehicles and six weeks of history; this seed is ten
times its fleet over 13 months, in one organization, as `xcode_owner` in a disposable clone of the
test template (`xcode_perf_08be`, dropped after), followed by `VACUUM ANALYZE`. The script is kept
with the build report's scratch files (`perf_expenses.py`, `perf_layers.py`); its rows:

- 10 companies, 500 vehicles joined 2025-09-01 (one in ten later, one in fifty left 30 days back),
  each with a fleet number; 5 categories with 4 items each.
- 65,951 central expenses: one every third day per vehicle, one in fifty removed.
- 28,322 approved petty-cash expenses: one a week per vehicle.
- 20 monthly scheduled costs, each shared by 50 vehicles (1,000 shares).

A 367-day ledger over every vehicle therefore holds 96,774 rows (central 58,845, petty cash about
26,000, scheduled about 11,900).

## Conditions

- Business date 2026-10-09. The caller is the Owner (every company, both expense rights); page 1
  of 100 unless stated.
- PostgreSQL 16 on Windows 10, local, `shared_buffers` 128 MB, `work_mem` 4 MB; the 4-core laptop
  shared with two other build sessions' test runs, so absolute figures vary by a factor of about
  two between runs. Compare within a table.

## The route, end to end (median of 5 calls, as `xcode_app`)

| Period and filter | Rows matching | Rows on the page | Median (ms) | Max (ms) |
|---|---:|---:|---:|---:|
| 1 day, page size 5 | 75 | 5 | 358 | 365 |
| 1 day, page size 100 | 75 | 75 | 354 | 471 |
| 7 days | 1,817 | 100 | 604 | 768 |
| 30 days | 7,765 | 100 | 1,451 | 1,713 |
| 30 days, page 30 | 7,765 | 100 | 1,353 | 1,445 |
| 367 days | 96,774 | 100 | 10,230 | 10,769 |
| 367 days, central only | 58,845 | 100 | 10,400 | 12,310 |
| 367 days, search `KAB` | 172 | 100 | 7,549 | 9,787 |
| 367 days, a search that matches nothing | 0 | 0 | 5,531 | 6,594 |

The page number and page size cost nothing measurable: the work is reading the period's rows,
which the figures need whatever the filter (CE-18).

## Each layer (median of 3, same seed, a quieter moment)

| Layer | 1 day | 7 days | 30 days | 367 days |
|---|---:|---:|---:|---:|
| `setup.report_window` over the 500 vehicles | 23 | 16 | 21 | 19 |
| `setup.scheduled_runs` | 332 | 489 | 246 | 347 |
| `setup.fleet_postings` | 354 | 422 | 547 | 3,952 |
| `expenses.ledger_rows` | 346 | 384 | 603 | 4,204 |
| `api.expenses_ledger_get` | 377 | 452 | 792 | 5,199 |

- `setup.fleet_postings` (the shared posting helper every report reads) is the cost: about 350 ms
  of fixed work (the scheduled runs of every share) plus about 37 ms per thousand postings.
- `expenses.ledger_rows` adds the registration, fleet number and the two names: about 250 ms at
  96,774 rows.
- `api.expenses_ledger_get` adds the figures, the count and amount of the matching rows and the
  sorted page: about 1 s at 96,774 rows (one sort of the materialised rows by day, source,
  registration and id).

## The plan of the 367-day call

From `auto_explain` with nested statements (`log_analyze`, `log_buffers`; its instrumentation
roughly doubles the nested timings, so read the shapes, not the milliseconds):

- `setup.fleet_postings`: the vehicles' windows once (a CTE of 500 rows); central expenses by a
  sequential scan of `expenses.entries` (64,664 rows not removed) hash-joined to the windows with the
  `span @> entry_date` join filter; the approved petty-cash expenses likewise (28,322 rows); the
  scheduled runs from `setup.scheduled_runs`; each branch joined to the item, category and main
  category tables (20, 5 and 0 rows) by nested loops over a materialised scan, a cheap choice at
  these sizes although the estimate is 26 rows where 58,845 come.
- `expenses.ledger_rows`: one hash join to `setup.fleet_vehicles` and two to
  `tenancy.memberships` over the materialised postings.
- `api.expenses_ledger_get`: the materialised ledger rows scanned for the figures, the count and
  amount, and one sort for the page.

A 367-day period over a whole 500-vehicle fleet reads every row of the year (CE-18's figures
cover the period whatever the filter), so the sequential scans are the right plan for it; the
indexes `ix_entries_vehicle_date` and `ix_entries_date` serve the short periods and scoped viewers.

## After the posting helpers' rewrite (2026-10-13 10:38)

The stream that owns `setup.fleet_postings` and `setup.scheduled_runs` rewrote both: due days are
computed once per version over its shares' windows (20 walks in this seed instead of 1,000), and
the stored branches take date bounds the vehicle and date indexes can use. Its measurement, with
`perf_layers.py` on its own clone of the same seed, on a loaded machine (absolutes high; compare
within the table), median of 3 at 367 days:

| Layer | Before (ms) | After (ms) |
|---|---:|---:|
| `setup.scheduled_runs` | 1,101 | 370 |
| `setup.fleet_postings` | 5,506 | 1,795 |
| `expenses.ledger_rows` | 9,625 | 3,410 |
| `api.expenses_ledger_get` | 12,100 | 6,924 |

The route after it, same conditions: 570 ms for 1 day, 380 ms for 7, 685 ms for 30. What is left
of `fleet_postings` is mostly materialising about 96,000 rows (its central branch alone takes
122 ms). Of the route's 6.9 s, about 1.6 s is `expenses.ledger_rows` over the postings (the
registration, fleet number and two names) and about 3.5 s the route's figures, count, amount
and sort.

## The page-only route (2026-10-13, about 11:45)

The fix for finding 1's residual. `api.expenses_ledger_get` now reads `setup.fleet_postings` once
for the keys of every posting (source, day, vehicle, id, amount, registration and whether the
query matches). The figures, count, amount and the page's 100 keys are cut from those keys. Only
the page's rows are built, through `expenses.ledger_rows` over the page's vehicles and days.
`expenses.ledger_rows` itself is unchanged, so the export and the saved row still read it. The
order's last key is the row id as a uuid (a uuid sorts as its text does, ordinally), then the
vehicle (a scheduled row's id is its item, day and vehicle).

Same seed, a quieter machine (another session's full run stopped). Each route is called in its own
session, 2 warm-up calls then 3 timed, over 3 sessions; median of the 9 (ms):

| Period | Before | After |
|---|---:|---:|
| 1 day (74 rows) | 170 | 271 |
| 7 days (1,813 rows) | 209 | 295 |
| 30 days (7,767 rows), page 1 | 338 | 382 |
| 367 days (96,721 rows), page 1 | 2,138 | 1,706 |
| 367 days, page 900 | 2,779 | 1,836 |
| 367 days, search `KAB` (174 rows) | 2,348 | 2,120 |

- **The answers are unchanged.** Both routes, called on the clone in 9 cases (1, 7 and 30 days,
  30 days page 30, 367 days pages 1 and 900, `central`, `KAB`, a search matching nothing), gave
  equal documents. `tests/db/test_expense_routines.py::test_every_page_is_the_ledger_rows_helper_cut_in_the_ledgers_order`
  checks the same for every page of two viewers under seven filters. With the page cut ordered
  without the registration, that test failed and the older page test passed.
- **What is left at 367 days** is mostly the posting helper: `setup.fleet_postings` over the 500
  vehicles alone takes 1,127 to 1,368 ms (median of 5). The route adds about 0.3 s: the key pass,
  the figures and the top-100 sort. Building the page's rows adds 50 to 100 ms.
- **The price on short periods is the second, small postings call** for the page's rows, which
  costs about 50 to 100 ms at this scale. The helper's cost there is per vehicle (each vehicle's
  window and schedule shares), so it shrinks with the fleet.
- **A single-call variant was measured and dropped.** It read the postings once, kept every
  column, and built only the page's rows in the route: 162, 191 and 355 ms on 1, 7 and 30 days,
  but 2,356 ms at 367 days and 2,871 ms on page 900. Keeping 96,000 wide rows costs what building
  them did, and it would have repeated the row formulas of `expenses.ledger_rows` in the route.
- **Load still matters.** Earlier in the same session, with the processor at 100% from other
  sessions' suites, the year took 3.6 to 5.0 s after the fix against 4.7 to 5.7 s before (the
  same calls, interleaved). With a larger `work_mem` (32 MB, session only) both routes ran about
  3.2 s under that load: much of a loaded year's cost is spilling wide intermediate rows to disk.
  `work_mem` is the server's and was left alone.

## Findings

1. **A year's ledger over a 500-vehicle fleet can still exceed `xcode_app`'s 5 s
   `statement_timeout` on a loaded machine.** The route then answers 500: SQLSTATE 57014 is
   neither a refusal nor transient in `db/errors.py`, so it is reported as an unexpected
   database error. Before the rewrite, `setup.fleet_postings` was most of the cost (about 4 s
   quiet for 96,774 postings); it was raised with the stream that owns the posting helpers
   (board section 4, 2026-10-13 10:05) and fixed there (5.5 s to 1.8 s loaded). The residual is
   the ledger's own: `expenses.ledger_rows` and the route's figures and sort, about 5 s loaded
   at 367 days. Periods up to 30 days answer in under 0.7 s even loaded. Fixed the same day by
   the second option the build report listed: the figures, count and page are read from a narrow
   row set and only the page's rows are built (section "The page-only route"). 367 days now takes
   1.7 s quiet (2.1 s before) and page 900 takes 1.8 s (2.8 s). Short periods pay 50 to 100 ms
   for it. Under heavy load a year can still come near the timeout. What is left is mostly the
   posting helper's, at about 1.1 to 1.4 s quiet for 96,000 postings.
2. The fixed cost of `setup.scheduled_runs` (about 350 ms quiet on every call, even a one-day
   one) came from walking the due days of every share before the window cut them. The rewrite
   walks once per version: 370 ms at 367 days loaded, against 1,101 ms before it under the
   same load.
