# Expenses and reports inventory: what the .NET API gained on 9 and 10 October 2026

Purpose: one file, four lenses (rules, persistence, HTTP contract, tests) plus the client dependencies, for the .NET
changes of drift register rows 1 to 6, 8 and 12 (`docs/prompts/README.md`): central expenses, reports and exports, day
capture, scheduled-item pause, resume, runs and summary, the list filters, and the fleet postings every report reads.
Nothing here is Python design: that is `docs/04-schema.md` section 14, `docs/05-routines.md` section 11 and
`docs/06-http-contract.md` section 2.13, which say where Python follows the design notes instead (section 7 below lists
the differences).

Basis of this inventory
- Repository `C:\Users\user\Documents\Coding\PrioriTech\xcode-wt\revenue`, branch `fix/web-dropdowns`, `HEAD` 493bf82
  (the feature's commit is 9276c51, 2026-10-09, "feat: expenses group, central expenses, reports and day capture"; no
  later commit touches `apps/api` or `tests/api`). Read on 2026-10-12 between 17:55 and 18:40, read-only: no build, no
  test run, so nothing here records a pass or a failure.
- **(uncommitted)** marks a fact whose only source is an uncommitted or untracked file. The Appendix lists every such
  file with its `git status` and modification time (all written 2026-10-10 between 22:20 and 22:46) and the line ranges
  the working tree changed against `HEAD`.
- `file:line` uses the numbering of the working tree as read. Abbreviations (all under `apps/api/` unless stated):

| Short | File |
|---|---|
| `CED` | `Domain/CentralExpense.cs` |
| `CEC` | `Application/CentralExpenseContracts.cs` |
| `CEU` | `Application/CentralExpenseUseCases.cs` |
| `CEE` | `Api/CentralExpenseEndpoints.cs` |
| `CER` | `Infrastructure/CentralExpenseRepository.cs` |
| `CEM` | `Infrastructure/CentralExpenseModel.cs` |
| `M1` | `Infrastructure/Migrations/20261009153259_CentralExpenses.cs` |
| `M2` | `Infrastructure/Migrations/20261010194310_RecurringPauses.cs` (uncommitted) |
| `RE` | `Api/ReportEndpoints.cs` |
| `RC` | `Application/Reports/ReportContracts.cs` |
| `RU` | `Application/Reports/ReportUseCases.cs` |
| `FR` | `Application/Reports/FleetReports.cs` |
| `PR` | `Application/Reports/PettyCashReports.cs` |
| `SX` | `Application/Reports/ScreenExports.cs` (untracked) |
| `TB` | `Application/Reports/Tables.cs` |
| `RF` | `Application/Reports/ReportFormat.cs` |
| `RW` | `Application/Reports/ReportWorkbook.cs` |
| `RPDF` | `Infrastructure/Reports/ReportPdf.cs` |
| `RR` | `Infrastructure/Reports/ReportRepository.cs` |
| `RPS` | `Domain/Setup/RecurringPause.cs` (untracked) |
| `RI` | `Domain/Setup/RecurringItem.cs` |
| `RS` | `Domain/Setup/RecurringSchedule.cs` |
| `RUC` | `Application/Setup/RecurringUseCases.cs` |
| `SC` | `Application/Setup/SetupContracts.cs` |
| `SR` | `Infrastructure/Setup/SetupRepository.cs` |
| `SM` | `Infrastructure/Setup/SetupModel.cs` |
| `SEP` | `Api/SetupEndpoints.cs` |
| `AFP` | `Application/Setup/FleetPostings.cs` |
| `IFP` | `Infrastructure/Setup/FleetPostings.cs` |
| `RVE` | `Api/RevenueEndpoints.cs` |
| `RDC` | `Application/RevenueDayContracts.cs` |
| `RDQ` | `Infrastructure/RevenueDayQueries.cs` |
| `RVU` | `Application/RevenueUseCases.cs` |
| `RVC` | `Application/RevenueContracts.cs` |
| `PCR` | `Infrastructure/PettyCashRepository.cs` |
| `PCU` | `Application/PettyCashUseCases.cs` |
| `CET`, `RPT`, `RPA`, `RDT`, `LFT`, `VRT`, `PCT` | `tests/api/CentralExpenseTests.cs`, `ReportTests.cs`, `RecurringPauseTests.cs`, `RevenueDayTests.cs`, `ListFilterTests.cs`, `VehicleReportTests.cs`, `PettyCashTests.cs` |

- The .NET namespace `Auth` appears only inside citations. The product is "xcode".
- Endpoint ids continue the existing series: `E01` to `E06` (central expenses), `G01` to `G04` (reports), `D01` and
  `D02` (day capture), `X02` to `X04` (screen exports; `X01` is taken), `S53` to `S56` (scheduled items). Rule ids:
  `CE-*` central expenses, `SR-*` scheduled runs and pauses, `RP-*` reports and exports, `RD-*` day capture, `LF-*` list
  filters, `FP-*` fleet postings.

Section list
1. Scope and state
2. Entities and rules
3. Persistence
4. HTTP contract
5. Tests
6. Client dependencies
7. Against the design notes
Appendix: uncommitted files, modification times, changed line ranges

---

## 1. Scope and state

| Drift row | What | Where | State on 2026-10-12 |
|---|---|---|---|
| 1 | Central expenses: ledger, options, record, change, remove; table `CentralExpenses` | `CED`, `CEC`, `CEU`, `CEE`, `CER`, `CEM`, `M1` | committed in 9276c51; `CEU` and `CEE` changed in the working tree (the export route, `AllRows`, the shared `LedgerPage`) |
| 2 | Reports: catalogue, fleet and petty-cash reports, report export (Excel built by hand, PDF with PDFsharp and the bundled OFL fonts) | `RE`, `RC`, `RU`, `FR`, `PR`, `TB`, `RF`, `RW`, `RPDF`, `RR`, `Assets/Fonts/*` | committed in 9276c51; `RE`, `RU`, `PR` changed in the working tree |
| 3 | Day capture: one day for the fleet, read and saved together | `RVE:54-64`, `RDC`, `RDQ`, `RVU:45-100` | committed in 9276c51 |
| 4 | Screen exports of Revenue, Central expenses and Petty cash under `reports.export` | `SX`, `RVE:44-47`, `CEE:39-42`, `PettyCashEndpoints.cs` | uncommitted (`SX` untracked) |
| 5 | Scheduled items: pause, resume, runs, summary; list fields `pausedFrom`, `lastRun`, `lastRunVehicles`, `balance`; table `RecurringPause` | `RPS`, `RI`, `RUC`, `SC`, `SR`, `SM`, `SEP:126-133`, `M2` | uncommitted |
| 6 | Fleet postings: one service every report and the vehicle report read | `AFP`, `IFP`, `SR:328-363` | committed in 9276c51; `IFP:94` (pauses loaded) uncommitted |
| 8 | List filters: people, vehicles, scheduled items | `SEP:74-77`, `:107-110`, `:123-125`, `SC:7-29`, `SR:79-84`, `:175-203` | committed in 9276c51; built in Python (people by the `verify.md` run on prompt 05, the others by 06) |
| 12 | Test classes in no inventory: `CentralExpenseTests`, `CentralExpenseDomainTests`, `ListFilterTests`, `RecurringPauseTests`, `ReportTests`, `RevenueDayTests` (`EmailSenderTests` belongs to row 10, closed) | `tests/api/` | section 5 |

