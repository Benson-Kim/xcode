# Central expenses and reports: API contract and rules

Types: `packages/shared/src/expenses.ts`, `reports.ts` and `periods.ts` (import from `@xcode/shared/expenses`, `/reports`,
`/periods`). Design reference: `docs/design/XCODE_Web_v2.28.html` and `XCODE_Build_Notes_v2.28.pdf`. Where this file and the
prototype differ, this file wins. Web: `/api/setup/...` through the proxy; mobile (not built yet): `setup/...`.

## Menu

Dashboard, Revenue, an **Expenses** group (Central expenses, Petty cash, Scheduled expenses and savings, Expense
categories), Reports, then the **Setup** group (`NAV_SECTIONS` in `@xcode/shared/permissions`). No new permission keys.

## Central expenses: one ledger, three sources

- Every row holds exactly one vehicle. Sources: `central` (recorded here), `pettycash` (a petty cash expense, listed only
  while approved), `scheduled` (a scheduled cost, posted in full on each run date up to the business date, one row per
  vehicle). Savings are never in the ledger. Only central rows are edited here.
- A purchase shared by several vehicles is recorded once and saved as one row per vehicle. Every row keeps the purchase
  (`group`: id, size, total, units, unit amount) so price reports use the true unit cost and quantity. An even split keeps
  the unit cost (units / vehicles); any other split stores one unit at the vehicle's amount. Changing a row's item, units
  or unit amount takes it out of its group; date, vehicle and note keep it.
- Totals round to the cent, halves away from zero (`expenseTotal`). Amounts are signed and never zero (negative = refund).
- Removing is soft and needs a reason. Every record, change and removal is in the change log, section `centralexpenses`.

| Action | Needs |
|---|---|
| See the ledger | `expenses.view` |
| Record | `expenses.capture` (vehicles in the person's scope, active on the date; item in use; date not after the business date) |
| Change or remove a row | `expenses.correct`, or `expenses.capture` for the person's own row dated on the business date (its date only with `expenses.correct`) |

Each row carries `canEdit` and `canRemove`; clients never re-derive them.

| Method and path | Body / query | Returns |
|---|---|---|
| `GET setup/expenses/ledger` | `from`, `to` (at most 367 days), `source?`, `q?`, `page`, `pageSize` (at most 100) | `ExpenseLedger`, newest first; `figures` cover the whole period, `total` and `amount` every matching row |
| `GET setup/expenses/options` | `date?` | vehicles and items for the form |
| `POST setup/expenses/entries` | `RecordExpense` (client `id` for safe retry) | `ExpenseRecorded` |
| `PUT setup/expenses/entries/{id}` | `ChangeExpense` with `version` | `ExpenseSaved` |
| `POST setup/expenses/entries/{id}/remove` | `{ version, reason }` | `ExpenseSaved` |

Paging is done in the database: stored rows (central and approved petty cash) are one `UNION ALL` query cut with
`OFFSET/FETCH`; scheduled rows are worked out from the schedules and merged by date. Errors are problem+json as in petty
cash (400, 403, 404, 409 with `current`).

## Reports

`GET setup/reports` says which reports the person may open (`ReportsAccess`). Every report is one table built by the
server for a period (`from`/`to`, at most 367 days, cut back to the business date), searched (`q`) and paged
(`page`, `pageSize` at most 100) by the server. `headline` and `figures` cover the whole report; `total` and `totals`
(the footer) cover every matching row; `rows` is the page.

- Fleet (`reports.view`): Net by vehicle, Revenue against target, Money out (all three sources by item, true unit cost),
  Capture gaps, Savings, Investment (also `invest.view`; since each vehicle joined, no period).
- Petty cash (`reports.view` plus `pettycash.spend` for your own float or `pettycash.view_all` for every float): Cash book,
  By manager, By vehicle, By item, Waiting for approval (no period), Sent back.
- Everything is cut to the vehicles the person can see. Net by vehicle agrees with each vehicle's own report.

| Method and path | Query | Returns |
|---|---|---|
| `GET setup/reports` | none | `ReportsAccess` |
| `GET setup/reports/fleet/{report}` | `from`, `to`, `companyId?`, `q?`, `page`, `pageSize` | `ReportTable` |
| `GET setup/reports/pettycash/{report}` | `from`, `to`, `holderId?`, `q?`, `page`, `pageSize` | `ReportTable` |
| `GET setup/reports/{group}/{report}/export` | the same filters and `q`, `format=xlsx` or `pdf` | an Excel or PDF file of every matching row (`reports.export`), written to the change log, section `reports` |

Exports are built on the server. PDF: A4 landscape, brand band with the XCODE mark, headline card and figure tiles,
dark header row repeated on every page, banded rows, bars beside percentages, tinted totals row, "Page x of y";
Figtree and Fraunces are embedded (`apps/api/Assets/Fonts`, SIL Open Font License) and drawn with PDFsharp (MIT).
Excel: title band, organization, period and filters, who exported it, figure tiles, frozen and filtered header row,
banded rows, numbers as numbers and dates as dates, a totals row, landscape and one page wide when printed.

## Petty cash periods

`GET setup/pettycash/overview` also takes `from` and `to` (both or neither, at most 367 days, starting no later than
the business date). It then answers `period: "day"` for one day or `"range"`, opening at the start of `from` and
closing at the end of `to`; floats stay to date. `date` and `period` (`day`/`week`) still work for the phone.

## Revenue days in any order

Revenue for a vehicle can be recorded for any active day up to the business date, whatever earlier days hold. A fleet
without its history records from today and fills earlier days if and when it has them. The week still reports each
vehicle's `earliestMissing` and the dashboard still counts missing days, so gaps stay visible without being forced.
Every missing day a person may capture has `canEdit: true`.

## Capture revenue for a day

The web's Capture revenue dialog (design v2.28, `openCapture`) takes one day for every vehicle at once. Types:
`RevenueDay`, `SaveRevenueDay` and `RevenueDaySaved` in `@xcode/shared/revenue`.

| Method and path | Body / query | Returns |
|---|---|---|
| `GET setup/revenue/day` | `date?` (default the business date, never later), `companyId?` | `RevenueDay`: each vehicle active that day, in registration order, with its cell and the same day last week; at most 500, `truncated` beyond that |
| `PUT setup/revenue/day/{date}` | `{ rows: [{ vehicleId, amount, reason, note, version? }] }` | `RevenueDaySaved` |

The rows are saved together or not at all, each under the rules of a single save (`revenue.capture`, `revenue.correct`
for a past day that has a record, `revenue.noearnings` for a reason, `version` for an existing record). A row identical
to the saved record changes nothing. A refused row's message starts with the registration ("KDA 101A: …"); a 409 also
carries `vehicleId` and `current`. Rows left blank are not sent: the day stays missing for those vehicles.

## Setup lists page and filter on the server

Every list pages in the database (`page`, `pageSize` at most 100, 25 by default on the web) and filters there too, so a
filtered list counts and pages its own matches:

- `GET setup/vehicles?companyId=`
- `GET setup/recurring?kind=cost|savings&companyId=&status=running|stopped`: running items first (not stopped or ended,
  and sharing to a vehicle in the fleet today), then by name
- `GET setup/people?role=&status=active|waiting|none`: active has a PIN, waiting has none yet, none is switched off
- `GET setup/history` pages by number with `includeTotal=true`

## Not built yet

Splitting petty cash spending across vehicles; savings rules (minimum revenue, held runs) and opening
balances; schedules posted as stored rows; the mobile screens for all of the above.
