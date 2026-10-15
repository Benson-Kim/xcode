# Prompt 08b: what the .NET API gained on 9 and 10 October

Central expenses, scheduled-item pauses, runs and summary, reports and exports, day
capture, list filters, and the new posting sources of the vehicle report.

This prompt runs as two sessions:
1. **Design (Opus)**: D0 only. It reads the .NET code and the design documents, writes the
   inventory and the documents, and changes no code. Then run `docs/prompts/verify.md` with
   `SCOPE: change:<the files D0 changed>` and `MODE: report` in a third session, and fix
   what it finds before building.
2. **Build (Sonnet)**: D1 to D7, from the documents D0 wrote.

Requires prompts 00 to 08. Do not run beside 08 or 09 (shared `container.py`, `main.py`,
`application/repositories.py`, `tests/support/fakes.py`, `http/messages.py`).

---

You are bringing `apps/api-python` level with what the .NET API in `apps/api` gained on 9
and 10 October 2026, which no inventory or design document of the rewrite describes yet:
rows 1 to 6, 8 and 12 of the drift register in `docs/prompts/README.md`. The parameter
below says which session you are.

`SESSION:` <`design` (D0) | `build` (D1 to D7)>

## Read first, in this order

1. `CLAUDE.md`; `apps/api-python/README.md`.
2. `docs/00-principles.md`, `docs/01-architecture.md` sections 3, 4, 7, 8, 9,
   `docs/11-naming.md`, `docs/14-verification.md`.
3. `docs/prompts/README.md`: the status, the drift register and the design register
   (re-measure both; they are claims from 2026-10-11).
4. The design, in the repository root's `docs/design/` (not `apps/api-python/docs`):
   `XCODE_Web_v2.28.html` (the `MODS` permission list and the `NAV`
   groups: Expenses holds central expenses, petty cash and scheduled expenses; Setup holds
   companies, vehicles, items, people and the change log) and
   `XCODE_Build_Notes_v2.28.pdf`. The owner's instruction of 2026-10-09: petty
   cash and the expense catalogue move into an Expenses group like Setup, central expenses
   are added, the designs stay as they are, and the new capabilities, reports included,
   are added. `XCODE_Build_Notes_v2.3.md` and `XCODE_Web_v2.3.html` (v2.29 to v2.33)
   supersede v2.28 where they differ: three-level expense categories, savings split from
   scheduled expenses with their own rights, the saving model, reports that sum dated
   targets, and the back-dating limit on central expenses. Python builds them ahead of
   .NET (`docs/13-open-questions.md` question 46): design register rows B18 (the saving
   model, question 49) and the report parts of B9, B15 and B16, and the B12 check on
   central-expense writes; where the notes and .NET differ, the notes decide.
5. `design` only: the .NET sources of the drift rows (endpoints, use cases, domain,
   repositories, migrations `20261009153259_CentralExpenses` and
   `20261010194310_RecurringPauses`, `Application/Reports/*`, `Infrastructure/Reports/*`,
   `Application/Setup/FleetPostings.cs`, `Infrastructure/Setup/FleetPostings.cs`) and their
   tests (`CentralExpenseTests`, `CentralExpenseDomainTests`, `RecurringPauseTests`,
   `ReportTests`, `RevenueDayTests`, `ListFilterTests`, and the parts of
   `VehicleReportTests`, `PettyCashTests` and the revenue tests changed in commit 9276c51),
   read at `HEAD` and in the working tree (uncommitted changes count). The clients:
   `apps/web/components/expenses/*`, `reports/*`, `period/*`,
   `packages/shared/src/reports.ts`, `packages/shared/src/pettyCash.ts`, and any mobile use
   (`grep -rn "setup/expenses\|setup/reports\|revenue/day" apps/mobile/src`).
6. `build` only: the documents and the inventory D0 wrote, the code from prompts 00 to 08,
   and the test style of `tests/db/test_setup_recurring_routines.py` and
   `tests/api/test_setup_companies.py`. Do not read C#.

The build notes state these rules; D0 checks each one against the PDF and the .NET code,
and where they disagree the .NET code decides behaviour and D0 records the difference:
- an expense split across vehicles is one transaction per vehicle sharing a group
  reference;
- central expenses are the ledger of record, with sources central, petty cash and
  scheduled;
- a schedule is a standing order that posts on its run dates, unique per (schedule, run
  date, vehicle);
- savings carry a revenue condition, with held, skipped and saved runs and opening
  balances;
- one period model `{from, to, unit}`;
- Excel and PDF exports are built on the server and logged;
- vehicle visibility is per person.

## Environment

As prompt 01; the local cluster is PostgreSQL 16 (`docs/09-testing.md` section 5).
`git status` first; write only under `apps/api-python/`.

## Deliverables

### D0 Inventory and design (`SESSION: design`; documents only)

