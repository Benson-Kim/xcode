# Prompt 07: revenue (week grid, dashboard, capture and offline replay)

Paste everything below the line into a fresh Claude Code session running Sonnet, started in
the repository root. Requires prompts 00 to 06. Do not run beside prompt 06 or 08.

---

You are implementing revenue in `apps/api-python`: the week grid with its paging, the
dashboard cards, and the capture endpoint that is also the phones' offline-replay target,
as routines, use cases, HTTP routes and tests. The eleven-step capture rule and the 409 and
400 extension bodies are what the mobile queue depends on; they are reproduced exactly.

## Read first, in this order

1. `CLAUDE.md`; `apps/api-python/README.md`.
2. `docs/00-principles.md` sections 3, 4; `docs/01-architecture.md` sections 3, 4, 7;
   `docs/11-naming.md`.
3. `docs/06-http-contract.md` sections 1.2 (numbers, enumerations), 1.6 (B, the revenue
   rows), 2.8, 3 (revenue block), 4 (the mobile queue facts).
4. `docs/05-routines.md` sections 1, 2.4, 4.7, 6, 7, 8.
5. `docs/04-schema.md` sections 6, 7.
6. `docs/inventory/inventory-http-contract.md` sections 2.10 (R01 to R03, the eleven
   steps), 3.6 (DTOs, cell rules, the mobile queue table) and its final "Drift log" section
   (the paged week form: `page`, `pageSize`, `truncated`, `totalVehicles`, `dayTotals`,
   `firstGap`, the legacy limit of 500, `vehicleId` never paged);
   `docs/inventory/inventory-persistence.md` sections 5.6, 6 and its drift log (SQL
   aggregation of the dashboard, the cache the .NET API added and this design does not
   reproduce); `docs/inventory/inventory-domain.md` sections 2.9 (`RV-*`), 3 (week maths,
   rounding, dashboard maths).
7. `docs/inventory/inventory-tests.md` rows for `RevenueCaptureTests`, `RevenueTests`,
   `RevenueRefusalTests`, `RevenueDashboardCardTests`, `RevenueDashboardCacheTests`,
   `RevenueWeekPagingTests`, `RevenueComplexityTests`, `VehicleReportTests`.
8. The code from prompts 00 to 06, in particular `http/messages.py`, `http/errors.py`,
   `db/routines/setup.py`, the setup helpers (`setup.vehicle_active_on`, `setup.target_on`,
   `setup.visible_vehicles`), `tests/support/*`.

Do not read the C# sources except in the drift check; the clients' expectations are in
the inventories.

## Drift check (before any code)

The inventories describe the .NET API of 7 to 10 October; it changed afterwards. Run
`git log --since=2026-10-07 --stat -- apps/api/Api/RevenueEndpoints.cs apps/api/Application apps/api/Infrastructure tests/api`
and `git diff HEAD --stat -- apps/api tests/api`, and read the changes to revenue. Rows 3,
9 and 11 of the drift register in `docs/prompts/README.md` are known: day capture (row 3)
belongs to 08b, but commit 9276c51 also changed `Application/RevenueUseCases.cs`,
`Application/RevenueContracts.cs`, the dashboard cache and four revenue test classes,
which may alter the capture, week or dashboard behaviour this prompt builds. Correct the
inventory and documents before building; list every correction with the .NET `file:line`
that caused it; add anything new to the register.

## Environment

As prompt 01. `git status` first; write only under `apps/api-python/`.

## Deliverables

### D1 Revenue helpers (`db/routines/50_revenue/`)

- `revenue.earliest_missing`, `revenue.cell`, `revenue.vehicle_week`,
  `revenue.reason_label`, `revenue.reason_code`, `revenue.record_snapshot` per
  `docs/05-routines.md` section 2.4 and the cell rules of `inventory-http-contract.md`
  section 3.6 (`status`, `can_edit`, `edited_after_capture`, `expected` per day with
  banker's rounding, totals from unrounded daily expectations rounded once, `percent` half
  away from zero and null when expected is 0).
- Evidence: `tests/db/test_revenue_helpers.py`: the cell status table (none, future,
  missing, amount, reason), `can_edit` for each status and permission combination,
  `earliest_missing` with away days and a leave date, the rounding cases (a target of
  `1000` gives `142.86` per day and `1000.00` per week; a half-cent case for banker's
  rounding), `reason_code` for `No Crew` and `NoCrew` and the refusal of `no crew`.

### D2 Routines

- `api.revenue_week_get`, `api.revenue_dashboard_get`, `api.revenue_capture` per
  `docs/05-routines.md` section 4.7. `api.revenue_capture` follows its steps in
  order: entry shape, visibility, lock (`NOWAIT`), identical replay, future date, activity,
  permissions (before any disclosure), version conflict with `current`, write with the two
  race outcomes (the earliest-missing step was removed by the .NET commit 9276c51: days
  are captured in any order, drift register row 13), change log through `tenancy.record_change` with the
  four sentences and `d MMM yyyy`.
- The week routine answers the paged form and the legacy form (first 500 vehicles with
  `truncated` and `total_vehicles`), `day_totals` and `first_gap` over the whole filtered
  grid, and the single-vehicle form for any week; the dashboard aggregates in one query
  with each card null without its permission; no cache anywhere.
- Evidence: `tests/db/test_revenue_routines.py`: one test per step (named after it),
  replay after the day closed with any `version`, a replay that stopped being identical
  after another person's correction answering the permission refusal without `current`,
  two first captures racing (two connections: the loser gets `unique_conflict`), two
  updates racing (`revenue_concurrent_save`), the week maths for a seeded fleet, the week
  range refusal at both bounds, paging and `truncated`, `day_totals` and `first_gap`
  unchanged by paging, the dashboard figures per card and per permission for `today`,
  `week`, `month` with a company filter, and `EXPLAIN (ANALYZE, BUFFERS)` of the week and
  dashboard queries at 10x the demo seed saved under `docs/perf/` (create the folder) and
  summarised in the report.

