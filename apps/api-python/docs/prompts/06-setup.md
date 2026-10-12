# Prompt 06: setup (companies, vehicles, away periods, expense catalog, scheduled items, investment)

Paste everything below the line into a fresh Claude Code session running Sonnet, started in
the repository root. Requires prompts 00 to 05. Do not run beside prompt 05 or 07 (shared
`container.py`, `main.py`, `application/repositories.py`, `tests/support/fakes.py`).

---

You are implementing the setup area of `apps/api-python`: PSV companies, fleet vehicles
with dated weekly targets and away periods, the expense catalogue, scheduled expenses and
savings with their immutable versions and allocations, vehicle investment, and the vehicle
report, as routines, use cases, HTTP routes and tests.

## Read first, in this order

1. `CLAUDE.md`; `apps/api-python/README.md`.
2. `docs/00-principles.md` section 3; `docs/01-architecture.md` sections 3, 4, 7, 8, 9;
   `docs/11-naming.md`.
3. `docs/06-http-contract.md` sections 1.6, 1.7, 2.3, 2.4, 2.6, 2.7, 3 (companies and
   vehicles, scheduled items, change log and catalogue and investment blocks).
4. `docs/05-routines.md` sections 1, 2.3, 4.2, 4.3, 4.5, 4.6, 6, 7, 8.
5. `docs/04-schema.md` sections 5, 7, 8.
6. `docs/inventory/inventory-http-contract.md` sections 2.4, 2.5, 2.6, 2.8, 2.9, 3.4, 3.5,
   3.9 and `docs/inventory/inventory-domain.md` sections 2.4 (`SU-C`, `SU-V`, `SU-A`), 2.5
   to 2.8 (`SU-E`, `SU-R`, `SU-I`, `SU-X`), 3 (schedule maths, due days, target backfill,
   report maths), 4 (the use-case check orders).
7. `docs/inventory/inventory-tests.md` rows for `DomainRuleTests`, `VehicleAwayTests`,
   `RecurringCrudTests`, `ScheduledItemRulesTests`, `DueDateGeneratorTests`,
   `ExpenseCatalogTests`, `InvestmentTests`, `VehicleReportTests`, `RecurringQueryCostTests`,
   `AutomaticReasonTests`.
8. The code from prompts 00 to 05: `http/messages.py`, `http/errors.py`,
   `db/routines/tenancy.py`, the tenancy helpers, `tests/support/*`, and the test style of
   `tests/db/test_access_routines.py`.

Do not read the C# sources except in the drift check.

## Drift check (before any code)

The inventories describe the .NET API of 7 to 10 October; it changed afterwards. Run
`git log --since=2026-10-07 --stat -- apps/api/Api/SetupEndpoints.cs apps/api/Application/Setup apps/api/Domain/Setup apps/api/Infrastructure/Setup tests/api`
and `git diff HEAD --stat -- apps/api tests/api`, and read the changes to what this prompt
builds. Rows 5, 6 and 8 of the drift register in `docs/prompts/README.md` are known:
- build the vehicle and scheduled-item list filters of row 8 here (`?companyId=` on the
  vehicle list; `?kind=&companyId=&status=` with running items first on the scheduled-item
  list; `tests/api/ListFilterTests.cs` is the reference), because they change routes this
  prompt builds;
- leave pause, resume, runs, summary and the new posting sources (rows 5 and 6) to 08b,
  but compare the vehicle report and investment maths you build with
  `apps/api/Infrastructure/Setup/FleetPostings.cs` and `tests/api/VehicleReportTests.cs`
  for the sources that exist before 08b, and build the current behaviour.
Correct the inventory and documents before building; list every correction with the .NET
`file:line` that caused it; add anything new to the register.

## Environment

As prompt 01. `git status` first; write only under `apps/api-python/`.

## Deliverables

### D1 Setup helpers (`db/routines/40_setup/`)