- `docs/inventory/inventory-expenses-reports.md`, in the shape of
  `inventory-petty-cash.md`: the reference commit and every uncommitted file it read; the
  entities and rules with ids (`CE-*` central expenses, `SR-*` scheduled runs and pauses,
  `RP-*` reports and exports, `RD-*` day capture, `LF-*` list filters, `FP-*` fleet
  postings), each with the .NET `file:line`; every endpoint with method, path, permission,
  check order, status codes, request and response DTOs in wire order, messages verbatim,
  operation id and tag; the tests that pin each rule; what the web, mobile and shared
  clients read.
- `docs/04-schema.md`: the new tables (central expenses, scheduled-item pauses, and
  whatever the runs need), with constraints, RLS, grants, append-only rules and an index
  per query; `docs/05-routines.md`: the helpers and `api.*` routines, with check orders and
  statement budgets; `docs/06-http-contract.md`: new sections for central expenses and
  reports, the additions to people, vehicles, scheduled items, revenue and petty cash, the
  message block, the client facts.
- `docs/02-stack.md`: an ADR for building Excel and PDF in Python. Compare the candidates
  on licence, pure-Python versus system libraries (the host may not offer them: questions
  41 and 42 of `docs/13-open-questions.md`), font embedding (the OFL fonts in
  `apps/api/Assets/Fonts`), memory for a large export, and byte-level determinism for
  tests; argue the rejected option at full strength before choosing.
- `docs/12-security.md`: exports and reports (permission per report, bounds on rows,
  bytes and time, the audit row, spreadsheet formula injection for cells starting with
  `=`, `+`, `-` or `@`, scoped viewers' totals).
- `docs/09-testing.md` section 4: crosswalk rows for the test classes of drift row 12;
  `docs/10-data-migration.md` section 3: rows for the new tables; `docs/13-open-questions.md`:
  every decision you could not take on the merits.
- Mark drift rows 1 to 6 and 8 "documented" in `docs/prompts/README.md`, and add any
  change you found that the register missed.

### D1 Migration `0013_expenses.sql`

(`0009` to `0012` exist: 07b's and 08's. `docs/04-schema.md` section 14 is the specification.)

- The tables of D0's `docs/04-schema.md` sections, with code tables for every enumeration,
  RLS and `tenant_isolation`, grants (`INSERT` only on append-only tables), and a reviewed
  `.down.sql`.
- Evidence: `tests/db/test_schema_structure.py`, `test_constraints.py` (one failing insert
  per `CHECK`), `test_enum_parity.py`, `test_grants.py` extended; `db verify` exit 0.

### D2 Routines

- Folders numbered after `55_pettycash` (for example `57_expenses`, `58_reports`) so their
  dependencies load first; additions to `40_setup` (pause, resume, runs, summary, the list
  fields and filters) and `50_revenue` (day capture, the revenue export source). Every
  routine per D0's `docs/05-routines.md` entries, with the tenant guard, the check order
  and the messages as codes.
- The vehicle report and investment read their postings from every source D0 documented
  (revenue, scheduled runs, central expenses, approved petty cash) through one SQL
  function, as `setup.vehicle_net` does today; no source is summed in Python.
- Evidence: `tests/db/test_expense_routines.py`, `test_recurring_pause_routines.py`,
  `test_report_routines.py`, `test_revenue_day_routines.py`: one test per rule id and per
  `Raises:` code; the uniqueness of (schedule, run date, vehicle) under two racing
  connections; split expenses as one row per vehicle with one group reference; scoped
  viewers' totals; the period model's bounds.

### D3 Domain, ports, gateway, fakes

- `domain/` records and commands for each new area; one repository port per area in
  `application/repositories.py`; `db/routines/*.py` gateways (exports and reads marked
  idempotent, writes not); `tests/support/fakes.py` fakes with parity cases in
  `tests/db/test_fakes_match_routines.py`.

### D4 Messages, use cases and HTTP

- `http/messages.py`: every new code with its sentence; `test_message_codes.py` green.
- `application/expenses/*`, `application/reports/*` and the additions to `setup`,
  `revenue`, `pettycash` and `access`; routers under `/setup/expenses` (tag
  `Central expenses`) and `/setup/reports` (tag `Reports`), and the new routes on the
  existing routers, with the .NET operation ids, query parameters and their validation
  sentences.
- Evidence: `tests/api/test_expenses.py`, `test_reports.py`, `test_recurring_pause.py`,
  `test_revenue_day.py`, `test_list_filters.py`: every scenario of the matching .NET test
  class with the same assertions; statement budgets; DTO names and order; 401, 403, 404.

### D5 Exports

- The screen exports (revenue, central expenses, petty cash) and the report exports, built
  with the library of D0's ADR: content types and `Content-Disposition` names as the .NET
  API sends them, the bounds of `docs/12-security.md`, an audit row per export, formula
  injection neutralised.
- Evidence: tests that open the produced file and check the sheet or page contents (not
  only the status), a scoped viewer's export without hidden vehicles, a cell starting with
  `=` that stays text, an export past the bound refused with its sentence.

### D6 Additions to existing areas

- Scheduled items: pause and resume with the rules `RecurringPauseTests` pins (D0 lists
  them; a pause has a start and, once resumed, an end; a stop stays final), runs, summary,
  the list fields `pausedFrom`, `lastRun`, `lastRunVehicles`, `balance`.
- List filters: built already (people by the `verify.md` run on prompt 05, vehicles and
  scheduled items by 06); check them against `tests/api/ListFilterTests.cs` in the drift check.
- Day capture: `GET /setup/revenue/day`, `PUT /setup/revenue/day/{date}`. Each row runs the
  single capture's own steps as 07b D4 built them (`docs/05-routines.md` 10.5: the identical
  replay, the low-day threshold after it, `revenue.capture` for a day without a record and
  `revenue.correct` for a saved one, `tenancy.check_writable`, the version), through one
  helper both routes call (`revenue.capture_entry`, `docs/05` 11.5), never .NET's older
  steps. Only the batch shape comes from .NET: the rows, the 500 limit, duplicates, all or
  none, the vehicle named in a 400 and the 409's `vehicleId`.