### D3 Domain, ports, gateway, fakes

- `domain/revenue.py` records (`RevenueCell`, `RevenueVehicleWeek`, `RevenueWeek`,
  `RevenueDashboard`, `CaptureResult` with `outcome` created/updated/replayed) and the
  `RevenueCapture` command (named like the other commands, `VehicleRetirement` or
  `PersonSave`; the use case is `CaptureRevenue`) (`CellStatus` already holds the five wire statuses, pinned
  against `packages/shared/src/revenue.ts` by `tests/unit/test_permission_keys.py`:
  `RevenueCell.status` uses it); `application/repositories.py` `RevenueRepository`;
  `db/routines/revenue.py` `RevenueRoutines` (capture marked not idempotent for the
  gateway retry; the two reads idempotent); `tests/support/fakes.py`
  `FakeRevenueRepository` with parity cases for an identical replay and a version
  conflict with its `current` (the earliest-missing refusal no longer exists).

### D4 Use cases and HTTP

- `application/revenue/get_week.py`, `get_dashboard.py`, `capture_revenue.py`;
  `http/schemas/revenue.py` (DTOs of `inventory-http-contract.md` section 3.6 in wire order;
  `status` as the five strings; money as numbers; `version` nullable; the paged fields);
  `http/routers/revenue.py` with the `Revenue` tag, operation ids, the `{vehicleId}` UUID
  route constraint (404 empty body for a non-UUID), the date segment, and the three
  revenue-specific answers: 409 with `current` (title `This day already has a different
  record.`), 409 `This day was changed by another save.` (the 400 with `earliestMissing`
  went with the earliest-missing step); 200 body exactly `{"id": ..., "version":
  ...}` in that order.
- Evidence: `tests/api/test_revenue.py`: every row of the mobile queue table in
  `inventory-http-contract.md` section 3.6 as a scenario (200 replay, 409 with and without
  `current`, 403 details, 404 for a hidden vehicle), the web paging sequence (first call legacy, then `page=6..&pageSize=100` when
  `truncated`), the single-vehicle read for a past week, the dashboard per permission,
  statement budget 2 per request, the exact JSON property order of the capture answer.

## Invariants at the end

- There is no idempotency key, no client id and no cache; a replay is decided by value
  equality in step 4 of the routine and creates no change-log row.
- A 403 never carries `current`; a 409 with `current` carries the stored cell, its
  `can_edit` from the caller's permissions alone.
- Every revenue change-log row has `vehicle_id` set and a reason with `d MMM yyyy`.
- The week and dashboard routines run one statement each; `EXPLAIN` output is in
  `docs/perf/` with the row counts of the 10x seed.
- Lint, types, all tests green; `db verify` exit 0; `test_message_codes.py` green; no
  TODO/FIXME; no plan or prompt identifiers.

## Verify (paste the outputs into the report)

```
cd apps/api-python
ruff check . && ruff format --check . && mypy
pytest <the test modules you touched> -q
pytest -n 3 -q -p no:cacheprovider > <scratchpad>/full.log 2>&1
xcode-api db routines && xcode-api db verify ; echo "exit=$?"
ls docs/perf
```

Run the touched modules while you work and the full suite once at the end, in the
background, with its log in your scratchpad; report passed, failed, skipped and errors
from the log. Before that run, drop `xcode_template` if you changed a migration or routine
file, after checking that no other session's run uses the cluster (`docs/09-testing.md`
section 5).

## Challenge pass (before the report)

Apply `docs/14-verification.md` to your own work as if nobody, including you earlier in
this session, had reviewed it:
1. Steelman: list every deliverable bullet and invariant above as a claim, with the code
   that carries it.
2. Falsify: for each claim, name the observation that would disprove it and look for it;
   grade the evidence (section 5). Tenancy, security and integrity claims need grade A.
3. Run the five modes over D1, D3 (the replay and the two races, with two connections), D4 (the mobile queue's 409 and 400 bodies), D5 (week maths, rounding, business dates, the calendar persona) and D6 and D7 (the `EXPLAIN` evidence), plus D10 (tests as evidence) and D11 (documents);
   give every probe of section 4 for those domains a verdict.
4. Try to refute each finding; fix the survivors with a test that fails first, or record
   them (corrected document, open question, residual risk).
5. Report the findings table (section 7), the conceded challenges with the guard that
   defeated each, and the three hardest attacks for any domain without findings.

This pass does not replace the separate `verify.md` run on this prompt; it makes that run
cheaper.

## Report format

1. Checklist: one row per deliverable D1 to D4 and per bullet: done or not, `file:symbol`,
   test name.
2. Verify outputs, trimmed, and the two `EXPLAIN` summaries (rows, buffers, time at 10x).
3. Deviations from the documents with reasons; document and inventory lines changed.
4. Items left for later prompts (expected: the dashboard cache table if the measured cost
   requires it, `docs/05-routines.md` section 7).

Add the challenge-pass results and the drift-check corrections as the last section of
the report.

## House rules

- Shared tree: `git status` first; edit only under `apps/api-python/`; never revert or
  reformat others' changes; never kill processes you did not start; never bare `git stash`.
- No commits unless the user asks. No AI attribution anywhere.
- No comments unless needed; routine files carry the header the conventions require and
  nothing decorative; no plan or prompt identifiers anywhere.
- Never weaken a test to make it pass. If a document is wrong, fix the document and report
  it.
