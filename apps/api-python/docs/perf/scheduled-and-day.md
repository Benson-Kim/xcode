# Scheduled runs, postings, the scheduled-item summary and the day read at 10x

Timings for the posting helpers every figure reads (`setup.scheduled_runs`, `setup.fleet_postings`,
`docs/05-routines.md` 11.1) and for the stream-C routes of 08b (`api.setup_recurring_summary`,
`api.setup_recurring_list`, `api.revenue_day_get`; 11.3 and 11.5), measured on 2026-10-13. Each route
is two statements whatever the data (`tests/api/test_recurring_pause.py`, `test_revenue_day.py`); this
file is the cost of that one statement.

## Seed

The seed of `docs/perf/expenses.md` (10 companies, 500 vehicles, 65,951 central expenses, 28,322
approved petty-cash expenses, 20 monthly scheduled costs over 1,000 shares), in a disposable clone of
the build's private template (`xcode_perf_08bc`), `VACUUM ANALYZE`d. The machine ran other sessions'
test suites at the time, so the absolute figures are high; compare the columns, not other files.

## The posting helpers, before and after the rewrite (median of 3, ms)

Before: one due-day walk per share (1,000 walks) and a range-containment predicate the vehicle and
date index could not use. After: one walk per version over the union of its shares' windows, cut to
each share's window, and `entry_date >= lower(span) AND entry_date < upper(span)` on the stored rows.

| Layer | 1 day | 7 days | 30 days | 367 days |
|---|---:|---:|---:|---:|
| `setup.scheduled_runs`, before | 507 | 751 | 747 | 1,101 |
| `setup.scheduled_runs`, after | 110 | 98 | 114 | 370 |
| `setup.fleet_postings`, before | 776 | 675 | 1,080 | 5,506 |
| `setup.fleet_postings`, after | 246 | 266 | 250 | 1,795 |
| `expenses.ledger_rows`, before | 588 | 1,059 | 1,407 | 9,625 |
| `expenses.ledger_rows`, after | 184 | 221 | 450 | 3,410 |
| `api.expenses_ledger_get`, before | 902 | 1,685 | 3,085 | 12,100 |
| `api.expenses_ledger_get`, after | 570 | 380 | 685 | 6,924 |

At 367 days `fleet_postings` returns 96,743 rows (58,814 central, 26,038 petty cash, 11,891 scheduled);
the central branch alone is 122 ms, so what remains is mostly the rows themselves passing through the
function. A 367-day ledger at ten times the demo fleet can still exceed `xcode_app`'s 5 s statement
timeout on a loaded host (residual, the ledger's own report).

`setup.vehicle_net` costs about 28 ms a vehicle (50 calls: 1.3 to 1.5 s): fine for one vehicle's report
or investment, never for a loop over a fleet (the fleet reports read `fleet_postings` once).

## The stream-C routes (median of 3, ms)

| Route | ms |
|---|---:|
| `api.setup_recurring_summary` (the month; 20 items, 1,000 shares) | 1,058 |
| `api.setup_recurring_list` (first page of 25) | 236 |
| `api.revenue_day_get` (500 vehicles, today) | 120 |

The summary walks the month twice (`scheduled_runs` to the month's end for the costs, to today for the
savings) and adds one `setup.saving_balance` per saving the caller sees.

Command (scratch script beside the build report's files): `perf_layers.py <out> <dir>` with the clone
kept, then the three routes as `xcode_app` with `statement_timeout` 60 s.

## The day save at 500 rows (2026-10-14)

Measured by the 08b verify (`docs/audit/2026-10-14-verify-prompt-08b.md`): the day-save test world
(`tests/db/test_revenue_day_routines.py`, `yard`) multiplied by `tests/support/scenario.py`
`seed_10x` to 600 vehicles, no scheduled items, `ANALYZE`d; one `api.revenue_day_save` of 500 rows as
`xcode_app` (its role timeout is 5 s; lifted to 120 s for the measurement), on the laptop while other
sessions ran test modules.

| Call | s |
|---|---:|
| 500 new records | 18.9 |
| the same 500 rows again (identical replays) | 7.6 |
| 500 corrections with their versions | 15.7 |

With the role's 5 s timeout the first call is cancelled. Per function (`track_functions = 'pl'`, one
500-row capture, 13.7 s that time): `revenue.capture_entry` 7.0 s of its own statements,
`setup.decide_saving_runs` 2.1 s, `tenancy.record_change` 1.4 s, `tenancy.check_writable` 1.0 s,
`tenancy.business_date` 0.9 s (three calls a row), `setup.vehicle_active_on` 0.5 s. Without the
decision call the capture still took 17.4 s: the cost is the per-row steps, not one statement.
Open question 101 and `docs/12-security.md` section 7.

## The day save at 500 rows, set-based (2026-10-14, later)

Built at the user's request in the 10b verify (`docs/audit/2026-10-14-verify-prompt-10b.md`):
`api.revenue_day_save` reads the actor's rights, the low-day threshold, the business date and the
earliest writable date once per call and passes them to `revenue.capture_row` (the single capture's
steps; `revenue.capture_entry` is now that routine with each value worked out per row). The loop is
one subtransaction, not two per row: `capture_row` locks the record `FOR UPDATE SKIP LOCKED` (a record
that exists but was skipped is held by another save) and inserts `ON CONFLICT DO NOTHING` (no row
back is the losing first capture). The saving runs are decided once, after the loop, by
`setup.decide_fleet_saving_runs`.

Same world and call as above, timeout lifted for the measurement, on a quiet cluster (no other
session's job), two runs each:

| Call | Before (s) | After (s) |
|---|---:|---:|
| 500 new records | 7.7, 8.5 | 1.46, 1.39 |
| the same 500 rows again (identical replays) | 5.3, 2.8 | 0.44, 0.40 |
| 500 corrections with their versions | 9.4, 5.6 | 1.69, 1.22 |

With my other test modules running beside it, the build before the subtransaction change took
2.9 to 3.4 s to capture and 3.4 to 3.5 s to correct. Without the per-row subtransaction, under the
same load, it took 2.4 s and 2.5 s. Per function, for a 3-row save: `tenancy.effective_permissions`
1 call (was 4), `setup.scheduled_runs` 1, `tenancy.earliest_writable` 1,
`tenancy.business_date` at most 2. `tests/db/test_revenue_day_routines.py` holds both: the 500-row
save under the role's own 5 s timeout, and the once-per-call counts.