- The saving model of design register row B18 (`docs/15-design-v2-3.md` B18, `docs/05` 11.1
  and 11.3): the revenue rule, held, skipped and saved runs decided by the writes that
  complete a window, opening balances, no start date, no end date.
- Petty-cash shared purchases (question 68, `docs/05` 11.6) and the change-log sections of
  drift register row 14 (`docs/05` 11.8).
- Evidence: the .NET tests' scenarios as above; the mobile queue's bodies unchanged for
  the single-cell capture.

### D7 Released clients

- `tests/api/test_contract_released_clients.py`: raw-JSON rows for every new screen the web
  reads (expenses ledger and options, reports catalogue and one report per group, the
  scheduled-items summary), in that file's style.

## Invariants at the end

- Every route of drift rows 1 to 5 and 8 exists in the Python routers, in
  `docs/06-http-contract.md` and in the OpenAPI document, with the .NET method, path, tag
  and operation id.
- No posting source is summed outside SQL; split expenses never lose or invent a cent.
- Exports never contain a row the caller may not see, and each one leaves an audit row.
- Lint, types, all tests green; `db verify` exit 0; no TODO/FIXME; no plan or prompt
  identifiers.

## Verify (paste the outputs into the report)

```
cd apps/api-python
ruff check . && ruff format --check . && mypy
pytest <the test modules you touched> -q
pytest -n 3 -q -p no:cacheprovider > <scratchpad>/full.log 2>&1
xcode-api db migrate && xcode-api db routines && xcode-api db verify ; echo "exit=$?"
```

Run the touched modules while you work and the full suite once at the end, in the
background, with its log in your scratchpad; report passed, failed, skipped and errors
from the log. Before that run, drop `xcode_template` (you changed migrations and routines),
after checking that no other session's run uses the cluster (`docs/09-testing.md`
section 5).

## Challenge pass (before the report)

Apply `docs/14-verification.md` to your own work as if nobody, including you earlier in
this session, had reviewed it:
1. Steelman: list every deliverable bullet and invariant above as a claim, with the code
   (or, in the design session, the document section and the .NET `file:line`) that
   carries it.
2. Falsify: for each claim, name the observation that would disprove it and look for it;
   grade the evidence (section 5). Tenancy, security and integrity claims need grade A.
3. Run the five modes over D1 (aggregates, reports and exports for scoped viewers first),
   D3 (splits, runs, pauses, races), D4 (every route against `apps/api/Api/*.cs`), D5 (the
   period model, run dates, month ends), D6, D7 (reports and exports at 10x the demo seed)
   and D9 (the export library's licence, system libraries and supply chain), plus D10
   (tests as evidence) and D11 (documents); give every probe of section 4 for those
   domains a verdict. The design session argues the other side of each decision it took.
4. Try to refute each finding; fix the survivors with a test that fails first (build) or a
   corrected document (design), or record them (open question, residual risk).
5. Report the findings table (section 7), the conceded challenges with the guard that
   defeated each, and the three hardest attacks for any domain without findings.

This pass does not replace the separate `verify.md` run; it makes that run cheaper.

## Report format

1. Design session: the reference commit and uncommitted files read; every rule id with its
   .NET `file:line`; every document section written; the ADR decision; the open questions
   added; the drift register as you left it.
2. Build session: checklist, one row per deliverable D1 to D7 and per bullet: done or not,
   `file:symbol`, test name; verify outputs, trimmed.
3. Deviations from the documents with reasons; document and inventory lines changed.
4. The challenge-pass results.
5. Items left for later prompts.

## House rules

- Shared tree: `git status` first; edit only under `apps/api-python/`; never revert or
  reformat others' changes; never kill processes you did not start; never bare `git stash`.
- No commits unless the user asks. No AI attribution anywhere.
- No comments unless needed; routine files carry the header the conventions require and
  nothing decorative; no plan or prompt identifiers anywhere.
- Never weaken a test to make it pass. If a document is wrong, fix the document and report
  it.