- `setup.company_visible`, `setup.vehicle_visible`, `setup.visible_vehicles`,
  `setup.visible_companies`, `setup.company_active_on`, `setup.vehicle_active_on`,
  `setup.vehicle_away_on`, `setup.target_on`, `setup.registration_normalize`,
  `setup.recurring_current_version`, `setup.recurring_version_on`,
  `setup.recurring_due_days`, `setup.schedule_valid`, and the six snapshot builders, per
  `docs/05-routines.md` sections 2.3 and 6.2.
- Evidence: `tests/db/test_setup_helpers.py`: visibility for the three scope kinds;
  `target_on` with several revisions and same-day revisions (highest revision wins); away
  days; `registration_normalize` table (`kda482m`, `KDA 482M`, `KDA-482M`, a wrong shape);
  `recurring_due_days` with the cases of `DueDateGeneratorTests` (weekly weekday, monthly
  28, last day in February of a leap and a common year, yearly month and day, a version
  superseded mid-range, `start_on`/`end_on`/`stopped_from` bounds, the legacy daily
  frequency); snapshots byte for byte against literal JSON.

### D2 Companies and vehicles routines

- `api.setup_company_list`, `_create`, `_rename`, `_archive`, `_restore`,
  `api.setup_vehicle_list`, `_create`, `_update`, `api.setup_company_options`,
  `api.setup_vehicle_retire`, `_restore`, `api.setup_vehicle_report` per
  `docs/05-routines.md` section 4.2, the check orders of `inventory-http-contract.md`
  sections 2.4 and 2.5, the target rules `SU-V6` (append a revision at
  `greatest(today, joined_on)`; backfill at the old join date when `joined_on` moves
  earlier), away periods on restore, and the report maths of `inventory-http-contract.md`
  section 3.5.
- Evidence: `tests/db/test_setup_company_routines.py`, `test_setup_vehicle_routines.py`:
  one test per `Raises:` code, `unchanged` no-ops (same name, same leave date, restore of
  an active vehicle), the automatic reasons byte for byte (including the `{CUR} {amount}`
  formatting for a whole and a fractional target and the `; it was away from ... to ...`
  suffix), target backfill, revenue-dated refusals with the exact `{registration}` and
  `{date}` (seed records through direct inserts as owner until prompt 07 exists, marked),
  the investment-viewer shape of the vehicle list (hidden targets), company option and
  vehicle counts, the report window and bucket sums with a scheduled item on the vehicle.

### D3 Expense catalogue routines

- `api.setup_expense_category_list`, `api.setup_expense_item_options`,
  `api.setup_expense_category_create`, `_update`, `_set_stopped`,
  `api.setup_expense_item_create`, `_rename`, `_set_stopped` per `docs/05-routines.md`
  section 4.5.
- Evidence: `tests/db/test_setup_expense_routines.py`: every code; the three rename
  reasons; stopped-category items still accepted; options exclude stopped items and
  categories; ordering by name then id.

### D4 Scheduled items routines

- `api.setup_recurring_list`, `api.setup_vehicle_options`, `api.setup_recurring_create`,
  `_revise`, `_stop`, `_cancel_stop` per `docs/05-routines.md` section 4.3 with the nine
  steps of `inventory-http-contract.md` section 2.6 in order, the allocation sum through
  the deferred constraint trigger plus the routine's own message, `effective_from` rules,
  `partial` and `active_amount` in the list, the cost name and bucket taken from the
  expense item.
- Evidence: `tests/db/test_setup_recurring_routines.py`: one test per step and per code
  (`recurring_*`), `unchanged` revise, the exempted vehicle already on the current version,
  the running-item start rule, stop and cancel-stop states (`stopped today`, `later`,
  `in effect`), the `Changed the {...} of {name}` sentence with one, two and three parts,
  a scoped viewer's list (`partial` true, `amount` of visible allocations only, 403 on
  revise when a hidden vehicle is on the version).

### D5 Investment routines

- `api.setup_investment_get`, `_create`, `_update`, `_delete` per `docs/05-routines.md`
  section 4.6; `returned` reuses the report maths of D2 (one SQL function
  `setup.vehicle_net(vehicle, from, through, today)` shared by the report and the
  investment read).
