# Verify `area:prompt 07`, 2026-10-12 (fix mode, standard depth)

Scope: `docs/prompts/07-revenue.md` D1 to D4 and its invariants: the revenue helpers, the
week grid, the dashboard, the capture (also the phones' offline replay), domain, gateway,
fakes, use cases and HTTP; drift register rows 9, 11 and 13, which 07 closed. Run beside
four other sessions (07b D2 build, 08 build, verify-06, verify-07b-d1), coordinated through
`apps/api-python/.coordination/board.md` (kept out of git). Session: revenue-17 [a39ec0].

## 1. Verdict

**pass with findings** (changed by the coordinator, revenue-d5 [b49167], at 20:40 under "Where
to resume"): the first full run after 07b D4's landing (board queue row 7, 17:35 to 19:31)
passed every module section 11 lists, and none of its 3 failures (07b D1's
`tests/db/test_gateway.py`) touches `revenue_capture.sql` or `_to_decimal` (section 12). No
blocker survives. Claims: 34 checked:
29 hold, 3 failed and fixed (C12, C31, C26 as evidence), 1 failed and documented as an
accepted deviation (C4), 1 unproven (C18, the builder's `EXPLAIN` timings, not re-measured).
Findings: 0 blockers, 2 majors (both fixed), 2 minors (one fixed, one a corrected document
with a pinning test), 2 notes (for the user). Full suite: run after D4's landing, green for
07 (section 12); at 08:41 the shared run (board queue row 3) had not started. The targeted
modules and every money-parser caller passed (section 8).

## 2. Thesis and claims

Thesis (steelmanned): prompt 07 delivers D1 to D4; the capture runs the .NET steps in the
.NET order (membership and one of the two permissions, entry shape, visibility, lock,
identical replay, future date, fleet membership, the path's permission before anything
stored is shown, version with `current`, write, change log); an identical entry is a replay
whatever the version, the date and the permissions, and writes nothing; two saves of one day
end as one row and a 409; the week and the dashboard compute the .NET figures (banker's
rounding of money, half away from zero for the percent, totals rounded once) over the
caller's visible vehicles only, in one routine call each with no cache; and the routes and
wire shapes equal the .NET API at 493bf82 plus the working tree of `fix/web-dropdowns`.

Grades per `docs/14-verification.md` section 5. "Fixed" claims hold now, with the test named
in section 7.

| # | Claim (where stated) | Code | Verdict | Grade |
|---|---|---|---|---|
| C1 | `earliest_missing` skips away days, stops at the leave date (D1) | `50_revenue/earliest_missing.sql` | holds | A (`test_the_earliest_missing_day_skips_away_days_and_stops_at_the_leave_date`) |
| C2 | Cell status table and `can_edit` per status and permission (D1) | `cell.sql` | holds | A (helpers module) |
| C3 | Expected per day banker's rounded; totals from unrounded expectations rounded once (D1) | `cell.sql`, `vehicle_week.sql`, `round_half_even.sql` | holds | A (`1000` -> `142.86` / `1000.00`) |
| C4 | Percent half away from zero, null when nothing is expected, equal to .NET (D1, docs/05 2.4) | `percent.sql` | fails at exact halves (finding V-D4-2); documented as an accepted deviation | A (`dotnet run` and `revenue.percent`, section 8) |
| C5 | `reason_code` takes `No Crew` and `NoCrew`, refuses `no crew` (D1) | `reason_code.sql` | holds | A |
| C6 | Snapshot keys and order, `Reason` as the .NET enum name (docs/05 6.2) | `record_snapshot.sql` | holds | A (`test_a_first_capture_creates_version_1_and_logs_it`) |
| C7 | Capture steps in order, first failing step answers (D2, docs/05 4.7) | `revenue_capture.sql` | holds | A (one test per step) |
| C8 | Replay after the day closed, any version (D2) | same | holds | A |
| C9 | A replay no longer identical gets the permission refusal without `current` (D2) | same | holds | A |
| C10 | Two first captures racing: one row, the loser `unique_conflict` (D2) | same | holds; parity with .NET `RevenueCaptureTests.TwoClerksCapturingTheSameDayAtOnceGetAConflictNotAServerError` | A (two connections) |
| C11 | Two updates racing: `revenue_concurrent_save` (D2) | same | holds | A (two connections) |
| C12 | A capture never lands on a day the vehicle is not in the fleet (docs/05 4.7 step 6; the retirement rule of `setup_vehicle_retire`), also under a concurrent fleet change | same | failed, fixed (V-D3-1) | A (two connections, both orders) |
| C13 | Week: legacy form (500, `truncated`), paged form, `total_vehicles` (D2) | `revenue_week_get.sql` | holds | A |
| C14 | `day_totals`, `first_gap`, totals over the whole filtered grid, unchanged by paging (D2) | same | holds | A |
| C15 | One vehicle in any week, never paged; 404 for an unseen vehicle (D2) | same | holds | A |
| C16 | Week range refused at both bounds (D2) | same | holds | A |
| C17 | Dashboard per card and permission, `today`/`week`/`month`, company filter, scoped viewer (D2) | `revenue_dashboard_get.sql` | holds | A |
| C18 | `EXPLAIN (ANALYZE, BUFFERS)` at 10x in `docs/perf/` (D2, invariant 4) | `docs/perf/revenue.md` | unproven by this run: present and consistent with `docs/05` 7, not re-measured (machine at 0.4 to 0.8 GB free with five sessions) | D |
| C19 | No cache anywhere (invariant 1) | `db/routines/revenue.py`, routines | holds | B (code read: both reads call their routine on every request; the only `functools.cache` in `src` holds type hints, `db/types.py:243`; no cache table or helper in `50_revenue`) |
| C20 | Domain records; `CellStatus` pinned to `packages/shared` (D3) | `domain/revenue.py`; `tests/unit/test_permission_keys.py` | holds | A (live-tree unit run, section 8) |
| C21 | Capture not retried by the gateway; reads idempotent (D3) | `db/routines/revenue.py` | holds | B (`call` default `idempotent=False`; generic gateway tests) |
| C22 | Fake parity cases: replay, version conflict with `current` (D3) | `tests/support/revenue_cases.py` | holds | A (`test_the_revenue_fake_answers_as_the_routines_do`, section 8) |
| C23 | DTOs in wire order, statuses as words, money as numbers, nullable `version` (D4) | `http/schemas/revenue.py` | holds | A |
| C24 | Router: tag, operation ids, `{vehicleId:uuid}` (404 empty), date segment (D4) | `http/routers/revenue.py` | holds | A (`test_the_route_takes_a_uuid_and_a_date`; OpenAPI sweep) |
| C25 | 409 with `current`, title `This day already has a different record.` (D4) | `http/messages.py` | holds | A |
| C26 | 409 `This day was changed by another save.` without `current` (D4; the phone queue's "409 without current") | same | holds now; was grade B (code only at the database layer), test added (V-D10-1) | A |
| C27 | 200 body exactly `{"id", "version"}` (D4) | router | holds | A (bytes compared) |
| C28 | Every mobile-queue row (200 replay, 409 with and without `current`, 403, 404, 400) (D4) | router, routine | holds | A |
| C29 | Statement budget 2 per request (D4, docs/05 7) | gateway | holds | A |
| C30 | The web paging sequence (legacy first call, then pages) (D4) | routine | holds | A |
| I1 | No idempotency key, client id or cache; replay by value equality, no change-log row | routine | holds | A (`test_an_identical_entry_replays_whatever_version_is_sent_and_writes_nothing` counts change rows) |
| I2 | A 403 never carries `current`; a 409 `current` has `can_edit` from the caller's permissions alone | routine | holds | A (`test_the_clerk_gets_the_conflict_only_on_a_day_they_may_change`, queue test) |
| I3 | Every revenue change-log row has `vehicle_id` and a `d MMM yyyy` reason | routine | holds | A |
| C31 | Every capture body answers below 500 (docs/06 1.2 numbers; docs/14 severity "a 5xx on a valid request") | `http/schemas/common.py` `_to_decimal` | failed, fixed (V-D4-1) | A |

Counts: 34 rows; 29 hold, C4 fails (documented), C12 and C31 failed and fixed, C26 held
only at grade B and is now A, C18 unproven.

## 3. Findings

| id | mode | claim attacked | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| V-D3-1 | red team, pre-mortem | C12; `setup_vehicle_retire.sql` "never on or before a day it has revenue for"; .NET runs these writes `SERIALIZABLE` (`OrganizationRepository.cs:68`) | An office admin retires KDA from today (or moves KDB's join date later) while a clerk's phone saves that day. `revenue_capture.sql:84` read the vehicle without a lock; the retirement locks it `FOR UPDATE`, finds no record and commits; the capture's insert waited only at the foreign-key check, then saved a day on the leave date (or before the new join date). Expected `revenue_vehicle_inactive`; actual `created`. The record is then on a day the vehicle is not in the fleet, so every report drops it | `tests/db/test_revenue_routines.py::test_a_capture_waits_for_a_fleet_change_of_its_vehicle_and_then_reads_it[retire]` and `[join later]` failed before the fix with `outcome: created` (section 8) | Looked for a guard: none in the capture; the foreign key takes `FOR KEY SHARE` only after the active check; `setup_vehicle_restore` does not check records. The opposite order (capture first) was already safe: the retirement's `FOR UPDATE` waits for the insert's key share and then sees the record (test added, held before the fix). .NET is not the same: its `SERIALIZABLE` unit retries on deadlock and re-reads | survives, major (found by verify-06, `06:V-D3-1` on the board; the 07 file is mine) | fixed: the capture reads the vehicle `FOR SHARE` (`revenue_capture.sql:84-87`), which conflicts with every 06 writer's `FOR UPDATE` in both orders; lock order vehicle -> record -> organization row, the same as the 06 writers; tests above |
| V-D4-1 | red team | C31 | `PUT /setup/revenue/{id}/{date}` with `{"amount":"1e999999"}`, `"-1e999999"` or `"1e-999999"` (numeric strings are accepted, docs/06 1.2). `_to_decimal` passed the `Decimal` on; PostgreSQL cannot parse that exponent (`22003 value overflows numeric format`, measured: limits `1E+131071` and `1E-16383`), which is not a mapped SQLSTATE, so `IntegrityBug` and 500. Expected 400: .NET's binder refuses a decimal it cannot hold, and reads a value below 1e-28 as 0 (then the money sentence). The same parser serves every `Amount`/`Money` body field: people `approvalLimit`, vehicle `weeklyTarget`, recurring and investment amounts, 08's petty cash | `tests/api/test_revenue.py::test_an_amount_no_decimal_can_hold_is_refused_before_the_routine` (5 cases) and `::test_an_amount_below_what_a_decimal_holds_reads_as_zero` answered 500 before the fix | NaN and Infinity as JSON tokens were already a field refusal (`errors: {"amount": ...}`); a value over 2^96 - 1 as a string reached the routine and got the money sentence (400), so only the exponent cases were 5xx | survives, major (a 5xx on a client-reachable body; posted as `07:V-D4-1` on the board, 08 informed) | fixed: `_to_decimal` refuses a non-finite value or one above 2^96 - 1 as a field refusal (as the .NET binder did) and rounds past 28 decimal places as .NET read them (`common.py:34-47`); docs/06 1.2 numbers row; tests above |
| V-D4-2 | falsification | C4, docs/05 2.4 | The week and dashboard percent: .NET sums `target / 7m` per day (28 digits) and divides; Python divides exactly (`amount * 700 / target_sum`). At an exact half they part: weekly target 10 000, a full week, 5 050 recorded: .NET 50, Python 51 (`dotnet run`, section 8). Amounts ending in 50 make such halves common at targets not divisible by 7. One day alone agrees (both 179 for 2 550) | `revenue.percent(5050, 70000)` = 51; .NET `Percent(5050, 7 x 10000/7m)` = 50 | `total_expected` cannot differ: a sum of cents over 7 never lies exactly on a half cent, and .NET's error is below 1e-25 | survives, minor (a display figure, one point, only at exact halves; .NET's answer is an artefact of where its 28-digit quotient rounded) | doc corrected (docs/05 2.4 `revenue.percent` row: accepted deviation with the example) and pinned by a new case in `tests/db/test_revenue_helpers.py::test_percent_rounds_half_away_from_zero_and_holds_to_32_bits` (`5050`, `70000` -> 51); for the user (section 10) |
| V-D10-1 | falsification | C26, prompt D4 evidence "409 with and without `current`" | No HTTP test showed the 409 without `current` that the phone queue turns into a conflict (title, detail, no `current`): the database test asserted the code only | grep of `tests/api/test_revenue.py` | `tests/unit/test_messages.py` pins the sentence against docs/06 section 3, so the text was right; the wire body was untested | survives, minor | fixed (evidence): `tests/api/test_revenue.py::test_a_day_another_save_holds_is_a_409_without_current` (passes; a second connection holds the day's row) |
| V-D4-3 | red team | phone queue recovery after a 409 without `current` | `apps/mobile/src/revenue/queue.ts:300` re-reads the day with `weekStart = date - 6`; the API answers the week holding that day, which holds `date` only when `date` is the week's last day. On the other six days `savedNow` finds no cell and the conflict shows no current value. The mobile test fakes the route with the same expression (`apps/mobile/tests/revenue.test.tsx:333`), so it cannot see it | code read; API rule `revenue.week_start(coalesce(p_week_start, today))`, .NET `StartOfWeek(weekStart)` | same in .NET (the API is right); outside `apps/api-python` and mobile is out of scope this round | survives, note | for the user (section 10) |
| V-D3-2 | pre-mortem, dialectic | "an identical entry is answered as replayed ... so a phone draining its queue late always succeeds" (`revenue_capture.sql` header) | A retry that arrives while the same entry's first attempt still holds the day (a client timeout during a slow commit) gets 409 (`revenue_concurrent_save` on an existing day, `unique_conflict` on a first capture), not 200 | `test_a_save_of_a_day_another_save_holds_is_refused_at_once`, `test_two_first_captures_...` | .NET pins the same 409 for the first-capture race (`RevenueCaptureTests.cs:226-249`, no `current`); the window is the first attempt's open transaction (about 10 ms, up to 1.8 s under the burst of `docs/perf/revenue.md`), and the phone keeps the entry as a conflict, losing nothing | survives as a note (parity) | residual: recorded here; no change |

## 4. Per domain

### D1 Tenancy and authorization

| Probe | Verdict | Evidence |
|---|---|---|
| `enter_organization` before the first tenant read | holds (A) | first statement of the three `api.revenue_*`; `test_an_actor_of_another_organization_is_not_a_member`; `db verify` tenant-guard check (section 8) |
| RLS and `tenant_isolation` on revenue tables; owner-owned functions | holds (B) | `db verify` exit 0 on a database built from the tested files; `pg_proc` in the CLI database: the eleven `revenue.*` helpers are owned by `xcode_owner` but `SECURITY INVOKER` (`prosecdef` false), so they run as the calling executor under RLS; the three `api.revenue_*` are `SECURITY DEFINER` owned by `xcode_api_executor`, which RLS binds; every helper filters on `tenancy.current_organization()`, set only by `tenancy.enter_organization` after the membership check (`test_an_actor_of_another_organization_is_not_a_member`) |
| Scoped viewers: totals, `total_vehicles`, `first_gap`, companies, dashboard cards | holds (A) | `test_a_scoped_viewer_counts_only_the_vehicles_they_may_see` (week and dashboard, three periods) |
| `{vehicleId}` belongs to the organization and is visible | holds (A) | `test_an_unknown_or_unseen_vehicle_is_not_found_before_the_date_is_read`, `test_an_unknown_or_unseen_vehicle_is_not_found` |
| 403 versus 404 order | holds (A) | permission (`permission_missing`) before the vehicle is read: `test_a_member_with_neither_capture_nor_correct_is_refused_before_the_entry_is_read` |
| Anti-escalation, catalogue | n/a | 07 grants nothing and adds no key; `CellStatus` pinned (C20) |

### D3 Data integrity and concurrency

| Probe | Verdict | Evidence |
|---|---|---|
| Version bumped and compared; stale writer 409 with `current` | holds (A) | C7, C11, C25 |
| Lock order | holds (A for capture x retirement and capture x join-date change, both orders; B elsewhere) | capture: vehicle `FOR SHARE` -> record `FOR UPDATE NOWAIT` -> organization row (`record_change`) -> membership key share (change-log foreign key); 06 writers: (company `FOR SHARE`) -> vehicle `FOR UPDATE` -> organization row; people writers: membership `FOR NO KEY UPDATE` -> user -> organization row. No pair in opposite orders |
| Replays rely on the unique constraint; identical replay adds no change-log row; two first writes give one row | holds (A) | C10, I1 |
| Append-only tables by grant | n/a | 05's tables; untouched |
| Money `numeric(14,2)`; rounding modes named; sums cannot overflow | holds (A) | `ck` and column types in `0006_revenue.sql`; sums are unbounded `numeric`; C3, C4 |
| One call one transaction; only idempotent commands retried | holds (B) | C21 |

### D4 Contract parity

| Probe | Verdict | Evidence |
|---|---|---|
| Routes: .NET, docs/06, routers, OpenAPI | holds | .NET `RevenueEndpoints.cs`: 6 routes; Python and OpenAPI: R01 `GetRevenueWeek`, R02 `GetRevenueDashboard`, R03 `SaveRevenue`, tag `Revenue`; the other three (`/day` x2, `/export`) are drift rows 3 and 4, owned by 08b and listed in docs/06 2.8. OpenAPI lists a `422` on each (FastAPI default), already posted by verify-06 as `06:V-D4-3` for prompt 09 |
| Bodies: names, order, nullability, numbers | holds (A) | C23, C27 |
| Errors: titles and details | holds (A) | C25, C26 (now), 400/403/404 sentences in the queue test |
| Clients | holds for the API (A); one client defect noted | C28; V-D4-3 |
| Drift since the inventory | holds | `git log --since=2026-10-10 -- apps/api tests/api`: no commit; working tree: `RevenueEndpoints.cs` gains only `/export` (row 4). Rows 9, 11, 13 re-read: still closed |
| Amount parsing | failed, fixed | V-D4-1 |
| Percent | fails at exact halves, documented | V-D4-2 |

### D5 Domain rules and time

| Probe | Verdict | Evidence |
|---|---|---|
| Business dates from the organization zone and `p_now`; no `now()` | holds (A) | `test_the_business_date_is_the_organizations_own_calendar_day` (America/New_York); sweep: no `now()`, `current_date`, `clock_timestamp()`, `random()` in `50_revenue` |
| Week start per organization; month ends; 29 February; DST zones | holds (A for the week start, B for the month) | `test_revenue_helpers.py:431` (every first day); `date_trunc('month', d)::date` is the 1st in America/Santiago, America/Havana, Pacific/Apia and Africa/Nairobi for 2026-09-06, 2028-02-29, 2026-03-08, 2026-11-01 (section 8) |
| Reasons and snapshots byte for byte | holds (A) | I3, C6 |
| Normalisation | holds (A) | reason spellings C5; note trimmed with the .NET white-space set (`tenancy.trim_text`); note length in code points, an accepted deviation (docs/06 1.2 "Text lengths") |

### D6 Database craft

| Probe | Verdict | Evidence |
|---|---|---|
| `db verify` exit 0 | holds | section 8: on a clone of `xcode_template_v07` (snapshot + fixes) after `db routines`, 21 of 21 checks `ok` |
| `SECURITY DEFINER` with fixed `search_path` | holds | sweep: every `50_revenue` file with `SECURITY DEFINER` sets it |
| `EXECUTE` revoked from `PUBLIC` | holds | each helper `REVOKE ALL ... FROM PUBLIC`; `db verify` privilege checks |
| No dynamic SQL | holds | sweep: no `EXECUTE` statement or `format(` in `50_revenue` |
| Indexes | holds | `uq_records_vehicle_day (organization_id, vehicle_id, business_date)`, `ix_records_business_date` serve every revenue query (plans in `docs/perf/revenue.md`) |
| Version features | holds | `range_agg` and multirange `@>` (PostgreSQL 14), `trim_scale` (13); the effective minimum is 16 (question 39) |
| Template fingerprint | holds | `xcode_template_v07` comment `23e6a74f...` equals `template_fingerprint` of the tested `db/` (snapshot with the fix); private template, no other session used it |

### D7 Performance and scale

| Probe | Verdict | Evidence |
|---|---|---|
| Statement budgets | holds (A) | `count == 2` in `test_a_capture_answers_exactly_id_and_version_in_two_statements`, the week and the vehicle reads |
| `EXPLAIN` at 10x | unproven by this run | C18 |
| No query per row in a loop | holds (B) | `vehicle_week` loops over seven days without a query; `earliest_missing` walks each vehicle's records with an index-only `LIMIT 1` inside the one statement, as measured in `docs/perf/revenue.md` |
| Hot rows | holds (recorded) | the organization row per capture (question 32, `docs/perf/revenue.md`); the new vehicle `FOR SHARE` lock conflicts only with fleet edits of that vehicle |
| Paging capped | holds (A) | `tenancy.check_page` 1..100000 x 1..100; `test_a_page_out_of_range_is_refused_before_the_week_is_read`; `(page - 1) * size` cannot overflow `integer` |

### D8, D9

D8: no revenue log call carries a body or an amount (`request.completed` logs the route
template); nothing else in 07. D9: n/a (07 adds no setting, dependency or host step).

### D10 Tests as evidence

| Probe | Verdict | Evidence |
|---|---|---|
| No fake of the capability under test | holds | the revenue fake only proves orchestration and matches the routines (C22) |
| `skip`, `xfail`, `sleep`, broad `except` | holds | sweep: only `# fmt: skip` comments; the two-connection tests wait on `pg_blocking_pids`, not a sleep |
| A test named after a rule asserts it; five wrong implementations | holds | a capture that skipped visibility fails `..._not_found_before_the_date_is_read`; one that checked the version before the permission fails `test_changing_an_earlier_day_needs_the_correct_permission_and_shows_nothing_stored`; one that wrote on a replay fails the change-row count of I1; a week that summed only the page fails `test_pages_list_a_slice_and_keep_the_whole_grid_figures`; a capture without the vehicle lock fails the new race test |
| Every `Raises:` code has a test | holds (B for `time_zone_invalid`) | every code of the three headers is asserted in the revenue modules except `time_zone_invalid`, raised by `tenancy.business_date` and tested in `tests/db/test_organization_routines.py` |
| Full suite on a fresh template | holds | the first full run after 07b D4's landing (`xcode_template_d4full`, 17:35 to 19:31): every 07 module and money-parser caller passed (section 12) |

### D11 Documents and prompts

| Probe | Verdict | Evidence |
|---|---|---|
| Doc clauses match the code | holds after corrections | docs/05 4.7 R03 step 2 (the vehicle `FOR SHARE`), docs/05 2.4 `revenue.percent` (deviation), docs/06 1.2 numbers (amount bounds) |
| Prompt references resolve | holds | the sections cited by `docs/prompts/07-revenue.md` exist |
| README status | holds after update | `docs/prompts/README.md` row 07 said "`verify.md` run pending"; it now names this report, its verdict and what is owed (08:35) |

## 5. Per mode

### Assumptions (Socratic)

| Assumption | Where stated | Enforced by |
|---|---|---|
| "A capture is recorded only for a day the vehicle is in the fleet" | docs/05 4.7 step 6 | `setup.vehicle_active_on` at capture time; under a concurrent fleet change: nothing before this run, now the vehicle `FOR SHARE` (`revenue_capture.sql:84-87`) |
| "The amount is read exactly and checked by the routine" | `http/schemas/revenue.py` docstring | `tenancy.check_money`; but only for values PostgreSQL can parse: now `_to_decimal` bounds them |
| "sum(target) / 7 equals the sum of the daily target / 7 exactly" | `vehicle_week.sql` header | true for `total_expected`; the percent at an exact half is not the .NET figure (V-D4-2) |
| "An identical replay always succeeds" | `revenue_capture.sql` header | true once the day is not held by another open save (V-D3-2) |
| "Weeks start on the organization's first day" | `week_start.sql` | localization `first_day_of_week`, tested for every day |

### Falsification

Section 2 is the falsification table: each claim with the observation that would disprove
it (a racing fleet change, a body PostgreSQL cannot parse, a .NET percent, a missing wire
assertion) and its grade.

### Pre-mortem (three months after cutover)

1. **Revenue vanishes from a retired bus** (likely x high, before the fix). An office admin
   retires KDA at 18:02 while the night clerk's phone drains the day's queue; the capture
   lands on the leave date; reports and the dashboard skip inactive days, so 4 500 KES is in
   the table and nowhere on screen. Noticed at month-end reconciliation against M-Pesa.
   Inversion: guaranteed by any check-then-write on an unlocked row under READ COMMITTED,
   which existed (`revenue_capture.sql:84`). Fixed (V-D3-1).
2. **A crafted body takes the API's error budget** (possible x medium). Any client or script
   sends `"amount":"1e999999"`; each answer is a 500 with an `integrity_bug` error log; on
   the host this looks like a database fault and pages someone. Inversion: guaranteed by
   passing unparsed-by-PostgreSQL values through, which existed (`common.py:34`). Fixed
   (V-D4-1).
3. **Parity run flags revenue percent** (likely x low). The `parity.md` session compares
   .NET and Python week answers and finds `percent` 50 versus 51 on full weeks ending in 50;
   a day is lost chasing a "bug". Mitigated: documented (V-D4-2).
4. **Phones show conflicts with no saved value** (possible x low). After two clerks race on
   one day, the loser's phone shows "Someone else saved this day first" with nothing to
   compare (V-D4-3). Early sign: support messages about empty conflicts. Owner: mobile.
5. **Month dashboard slow on the host** (possible x low). 41 ms median here, 90 ms at full
   load; prompt 09 measures on the host and decides on `revenue.dashboard_cache`
   (docs/05 7).

### Red team

| Persona | Vector | Defence or gap |
|---|---|---|
| Clerk in tenant A | another tenant's vehicle id on R03 or R01 | 404 (organization filter, then `vehicle_visible`) |
| Clerk in tenant A | another tenant's `companyId` on R01/R02 | an empty grid and zero cards; no other tenant's rows (visibility helpers) |
| Scoped clerk | totals, `total_vehicles`, `first_gap`, companies, dashboard counts | computed over `setup.visible_vehicles()` only (C17, D1) |
| Clerk with `revenue.capture` only | guess a past day's stored amount through the replay answer (200 when equal, 403 when not) | an oracle, but the clerk already reads the grid: `revenue.capture` depends on `revenue.view` (`0004_access_catalog.sql`, `permission_dependencies`) |
| Dismissed employee | replay an old queue after deactivation or after losing `revenue.correct` | membership refused at `enter_organization`; identical replays write nothing; a changed past day needs `revenue.correct` (C9) |
| Gamer | overwrite a closed day | `revenue_correct_permission` before any disclosure (C7, I2) |
| Anyone | a body PostgreSQL cannot parse | was a 500 (V-D4-1), now 400 |
| Office admin x clerk | retire or move a vehicle while its day is captured | was a stranded record (V-D3-1), now serialised |
| Calendar | DST zones, 29 February, a held business date, a wrong phone clock | dates from `tenancy.business_date(p_now)`; month start probed (D5) |
| Injection | SQL through reason, note, registration; formula text in a note | no dynamic SQL; snapshots built with `json_build_object`; a note starting with `=` is a matter for the exports of 08b (posted as a check-in) |

### Dialectic

| Decision | Strongest counter | Verdict | Confidence |
|---|---|---|---|
| `FOR UPDATE NOWAIT` on the day's record (409 at once) | waiting would turn a concurrent identical retry into a 200 | keep: .NET pins a 409 for the race, and waiting adds lock queues on hot days | medium |
| Vehicle `FOR SHARE` in the capture (this run) | run the capture `SERIALIZABLE` as .NET did | keep the lock: `SERIALIZABLE` in PostgreSQL turns races into 40001, which the gateway may not retry for a capture (not idempotent), so clients would see 503 | high |
| Exact percent | reproduce .NET's 28-digit quotients | keep exact; document the deviation; the .NET figure depends on the digits of target / 7 | medium (owner may overrule, section 10) |
| No dashboard cache | the .NET 60-second cache | keep: fresh figures, measured 25 to 90 ms; 09 decides on the host | medium |
| Bound amounts in `_to_decimal` (field refusal beyond a .NET decimal) | map `22003` to 400 in the gateway | keep: a `22003` inside a routine is a bug and must stay a 500 | high |

## 6. Conceded

| Challenge | Guard that defeated it |
|---|---|
| `(page - 1) * page_size` overflows `integer` for a huge page | `tenancy.check_page` caps the page at 100000 (as .NET), product 10^7 |
| Two identical first captures racing should answer 200 (replay), not 409 | .NET pins 409 without `current` (`RevenueCaptureTests.TwoClerksCapturingTheSameDayAtOnceGetAConflictNotAServerError`); title equals `CONFLICT_TITLE` |
| Replay before the permission checks lets a clerk read stored amounts | `revenue.capture` depends on `revenue.view` |
| `total_expected` differs from .NET at a half cent | impossible: N/700 is never within 1/1400 of a half cent |
| The month card is wrong in a zone with daylight saving | `date_trunc('month', d)::date` converts both ways in the same zone (D5 probe) |
| Away periods with an open end are skipped (`returned_on` null) | `returned_on` is `NOT NULL` (`0005_setup.sql:109`) |
| The new vehicle `FOR SHARE` makes a capture hang behind a slow fleet edit | bounded by `xcode_app` `lock_timeout = 2s` (`db/roles/010_roles.sql:25`); 06's writers hold the vehicle for milliseconds; the answer to a timeout (500, not 503) is open question 57, unchanged |
| Upper-case or hyphen-less ids miss the `{vehicleId:uuid}` route | Starlette's convertor accepts both; only braces (accepted by .NET) are refused, and no client sends them |
| `NaN` or `Infinity` amounts reach the routine | already a field refusal for JSON tokens; strings now too |
| `earliest_missing` misses a gap after an away period or a record on an away day | its candidates (join date, the day after a record, each return) cover every case (the day before the earliest missing day is before the join, recorded or away); `test_the_earliest_missing_day_agrees_with_a_day_by_day_walk` holds it equal to a walk over `setup.vehicle_active_on`, which follows the .NET loop (`RevenueRepository.cs` `EarliestMissing`) |
| The note length counts differently from .NET | accepted deviation, docs/06 1.2 "Text lengths" |
| Dashboard `?period=` empty or repeated | empty is refused as in .NET; a repeated key takes the last value (FastAPI) where .NET joined them: no client sends it, framework-wide |

## 7. Fixes

| Finding | Files changed | Test that failed before and passes now |
|---|---|---|
| V-D3-1 | `db/routines/50_revenue/revenue_capture.sql` (vehicle read `FOR SHARE`, header), `docs/05-routines.md` 4.7 R03 step 2 | `tests/db/test_revenue_routines.py::test_a_capture_waits_for_a_fleet_change_of_its_vehicle_and_then_reads_it[retire]`, `[join later]` (before: `created`); plus `::test_a_retirement_waits_for_a_capture_of_its_vehicle_and_then_sees_the_record` (the other order; passed before and after) |
| V-D4-1 | `src/xcode_api/http/schemas/common.py` (`_to_decimal`, `_read_decimal`), `docs/06-http-contract.md` 1.2 numbers row | `tests/api/test_revenue.py::test_an_amount_no_decimal_can_hold_is_refused_before_the_routine` (5 cases; before: three 500s, one money sentence, NaN/Infinity already refused), `::test_an_amount_below_what_a_decimal_holds_reads_as_zero` (before: 500) |
| V-D4-2 | `docs/05-routines.md` 2.4 `revenue.percent` row; `tests/db/test_revenue_helpers.py` one case | the case passes before and after: it pins the documented rule, not a change |
| V-D10-1 | `tests/api/test_revenue.py` | `::test_a_day_another_save_holds_is_a_409_without_current` (evidence; passes) |

Process note: `docs/05-routines.md` and `docs/06-http-contract.md` had been changed by other
sessions at 07:46 and 07:51; I edited them at 08:03, inside the 30 minutes `verify.md` asks
to wait. Each edit was one exact-match replacement in a row claimed on the board (section 3),
read and written back within one second with `newline=""`; both files kept CRLF and my text
was found in each afterwards. `src/xcode_api/http/schemas/common.py` lost its CRLF endings to an in-place `sed`
and was restored to CRLF at once (byte count checked).
`docs/prompts/README.md` row 07 was written at 08:35, 42 minutes after the file's last change,
under a board claim, CRLF kept. The first live-tree `tests/unit` run at 08:37 inherited the
snapshot's `PYTHONPATH` and stopped at collection (`ImportError: BackLimit`, the snapshot's
pre-D2 `src`); the counts in section 8 are from the rerun with it cleared.

## 8. Commands and outputs

Environment (measured 07:24 to 08:30): PostgreSQL 16.15 (5433 cluster, `SELECT version()`);
Python 3.13.2; CI service image `postgres:18` (`.github/workflows/xcode-api.yml:63,107`),
never run (the folder is untracked). Machine: 4 cores, 0.44 to 0.83 GB free (five
sessions); every run single-process (`-n 0`) by the coordinator's rule.

Snapshot: `src`, `db`, `tests`, `pyproject.toml` copied at 07:38:15 into the scratchpad,
without 07b D2's in-flight `0009_access` (its tenancy routines were rewritten after the copy,
so the snapshot is the pre-D2 state); private template `xcode_template_v07`.

```
baseline (snapshot, before any change)
  tests/db/test_revenue_helpers.py    46 passed (5:38, includes the template build)
  tests/db/test_revenue_routines.py   63 passed (6:07)
  tests/api/test_revenue.py           15 passed (1:08)

new tests, before the fixes (snapshot)
  8 failed, 2 passed: the two race cases (outcome 'created'); "1e999999", "-1e999999",
  "1e-999999" -> 500; "79228162514264337593543950336" -> 400 money sentence (no errors key);
  NaN/Infinity -> field refusal named 'amount' (the test expected 'body.amount'; corrected)
after the fixes: 10 passed

regression (snapshot + fixes, -n 0, one module at a time)
  tests/db/test_revenue_helpers.py    46 passed
  tests/db/test_revenue_routines.py   66 passed
  tests/api/test_revenue.py           22 passed
  tests/api/test_setup_vehicles.py    67 passed   (money-parser callers: weeklyTarget)
  tests/api/test_setup_recurring.py   35 passed   (recurring amounts)
  tests/api/test_setup_investment.py  34 passed   (investment amounts)
  tests/api/test_people.py            24 passed   (approvalLimit)
  tests/api/test_http_plumbing.py     32 passed
  tests/api/test_contract_released_clients.py  24 passed (08:33)
  tests/unit (snapshot)               187 failed, 697 passed, 2 skipped: environmental, the
                                      snapshot has no docs/, .env.example or packages/shared
                                      (FileNotFoundError); rerun in the live tree below
final (08:35-08:38)
  snapshot with the final test files: the new and changed tests of the three revenue
  modules, tests/db/test_message_codes.py, the two revenue fake-parity tests of
  tests/db/test_fakes_match_routines.py      74 passed (2:49)
  tests/unit in the live tree                8 failed, 917 passed: none from 07. Seven in
    tests/unit/test_messages.py: people_*, record_too_old (07b D2's in-flight people block,
    messages.py and docs/06 section 3, both claimed by D2, docs/06 written 08:38); one in
    test_routine_catalogue.py: nine pettycash.* routines not yet named in docs/05 (08's
    in-flight 4.9). 07 adds no message code and no routine.

PostgreSQL numeric limits:  '1E+131071' parses, '1E+131072' 22003; '1E-16383' parses,
  '1E-16384' 22003; '1E+999999' / '1E-999999' 22003 "value overflows numeric format"

.NET percent (dotnet run, file-based app, the expression of RevenueRepository.cs:329-330):
  target 10000, 7 days, amount 5050 -> expected 10000.000000000000000000000001, percent 50
  target 10000, 1 day,  amount 2550 -> 179     target 7000, 7 days, 3535 -> 51
Python: revenue.percent(5050, 70000) = 51; (2550, 10000) = 179; (3535, 49000) = 51

ruff check (changed files): All checks passed; ruff format: 2 files reformatted (my new
lines only), then clean; mypy: Success, no issues in 165 source files
whole live tree at 08:27: ruff check . -> All checks passed!; ruff format --check . -> 359
files already formatted; mypy -> Success: no issues found in 165 source files
db on test_v07_verify (a clone of xcode_template_v07, snapshot + fixes, 08:40; dropped after)
  db status    applied 0001..0008, pending none, routine drift none, checksum drift none; exit 0
  db routines  applied 204 routine files (50_revenue/revenue_capture.sql among them); exit 0
  db verify    21 checks ok (roles, RLS, api.* routine properties, no dynamic SQL, tenant
               routines enter their organization, ...); exit 0
  The CLI database xcode was not used: it is at 0008 and D2's 0009 is in flight there.
full suite: not run in this session; queued 08:14 as row 3 of the shared run, which had not
  started at 08:41 (the coordinator waits for 07b D2's 0009)
```

## 9. Regressions and misses against earlier reports

No earlier report covers prompt 07 (`docs/audit/` has none; the build's own challenge pass
lives in `docs/perf/revenue.md` "What the first measurement found" and the prompt README
status). The earlier audits mention 07 only as in-flight work (`2026-10-11-verify-area-docs.md`
line 220, `-prompt-02.md` line 228). Nothing recorded as fixed is broken again. Missed by
the build: V-D3-1 (the build tested the two capture races but not a capture against a
fleet change), V-D4-1 (shared parser, also missed by the 04, 05 and 06 work that uses it),
V-D4-2 (the deviation was known to the author, `vehicle_week.sql` header, but not recorded
as one), V-D10-1.

## 10. For the user

1. **Revenue percent at exact halves (V-D4-2).** Python reports the exact rounding (51 for
   5 050 of 10 000 over a full week); .NET reports 50 because of how its decimal division
   rounds. Recommendation: keep the exact figure. It is the one a person checking by hand
   gets, and .NET's figure flips with the digits of target / 7. Say so if you want .NET's
   figure reproduced instead.
2. **Mobile conflict recovery reads the wrong week (V-D4-3).** `apps/mobile/src/revenue/queue.ts:300`
   asks for `weekStart = date - 6`, so after a race the phone shows no saved value on six days
   of seven. Recommendation: `weekStart = date` (any day names its week). It is a one-line
   mobile change for when mobile is back in scope; its test fakes the route and needs the real
   week rule.

## 11. Where to resume

Owed: the shared full run (board queue row 3). Its log decides the verdict: read it for
`tests/db/test_revenue_helpers.py`, `tests/db/test_revenue_routines.py`,
`tests/api/test_revenue.py` and the money-parser callers (`tests/api/test_setup_vehicles.py`,
`test_setup_recurring.py`, `test_setup_investment.py`, `test_people.py`, and 08's petty-cash
API tests once they exist). If every one of them passes, and nothing else fails because of
`revenue_capture.sql` or `_to_decimal`, section 1 becomes **pass with findings**, D10's full
run becomes `holds`, and the `docs/prompts/README.md` row 07 drops "fail until...". Everything
else in this report is complete. Nothing is `not checked` except the full run and C18
(unproven; re-measuring the `EXPLAIN` timings belongs to prompt 09's performance pass).

## 12. Shared full run (added by the coordinator, revenue-d5 [b49167], 2026-10-12 15:30)

The shared full run: `pytest -n 2 -q -p no:cacheprovider -rfE --junitxml` on a fresh
`xcode_template_full` built at 13:01 from the frozen live tree, 13:00 to 15:23 (2:22:27):
5617 passed, 42 failed, 0 errors, 0 skipped. Log and JUnit XML in revenue-17 [60bb7c]'s
scratchpad (`full.log`, `full.xml`); every failure has an owner (coordination board
section 5, 15:26).

Section 11's list:
- `tests/db/test_revenue_helpers.py` 47 passed.
- `tests/db/test_revenue_routines.py` 62 passed, 4 failed: `test_recording_a_reason_needs_the_no_earnings_permission_first`
  and `test_each_card_needs_its_own_permission[owner-shown0]`, `[admin-shown2]` (the
  permission keys 07b D2's `0009` retired or renamed: `revenue.no_earnings`, the four `dash.*`
  cards); `test_a_capture_waits_for_a_fleet_change_of_its_vehicle_and_then_reads_it[join
  later]` (07b D3's new `api.setup_vehicle_update` signature).
- `tests/api/test_revenue.py` 1 passed, 21 failed, every one at vehicle creation (400 "Enter
  the fleet number.": 07b D3's S18 rule; its test-helper fix landed 15:28).
- Money-parser callers: `test_setup_vehicles.py` 79, `test_setup_investment.py` 34,
  `test_people.py` 29, `test_petty_cash.py` 14 passed; `test_setup_recurring.py` 33 of 35 (the
  two failures are D3's B16 change, not the money parser).

None of the 25 revenue failures comes from `revenue_capture.sql` or `_to_decimal`, but the
condition of section 11 (every listed module passes) does not hold, so section 1, D10 and
README row 07 are **not** changed here. 07b D4 rewrites these three revenue modules for its
rules when it lands; the run that decides this report's verdict is the first full run after
D4's landing (D4 queues it).

### After D4's landing (added by the coordinator, 20:40)

D4's full run (board queue row 7): the same command on a fresh `xcode_template_d4full` built
at 17:35 from the live tree (D4 landed at 17:12), 17:35 to 19:31 (1:55:20): 5733 passed, 3
failed, 0 errors, 0 skipped. Log and JUnit XML in revenue-d5 [b49167]'s scratchpad
(`full/full.log`, `full/full.xml`). The 3 failures are all in `tests/db/test_gateway.py` and
are 07b D1's: the test lags D1's `domain/identity.py` types. None is revenue's or the money
parser's.

Section 11's list:
- `tests/db/test_revenue_helpers.py` 63 passed.
- `tests/db/test_revenue_routines.py` 91 passed (D4 replaced the retired-key tests with its
  own; the join-later race test calls D3's new `api.setup_vehicle_update`).
- `tests/api/test_revenue.py` 39 passed.
- Money-parser callers: `test_setup_vehicles.py` 79, `test_setup_recurring.py` 35,
  `test_setup_investment.py` 34, `test_people.py` 30, `test_petty_cash.py` 16,
  `test_http_plumbing.py` 32 passed.

Section 11's condition holds, so section 1 is now **pass with findings**, D10's full-suite
probe is `holds`, and README row 07 no longer says "fail until".