No `TODO` or `FIXME` in any of these files. The mobile app calls none of these routes (`grep -rn
"setup/expenses\|setup/reports\|revenue/day" apps/mobile/src` returns nothing). The web calls all of them (section 6).

---

## 2. Entities and rules

### 2.1 Central expenses (`CE-*`)

| Id | Rule | Cite |
|---|---|---|
| CE-1 | One purchase is 1 to 50 distinct, non-empty vehicles; else `Choose 1-50 distinct vehicles.` (checked first). | `CED:21`, `:27-29` |
| CE-2 | The purchase's line is validated as a petty-cash expense line (`docs/inventory/inventory-petty-cash.md` 2.3 rows 2 to 11 in that order, with the first allocation's vehicle): `Enter the date.`, `Enter an amount other than zero.`, `Enter the amount with at most two decimals.`, `Units must be above zero, with at most three decimals.`, `The total rounds to zero. Check the units and the amount.`, `The total is too large.`, `The note must be at most 80 characters.`, `Choose the vehicle.`, `Choose what it was for.` | `CED:11-12`, `:30` |
| CE-3 | Each allocation is non-zero with at most two decimals (`Each vehicle's amount must be other than zero, with at most two decimals.`), has the total's sign (`Each vehicle's amount must have the same sign as the total.`), and the allocations sum to the total exactly (`The vehicle amounts must add up to the total.`), in that order. A negative purchase is a refund. | `CED:31-36`; `CET:72-75` |
| CE-4 | Total = `round(units x unit_amount, 2)` half away from zero, for the purchase and each row. | `CED:7`, `:23` |
| CE-5 | Rows: one vehicle takes the purchase as typed; several vehicles with equal amounts take `units / n` at the unit amount when that share has at most three decimals and `round(share x unit_amount, 2)` equals the amount; any other split stores one unit at the vehicle's own amount. | `CED:39-54`; `CET:79-112`, `CentralExpenseDomainTests` |
| CE-6 | The group: the purchase id (the client's `id`, or a new one) is every row's `GroupId`; one vehicle: the row's id is the group id; several: each row gets a new id. Each row keeps the purchase as bought: `GroupSize` (rows), `GroupTotal`, `GroupUnits`, `GroupUnitAmount`. | `CED:82-86`, `:98-119` |
| CE-7 | Note trimmed, blank is null. | `CED:9`; `CEC:35`, `:46` |
| CE-8 | A retried record: rows whose `GroupId` or `Id` equals the client id (removed or not, any vehicle, the organization's only) are found first; if any belongs to another group or another recorder, 409 `This expense was already saved by someone else. Reload and try again.` with no `current`; else 200 with their ids (ordered by id) and the stored `GroupTotal`, even if they changed since. This lookup comes before the date and vehicle checks. | `CEU:119-129`; `CER:114-115`; `CET:183-216` |
| CE-9 | Record, in order: permission `expenses.capture`; CE-1 to CE-3; CE-8; the date (`An expense cannot be recorded for a future date.`; more than 3 650 days back: `Choose a date in the last ten years.`); every allocation's vehicle in the actor's scope (`Choose one of your vehicles.`) and active that day, away periods included (`{registration} was not in the fleet on that day.`); the item and its category in use that day (`Choose an item that is in use.`); then the rows, one change-log entry each. | `CEU:116-151`, `:225-231`; `CET:149-180` |
| CE-10 | Change, in order: either `expenses.capture` or `expenses.correct`; the line (CE-2 with the row's vehicle); the row in scope and not removed, else 404; an identical line is a replay (no write, no log, the current id and version) before any permission or version check; who may change (CE-12); a new date needs `expenses.correct`; the version (missing: `Send the version of the expense you opened.`; stale: 409 with `current`); a new date is checked as in CE-9; a new date or vehicle: the target vehicle in scope and active, and no other row of the purchase (removed or not) already on it (`This purchase already has a row for {registration}.`); a new date or item: the item in use; then the write and its log. | `CEU:153-187`; `CEC:41-50`; `CET:218-258`, `:278-311` |
| CE-11 | A change of item, units or unit amount takes the row out of its group (`GroupSize` 1, `GroupTotal`, `GroupUnits`, `GroupUnitAmount` become the row's own); a new date, vehicle or note keeps it. The group id stays, so a retried record still finds every row. The other rows keep their `GroupSize` (no recount). | `CED:125-137`; `CET:278-311` |
| CE-12 | `expenses.correct` changes or removes any row; `expenses.capture` alone changes or removes only rows it recorded and dated on the business date. Refusals: `Changing someone else's expense needs the permission "Change an expense after the day".`, `Changing an expense from an earlier day needs the permission "Change an expense after the day".`, `Changing the date of an expense needs the permission "Change an expense after the day".` (403). | `CEU:162-163`, `:206-218`; `CET:348-390` |
| CE-13 | Remove, in order: either right; the typed reason (`A reason of 1–500 characters is required.`, trimmed); the row in scope and not removed, else 404; CE-12; the version (missing or stale as CE-10); then the soft removal (`RemovedBy`, `RemovedAt`, `RemovalReason`, version + 1) and its log. A removed row leaves the ledger, the figures, the vehicle report and every report; a later change or remove of it is 404. | `CEU:189-204`; `CED:139-147`; `SC:142-146`; `CET:313-346` |
| CE-14 | Version starts at 1 and moves on every change and removal; it is an EF concurrency token, so a writer that loses a race gets 409 `This expense was changed by another save.` / `Reload and try again.` and nothing is written. | `CED:94`, `:153-158`; `CEM:23`; `CEE:27-30`; `CET:260-276` |
| CE-15 | Change log: section `centralexpenses`, entity = the row id, vehicle = the row's vehicle (so scoped viewers see it by vehicle). Reasons: `Recorded central expense on {registration} for {d MMM yyyy}: {item}, {CUR} {amount}`, `Changed central expense on ...` (the values after the change), `Removed central expense on ... . Reason: {reason}.` (the typed reason through `SetupPagination.Automatic`). The amount is `#,##0` when whole, else `#,##0.00`. Every write also writes the audit event `expenses.recorded` with the before and after snapshots. | `CEU:147-148`, `:185`, `:202`, `:279-287`; `CER:146-151`; `SR:383` |
| CE-16 | Snapshot keys, in order: `Id, Date, VehicleId, ExpenseItemId, Units, UnitAmount, Total, Note, GroupId, GroupSize, GroupTotal, GroupUnits, GroupUnitAmount, RecordedBy, RecordedAt, UpdatedBy, UpdatedAt, RemovedBy, RemovedAt, RemovalReason, Version`. | `CEU:289-312` |
| CE-17 | Ledger, `expenses.view`, in order: page and page size (`Page must be 1–100000 and page size 1–100.`); `from` and `to` both given (`Choose the first and the last date.`); `from <= to` (`The first date cannot be after the last date.`); `to - from <= 366` (`Choose a period of at most 367 days.`); `source` (`Choose central, petty cash or scheduled.`); `q` trimmed, at most 200 (`Search for 200 characters or fewer.`). Nothing counts after the business date; a period that starts after it answers no rows and zero figures. | `CEU:19-47`; `AFP:23-30`; `CET:473-479` |
| CE-18 | Ledger rows: central rows not removed and approved, not removed petty-cash expenses, each inside its vehicle's own days (join date to the day before it left; days away are not excluded); and the scheduled cost runs of FP-5 (never savings). `figures` sums each source over the period whatever `source` and `q` say; `total` and `amount` count and sum the rows matching both. | `CER:17-51`; `CEU:49-57`, `:105`; `CET:392-429` |
| CE-19 | Ledger order: newest day first; within a day central, then petty cash, then scheduled (`PostingSource` 1, 2, 3); stored rows by registration (ordinal) then id; scheduled rows by registration then their row id `{scheduleId}:{yyyy-MM-dd}:{vehicleId}` (ordinal). Pages are cut so the stored rows read are the page's own (per-day counts). | `AFP:5-11`; `CER:83-87`; `CEU:63-101`, `:239-241`; `CET:558-613` |
| CE-20 | Ledger search, case-insensitive substring: stored rows match registration, item name, category name, note, the recorder's or (petty cash) the holder's full name (`{FirstName} {LastName}` of the membership); scheduled rows match registration, the schedule's name, category name and note. | `CER:53-69`; `CEU:59-61`, `:246-252`; `CET:432-480` |
| CE-21 | A row's flags: `canEdit` = `canRemove` = a central row the actor may change (CE-12); petty-cash and scheduled rows false; `permissions` `{canRecord: expenses.capture, canCorrect: expenses.correct}`. `group` only when the row's `GroupSize` is above 1. `version` only on central rows. `recordedByName` null on scheduled rows, empty when the person is unknown; `holderName` on petty-cash rows. | `CEU:223`, `:254-264`; `CEC:7-21` |
| CE-22 | Options, any of `expenses.capture`, `expenses.correct`: `date` (default the business date) checked as CE-9; vehicles in scope joined by the date, not left and not away, by registration (`{id, companyId, companyName, registration, active: true}`); items whose item and category are in use that day (`{id, name, categoryId, categoryName, bucket}`, by category name, item name, id). | `CEU:108-114`; `CER:101-112`; `SR:501-511`; `CET:169-179` |
| CE-23 | A 409 from the version check carries `current`: the row as the ledger would list it (the vehicle report's postings of that day), or null when it cannot be found. Title `This expense has changed.`, detail the exception's message (`This expense was changed after you opened it. Check it and save again.` by default). | `CEE:19-31`; `CEU:266-275`; `CEC:55-60` |
| CE-24 | Instants are UTC; a removed row refuses further changes in the domain (unreachable through HTTP: the row lookup excludes removed rows). | `CED:160-168` |
| CE-25 | Organizations never see each other's rows; another organization's client id is free in this one. | `CET:512-544` |

### 2.2 Scheduled runs and pauses (`SR-*`)

| Id | Rule | Cite |
|---|---|---|
| SR-1 | A pause is a span `[From, Through]` of an item; `Through` is null while it is paused; one resumed on the day it was paused covers no day (`Through = From - 1`). Table `RecurringPause (OrganizationId, Id, ItemId, From, Through)`, index `(OrganizationId, ItemId, From)`, FK to the item. | `RPS:3-27`; `M2`; `SM:42-46` (uncommitted) |
| SR-2 | Pause, as of the business date: an item stopped on or before today -> 400 `The item is already stopped.`; already paused -> nothing changes, nothing is logged, 200; else a pause from today. | `RI:67-76` (uncommitted); `RPA:58-124` |
| SR-3 | Resume: no open pause -> nothing changes (checked before the stop, so a stopped item that is not paused answers 200); stopped -> `The item is already stopped.`; else the open pause ends the day before today (or covers nothing when resumed the day it began). | `RI:77-85`; `RPS:26`; `RPA:95-107` |
| SR-4 | A paused day posts nothing; the runs a pause skipped are never made up; a resumed item runs again from the day it is resumed. | `RI:67-68`, `:86-90`, `:100-101` |
| SR-5 | Pause and resume: `commitments.manage`; the item visible (any version shares to a visible vehicle) else 404; every vehicle of the latest version visible else 403 with no detail; logged only when something changed, section `recurring`, reason `Paused {name} from {yyyy-MM-dd}` / `Resumed {name} from {yyyy-MM-dd}`; the answer is `{id}`. | `RUC:24-42` (uncommitted); `SEP:130-133`; `RPA:89-92`, `:109-124` |
| SR-6 | Every scheduled-item snapshot gains `PausedFrom` and `Pauses` (`[{From, Through}]` by `From`) after `StoppedFrom`. | `RUC:170-175` (uncommitted) |
| SR-7 | The list's new fields: `pausedFrom` (the start of the open pause, else null); for a saving `lastRun` (the last run date on or before today on the viewer's vehicles), `lastRunVehicles` (the postings that day) and `balance` (every posting to date on the viewer's vehicles); for a cost `null`, 0 and `null`. Postings are FP-5's from the earliest start of any of the item's versions to today. | `SR:235-278` (uncommitted); `SC:86-93`; `RPA:37-56` |
| SR-8 | Runs (`GET /setup/recurring/{id}/runs`), `commitments.view`: the item visible else 404; `{id, name (latest version), kind, start (earliest start of its versions), total (every run to date), runCount (run dates), runs}` where `runs` are the last ten run dates, newest first, each `{date, amount, shares: [{vehicleId, registration, amount}]}` by registration. Costs have runs too. | `RUC:16-19`; `SR:280-296`; `SC:94-98`; `RPA:46-51` |
| SR-9 | Summary (`GET /setup/recurring/summary`), `commitments.view`: the month holding the business date, `{from, to, costsDue, saved, savingsBalance}` on the viewer's vehicles: `costsDue` = cost runs from the first of the month to today plus those from tomorrow to the month's end on vehicles in the fleet those days (join and leave only); `saved` = saving runs this month to today; `savingsBalance` = every saving run to date. Zeros when the viewer has no vehicle or no item. | `SR:298-322`; `SC:99-101`; `RPA:53-56`, `:70-73` |
| SR-10 | A stop stays final and refuses a pause or resume; a stop dated later is pending and can be cancelled (unchanged). | `RI:42-66`; `RPA:110-119` |

### 2.3 Reports and exports (`RP-*`)

| Id | Rule | Cite |
|---|---|---|
| RP-1 | Catalogue (`GET /setup/reports`), `reports.view`: `{businessDate, firstDayOfWeek, fleet, pettyCash, holders, canExport}`; `fleet` lists `net, target, moneyOut, gaps, savings, investment`, investment only with `invest.view`; `pettyCash` lists `cashBook, managers, vehicles, items, waiting, sentBack` only with `pettycash.spend` or `pettycash.view_all`; `holders` every float with `view_all`, else the person's own; `canExport` = `reports.export`. | `RU:16-22`; `RC:7-19`, `:49-50`; `RPT:232-245`, `:485-489` |
| RP-2 | A report read, `reports.view`, in order: page and page size; `q` trimmed, at most 200; the group and report known, else 404; the period (dated reports): both days (`Choose the first and last day.`), `from <= to` (`The first date cannot be after the last date.`), at most 367 days counted inclusive (`Choose at most 367 days.`), `from` not after today (`Choose a period that starts on or before today.`); `to` is cut to the business date. | `RU:24-39`, `:96-113`, `:216-228`; `RPT:420-490` |
| RP-3 | Every fleet figure is cut to the vehicles the person sees (scope: all companies, companies, vehicles), optionally narrowed by `companyId`. | `RR:12-21`; `RPT:247-262` |
| RP-4 | One vehicle's figures over a period (shared by net, target, gaps, investment and the vehicle report): its days are the period cut to `[join date, day before it left]` and never after today; the target sums `weekly target / 7` over the days before today and any day captured; a missing day is before today, active (away excluded) and without a record; revenue sums the amounts; captured counts records with an amount, no-revenue days records without one; the three buckets sum cost postings; saved sums saving postings. | `FR:11-43`; `SR:328-363` |
| RP-5 | Net by vehicle: rows by net (highest first) then registration; columns `vehicle, company, revenue, repairs, charges, loans, moneyOut, net, saved` (the money columns summed); headline `Net`; figures `Revenue`, `Money out`, `Saved`. | `FR:59-72`; `RPT:41-86` |
| RP-6 | Revenue against target: rows by reached (lowest first, no target last) then registration; columns `vehicle, company, captured, noRevenue, missing, revenue, target, reached, against`; headline `Revenue`; figures `Target`, `Reached` (of the totals, 0 without a target), `Missing days`. Reached = `round(part / whole x 100, 1)` half away from zero, null when the whole is 0. | `FR:74-91`; `TB:11-13`; `RPT:88-118` |
| RP-7 | Capture gaps: one row per missing day, by day then registration, `What is missing` = `Revenue not captured`; headline `Missing days`; figure `Vehicles with gaps`. | `FR:93-104`; `RPT:114-117` |
| RP-8 | Savings: postings from the earliest join date to `to`; `runs` and `saved` count the period, `balance` every run since each saving began; vehicles with neither are left out; by balance then registration. | `FR:106-129`; `RU:128-133`; `RPT:144-155` |
| RP-9 | Investment, `invest.view` else 403 `The investment report needs the permission "See what was invested in a vehicle".`: undated, each vehicle that has joined, `invested` = the sum of its investment entries, `net` = RP-4 from the join date to today, `recovered` = RP-6's percent (null when nothing invested); by recovered (highest first, none last) then registration; headline `Invested in vehicles`; figures `Net since joining`, `Recovered`. | `RU:119-126`; `FR:131-154`; `RR:38-45`; `RPT:157-180` |
| RP-10 | Money out: cost postings of the visible vehicles in the period from every source, grouped by expense item (a scheduled cost without one by its name), the category its category's name or the bucket's label; a central row shared by several vehicles counts `group units x amount / group total` units at the group's unit cost, so lowest and highest unit cost are what was paid; by amount then item; headline `Money out`; figures the three buckets. A scheduled cost shows its item's current name. | `FR:156-197`; `RU:140-142`; `RPT:120-142` |
| RP-11 | Petty-cash reports need `pettycash.spend` or `pettycash.view_all` (else 403 `Petty cash reports needs the permission "View every float".`); `holderId` must be one of the person's floats, else 404; rows are the entries the Petty cash page shows them, not removed. `waiting` is undated (every waiting entry up to today), the others dated. | `RU:156-206`; `PCR:18-24`, `:112-133`; `RPT:182-245` |
| RP-12 | Cash book (opening from the tallies before `from`, a row per day: opening, cash, expenses, credits, closing, waiting), By manager, By vehicle (company only for vehicles in the person's scope; a vehicle outside it keeps its registration), By item, Waiting (oldest first, `days waiting`), Sent back (with the comment); a credit note reads `Credit note to {payee}`, or `Credit note` without a payee (uncommitted). | `PR:13-152`; `PR:38-39` |
| RP-13 | Search and paging on the server: every word of `q` must appear in the row, case-insensitive, matched against what the cells show (text; a date also as `9 Oct 2026`; a number as written and with thousands separators); `total` counts the matches, `totals` adds up each summed column over all of them (null for the others); headline and figures always cover the whole report. Default page size 50. | `TB:20-68`; `RC:17`, `:37-47`; `RPT:418-513` |
| RP-14 | Report export (`GET /setup/reports/{group}/{report}/export`), `reports.export`, one write transaction: `format` (null, empty or `xlsx` Excel, `pdf` PDF, else `Choose Excel (xlsx) or PDF.`), `q` as RP-13, the table and every row `q` leaves (no paging, no cap), the file, and one change-log entry: section `reports`, a new entity id, no vehicle, `before` null, `after` `{group, report, From, To, holderId, companyId, q, Rows (the count), Format}`, reason `Exported {title}[ for {period}][, searched for "{q}"] to {Excel|PDF}`. File name `{title}[ {period}].{xlsx|pdf}`; period `{d MMM yyyy}` or `{from} to {to}`. | `RU:41-81`, `:230-233`; `RE:36-45`; `RPT:264-307`, `:385-416` |
| RP-15 | Screen exports (uncommitted), each the screen's own read under its own right, then the file through RP-14's writer under `reports.export` (a second transaction): Revenue (`weekStart`, `companyId`, `format`; table `Revenue`: vehicle, company, the seven days labelled `ddd d` with the amount, the reason, `Missing` or nothing, `Week total`, `Expected`, `Reached`; figures `Expected`, `Reached`, `No revenue days`, `Missing days`; filter `All companies` or the company); Central expenses (the ledger's filters, every matching row up to 10 000; columns `date, vehicle, item, category, quantity, unit, amount, source, recordedBy` where `recordedBy` is `Standing order` for a scheduled row and `{recorder}, {holder}'s float` for petty cash; figures `Central`, `Petty cash`, `Scheduled`); Petty cash (`view` `expenses` or `cash`, else `Choose the expenses or the cash received.`; the overview's period; tables `Petty cash, expenses` and `Petty cash, cash received`; headline `Cash balance`). Past 10 000 rows: 400 `There are {n:N0} rows to export, more than 10,000. Choose a shorter period or search.` | `SX:11-142`; `RVE:44-47`; `CEE:39-42`; `RPT:309-368` |
| RP-16 | Excel (built in code): row 1 title band; row 2 `{organization}  ·  {period}  ·  {filters}`; row 3 `Exported {d MMM yyyy} by {name}`; row 5 the figure labels upper-cased (money and net with ` ({CUR})`); row 6 their values; row 8 the header; rows from 9 banded; a totals row when any column sums (`{n} rows` or `1 row` in the first cell); header frozen and repeated on printed pages; auto-filter over the table; A4 landscape one page wide; footer `XCODE Fleet finance | {title}, {period}` and `Page &P of &N`; numbers as numbers (formats `#,##0` or `#,##0.00`, net in red when negative, percent `0.0"%"`, quantity `#,##0.###`), dates as day serials formatted `d mmm yyyy`, every text cell an inline string; sheet name at most 31 characters without `: \ / ? * [ ]`; characters XML cannot hold are dropped. The organization is the branding's display name or `XCODE`. An undated report's period reads `As at {d MMM yyyy}`. | `RW:8-317`; `RF:5-46`; `RR:35-36`; `RPT:271-296` |
| RP-17 | PDF (PDFsharp 6, MIT): A4 landscape (842 x 595 pt); a brand band with the logo, title and period; the organization and filters with the stamp; a headline card and figure tiles; the header row repeated on every page; banded rows; a bar beside each percentage; a tinted totals row; `Nothing to show for these dates.` when empty; footer with `Page i of n`; Figtree Regular, Figtree Bold and Fraunces Bold embedded (`/FontFile2`); document title = report title, author = organization, creator `XCODE Fleet finance`. | `RPDF:10-304`; `RPT:385-416` |
| RP-18 | The change log's `reports` rows are visible only to people who see every company (the scoped-viewer filter lists no `reports` section). | `SR:372-387` |

### 2.4 Day capture (`RD-*`)

| Id | Rule | Cite |
|---|---|---|
| RD-1 | `GET /setup/revenue/day?date&companyId`, `revenue.view`: `date` defaults to the business date; after it or more than 3 650 days before it -> 400 `Choose a day from the last ten years up to today.` | `RVU:45-53`; `RDT:65` |
| RD-2 | Vehicles: in scope, joined by the date and not left, of the company when given, not away that day; by registration then id; at most 500, `truncated` when more were active. | `RDQ:12-28`; `RDC:5-8` |
| RD-3 | A row is `{id, companyId, registration, day, lastWeek}`: `day` the week grid's cell for that date (status, expected, amount, reason, note, canEdit, editedAfterCapture, version); `lastWeek` the record seven days earlier as `{amount, reason label}`, or null. | `RDQ:30-45`; `RDC:10-13`; `RDT:41-72` |
| RD-4 | `PUT /setup/revenue/day/{date}` body `{rows: [{vehicleId, amount, reason, note, version}]}`, either `revenue.capture` or `revenue.correct`: rows required (`Enter the revenue or a no-earnings reason for at least one vehicle.`), at most 500 (`Save at most 500 vehicles at once.`), distinct (`Each vehicle can be in the day only once.`); every vehicle in scope, else 404; then each row through the single save's steps (replay first, then date, activity, rights, version) in the order sent. | `RVU:64-100`; `RDC:15-22`; `RDT:103-128` |
| RD-5 | All or nothing: a refused row saves none of the day. A 400 names the vehicle: `{registration}: {sentence}`; a 403 keeps its own sentence; a conflict is 409 title `This day already has a different record.`, detail `{registration} was changed after you opened the day. Check its current record and save again.`, with `current` (the cell) and `vehicleId`. A single save's conflict has no `vehicleId` and the detail `This day was changed after you opened it. Check the current record and save again.` | `RVU:82-99`; `RVE:22-36`; `RVC:138-148`; `RDT:103-149` |
| RD-6 | The answer is `{rows: [{vehicleId, id, version}]}` in the order sent; an identical row is a replay (no write, no log). | `RDC:24-26`; `RDT:74-101` |

### 2.5 List filters (`LF-*`)

| Id | Rule | Cite |
|---|---|---|
| LF-1 | People: `role` (a role name) and `status` (`active`, `waiting`, `none`; else `Status must be active, waiting or none.`). Built in Python by the `verify.md` run on prompt 05; 07b D2 widened `status`. | `SEP:73-77`; `LFT:35-67` |
| LF-2 | Vehicles: `companyId` keeps that company's visible vehicles; the total counts them. | `SEP:107-110`; `SR:79-84`; `LFT:16-33` |
| LF-3 | Scheduled items: `kind` (`cost`, `savings`; else `Kind must be cost or savings.`), `companyId`, `status` (`running`, `stopped`; else `Status must be running or stopped.`), each blank or `all` meaning none; running items first, then the current name, then id. | `SC:7-29`; `SR:175-203`; `LFT:69-102` |

### 2.6 Fleet postings (`FP-*`)

| Id | Rule | Cite |
|---|---|---|
| FP-1 | One service is where every report, the ledger's scheduled rows and the vehicle report read a vehicle's postings: central expenses not removed; petty-cash expenses approved and not removed (present only while approved); scheduled runs, costs and savings. | `AFP:43-58`; `IFP:8-78`; `SR:340-345` |
| FP-2 | Each vehicle counts only inside its own days: from `max(from, join date)` to `min(through, business date)`, ending the day before it left. Days away are not excluded. | `IFP:12-24` |
| FP-3 | A central posting carries the item and category names, the category's bucket, units, unit amount, total, note, recorder, group and version. | `IFP:44-58` |
| FP-4 | A petty-cash posting carries the entry id, item, category, bucket, units, unit amount, total, note, recorder and holder. | `IFP:60-74` |
| FP-5 | A scheduled posting is one per due date and share: the item id, the version id, the version's name, item and note, the share as one unit, the category's name when the version names an item, the reported bucket (a cost's bucket, a saving none); due dates per FP-2's window and the item's pauses. | `IFP:80-113`; `RI:96-115` (pauses uncommitted) |
| FP-6 | The vehicle report lists postings `{itemId, versionId (the entry id for central and petty cash), date, name, kind, amount, bucket, source}` with `source` `central`, `pettycash` or null for scheduled, by date, name, item, version; its buckets, money out, net, savings and costs sum them. Gate `vehicles.manage`. | `SR:328-363`; `SC:105-113`; `VRT:111-124`, `:228-287` |
| FP-7 | The investment's `returned` is the vehicle report's net from the join date to today. | `VRT:167-195` |

---

## 3. Persistence

### 3.1 `CentralExpenses` (migration `20261009153259_CentralExpenses`, committed)

| Column | Type | Null | Note |
|---|---|---|---|
| `Id`, `OrganizationId` | uniqueidentifier | no | PK `(OrganizationId, Id)` |
| `Date` | date | no | |
| `VehicleId` | uniqueidentifier | no | FK `(OrganizationId, VehicleId) -> FleetVehicle` restrict |
| `ExpenseItemId` | uniqueidentifier | no | FK `(OrganizationId, ExpenseItemId) -> ExpenseItem` restrict |
| `Units` | decimal(12,3) | no | |
| `UnitAmount`, `Total` | decimal(14,2) | no | |
| `Note` | nvarchar(80) | yes | |
| `GroupId` | uniqueidentifier | no | |
| `GroupSize` | int | no | |
| `GroupTotal` | decimal(14,2) | no | |
| `GroupUnits` | decimal(12,3) | no | |
| `GroupUnitAmount` | decimal(14,2) | no | |
| `RecordedBy`, `UpdatedBy` | uniqueidentifier | no | no FK |
| `RecordedAt`, `UpdatedAt` | datetimeoffset | no | |
| `RemovedBy`, `RemovedAt` | uniqueidentifier / datetimeoffset | yes | |
| `RemovalReason` | nvarchar(500) | yes | |
| `Version` | bigint | no | concurrency token |

Indexes: `(OrganizationId, Date)`, `(OrganizationId, ExpenseItemId)`, UNIQUE `(OrganizationId, GroupId, VehicleId)`,
`(OrganizationId, VehicleId, Date)`. FK to `Organizations`. Tenant query filter like every entity (`CEM:13`). Never
deleted; no `CHECK` constraints (the domain holds the rules).

### 3.2 `RecurringPause` (migration `20261010194310_RecurringPauses`, uncommitted)

`(OrganizationId, Id)` PK, `ItemId` FK `(OrganizationId, ItemId) -> RecurringItem` restrict, `From date`, `Through date
NULL`; index `(OrganizationId, ItemId, From)`. No constraint ties `Through` to `From`, and nothing stops two open pauses
but the domain (`RI:73`).

### 3.3 Reports

No table. Exports are written to the change log (`OrganizationSettingsVersion`, section `reports`, `VehicleId` null).

---

## 4. HTTP contract

Every route below is under `RequireAuthorization()` and `WithSetupErrors()` (`SEP:26-44`): 400 `Invalid setup change`
with the sentence as `detail`; 403 `Not permitted in this organization or data scope.` with the sentence as `detail` or
none; 404 `Record not found in your scope.`; 409 `Settings changed. Reload before saving.` (EF concurrency) or `A
conflicting record exists. Reload before saving.` (unique). Problem details as in `docs/06-http-contract.md` 1.6.

### 4.1 Central expenses (tag `Central expenses`, `CEE:18`)

| Id | Method and path | Permission | operationId | Success |
|---|---|---|---|---|
| E01 | `GET /setup/expenses/ledger?from&to&source&q&page=1&pageSize=100` | `expenses.view` | `GetExpenseLedger` | `ExpenseLedgerDto` |
| E02 | `GET /setup/expenses/export?from&to&source&q&format` | `expenses.view`, then `reports.export` | `ExportExpenseLedger` | file (RP-15) |
| E03 | `GET /setup/expenses/options?date` | any of `expenses.capture`, `expenses.correct` | `GetExpenseOptions` | `ExpenseOptionsDto` |
| E04 | `POST /setup/expenses/entries` | `expenses.capture` | `RecordExpense` | 200 `ExpenseRecorded` |
| E05 | `PUT /setup/expenses/entries/{id:guid}` | any of `expenses.capture`, `expenses.correct`, then CE-12 | `ChangeExpense` | 200 `ExpenseSaved` |
| E06 | `POST /setup/expenses/entries/{id:guid}/remove` | any of the two, then CE-12 | `RemoveExpense` | 200 `ExpenseSaved` |

DTOs, properties in wire order (camelCase):
- `ExpenseLedgerDto`: `businessDate, from, to, permissions {canRecord, canCorrect}, figures {total, central, pettyCash,
  scheduled}, items [ExpenseLedgerRowDto], pageNumber, pageSize, total, amount` (`CEC:24-25`).
- `ExpenseLedgerRowDto`: `id (string), source, date, vehicleId, registration, expenseItemId (null), itemName,
  categoryName (null), bucket (integer 1..3), units, unitAmount, total, note, recordedByName, holderName, scheduleId,
  group {id, size, total, units, unitAmount} | null, version | null, canEdit, canRemove` (`CEC:19-21`, `:15`).
- `ExpenseOptionsDto`: `vehicles [{id, companyId, companyName, registration, active}], items [{id, name, categoryId,
  categoryName, bucket}]` (`CEC:27`; `SC:104`, `:117`).
- `RecordExpense` (body): `date, expenseItemId, units, unitAmount, allocations [{vehicleId, amount}], id?, note?`
  (`CEC:32-37`); `ExpenseRecorded`: `ids, total` (`CEC:39`).
- `ChangeExpense` (body): `date, vehicleId, expenseItemId, units, unitAmount, version?, note?`; `RemoveExpense`:
  `version?, reason?`; `ExpenseSaved`: `id, version` (`CEC:41-53`).
- 409: title `This expense has changed.` with `current` (CE-23), or `This expense was changed by another save.` /
  `Reload and try again.` (CE-14).

### 4.2 Reports (tag `Reports`, `RE:18`)

| Id | Method and path | Permission | operationId | Success |
|---|---|---|---|---|
| G01 | `GET /setup/reports` | `reports.view` | `GetReportsAccess` | `ReportsAccessDto` |
| G02 | `GET /setup/reports/fleet/{report}?from&to&companyId&q&page=1&pageSize=50` | `reports.view` (investment also `invest.view`) | `GetFleetReport` | `ReportTableDto` |
| G03 | `GET /setup/reports/pettycash/{report}?from&to&holderId&q&page=1&pageSize=50` | `reports.view` and `pettycash.spend` or `pettycash.view_all` | `GetPettyCashReport` | `ReportTableDto` |
| G04 | `GET /setup/reports/{group}/{report}/export?from&to&holderId&companyId&q&format` | `reports.export` and the report's own gates | `ExportReport` | file; produces `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` and `application/pdf` |

- `ReportsAccessDto`: `businessDate, firstDayOfWeek, fleet [ids], pettyCash [ids], holders [{id, name, active}],
  canExport` (`RC:49-50`).
- `ReportTableDto`: `group, report, title, from, to, businessDate, headline {label, value, kind}, figures [{label,
  value, kind}], columns [{key, label, kind, sum}], rows [[cell]], pageNumber, pageSize, total, totals [number|null]`;
  a cell is a string, a number or null; dates `yyyy-MM-dd`; `from`/`to` null for undated reports (`RC:33-47`). Kinds:
  `text, vehicle, date, money, net, count, quantity, percent` (`RC:21-31`).
- A file answer is `Results.File(bytes, contentType, fileName)`: `Content-Disposition: attachment; filename=...;
  filename*=UTF-8''...` (ASP.NET Core's form) with the name of RP-14.

### 4.3 Day capture and screen exports (tag `Revenue`, `RVE:21`; petty cash under its own tag)

| Id | Method and path | Permission | operationId | Success |
|---|---|---|---|---|
| D01 | `GET /setup/revenue/day?date&companyId` | `revenue.view` | `GetRevenueDay` | `RevenueDayDto` `{date, businessDate, vehicles [{id, companyId, registration, day (cell), lastWeek {amount, reason} | null}], truncated}` |
| D02 | `PUT /setup/revenue/day/{date}` | any of `revenue.capture`, `revenue.correct` | `SaveRevenueDay` | `RevenueDaySaved` `{rows [{vehicleId, id, version}]}`; 400, 409 problems |
| X02 | `GET /setup/revenue/export?weekStart&companyId&format` | `revenue.view`, then `reports.export` | `ExportRevenueWeek` | file |
| X03 | `GET /setup/pettycash/export?from&to&holderId&view&status&q&format` | the petty-cash read rights, then `reports.export` | `ExportPettyCash` | file |
| X04 | = E02 | | `ExportExpenseLedger` | |

The petty-cash export's route and operation id are in `apps/api/Api/PettyCashEndpoints.cs` (uncommitted lines; checked by
prompt 08 D0's inventory); `ProducesExport` names it.

### 4.4 Scheduled items (tag `Setup`, `SEP:51-55`)

| Id | Method and path | Permission | operationId | Success |
|---|---|---|---|---|
| S53 | `GET /setup/recurring/summary` | `commitments.view` | `GetSetupRecurringSummary` | `{from, to, costsDue, saved, savingsBalance}` |
| S54 | `GET /setup/recurring/{id:guid}/runs` | `commitments.view` | `GetSetupRecurringRuns` | `{id, name, kind, start, total, runCount, runs [{date, amount, shares [{vehicleId, registration, amount}]}]}` |
| S55 | `POST /setup/recurring/{id:guid}/pause` | `commitments.manage` | `PauseSetupRecurring` | `{id}` |
| S56 | `POST /setup/recurring/{id:guid}/resume` | `commitments.manage` | `ResumeSetupRecurring` | `{id}` |

`RecurringDto` gains, at the end: `pausedFrom, lastRun, lastRunVehicles, balance` (`SC:89-93`). `summary` is mapped
before `{id:guid}` routes; ASP.NET's route constraint keeps the literal from matching `{id}` either way.

---

## 5. Tests

| Class | Methods | What they pin (decisive assertions) |
|---|---|---|
| `CentralExpenseTests` | 17 | one row and its log (`CET:47-76`); splits even and uneven (`:78-112`); bad allocations and lines with each sentence (`:114-146`); vehicles, dates, items and options by date (`:148-180`); retried record and a stolen id (`:182-216`); change, replay, stale 409 with `current`, move day and vehicle (`:218-258`); a lost race is a conflict (`:260-276`); group detachment and the retry key (`:278-311`); remove with a reason, out of the ledger and report (`:313-346`); capture-own-today versus correct (`:348-390`); the ledger's three sources and no savings (`:392-429`); source and search narrow rows not figures, paging (`:431-480`); a scoped person sees nothing outside their vehicles, log included (`:482-510`); another organization (`:512-544`); OpenAPI paths (`:546-556`); pages cut where all three sources meet (`:558-613`); the same number of reads at 5, 150 and 300 rows (`:615-648`) |
| `CentralExpenseDomainTests` | 5 | one vehicle keeps the purchase id; even split keeps the unit cost only while units divide into three decimals; uneven split adds up; the purchase is checked before any row; every change and removal bumps the version and item, units or price leave the group (`CET:815-909`) |
| `ReportTests` | 13 | net agrees with each vehicle report (`RPT:41-86`); target and gaps count captured, no-revenue and missing days (`:88-118`); money out at the true unit cost (`:120-142`); savings runs and balance (`:144-155`); investment and its permission (`:157-180`); petty-cash reports follow the floats (`:182-245`); scope (`:247-262`); the Excel file's cells and the change log (`:264-307`); screen exports and their log reasons (`:309-368`, uncommitted); the PDF's pages, size and fonts (`:385-416`); paging and search (`:418-462`); periods and unknown reports (`:464-490`); search and totals without a database (`:492-513`) |
| `RecurringPauseTests` | 4 (uncommitted) | a saving's last run, balance, runs and the summary (`RPA:36-56`); a pause skips runs until resumed (`:58-93`); resuming the day it was paused skips nothing (`:95-107`); only an editor who sees every vehicle may pause, and a stopped item cannot be paused (`:109-124`) |
| `RevenueDayTests` | 4 | the day lists active vehicles with last week (`RDT:41-72`); a day saves every row and a replay changes nothing (`:74-101`); one refused row saves nothing and names the vehicle (`:103-128`); each row checks rights and scope (`:130-149`) |
| `ListFilterTests` | 3 | vehicles by company, people by role and status, scheduled items by kind, company and status with running first (`LFT:16-102`) |
| `VehicleReportTests` (changed in 9276c51) | 7 | the report counts each bucket and savings once (`VRT:68-109`); the shape, `source` last (`:111-124`); a vehicle that left (`:126-147`); scope (`:149-165`); investment's return (`:167-195`); reads do not grow with items (`:197-226`); central expenses reach the report, one read for any number (`:228-287`) |
| `PettyCashTests` (changed in the working tree) | 2 new | approving a period (`approve-day` with `to`); approving ticked entries all or none (drift row 7, prompt 08's) |

---

## 6. Client dependencies

| Client | Reads | Where |
|---|---|---|
| Shared | ledger, options, record, change, remove types and paths; `EXPENSE_PAGE_SIZE` 100, `EXPENSE_MAX_DAYS` 367, `EXPENSE_MAX_VEHICLES` 50, note 80, reason 500; `splitEvenly` (odd cents to the first rows) | `packages/shared/src/expenses.ts:1-219` |
| Shared | the report ids and labels, cell kinds, `ReportTable`, `ReportsAccess`, `reportPath`, `reportExportPath`, and (uncommitted) `revenueExportPath`, `expenseExportPath`, `pettyCashExportPath` | `packages/shared/src/reports.ts:1-169` |
| Shared | the period model `{from, to, unit}` (`day`, `week`, `fourWeeks`, `month`, `custom`) and its seven presets, computed on the client from `businessDate` and `firstDayOfWeek` | `packages/shared/src/periods.ts:1-120` |
| Shared | `RevenueDay`, `SaveRevenueDay`, `RevenueDaySaved` | `packages/shared/src/revenue.ts:238-264` |
| Web | the ledger page (figures, source select, search, paging until `items.length >= total`), the expense dialog (split rows), the remove dialog | `apps/web/components/expenses/*` |
| Web | the reports page (catalogue, one report per request, page size, search), the export menu (downloads through the proxy and names the file itself: `{label} {period}.{format}`; shows `detail` of a refusal) | `apps/web/components/reports/*`; `exportReport.ts:28-84` |
| Web | day capture: `GET setup/revenue/day?date&companyId`, `PUT setup/revenue/day/{date}` | `apps/web/lib/endpoints/revenue.ts:48-62`; `components/revenue/FleetDayDialog.tsx`, `useFleetDay.ts` |
| Web | scheduled items: pause, resume, `summary`, `runs` | `apps/web/lib/endpoints/recurring.ts:39-41`; `components/setup/RecurringPage.tsx:114`; `RecurringRunsDialog.tsx:23` |
| Mobile | none | |

---

## 7. Against the design notes

The notes decide for the rows of the design register (`docs/13-open-questions.md` question 46); elsewhere the .NET
behaviour above decides. Differences found by this reading, and where the Python design settles them:

| Topic | .NET | Notes or prototype | Python (where decided) |
|---|---|---|---|
| Rights | `expenses.*`, `commitments.*`, `reports.*`, `invest.view`; every export `reports.export` | 59 rights; `revenue.export`, `expenses.export`, `pettycash.export`, `reports.export`; `scheduled.*` and `savings.*` apart; `reports.investment`; `pettycash.reports` (`docs/15` 3.1) | `docs/06` 2.13 |
| Back-dating limit | writes refuse only the future | adding or editing a central expense is checked on the record's date (B12) | checked on record, change (old and new date) and remove (`docs/15` DEC-30) |
| Saving model | one total split over vehicles, start and end dates, back posting from a past start, weekly or monthly | an amount per vehicle, daily to yearly, a revenue condition with held, skipped and saved runs, opening balances, no start date, no back posting, no end date (B18) | `docs/04` 14.3, `docs/05` 11.3 |
| Scheduled postings | computed on read, no stored row | "a job safe to run twice: unique on schedule, run date and vehicle" (v2.28) | costs stay computed on read (one posting per item, day and vehicle by construction); saving decisions are stored under that unique key (`docs/04` 14.3) |
| Pause semantics | a pause from today skips today's run | "editing or pausing never changes rows already posted" (v2.28) | .NET (drift row 5; recorded) |
| Net by vehicle, Money out | three bucket columns; category and bucket | one money-out column per main category plus "No main category"; Money out by main category, category, item; headline figures per main category (B16, v2.31 s3) | `docs/05` 11.4 |
| Revenue against target | weekly target / 7 per day | the day targets of the set in force each day (B9, v2.32 s1) | `docs/05` 11.4 |
| Investment | the sum of dated entries; every vehicle | the initial investment, a vehicle without one last with no "Recovered" (B11, v2.32 s2) | initial plus entries (question 61's default), `docs/05` 11.4 |
| Savings report | runs, saved, balance | saved, skipped and waiting runs, saved, not saved, balance with opening balances (prototype `reportData`) | `docs/05` 11.4 |
| Petty-cash reports | `sentBack` | `Rejected and reopened` beside the others (prototype `PCREPORTS`); rights `pettycash.reports` | both, `docs/05` 11.4 |
| Capture gaps | revenue gaps | also petty cash waiting (prototype) | question 76 |
| Revenue export | `Expected`, `Reached`, `No revenue days` | `Target to date` (or `Target`), `Gap` signed; `Below 4,000` (B15, B14) | `docs/06` 2.13 |
| Central expense edits | `expenses.capture` changes own rows of the day | the prototype shows Edit only with `exp.edit` | .NET (question 77) |

---

## Appendix: uncommitted files read

`git status` and modification times (2026-10-10) of the files this inventory cites as uncommitted:

| Status | Time | File |
|---|---|---|
| `M` | 22:30 | `apps/api/Api/CentralExpenseEndpoints.cs` (changed lines 2, 39-43) |
| `M` | 22:31 | `apps/api/Api/PettyCashEndpoints.cs` |
| `M` | 22:30 | `apps/api/Api/ReportEndpoints.cs` (11, 47-53) |
| `M` | 22:30 | `apps/api/Api/RevenueEndpoints.cs` (2, 44-48) |
| `M` | 22:41 | `apps/api/Api/SetupEndpoints.cs` (126-133) |
| `M` | 22:29 | `apps/api/Application/CentralExpenseUseCases.cs` (20, 23-42, 44-47, 49-57, 59-67, 69-84, 86-87, 89-95, 97-106) |
| `M` | 22:20 | `apps/api/Application/Reports/PettyCashReports.cs` (39) |
| `M` | 22:29 | `apps/api/Application/Reports/ReportUseCases.cs` (47, 50-51, 54-82) |
| `??` | 22:30 | `apps/api/Application/Reports/ScreenExports.cs` |
| `M` | 22:41 | `apps/api/Application/Setup/ISetupRepository.cs` |
| `M` | 22:41 | `apps/api/Application/Setup/RecurringUseCases.cs` (16-43, 174-175) |
| `M` | 22:41 | `apps/api/Application/Setup/SetupContracts.cs` (86-88, 92-101) |
| `M` | 22:39 | `apps/api/Domain/Setup/RecurringItem.cs` (17-19, 67-86, 90, 100-102) |
| `??` | 22:38 | `apps/api/Domain/Setup/RecurringPause.cs` |
| `M` | 22:39 | `apps/api/Infrastructure/Setup/FleetPostings.cs` (94) |
| `M` | 22:39 | `apps/api/Infrastructure/Setup/SetupModel.cs` |
| `M` | 22:41 | `apps/api/Infrastructure/Setup/SetupRepository.cs` (235-238, 256-259, 263-323, 325-326) |
| `??` | 22:43 | `apps/api/Infrastructure/Migrations/20261010194310_RecurringPauses.cs` (and its designer file) |
| `M` | 22:32 | `tests/api/ReportTests.cs` |
| `??` | 22:46 | `tests/api/RecurringPauseTests.cs` |
| `M` | 22:27 | `tests/api/PettyCashTests.cs` |
| `M` | 22:35 | `packages/shared/src/reports.ts` |
| `M` | 22:24 | `packages/shared/src/pettyCash.ts` |