- Evidence: `tests/db/test_setup_investment_routines.py`: codes, the vehicle as the
  change-log entity with `vehicle_id` set, the hard delete with `after` null,
  `percent_paid_off` null, positive, rounded half away from zero, a scoped viewer's 404.

### D6 Domain, ports, gateway, fakes

- `domain/setup.py` records and commands; `application/repositories.py`
  `SetupRepository` (one method per routine); `db/routines/setup.py` `SetupRoutines`;
  `tests/support/fakes.py` `FakeSetupRepository` with parity cases for a company rename,
  a vehicle update with a target change, a recurring revise and an investment delete.

### D7 Use cases and HTTP

- `application/setup/*` use cases, `http/schemas/setup.py` (DTOs of
  `inventory-http-contract.md` sections 3.4 and 3.5 in wire order; `kind`, `frequency`,
  `bucket` as integers; `weeklyTarget` and `targets` nullable for investment viewers),
  `http/routers/setup_companies.py`, `setup_vehicles.py`, `setup_expenses.py`,
  `setup_recurring.py`, `setup_investment.py` with the operation ids and the `Setup` tag,
  the required empty-object bodies (`{}`) where the contract says the body itself is
  required, the `?period` or `?from&through` report query.
- Evidence: `tests/api/test_setup_companies.py`, `test_setup_vehicles.py`,
  `test_setup_expenses.py`, `test_setup_recurring.py`, `test_setup_investment.py`: status
  codes, exact sentences, DTO names and order, 401/403/404, paging validation, statement
  budget 2, the report's figures for a seeded scenario, and the history entries these
  writes create (through `GET /setup/history`).
- Extend `tests/api/test_contract_released_clients.py` with the fleet rows of
  `inventory-tests.md` (`Phase1WebSettingsContractTests`):
  `FleetScreensReadAndWriteAsTheDevelopWebDoes`,
  `ARecurringCostFromTheDevelopWebIsRefusedWithAReason`,
  `ADailyItemFromTheDevelopWebIsRefusedWithAReason` and the company and vehicle-report
  parts of `RefusalsKeepTheirStatusAndAProblemTheWebCanShow`, in that file's raw-JSON
  style (`has(parent, name, kinds)`), and move its docstring's "join with the setup
  feature" sentence out.

## Invariants at the end

- Companies, vehicles, items, categories and recurring items are never deleted; targets,
  away periods, versions and allocations are append-only (a test proves the grants refuse
  `UPDATE`/`DELETE` and that no routine body contains such a statement for those tables).
- Every automatic reason and every snapshot equals the .NET text byte for byte for the
  scenarios the inventories quote.
- `due_days` and `target_on` exist once, in SQL; Python holds no copy of schedule or target
  arithmetic.
- Lint, types, all tests green; `db verify` exit 0; `test_message_codes.py` green with the
  new codes; no TODO/FIXME; no plan or prompt identifiers.

## Verify (paste the outputs into the report)

```
cd apps/api-python
ruff check . && ruff format --check . && mypy
pytest <the test modules you touched> -q
pytest -n 3 -q -p no:cacheprovider > <scratchpad>/full.log 2>&1
xcode-api db routines && xcode-api db verify ; echo "exit=$?"
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
3. Run the five modes over D1 (scoped viewers, report sums, option counts), D3, D4 (the setup routes against `apps/api/Api/SetupEndpoints.cs`), D5 (targets, schedules, due days, automatic reasons), D6 and D7, plus D10 (tests as evidence) and D11 (documents);
   give every probe of section 4 for those domains a verdict.
4. Try to refute each finding; fix the survivors with a test that fails first, or record
   them (corrected document, open question, residual risk).
5. Report the findings table (section 7), the conceded challenges with the guard that
   defeated each, and the three hardest attacks for any domain without findings.

This pass does not replace the separate `verify.md` run on this prompt; it makes that run
cheaper.

## Report format

1. Checklist: one row per deliverable D1 to D7 and per bullet: done or not, `file:symbol`,
   test name.
2. Verify outputs, trimmed.
3. Deviations from the documents with reasons; document and inventory lines changed.
4. Items left for later prompts.

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
