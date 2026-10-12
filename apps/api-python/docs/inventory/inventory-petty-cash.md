# Petty cash inventory: the .NET petty-cash feature (uncommitted) that the Python + PostgreSQL rewrite must reproduce

Purpose: one file, four lenses (rules, persistence, HTTP contract, tests) plus the client dependencies, so the planner can add
the petty-cash tables to `docs/04-schema.md`, the routines to `docs/05-routines.md`, the endpoint rows and message codes to
`docs/06-http-contract.md`, and write one conversion prompt. Other inventories (`inventory-http-contract.md`,
`inventory-domain.md`, `inventory-persistence.md`, `inventory-tests.md`) predate this feature and do not mention it.

Basis of this inventory
- Repository `C:\Users\user\Documents\Coding\PrioriTech\xcode-wt\revenue`, branch `fix/format`, HEAD `3253914`. Read-only
  reading of the working tree on 2026-10-08 (the clock of the machine read 00:13; the newest petty-cash file was written
  2026-10-07 21:46). No build, no test run: nothing here records a pass or a failure.
- **(uncommitted)** marks a fact whose only source is an uncommitted or untracked file. Almost everything in this file is
  uncommitted: the whole feature (entity, repository, use cases, endpoints, two migrations, the shared module, both client
  screens and their tests) is untracked (`??`). The permission keys, labels, dependencies and role defaults for petty cash
  are older and committed (as string literals); only their constants (`PermissionKeys.cs`, untracked) are new. Every file's
  modification time and `git status` line is in the Appendix. Another session may still be editing; re-check mtimes before
  relying on a line number.
- `file:line` uses the numbering of the file as read. Application and Domain files are cited by basename:
  `PettyCash.cs` = `apps/api/Domain/PettyCash.cs`; `Contracts` = `apps/api/Application/PettyCashContracts.cs`;
  `UseCases` = `apps/api/Application/PettyCashUseCases.cs`; `Endpoints` = `apps/api/Api/PettyCashEndpoints.cs`;
  `Model` = `apps/api/Infrastructure/PettyCashModel.cs`; `Repo` = `apps/api/Infrastructure/PettyCashRepository.cs`;
  `PettyCashTests.cs` = `tests/api/PettyCashTests.cs`; `Shared` = `packages/shared/src/pettyCash.ts`.
- The .NET namespace `Auth` appears only inside citations. The product is "xcode".
- **(2026-10-12)** Re-checked by prompt 08's drift pass against `HEAD` 493bf82 plus the uncommitted working tree of
  `fix/web-dropdowns`. The reading above matches commit ad2f1cc (2026-10-08 08:47: same line counts, 220, 449 and 88);
  6f130aa, 9276c51 and the working tree (2026-10-10 22:20 to 22:41) changed it since. Every correction is marked
  **(2026-10-12)** and cites the current file; other `file:line` citations keep the 2026-10-08 numbering. This file describes
  .NET only: the design notes change the feature further, and the Python build follows them where they differ
  (`docs/15-design-v2-3.md` B19, decisions DEC-21 to DEC-29).
- Endpoint ids `P01`-`P10` are new for this file (the existing ids stop at `A13`, `S44`, `R03`, `O07`, `H03`, `X01`).
  Rule ids are `PC-1`...`PC-30`.

Section list
1. Scope and state
2. Entities and rules
3. Persistence
4. HTTP contract
5. Tests
6. Client dependencies
7. Naming audit
8. Open questions
Appendix: files read, modification times, `git status`

---

## 1. Scope and state

### 1.1 What petty cash is (as built)

Petty cash is a per-person cash float. A **holder** is a member who records spending (permission `pettycash.spend`) or anyone
who already has an entry. Three kinds of **entry** move a float (`PettyCash.cs:3-8`): `cash` (money given to the float by an
issuer; negative means taken back), `expense` (spending against one vehicle and one expense item, `units x amount each`),
and `credit` (a "credit note": money paid out that belongs to no vehicle, with a payee and a reason). Balance = cash - credit -
expense over every entry not removed, whatever its status (`Repo:66-73`, `UseCases:357-378`). The float may go negative;
only **cash taken back** (and removing or reducing cash) is held at zero unless the person has `pettycash.issue_negative`
(`UseCases:327-335`). Expenses and credit notes start `waiting` and are approved or sent back by a reviewer; cash is never
reviewed (status null). An **approved expense** (only) posts into its vehicle's report as a cost under its item's category
bucket (`SetupRepository.cs:254-261`, **(uncommitted)** edit of a committed file). Removal is soft and needs a reason.

So the feature is: floats, entries, approvals (single and whole-day), issuing money (cash given or taken back), per-person
approval limits, two dashboard cards, and a change-log section `pettycash`. Office bills are **not** part of it and do not
exist in the API at all (only the permission keys `bills.*` exist; `apps/mobile/src/shell/access.ts:53` says
"Office bills are not available from the current API yet.").

### 1.2 What exists where (all **(uncommitted)** unless stated)

| Part | API | Web | Mobile | Shared |
|---|---|---|---|---|
| Entity, rules | `PettyCash.cs` (220 lines) | reads flags only | reads flags only | `Shared` types and parsers |
| Persistence | `Model` + 2 migrations + snapshot | none | none | none |
| Use cases | `UseCases` (449 lines) | none | none | none |
| Endpoints P01-P10 | `Endpoints` (88 lines) | proxy allow-list + `components/pettycash/*` | `src/pettycash/*` | path builders |
| Dashboard cards | P04 | `AppShell.tsx` + `dashboardCards.ts` | `screens.tsx` + `dashboard.ts` | `DASHBOARD_CARDS` in `permissions.ts` (untracked) |
| Permissions (committed strings) | `AccessContracts.cs:33-64`, `Access.cs:58-79` | `people/model.ts:11-15` | `access.ts` | `permissions.ts:23-28` |
| Contract note | none | `docs/petty-cash-contract.md` (75 lines, untracked) | same | same |

### 1.3 What is unfinished or only partly wired

- No `TODO`/`FIXME` marker in any petty-cash file (grep over API, shared, web, mobile petty-cash files returned nothing).
- API tests exist for most of P01-P10 but not for P03 (`options`) at all, nor for search `q`, `status`, `from > to`, paging
  validation, the 80/200-character limits, the ten-year window, kind change, holder change, the audit event row, or the
  idempotent replays of approve and send-back (Section 5.3 lists them). Web and mobile tests use fake servers.
- Offline: the phone does not queue petty cash; it needs the network (`PettyCashScreen.tsx:69,99,199-200`). The revenue
  offline queue is unrelated.
- `docs/petty-cash-contract.md:40` says reviewers change entries "any status" and the holder "while waiting or sentBack";
  the code adds conditions (Section 2.4, PC-13). The doc is a design note, not the contract.
- Week boundaries are computed twice: the server (`UseCases:337-338`) and the phone (`formats.firstDayOfWeek()`,
  `sections.tsx:117-122`, `PettyCashScreen.tsx:214`). The web takes `from`/`to` from the overview answer.
- Approval limits are read from `Memberships.ApprovalLimit` (committed column, `OrganizationModel.cs:29`); they are set by
  `AccessUseCases` (committed). No petty-cash endpoint sets them.
- The six `pettycash.*` keys and both `dash.*` keys are all used by the API; the `bills.*` keys are catalogue entries with no endpoint.

---

## 2. Entities and rules

### 2.1 Enums (domain, then wire)

| Enum | Values (stored int) | Wire word | Where |
|---|---|---|---|
| `PettyCashKind` | `Cash`=1, `Expense`=2, `Credit`=3 | `"cash"`, `"expense"`, `"credit"` | `PettyCash.cs:3-8`; `Contracts:10-16` |
| `PettyCashStatus` | `Waiting`=1, `Approved`=2, `SentBack`=3; column nullable (null for cash) | `"waiting"`, `"approved"`, `"sentBack"`, JSON `null` for cash | `PettyCash.cs:10-15`; `Contracts:18-25` |
| `ExpenseBucket` (shared, committed) | `RepairsAndMaintenance`=1, `RecurringCharges`=2, `LoanRepayments`=3 | JSON integer 1-3 (no string converter is registered; `Program.cs` has no JSON options) | `ExpenseCatalog.cs:5-10`; `Shared:9` |

Kind is stored as an integer, so `ORDER BY Kind` (entries list) orders cash, expense, credit.

### 2.2 Entity `PettyCashEntry` (table `PettyCashEntries`, **(uncommitted)** `PettyCash.cs:88-220`)

| Field | Type | Rule |
|---|---|---|
| `OrganizationId` | Guid | Tenant; part of the key; `IOrganizationEntity.OrganizationId` setter throws `Tenant cannot change.` (`:90-94`) |
| `Id` | Guid | Client may supply it on create (PC-15); not empty |
| `HolderId` | Guid | The float. FK to the holder's membership. Fixed at create; an entry cannot move (`UseCases:130-131`) |
| `Kind` | enum | Fixed at create (`PettyCash.cs:149-150`) |
| `Date` | DateOnly | Business date of the entry; window in PC-10 |
| `VehicleId` | Guid? | Required for `expense`, forbidden otherwise |
| `ExpenseItemId` | Guid? | Required for `expense`, forbidden otherwise |
| `Units` | decimal(12,3) | `> 0`, at most 3 decimals, `<= 999999999.999`; exactly 1 for cash and credit |
| `UnitAmount` | decimal(14,2) | Signed, never 0, at most 2 decimals, `abs <= 999999999999.99` |
| `Total` | decimal(14,2) | `round(Units * UnitAmount, 2, away from zero)`; never 0; `abs <= 999999999999.99` (PC-3) |
| `Payee` | string? (80) | Required for `credit`, forbidden otherwise; trimmed |
| `Note` | string? (80) | Required for `credit` (it is the reason); optional otherwise; trimmed; blank becomes null |
| `Reimbursable` | bool | Only a credit note may set it |
| `Status` | enum? | Null for cash; `Waiting` at create for expense and credit |
| `SentBackNote` | string? (200) | The reviewer's comment while `SentBack`; cleared on approve or change |
| `ReviewedBy` / `ReviewedAt` | Guid? / instant? | Set by approve and send-back; cleared by a change |
| `RecordedBy` / `RecordedAt` | Guid / instant | The actor and the UTC instant of the create; never change |
| `UpdatedBy` / `UpdatedAt` | Guid / instant | Set by every change, approve, send-back and remove |
| `RemovedBy` / `RemovedAt` / `RemovalReason` | Guid? / instant? / string? (500) | Soft delete; `RemovedAt != null` means removed |
| `Version` | long | Starts at 1; `+1` on every change, approve, send-back and remove (`PettyCash.cs:122,195-200`); EF concurrency token |
| derived (not stored) | | `Removed`, `Reviewed` (kind is not cash), `Effect` (cash `+Total`, others `-Total`) are ignored by the model (`Model:14-16`) |

All instants must have a zero offset or the domain throws `Petty cash instants must be UTC.` (`PettyCash.cs:216-219`).

### 2.3 Line validation `PettyCashLine.Validate` (`PettyCash.cs:37-83`), in this order; every failure is a 400 with the text as `detail`

| # | Condition | Message |
|---|---|---|
| 1 | kind not defined (unreachable from HTTP; the parser fails first) | `Choose an expense, a credit note or cash.` |
| 2 | `Date == default` (0001-01-01, also a missing `date`) | `Enter the date.` |
| 3 | `UnitAmount == 0` (also a missing `unitAmount`) | `Enter an amount other than zero.` |
| 4 | more than 2 decimals, or `abs > 999999999999.99` | `Enter the amount with at most two decimals.` |
| 5 | `Units <= 0`, `> 999999999.999`, or more than 3 decimals | `Units must be above zero, with at most three decimals.` |
| 6 | kind is not expense and `Units != 1` | `Only an expense has units.` |
| 7 | `Total == 0` after rounding | `The total rounds to zero. Check the units and the amount.` |
| 8 | `abs(Total) > 999999999999.99` | `The total is too large.` |
| 9 | trimmed note longer than 80 | `The note must be at most 80 characters.` |
| 10 | expense without vehicle (null or empty Guid) | `Choose the vehicle.` |
| 11 | expense without item | `Choose what it was for.` |
| 12 | expense with a payee or `reimbursable` | `Only a credit note has a payee.` |
| 13 | credit with a vehicle or an item | `A credit note is not recorded against a vehicle.` |
| 14 | **(2026-10-12)** removed: the payee is optional, only its length is checked (`PettyCash.cs:71`, 9276c51) | (was `Say who was paid.`) |
| 15 | credit payee longer than 80 | `The payee must be at most 80 characters.` |
| 16 | credit without a note | `Say why the money was paid.` |
| 17 | cash with a vehicle, item, payee or `reimbursable` | `Cash given has only an amount, a date and a note.` |

`Units` is `input.Units ?? 1` (`Contracts:89`). An unknown kind word, or a missing `kind`, gives message 1 text from
`ParseKind` (`Contracts:27-34,88`). Note, payee and comment are trimmed; blank is null.

### 2.4 Rules (all **(uncommitted)**)

| Id | Rule | Cite |
|---|---|---|
| PC-1 | Amounts are signed and never zero. Negative expense = refund, negative cash = cash taken back, negative credit = payee paid back. | `PettyCash.cs:17-18,43-44` |
| PC-2 | Line validation order and messages are the table in 2.3. The same `Validate` runs twice on create (in `SavePettyCashEntry.Line()` and in the entry constructor) and once on change. | `Contracts:86-92`; `PettyCash.cs:133,152` |
| PC-3 | `Total = round(Units * UnitAmount, 2, MidpointRounding.AwayFromZero)` in decimal arithmetic. `Effect = Total` for cash, `-Total` otherwise. Web/shared re-implement it with BigInt in thousandths (`Shared:307-314`; vectors in `packages/shared/tests/pettyCash.test.ts:31-40`: `11.875 x 182.40 = 2166.00`, `4.5 x 1250.50 = 5627.25`, `0.125 x 0.1 = 0.01`, `1.005 x 1 = 1.01`). | `PettyCash.cs:29,32` |
| PC-4 | Float balance of a holder = sum over non-removed entries of cash `Total` minus credit `Total` minus expense `Total`, any status. Computed by grouping `Total` per kind in the database and summing in memory. | `Repo:66-73` |
| PC-5 | Entry state machine (expense and credit only): create -> `Waiting`; `Waiting` -> `Approved` (approve) or `SentBack` (send back with comment); any change (including an unchanged save of a `SentBack` entry) sets `Waiting` and clears `SentBackNote`, `ReviewedBy`, `ReviewedAt`; an `Approved` entry can still be changed (back to `Waiting`) by an allowed person (PC-13). Approve and send back need `Waiting` and a live entry. Cash has no status and is never approved. Removal is allowed from any status. There is no stored "day" state. | `PettyCash.cs:136,146-186,207-214` |
| PC-6 | Nothing is deleted. `Remove` sets `RemovedBy/At/Reason` and bumps `Version`; removed entries leave every list, total, balance, holder list and dashboard. `Live()` throws `InvalidOperationException("This entry was removed.")` on any later operation; that type is not mapped by `WithSetupErrors` (would be a 500) but the visible-entries query excludes removed rows, so it is unreachable through HTTP (a second remove is a 404). | `PettyCash.cs:180-186,202-205`; `Repo:23` |
| PC-7 | `Matches(line)`: kind, date, vehicle, item, units, unit amount, reimbursable, payee and note equal (ordinal compare of the cleaned strings). Used for replays (PC-16). | `PettyCash.cs:140-143` |
| PC-8 | Holder of a new entry (`HolderFor`). Expense: the actor's own float; needs `pettycash.spend` (403 `Recording spending needs the permission "Record spending from my float".`); a different `holderId` is 400 `Spending is recorded on your own float.` Credit with no `holderId` or the actor's own: own float, needs spend (403 `Recording a credit note on your own float needs the permission "Record spending from my float".`). Credit for another person: needs `pettycash.issue` (403 `Recording a credit note on someone else's float needs the permission "Record money sent to a float".`) and the target must be an active holder. Cash: needs issue (403 `Giving cash to a float needs the permission "Record money sent to a float".`), `holderId` required (400 `Choose who the cash goes to.`), target an active holder (400 `Choose someone who keeps a petty cash float.`). | `UseCases:264-292` |
| PC-9 | An active holder is a member whose resolved permissions (role defaults from `PermissionCatalog.DefaultsFor` per role name, plus overrides, member active) contain `pettycash.spend`. The holders list also keeps anyone with a non-removed entry (shown `active=false`). Sorted by name (ordinal, ignore case) then id. Name = `"{first} {last}"` trimmed. Inactive members resolve to no permissions. | `Repo:27-48` |
| PC-10 | Date window: not after the organization's business date `actor.Today` (400 `Petty cash cannot be recorded for a future date.`), not before `Today - 3650 days` (400 `Choose a date in the last ten years.`). Applies to create, to change only when the date changed, and to the `date` of overview, options and approve-day (`Day()`); not to `from`/`to` of the list. | `UseCases:294-307,139-140` |
| PC-11 | Expense checks run on create and, on change, only for what changed (an old entry stays correctable after its vehicle left or its item was switched off). Vehicle must be in the actor's data scope (400 `Choose one of your vehicles.`) and active on the date (`FleetVehicle.ActiveOn`; 400 `The vehicle was not in the fleet on that day.`); item active on the date (`ActiveExpenseItem`; 400 `Choose an item that is in use.`). Vehicle first. Credit and cash skip this. | `UseCases:311-325` |
| PC-12 | Float guard: `after = Balance(holder) + delta`. Only for kind cash with `delta < 0` and `after < 0` and no `pettycash.issue_negative`: `PettyCashBelowZeroException(after)` (400, extension `balanceAfter`). Create: `delta = Effect`; change: `line.Effect - entry.Effect`; remove: `-entry.Effect` (so removing positive cash can be refused). Expenses and credit notes can always take a float below zero. | `UseCases:327-335,116,142,192` |
| PC-13 | Who may change or remove (`CanChange`; also the flags `canEdit` = `canRemove`). Cash: only `pettycash.issue`. Expense or credit: `own OR (approve_item AND holder != actor)`, where `own = status != Approved AND ((holder == actor AND spend) OR (kind == credit AND recordedBy == actor AND issue))`. So a holder cannot change an approved entry; a reviewer cannot change entries on their own float; a reviewer can change another holder's entry in any status. **(2026-10-12)** except an approved entry the reviewer recorded: `own OR (approve_item AND holder != actor AND NOT (status == Approved AND recordedBy == actor))` (`PettyCashUseCases.cs:302-311`; `PettyCashTests.cs:310-318` pins the refusal on a credit note an issuer recorded and someone else approved). Refusals (`AuthorizeChange`, all 403): cash -> `Changing cash given to a float needs the permission "Record money sent to a float".`; approved and (holder or recorder is the actor) -> `An approved entry can only be changed by someone else who approves petty cash.`; holder is actor -> `Changing your own entries needs the permission "Record spending from my float".`; otherwise `Changing someone else's entry needs the permission "Approve single entries".` | `UseCases:226-250` |
| PC-14 | Who may review (`CanReview`, flag `canReview`): reviewed kind, status `Waiting`, `approve_item`, holder != actor, recordedBy != actor, `abs(Total) <= approvalLimit` (null limit = no limit). `AuthorizeReview` raises: cash 400 `Cash given is not approved.`; holder is actor 403 `You cannot approve or send back entries on your own float.`; recorder is actor 403 `You cannot approve or send back an entry you recorded.`; over limit 403 `This entry is above your approval limit.` It does not test the status; the domain does, after the version check (400 `Only an entry waiting for approval can be approved or sent back.`). | `UseCases:236-262` |
| PC-15 | Idempotent create: `id` in the body (non-empty) is the entry id, else a new Guid. If any entry (removed or not, same organization) has that id: recorded by someone else -> 409 conflict with detail `This entry was already saved by someone else. Reload and try again.` and no `current`; recorded by the actor -> 200 with the existing `id`, `version`, status and the holder's current balance, without comparing the body. The check runs after line validation and before the holder, date, vehicle and float checks. | `UseCases:104-111` |
| PC-16 | Replays. Change with `entry.Matches(line)` and status not `SentBack` -> 200 with the current version and balance (before any permission or version check; an unchanged save of a `SentBack` entry is a resubmit, not a replay). Approve when already `Approved` by the same actor -> 200 (before authorization and version). Send back when already `SentBack` by the same actor with the same trimmed comment -> 200. Remove has no replay (a second remove is 404). | `UseCases:133-134,154-155,171-172` |
| PC-17 | Visibility `Visible(actor)`: non-removed entries where holder == actor, or (actor has `pettycash.view_all` AND (entry has no vehicle OR its vehicle is in the actor's scope: all companies, the vehicle's company listed, or the vehicle id listed)). An out-of-scope or removed entry is a 404 for read/change/review. Own-float entries show whatever the vehicle. Cash and credit notes carry no vehicle, so every viewer with view_all sees them. | `Repo:14-25` |
| PC-18 | Holders a person sees (`VisibleHolders`): all holders with `view_all`, else only their own. A `holderId` (overview, entries, approve-day) not among them -> 404 (`KeyNotFoundException`). | `UseCases:340-351` |
| PC-19 | Tallies: one grouped query over non-removed entries of the chosen holders, grouped by holder, kind, status and period (`Before` the window = 0, `Within` = 1, `After` = 2), returning sum of `Total`, count, latest date. Figures: opening = cash - credit - expense `Before`; `cashReceived`, `expenses`, `creditNotes` `Within`; `moneyOut = expenses + creditNotes`; `closing = opening + cash - expenses - credit`. Figures sum all chosen floats. **(2026-10-12)** The tallies count only entries the viewer may see (`Visible(actor)`, PC-17), so figures and float rows never count what the list hides (`PettyCashRepository.cs:53-56`; `PettyCashTests.cs:450-452`: a scoped viewer's row for the owner's float shows expenses 0 and balance 0); the figures gain `waiting` and `waitingCount`, the expenses and credit notes `Within` still waiting (`PettyCashUseCases.cs:436-445`). | `UseCases:359-366`; `Repo:53-64`; `Contracts:116-121` |
| PC-20 | Float row (to date, all periods): `cashReceived` (net cash), `creditNotes`, `expenses`, `waiting`/`approved`/`sentBack` = sums of expense and credit totals by status, `waitingCount`, `balance = cash - credit - expenses`, `lastCashOn` = latest date of any cash tally (negative cash included). **(2026-10-12)** Over visible entries only (PC-19), while `PettyCashSaved.balance` and the float guard keep the whole balance (`PettyCashRepository.cs:67-75`). | `UseCases:368-378` |
| PC-21 | Week: `period=week` starts on the organization's first day of week (`setup.FirstDayOfWeek`, 0 = Sunday) on or before `date`: `from = date - ((dow - first + 7) % 7)`, `to = from + 6`. `period` other than empty/`day`/`week` -> 400 `Choose a day or a week.`; `date` is validated (PC-10) before `period`. **(2026-10-12)** `from` and `to` ask for any period instead (`PettyCashUseCases.cs:22-68`): both or neither (400 `Choose the first and last day.`), then `from > to` (400 `The first date cannot be after the last date.`), at most 367 days (400 `Choose at most 367 days.`), `from` not after the business date (400 `Choose a period that starts on or before today.`), `from` not before `today - 3650` (400 `Choose a date in the last ten years.`); `to` may be after today. With them `date` and `period` are ignored; the answer's `period` is `day` when `from == to`, else `range`, and `date = to`. | `UseCases:21-39,337-338` |
| PC-22 | Dashboard (P04). `float` card (needs `dash.float`): the actor's own figures, balance to date, waiting count and total, `sentBackCount` = count of sent-back entries to date, `approvedThisMonth` = sum of approved totals dated from the first of the business month to today. `approvals` card (needs `dash.pettycash`): waiting entries of every visible holder (own included): count, total, the viewer's limit, `aboveLimit` = waiting entries with `abs(Total) > limit`, and per holder `{holderId, name, count, total, oldest}` ordered by oldest then name (ordinal). A card is `null` when its permission is missing; with neither permission the request is 403. | `UseCases:68-98` |
| PC-23 | Approve day: needs `pettycash.approve_day`; loads waiting (tracked) entries of the chosen visible holders for the date, keeps those the actor `CanReview`, approves each (one change-log row and one audit event per entry), answers `{approved, total (signed sum), skipped = waiting - approved}`. No version check; skipped entries raise no error; 404 when `holderId` is not visible. **(2026-10-12)** An optional `to` approves every day from `date` through `to`, checked by the period rules of PC-21 (`PettyCashUseCases.cs:242-260`). | `UseCases:202-218` |
| PC-24 | Concurrency. `Version` is an EF concurrency token (`Model:24`). Change, approve, send back and remove compare `input.Version != entry.Version` (a missing `version` therefore conflicts) and answer 409 with the entry as it now is. Every write also bumps the organization's `SettingsVersion` through the change log; when that collides, the whole use case runs again from fresh reads (the UnitOfWork retries Organization collisions only), so the float guard sees the latest balance. A lost race on the entry row surfaces as `DbUpdateConcurrencyException` (409, PC wording, Section 4.2). | `UseCases:137,158,175,190`; `PettyCashTests.cs:481-496` |
| PC-25 | Change log: every write calls `SettingsChangeLog.Record(org, actor, correlationId, section "pettycash", entityId = entry id, before, after, reason, vehicleId = entry.VehicleId)`. `before` is the JSON of the snapshot before (the text `null` on create), `after` the snapshot after, both `System.Text.Json` defaults: PascalCase names `Id, HolderId, Kind (enum NAME: "Cash"/"Expense"/"Credit"), Date, VehicleId, ExpenseItemId, Units, UnitAmount, Total, Payee, Note, Reimbursable, Status (enum NAME or null), SentBackNote, ReviewedBy, ReviewedAt, RecordedBy, RecordedAt, UpdatedBy, UpdatedAt, RemovedBy, RemovedAt, RemovalReason, Version`. Each Record bumps `Organization.SettingsVersion` (+1) and inserts one `OrganizationSettingsVersion` row (version = the new SettingsVersion). | `Repo:153-157`; `UseCases:422-448`; `SettingsChangeLog.cs:11-19` |
| PC-26 | Change-log reasons (`SetupPagination.Automatic`; `Describe`): recorded `Recorded {d}`, changed `Changed {d}`, approved `Approved {d}`, sent back `Sent back {d}. Reason: {comment}.`, removed `Removed {d}. Reason: {reason}.` where `{d}` is: expense `{holder}'s petty cash spending on {registration or "a vehicle"} for {d MMM yyyy, invariant culture}`; credit `{holder}'s petty cash credit note paying {payee}` (**(2026-10-12)** without a payee: `{holder}'s petty cash credit note, {note}`, `PettyCashUseCases.cs:496-498`); cash `petty cash given to {holder}` (total >= 0) or `petty cash taken back from {holder}` (total < 0); an unknown holder reads `someone`. The typed part gets a trailing `.` unless it ends in `.`, `!` or `?`; the whole text is clipped to 500 characters (`...` at 497; with a typed reason the automatic part is shortened first, never below 100 characters). Tested strings: `Removed Wanjiru Kamau's petty cash spending on KAA 501A for {today d MMM yyyy}. Reason: Recorded twice.` (today is the test's pinned Thursday) and `Recorded petty cash given to Wanjiru Kamau`. For change, `{d}` is read after the change; for remove, before. | `UseCases:119,146,162,180,197,215,408-420`; `SetupContracts.cs:106-124`; `PettyCashTests.cs:336-339` |
| PC-27 | Audit event on every write: one `AuditEvent` with action `pettycash.recorded` (also for change, approve, send back and remove), entity = entry id as text, before/after = the same snapshot objects serialized (null before on create). | `Repo:157` |
| PC-28 | Text search `q` (trimmed, at most 200 characters, else 400 `Search for 200 characters or fewer.`): a SQL `LIKE '%text%'` (with `[`, `%`, `_` escaped in the SQL Server bracket style) over the entry note, payee, the holder's `"first last"`, the vehicle registration and the expense item name; case-insensitive "under the collations XCODE runs on". Not searched: reviewer, recorder, status words. | `Repo:84-98`; `UseCases:46,49-50` |
| PC-29 | List order is `Date`, then `Kind` (int: cash, expense, credit), then `Id`, ascending; paging `(page-1)*pageSize`, `pageSize 1-100` (default 100), `page 1-100000`; `total` is the count before paging; names for the page are read in three extra queries (members, vehicles, items+categories). | `Repo:100-109,161-184`; `SetupContracts.cs:102-105` |
| PC-30 | Options (P03): vehicles only for a person with spend or approve_item (`setup.VehicleOptions`, their scope); items = active items on the date (`setup.ExpenseItemOptions`); holders only for a person with `pettycash.issue`, active holders only. | `UseCases:59-66` |
| PC-31 | Vehicle cost posting: the vehicle report (S-series, committed endpoint) adds one posting per non-removed, `Approved`, expense entry of the vehicle dated inside the report window: `PostingDto(ItemId = VersionId = entry id, Date, Name = item name, Kind = Cost, Amount = Total, Bucket = the item's category bucket, Source = "pettycash")`. Credit notes and cash never post. `moneyOut` and the buckets include them. **(2026-10-12)** Read through `FleetPostings.Load` (`Infrastructure/Setup/FleetPostings.cs:60-74`, `Application/Setup/FleetPostings.cs:35-58`), which every report shares: a posting counts only inside the vehicle's own days (from its join date, up to the day before it left, never after the business date); the report orders postings by date, name (ordinal), item id, version id (`SetupRepository.cs:340-345`). | `apps/api/Infrastructure/Setup/SetupRepository.cs:254-271`; `SetupContracts.cs:69-72`; `PettyCashTests.cs:187-208` |
| PC-32 | Change-log visibility: the history query lets `section = pettycash` rows through for a scoped viewer only when `VehicleId` is set and in scope (cash and credit rows, which have no vehicle, are visible only to an all-companies viewer). History section label on the web is `Petty cash` (`HistoryPage.tsx:30`). **(2026-10-12)** Now at `SetupRepository.cs:383`, beside `centralexpenses` rows under the same rule. | `SetupRepository.cs:307-312` |
| PC-33 | **(2026-10-12)** Ticked approval `POST /setup/pettycash/approve {entries: [{id, version}]}` (gate `pettycash.approve_item` only): duplicates by id dropped (the first kept); none -> 400 `Choose the entries to approve.`; more than 100 -> 400 `Approve at most 100 entries at a time.`; then for each in the order sent: not visible or removed -> 404; already `Approved` -> skipped; `AuthorizeReview` (PC-14, 400/403); `version` differs -> 409 with `current`. Only then is any approved, so one refusal approves none (an entry that is `SentBack` passes these checks and its approval then fails with the 400 of PC-5, still approving none). One change-log row and one audit row per approved entry; answer `PettyCashDayApproved {approved, total, skipped = asked - approved}` | `PettyCashUseCases.cs:262-293`; `PettyCashTests.cs:510-550` |

### 2.5 Permission matrix (committed keys; dependency graph `Access.cs:58-79`)

| Endpoint | Gate (any one of) | Extra checks |
|---|---|---|
| P01 overview, P02 entries | `pettycash.spend`, `pettycash.view_all` | scope: PC-17, PC-18 |
| P03 options | `pettycash.spend`, `pettycash.issue`, `pettycash.approve_item` | parts by permission, PC-30 |
| P04 dashboard | `dash.float`, `dash.pettycash` | card by permission, PC-22 |
| P05 create | `pettycash.spend`, `pettycash.issue` | PC-8 |
| P06 change, P09 remove | `pettycash.spend`, `pettycash.issue`, `pettycash.approve_item` | PC-13 |
| P07 approve, P08 send back | `pettycash.approve_item` | PC-14 |
| P10 approve day | `pettycash.approve_day` | PC-23 |
| P11 approve ticked **(2026-10-12)** | `pettycash.approve_item` | PC-33 |
| P14 export **(2026-10-12)** | `reports.export` | prompt 08b (drift register row 4) |

Dependencies (a granted key brings these): `dash.float` -> `pettycash.spend`; `dash.pettycash` -> `pettycash.view_all`; `approve_item` -> `view_all`; `approve_day` -> `approve_item`; `issue` -> `view_all`; `issue_negative` -> `issue`. Role defaults: Owner has every key except `dash.capture` (so all petty cash keys); Office admin has none; Fleet manager has `dash.float` and `pettycash.spend`; Revenue clerk has none (`AccessContracts.cs:104-125`). Labels: spend `Record spending from my float`, view_all `View every float`, approve_item `Approve single entries`, approve_day `Approve a whole day`, issue `Record money sent to a float`, issue_negative `Send money that takes a float below zero`, dash.float `See my petty cash float`, dash.pettycash `See petty cash waiting for approval` (`AccessContracts.cs:33,38,57-65`). The 403 helper is `PermissionCatalog.Refusal(action, key)` = `{action} needs the permission "{label}".` (`AccessContracts.cs:101-102`). Approval limit: `Memberships.ApprovalLimit decimal(14,2)?`, null = none, set only through people/access (`AccessUseCases.cs:163,351,533`).

---

## 3. Persistence

One new table, `PettyCashEntries`, plus one column on an existing table that the feature depends on. Source:
`Model:9-37`, migrations `20261007115030_PettyCash.cs`, `20261007124851_PettyCashDecimalUnits.cs`, snapshot
`AuthDbModelSnapshot.cs:368-463` and `:1394-1432`. The SQL types below are SQL Server; the test database is SQLite
(`EnsureCreated` from the model). All **(uncommitted)**.

### 3.1 Table `PettyCashEntries` (entity `PettyCashEntry`)

| Column | SQL Server type | Null | Default | Notes |
|---|---|---|---|---|
| `OrganizationId` | uniqueidentifier | no | none | PK part 1; tenant |
| `Id` | uniqueidentifier | no | none (set by the app; client may choose) | PK part 2 |
| `HolderId` | uniqueidentifier | no | none | FK part |
| `Kind` | int | no | none | 1 cash, 2 expense, 3 credit |
| `Date` | date | no | none | |
| `VehicleId` | uniqueidentifier | yes | | FK part |
| `ExpenseItemId` | uniqueidentifier | yes | | FK part |
| `Units` | decimal(12,3) | no | none | was `int` in `20261007115030_PettyCash`, altered by the second migration |
| `UnitAmount` | decimal(14,2) | no | none | |
| `Total` | decimal(14,2) | no | none | |
| `Payee` | nvarchar(80) | yes | | |
| `Note` | nvarchar(80) | yes | | |
| `Reimbursable` | bit | no | none (app sets false) | |
| `Status` | int | yes | | 1 waiting, 2 approved, 3 sent back; null for cash |
| `SentBackNote` | nvarchar(200) | yes | | |
| `ReviewedBy` | uniqueidentifier | yes | | no FK |
| `ReviewedAt` | datetimeoffset | yes | | |
| `RecordedBy` | uniqueidentifier | no | none | no FK |
| `RecordedAt` | datetimeoffset | no | none | |
| `UpdatedBy` | uniqueidentifier | no | none | no FK |
| `UpdatedAt` | datetimeoffset | no | none | |
| `RemovedBy` | uniqueidentifier | yes | | no FK |
| `RemovedAt` | datetimeoffset | yes | | |
| `RemovalReason` | nvarchar(500) | yes | | |
| `Version` | bigint | no | none (app starts at 1) | concurrency token (`Model:24`) |

Python/PostgreSQL mapping hints: `uuid`, `smallint` or `integer` for `Kind`/`Status`, `date`, `numeric(12,3)`, `numeric(14,2)`,
`varchar(n)`, `boolean`, `timestamptz`, `bigint`. `datetimeoffset` values are always UTC by construction (PC domain check).

### 3.2 Keys, indexes, foreign keys, filters

| Item | Definition | Cite |
|---|---|---|
| Primary key | `PK_PettyCashEntries (OrganizationId, Id)` | `Model:12`; migration `:46` |
| Index | `IX_PettyCashEntries_OrganizationId_HolderId_Date` | `Model:25`; migration `:78-81` |
| Index | `IX_PettyCashEntries_OrganizationId_Status_Date` | `Model:26`; migration `:83-86` |
| Index | `IX_PettyCashEntries_OrganizationId_VehicleId_Date` | `Model:27`; migration `:88-91` |
| Index | `IX_PettyCashEntries_OrganizationId_ExpenseItemId` (created by EF for the item FK, not declared in `Model`) | migration `:73-76`; snapshot |
| Unique constraints | none besides the primary key | |
| FK | `FK_PettyCashEntries_Memberships_OrganizationId_HolderId` -> `Memberships (OrganizationId, UserId)`, Restrict | `Model:28-30`; migration `:59-64` |
| FK | `FK_PettyCashEntries_FleetVehicle_OrganizationId_VehicleId` -> `FleetVehicle (OrganizationId, Id)`, Restrict (nullable column; not checked when `VehicleId` is null) | `Model:31-33`; migration `:53-58` |
| FK | `FK_PettyCashEntries_ExpenseItem_OrganizationId_ExpenseItemId` -> `ExpenseItem (OrganizationId, Id)`, Restrict (nullable) | `Model:34-36`; migration `:47-52` |
| FK | `FK_PettyCashEntries_Organizations_OrganizationId` -> `Organizations (Id)`, Restrict (from `Tenant()`) | `OrganizationModel.cs:12-16`; migration `:65-70` |
| Global query filter | `OrganizationId == CurrentOrganizationId` (from `Tenant()`); `AnyEntry` and the repository queries therefore see only the current organization | `OrganizationModel.cs:15` |
| Write guard | `ValidateWrites` (every `IOrganizationEntity`): an Added/Modified/Deleted row whose `OrganizationId` is not the current organization (or whose original id differed) throws `UnauthorizedAccessException("Cross-organization write rejected.")`; any `DateTimeOffset` with a non-zero offset throws `Instants must be UTC.`; the entity setter throws `Tenant cannot change.` | `OrganizationModel.cs:87-112`; `PettyCash.cs:90-94` |
| Concurrency | `Version` only. `SettingsVersion` on `Organizations` is the second token every write touches (PC-24) | `Model:24` |
| Ignored properties | `Removed`, `Reviewed`, `Effect` | `Model:14-16` |

### 3.3 Raw SQL, seeds, other tables touched

- Raw SQL in the two migrations: none (`CreateTable`, `CreateIndex`, `AlterColumn` only; `Down` drops the table or alters
  `Units` back to `int`). Raw SQL in the feature's code: none (all LINQ). `PettyCashTests.cs:15,489` contain SQL strings that
  the test harness injects (Section 5).
- Seed data: none. Role and permission defaults are code (`PermissionCatalog`), not rows.
- The migration `20261007115030_PettyCash` was generated after `20261007052529_ChangeLogVehicle` (also **(uncommitted)**), which
  adds `OrganizationSettingsVersion.VehicleId` (nullable Guid; two indexes `(OrganizationId, Section, VehicleId)` and
  `(OrganizationId, OccurredAt)`; a SQL back-fill by `UPDATE` in that migration, lines 15-20, not part of this feature).
  The petty-cash change log writes `VehicleId = entry.VehicleId` into it (PC-25, PC-32). A Python schema that reproduces
  petty cash must carry that column.
- `20261007181520_RenameUseGrouping` renames a column unrelated to petty cash; nothing to carry.
- Existing tables read: `Memberships` (name, active, `ApprovalLimit`), `PersonRoles`, `Roles`, `PermissionOverrides` (holders),
  `FleetVehicle` and its away periods (scope, `ActiveOn`), `ExpenseItem`/`ExpenseCategory` (name, bucket),
  `SetupDataScope`/company/vehicle scope tables (via the actor), `Localizations` (time zone), `Organizations`
  (`BusinessDate`, `SettingsVersion`). Tables written: `PettyCashEntries`, `OrganizationSettingsVersion`, `AuditEvents`,
  `Organizations.SettingsVersion`.

### 3.4 What the schema does not enforce (the application does)

- `Kind` and `Status` value ranges; `Status` null exactly for cash; the status transitions.
- `Total = round(Units * UnitAmount, 2)`; `UnitAmount != 0`; `Total != 0`; `Units > 0`; units equal to 1 for cash and credit.
- Which columns are required per kind (vehicle and item for expense, payee and note for credit, none for cash).
- That the holder is an active holder; that `RecordedBy`, `UpdatedBy`, `ReviewedBy`, `RemovedBy` are members (no FK).
- That the date is not in the future or older than 10 years; that the vehicle was in the fleet on the date; that the item
  was active on the date.
- That removal columns move together (`RemovedAt`, `RemovedBy`, `RemovalReason`), that `SentBackNote` is set only when
  `Status = 3`, and that `ReviewedBy/At` are set only after a review.
- That `Version` only increases. Nothing stops a hard delete except the Restrict FKs pointing at the entry's parents.
- Money columns hold two decimals (three for units) and have no CHECK; maximum values fit exactly the precision
  (`999999999999.99` in `decimal(14,2)`, `999999999.999` in `decimal(12,3)`).
- Search relies on the database collation being case-insensitive; PostgreSQL needs `ILIKE`, `citext` or a nondeterministic
  collation, and a real `ESCAPE` clause instead of the SQL Server bracket escapes (`Repo:88`).

---

## 4. HTTP contract (all **(uncommitted)**)

### 4.1 Group and envelope

One route group: `/setup/pettycash`, `RequireAuthorization()`, OpenAPI tag `Petty cash`, plus the shared `WithSetupErrors()`
filter, then a petty-cash filter added after it (`Endpoints:18`, filter `:19-36`). Registered by `AddPettyCash()`
(`Program.cs:71`) and `MapPettyCash()` (`Program.cs:173`). Unauthenticated: 401 with an empty body (JWT middleware). Success
bodies are camelCase JSON; `DateOnly` is `yyyy-MM-dd`; instants are ISO 8601 UTC (`DateTimeOffset`, framework default
format with `+00:00`; unverified); decimals are JSON numbers; Guids are lower-case; enums that have a word table travel as
words (2.1), `bucket` as an integer. All `/setup/**` errors are RFC 7807 `application/problem+json`
(`inventory-http-contract.md` section 1, mapping table (B)).

Error mapping inside this group, innermost first (`Endpoints:19-36`, then `SetupEndpoints.cs:26-42`):

| Exception | Status | `title` | `detail` | Extension members |
|---|---|---|---|---|
| `PettyCashConflictException` | 409 | `This entry has changed.` | the exception message: `This entry was changed after you opened it. Check it and save again.` (default) or `This entry was already saved by someone else. Reload and try again.` (PC-15) | `current`: the `PettyCashEntryDto` as it now is, or `null` when the entry is gone or the id belongs to someone else |
| `DbUpdateConcurrencyException` | 409 | `This entry was changed by another save.` | `Reload and try again.` | none |
| `PettyCashBelowZeroException` (an `ArgumentException`) | 400 | `Invalid setup change` | `This takes the float below zero, which needs the permission "Send money that takes a float below zero".` | `balanceAfter`: decimal, the balance the change would leave |
| `UnauthorizedAccessException` | 403 | `Not permitted in this organization or data scope.` | the message when custom (the refusal strings in PC-8, PC-13, PC-14); omitted for the plain gate | none |
| `KeyNotFoundException` | 404 | `Record not found in your scope.` | omitted | none |
| `ArgumentException` | 400 | `Invalid setup change` | the message (every validation text in 2.3, PC-8 to PC-14, PC-21, 4.3) | none |
| `DbUpdateException` | 409 | `A conflicting record exists. Reload before saving.` | omitted | none |

Not mapped (so a 500 from the global handler): `InvalidOperationException` (`This entry was removed.`, unreachable) and
anything else. The plain gate (`not an active member`, or none of the listed permissions) is `UnauthorizedAccessException`
with no message: 403 with no `detail`. A route `{id:guid}` that is not a Guid never matches: 404 from the framework, empty
body (framework default, unverified). A malformed JSON body or a wrongly typed field (for example `unitAmount: "abc"`,
`date: "tomorrow"`) is a framework 400 before the use case runs (shape unverified, no test).

### 4.2 Endpoint table

Gate = any one permission listed (`ReadAny`/`WriteAny`) unless "only". Line = `Endpoints` line of the route.

| Id | Method and path | operationId | Gate | Body or query (wire names, order) | Success | Line |
|---|---|---|---|---|---|---|
| P01 | `GET /setup/pettycash/overview` | `GetPettyCashOverview` | `pettycash.spend`, `pettycash.view_all` | query `date` (DateOnly?), `period` (string?), `holderId` (Guid?), **(2026-10-12)** `from`, `to` (DateOnly?) | 200 `PettyCashOverviewDto` | 38-42 (now `PettyCashEndpoints.cs:39-43`) |
| P02 | `GET /setup/pettycash/entries` | `ListPettyCashEntries` | same as P01 | query `from`, `to` (DateOnly?), `holderId` (Guid?), `kind`, `status`, `q` (string?), `page` (int, 1), `pageSize` (int, 100) | 200 `Page<PettyCashEntryDto>` | 44-48 |
| P03 | `GET /setup/pettycash/options` | `GetPettyCashOptions` | `spend`, `issue`, `approve_item` | query `date` (DateOnly?) | 200 `PettyCashOptionsDto` | 50-52 |
| P04 | `GET /setup/pettycash/dashboard` | `GetPettyCashDashboard` | `dash.float`, `dash.pettycash` | none | 200 `PettyCashDashboardDto` | 54-56 |
| P05 | `POST /setup/pettycash/entries` | `CreatePettyCashEntry` | `spend`, `issue` | body `SavePettyCashEntry` | 200 `PettyCashSaved` (always 200, never 201) | 58-61 |
| P06 | `PUT /setup/pettycash/entries/{id}` | `UpdatePettyCashEntry` | `spend`, `issue`, `approve_item` | body `SavePettyCashEntry` (with `version`) | 200 `PettyCashSaved` | 63-66 |
| P07 | `POST /setup/pettycash/entries/{id}/approve` | `ApprovePettyCashEntry` | only `approve_item` | body `{version}` | 200 `PettyCashSaved` | 68-71 |
| P08 | `POST /setup/pettycash/entries/{id}/send-back` | `SendBackPettyCashEntry` | only `approve_item` | body `{version, comment}` | 200 `PettyCashSaved` | 73-76 |
| P09 | `POST /setup/pettycash/entries/{id}/remove` | `RemovePettyCashEntry` | `spend`, `issue`, `approve_item` | body `{version, reason}` | 200 `PettyCashSaved` | 78-81 |
| P10 | `POST /setup/pettycash/approve-day` | `ApprovePettyCashDay` | only `approve_day` | body `{date, holderId?, to?}` (**(2026-10-12)** `to`) | 200 `PettyCashDayApproved` | 83-86 |
| P11 **(2026-10-12)** | `POST /setup/pettycash/approve` | `ApprovePettyCashEntries` | only `approve_item` | body `{entries: [{id, version}]}` | 200 `PettyCashDayApproved` | `PettyCashEndpoints.cs:94-97` |
| P14 **(2026-10-12)** | `GET /setup/pettycash/export?from&to&holderId&view&status&q&format` | `ExportPettyCash` | `reports.export` | query | a file | `PettyCashEndpoints.cs:89-92`; prompt 08b |

Every route also declares `.Produces<T>()` only for the success type; the group adds `ProducesProblem` for 400, 403, 404 and 409
(`SetupEndpoints.cs:37-40`). There is no DELETE, no PATCH, no endpoint that lists holders or reads one entry, and no export (**(2026-10-12)** the export P14 exists now, in prompt 08b's scope; P12 and P13 are the reject and reopen routes of the design, `docs/06-http-contract.md` 2.11).
The web proxy allow-list forwards `pettycash` and any deeper path (`apps/web/app/api/setup/[...path]/route.ts:87`, **(uncommitted)**).

### 4.3 Per-endpoint behaviour and check order

Order applies top to bottom; the first failing step answers. "Gate" is step 0 for every endpoint: not an active member, or none of
the listed permissions -> 403 with no `detail` (`OrganizationPort.cs:45-50`). Reads run in a read transaction, writes in the
retrying unit of work (PC-24).

**P01 overview** (`UseCases:21-39`; **(2026-10-12)** with `from` or `to`, steps 1 and 2 are replaced by the period checks of PC-21, in the order given there)
1. `date` (default `actor.Today`) outside the window -> 400 `Petty cash cannot be recorded for a future date.` or `Choose a date in the last ten years.`
2. `period` not empty/`day`/`week` (trimmed) -> 400 `Choose a day or a week.`
3. `holderId` not among the viewer's holders -> 404.
4. Answer: `businessDate = actor.Today`, `date`, `period`, `from`, `to`, `permissions`, `holders` (all the viewer may see), `figures`, `floats` (selected holders only). No paging.

**P02 entries** (`UseCases:41-57`)
1. `page` outside 1-100000 or `pageSize` outside 1-100 -> 400 `Page must be 1–100000 and page size 1–100.` (en dash).
2. `from > to` -> 400 `The first date cannot be after the last date.`
3. `q` trimmed longer than 200 -> 400 `Search for 200 characters or fewer.`
4. `kind`: comma list, trimmed, empty items dropped, duplicates removed, each `cash|expense|credit`, else 400 `Choose an expense, a credit note or cash.`; empty or absent = every kind. `status`: `waiting|approved|sentBack`, else 400 `Status must be waiting, approved or sentBack.`; absent = any (cash has a null status and never matches a status filter).
5. `holderId` not visible -> 404.
6. Rows: visible, non-removed, in the selected holders, `from <= date <= to` inclusive; order and paging PC-29. Answer `Page`: `items`, `pageNumber`, `pageSize`, `total`. Each item carries the per-person flags (`canEdit`, `canRemove`, `canReview`, `aboveLimit`; PC-13, PC-14).

**P03 options** (`UseCases:59-66`): date window check as P01 step 1; answer `vehicles`, `items`, `holders` (PC-30). No further errors.

**P04 dashboard** (`UseCases:68-98`): no input; no errors beyond the gate. Answer `float` and `approvals`, each possibly `null` (PC-22).

**P05 create** (`UseCases:100-121`)
1. Line validation (2.3; an unknown or missing kind first).
2. Idempotency lookup (PC-15): 409 `This entry has changed.` with detail `This entry was already saved by someone else. Reload and try again.`, or a 200 replay.
3. Holder rules (PC-8): 403 refusals and 400s. 4. Date window (PC-10). 5. Expense vehicle and item (PC-11).
6. Float guard (PC-12): 400 with `balanceAfter`.
7. Insert the entry (Version 1; `Waiting` for expense and credit, null status for cash), change-log row `Recorded ...`, audit event. Answer `PettyCashSaved {id, version, status, balance}`, `balance` = the holder's balance after the entry.

**P06 change** (`UseCases:123-148`)
1. Line validation. 2. Entry not visible or removed -> 404. 3. Kind differs -> 400 `An entry cannot change between expense, credit note and cash. Remove it and record it again.`
4. `holderId` present and different -> 400 `An entry cannot move to another float. Remove it and record it again.`
5. Replay (PC-16) -> 200. 6. `AuthorizeChange` (PC-13) -> 403. 7. `version` differs (or is missing) -> 409 with `current`.
8. Date window, only if the date changed. 9. Expense checks, only for what changed. 10. Float guard with the delta.
11. Apply; status back to `Waiting` (expense, credit); review fields cleared; `Version + 1`; log `Changed ...`. Answer `PettyCashSaved`, balance after.

**P07 approve** (`UseCases:150-164`): entry 404; replay if already approved by the same actor (200); `AuthorizeReview` (PC-14) 400/403; version 409; then the domain: status not `Waiting` -> 400 `Only an entry waiting for approval can be approved or sent back.`; status `Approved`, `ReviewedBy/At` set, `SentBackNote` cleared, `Version + 1`, log `Approved ...`. Answer `PettyCashSaved` (balance unchanged).

**P08 send back** (`UseCases:166-182`): entry 404; replay (same actor, same trimmed comment); `AuthorizeReview`; version 409; domain `Waiting` check first (same 400 text), then empty comment -> 400 `Say what should be fixed.`, comment over 200 -> 400 `The comment must be at most 200 characters.`; status `SentBack`, `SentBackNote` = trimmed comment; log `Sent back .... Reason: {comment}.`

**P09 remove** (`UseCases:184-199`): reason empty or over 500 after trim -> 400 `A reason of 1–500 characters is required.` (checked before the entry is loaded, after the gate); entry 404; `AuthorizeChange` 403; version 409; float guard on `-Effect` (400 with `balanceAfter`, cash only); soft delete. Answer `PettyCashSaved` with the entry's last status and the balance after removal.

**P10 approve day** (`UseCases:202-218`): date window (400; a missing `date` reads as 0001-01-01 and answers `Choose a date in the last ten years.`); `holderId` not visible -> 404; then PC-23. Answer `PettyCashDayApproved {approved, total, skipped}`. **(2026-10-12)** With `to`: the period checks of PC-21 on `date`..`to` instead of the date window.

**P11 approve ticked** **(2026-10-12)** (`PettyCashUseCases.cs:262-293`): PC-33.

### 4.4 DTO catalogue (wire order = record parameter order; camelCase on the wire)

Requests (`Contracts:80-99`)

| DTO | Fields in order (type, default) |
|---|---|
| `SavePettyCashEntry` | `kind` string, `date` date, `unitAmount` decimal, `id` Guid? (null), `holderId` Guid? (null), `vehicleId` Guid? (null), `expenseItemId` Guid? (null), `units` decimal? (null = 1), `payee` string? (null), `note` string? (null), `reimbursable` bool (false), `version` long? (null) |
| `ReviewPettyCashEntry` | `version` long |
| `SendBackPettyCashEntry` | `version` long, `comment` string? |
| `RemovePettyCashEntry` | `version` long, `reason` string? |
| `ApprovePettyCashDay` | `date` date, `holderId` Guid? (null), **(2026-10-12)** `to` date? (null) |
| `ApprovePettyCashEntries` **(2026-10-12)** | `entries` `ReviewedPettyCashEntry[]`? (`{id`, `version}`) |

Responses (`Contracts:51-107`; the TypeScript mirrors are `Shared:49-272`)

| DTO | Fields in order |
|---|---|
| `PettyCashSaved` | `id` Guid, `version` long, `status` string?, `balance` decimal |
| `PettyCashDayApproved` | `approved` int, `total` decimal, `skipped` int |
| `PettyCashOverviewDto` | `businessDate` date, `date` date, `period` string, `from` date, `to` date, `permissions` PettyCashPermissionsDto, `holders` PettyCashHolderDto[], `figures` PettyCashFiguresDto, `floats` PettyCashFloatDto[] |
| `PettyCashPermissionsDto` | `holderId` Guid? (the actor when they hold spend, else null), `canSpend`, `canViewAll`, `canIssue`, `canIssueNegative`, `canApproveItem`, `canApproveDay` (bool), `approvalLimit` decimal? |
| `PettyCashHolderDto` | `id` Guid, `name` string, `active` bool |
| `PettyCashFiguresDto` | `openingBalance`, `cashReceived`, `expenses`, `creditNotes`, `moneyOut`, `closingBalance` (all decimal), **(2026-10-12)** `waiting` decimal, `waitingCount` int (`PettyCashContracts.cs:59-60`) |
| `PettyCashFloatDto` | `holderId` Guid, `name` string, `active` bool, `cashReceived`, `creditNotes`, `expenses`, `waiting` (decimal), `waitingCount` int, `approved`, `sentBack`, `balance` (decimal), `lastCashOn` date? |
| `PettyCashEntryDto` | `id`, `kind` (word), `holderId`, `holderName`, `date`, `vehicleId?`, `registration?`, `expenseItemId?`, `expenseItemName?`, `bucket?` (int 1-3), `units`, `unitAmount`, `total` (decimal), `payee?`, `note?`, `reimbursable` bool, `status?` (word), `sentBackNote?`, `reviewedByName?`, `reviewedAt?` (instant), `recordedByName`, `recordedAt`, `updatedAt` (instants), `version` long, `canEdit`, `canRemove`, `canReview`, `aboveLimit` (bool) |
| `Page<PettyCashEntryDto>` | `items`, `pageNumber`, `pageSize`, `total` (int) |
| `PettyCashOptionsDto` | `vehicles` VehicleOption[] (`id`, `companyId`, `companyName`, `registration`, `active`), `items` ExpenseItemOption[] (`id`, `name`, `categoryId`, `categoryName`, `bucket` int), `holders` PettyCashHolderDto[] |
| `PettyCashDashboardDto` | `float` PettyCashDashboardFloat?, `approvals` PettyCashDashboardApprovals? |
| `PettyCashDashboardFloat` | `balance` decimal, `waitingCount` int, `waitingTotal` decimal, `sentBackCount` int, `approvedThisMonth` decimal |
| `PettyCashDashboardApprovals` | `count` int, `total` decimal, `approvalLimit` decimal?, `aboveLimit` int, `holders` PettyCashDashboardHolder[] |
| `PettyCashDashboardHolder` | `holderId` Guid, `name` string, `count` int, `total` decimal, `oldest` date |

`holderName`, `recordedByName` read `""` and `reviewedByName` null when the member row is missing (`Repo:178-182`). `expenseItemName`
and `bucket` are null for non-expense rows. `aboveLimit` = reviewed kind, `Waiting`, over the viewer's limit, whoever recorded it.
Enum wire values: kind and status are strings (2.1), `bucket` and `ExpenseBucket` are integers 1-3, `period` is `"day"` or `"week"` (**(2026-10-12)** or `"range"`, PC-21).

---

## 5. Tests

Format as `inventory-tests.md` section 2 (that file is still only its 51-line header when read): **Ln** is the method
declaration line (the attribute is the line above); **Ids** are the endpoint ids of Section 4 (`REPORT` = the committed
vehicle report endpoint `GET /setup/vehicles/{id}/report`, `HISTORY` = `GET /setup/history`); **EF/SQLite-bound** says what
the Python port must replace. `PettyCashTests.cs` is untracked **(uncommitted)** and was written 2026-10-07 15:52, earlier than
the last write of `PettyCashUseCases.cs` and `PettyCashRepository.cs` (19:37), so the tests may predate a late change to
those two files; no test could be matched to such a change.

### 5.1 Harness used by `PettyCashTests.cs`

- `Arrange()` (`:22-45`): `app.SeedDemo()`, pinned Thursday as business date, companies `Petty Fleet` (vehicle `KAA 501A`,
  joined today-30) and `Other Fleet` (vehicle `KAB 502B`), Clerk (`wanjiru.kamau@zurigenesis.co.ke`, name `Wanjiru Kamau`,
  scoped to Petty Fleet, granted `pettycash.spend`), Admin (`peter.otieno@zurigenesis.co.ke`, name `Peter Otieno`, Office
  admin, granted `pettycash.approve_item`, approval limit 5000 through `SetLimit`), Owner (`antony.maina@shamayah.co.ke`,
  every permission), expense item `Tyres`. Each person signs in at most once per test (device-code throttle of one minute).
- Helpers `Expense`, `Cash`, `Credit`, `Post`, `Approve`, `Overview`, `Entries`, `Report`, `Saved`, `AssertBadRequest`
  (400 and exact `detail`), `AssertForbidden` (403 and optional exact `detail`) (`:498-558`). Wire bodies are anonymous
  objects with the camelCase names of Section 4.4; responses are read as the C# records.

### 5.2 `PettyCashTests` (18 `[Fact]`; **(2026-10-12)** 21: three added below, two changed, two extended; the Ln column keeps the 2026-10-08 numbers)

| Method | Ln | Ids | Decisive assertions | EF/SQLite-bound |
|---|---|---|---|---|
| `RecordingSpendingWaitsForApprovalAndShowsOnTheFloat` | 48 | P05 P01 P02 | owner cash 10000 -> balance 10000; clerk expense 2 x 1500 note `Two tyres` -> `("waiting", 7000)`; overview `("day", today, today)`, `Figures = (0, 10000, 3000, 0, 3000, 7000)` (**(2026-10-12)** `+ (3000, 1)` for `waiting`, `waitingCount`); float `(clerk, cashReceived 10000, expenses 3000, waiting 3000, waitingCount 1, balance 7000, lastCashOn today)`; permissions `(holderId clerk, canSpend true, canIssue false, canApproveItem false)`; owner overview of the day before with `holderId=clerk`: opening 0, closing 0, float balance 7000; entries `from=to=today` total 2; expense row `("KAA 501A", "Tyres", 2, 1500, 3000, "waiting", "Two tyres")` flags `(canEdit, canRemove, canReview) = (true, true, false)`; cash row `status null, canEdit false, canRemove false` | no |
| `SpendingMayTakeAFloatBelowZeroButTakingCashBackNeedsPermission` | 82 | P05 P06 P01 | expense 3000 on empty float -> `("waiting", -3000)`; credit 500 -> -3500; overview `(opening 0, moneyOut 3500, closing -3500)`; PUT to 4000 -> -4500; expense `-200` -> -4300; owner cash `-500` -> -4800; after `Deny(Owner, pettycash.issue_negative)` cash `-100` -> 400, `detail` `This takes the float below zero, which needs the permission "Send money that takes a float below zero".`, `balanceAfter -4900`; cash `+1000` -> -3800 | no |
| `UnitsCanBePartOfOneAndAboveAThousand` | 111 | P05 P06 P02 | 182.40 x 11.875 -> `(11.875, 2166.00)`; 1250.50 x 4.5 -> 5627.25; 10 x 1001 -> 10010; PUT with the same units and the entry's version -> same `version` (replay); 400s: units 0, -2, 1.2345 -> `Units must be above zero, with at most three decimals.`; 0.01 x 0.001 -> `The total rounds to zero. Check the units and the amount.`; 10000 x 999999999.999 -> `The total is too large.`; cash with `units 2` -> `Only an expense has units.` | no |
| `AWeekShowsItsFiguresFromTheOrganizationsFirstDay` | 142 | P01 | Thursday today, Monday = today-3; cash 10000 on Saturday before, expense 1000 Monday, cash 2000 Wednesday, expense 500 today; `period=week`: `("week", today, monday, monday+6)`, `Figures = (10000, 2000, 1500, 0, 1500, 10500)` (**(2026-10-12)** `+ (1500, 2)`), float balance 10500; `date=monday+1` -> `from = monday`; after `SetFirstDayOfWeek(Saturday)`: `from = monday-2`, `to = monday+4`, `Figures = (0, 12000, 1500, 0, 1500, 10500)` (**(2026-10-12)** `+ (1500, 2)`); `period=month` -> 400 `Choose a day or a week.` | no |
| `SpendingIsOnlyOnYourOwnFloatAndForYourOwnVehicles` | 168 | P05 | outside vehicle -> `Choose one of your vehicles.`; `holderId=owner` on an expense -> `Spending is recorded on your own float.`; tomorrow -> `Petty cash cannot be recorded for a future date.`; today-40 -> `The vehicle was not in the fleet on that day.`; body with no `vehicleId` (it sends `itemId`, an unknown field) -> `Choose the vehicle.`; amount 0 -> `Enter an amount other than zero.`; 10.005 -> `Enter the amount with at most two decimals.`; clerk posts cash -> 403 `Giving cash to a float needs the permission "Record money sent to a float".` | no |
| `ApprovedSpendingReachesTheVehicleAndCreditNotesNever` | 187 | P05 P07 REPORT P02 | report before approval has no posting with `source "pettycash"`; admin approve `{version}` -> status `approved`; report after has exactly one `pettycash` posting `(itemId = entry id, date today, name "Tyres", amount 1200)` and `moneyOut` rises by exactly 1200 (the 800 credit note never posts); clerk's row `("approved", reviewedByName "Peter Otieno", canEdit false, canRemove false)` | no (the report is a committed endpoint) |
| `NobodyReviewsTheirOwnFloatTheirOwnEntryOrAboveTheirLimit` | 211 | P05 P07 P02 | owner approving an expense on the owner's float -> 403 `You cannot approve or send back entries on your own float.`; owner approving a credit note the owner recorded on the clerk's float -> 403 `You cannot approve or send back an entry you recorded.`; clerk's 6000 expense seen by admin: `aboveLimit true, canReview false`, admin approve -> 403 `This entry is above your approval limit.`, owner approve -> `approved`; approving a cash entry -> 400 `Cash given is not approved.` | no |
| `SendingBackNeedsACommentAndSavingAgainSendsItForApproval` | 237 | P08 P06 P02 | comment `" "` -> 400 `Say what should be fixed.`; comment `Attach the receipt` -> status `sentBack`; clerk row `("sentBack", "Attach the receipt", canEdit true)`; PUT with unchanged values and the new version -> status `waiting`; row then `("waiting", sentBackNote null)` | no |
| `AnApprovedEntryIsChangedOnlyBySomeoneElseWhoApproves` | 261 | P07 P06 P09 | clerk PUT and clerk remove of the approved entry -> 403 `An approved entry can only be changed by someone else who approves petty cash.`; admin PUT 1300 with the approved version -> `("waiting", balance 8700)` and `version` greater; **(2026-10-12)** the owner's credit note on the clerk's float, approved by the admin: the owner's row `(canEdit, canRemove) = (false, false)` and the owner's remove -> 403 with the same sentence | no |
| `AStaleVersionConflictsWithTheCurrentEntry` | 283 | P06 P09 | second PUT with the old version -> 409, body `current.unitAmount 1250`, `current.version = old + 1`; remove with the old version -> 409 | no |
| `ARetriedCreateAnswersWithTheEntryItMade` | 301 | P05 P02 | same client `id` twice -> same `id` and `version`, `balance 8800`, one expense listed; owner posting cash with that id -> 409 | no |
| `RemovingNeedsAReasonAndTakesTheEntryOutOfTheTotals` | 319 | P09 P01 P02 HISTORY P05 | reason `""` -> 400 `A reason of 1–500 characters is required.`; remove `Recorded twice` -> balance 10000, expense list total 0, overview float 10000; second remove -> 404; `GET /setup/history?section=pettycash` contains reasons `Removed Wanjiru Kamau's petty cash spending on KAA 501A for {today d MMM yyyy}. Reason: Recorded twice.` and `Recorded petty cash given to Wanjiru Kamau`; with `issue_negative` denied, removing the 10000 cash after a 100 expense -> 400 | no (the date format is invariant culture) |
| `CreditNotesNeedAPayeeAndAReasonAndBelongToNoVehicle` (**(2026-10-12)** renamed `CreditNotesNeedAReasonAndBelongToNoVehicle`, now 389: the `Say who was paid.` assertion is gone; added an 81-character payee -> `The payee must be at most 80 characters.`, and a credit note with payee `" "` and note `Paid the loader` -> balance 9800, its row's `payee` null, found by `q=loader`) | 350 | P05 P01 P02 | payee null -> `Say who was paid.`; note `" "` -> `Say why the money was paid.`; vehicle on a credit -> `A credit note is not recorded against a vehicle.`; valid reimbursable credit 500 -> `("waiting", 9500)`; overview `(creditNotes 500, expenses 0, moneyOut 500, closing 9500)`; row `(payee "Grace Wanjiku", note "Advance to be repaid", reimbursable true, vehicleId null)`; `kind=expense,credit` returns exactly `["credit"]`; `kind=expense,bills` -> 400 `Choose an expense, a credit note or cash.`; credit `-500` -> balance 10000 | no |
| `AHolderSeesOnlyTheirOwnFloat` | 377 | P01 P02 | clerk: `holders` and `floats` are exactly `[clerk]`; `overview?holderId=owner` -> 404; every listed entry has `holderId = clerk`; owner: holders include the clerk, float of the owner has `balance -100` (owner spent 100 on the outside vehicle), entries total 2; after Admin gets `pettycash.view_all` and `AllCompanies = false` (no company), admin's entries are exactly `["cash"]` (the owner's expense on a vehicle outside admin's scope is hidden); **(2026-10-12)** the admin's overview row for the owner's float has `(expenses, balance) = (0, 0)` | EF API (`db.Provisioning`, `IgnoreQueryFilters`, `SetupDataScopes`) |
| `ApprovingADayApprovesWhatThePersonMayAndSkipsTheRest` | 409 | P10 P02 | admin granted `approve_day`; today: expense 1000, credit 400, expense 6000; yesterday: expense 700; `POST approve-day {date: today}` -> `PettyCashDayApproved(2, 1400, 1)`; statuses today 1000 `approved`, 400 `approved`, 6000 `waiting`, yesterday 700 `waiting`; clerk calling approve-day -> 403 (no `detail` asserted) | no |
| `DashboardCardsFollowTheirPermissions` | 434 | P04 | clerk without dash keys -> 403; after `dash.float`: `approvals null`, `float = (balance 2800, waitingCount 2, waitingTotal 7200, sentBackCount 0, approvedThisMonth 0)`; admin with `dash.pettycash`: `float null`, `approvals (count 2, total 7200, approvalLimit 5000, aboveLimit 1)`, one holder `(clerk, "Wanjiru Kamau", 2, 7200, oldest today)` | no |
| `PeopleWithoutPettyCashAreRefused` | 457 | P01 P02 P05 | after the clerk's `pettycash.spend` override is set to denied: clerk overview, entries and create -> 403; owner overview lists the clerk with `active false`; owner cash to the clerk -> 400 `Choose someone who keeps a petty cash float.` | EF API (`PermissionOverrides.IgnoreQueryFilters`, `Provisioning`) |
| `AnyPeriodShowsItsFiguresFromTheFirstDayToTheLast` **(2026-10-12)** | 169 | P01 | cash 10000 at today-10, expense 1000 at -6, cash 2000 at -5, expense 700 at -4, credit 300 today; `from=-6&to=-4` -> `("range", date -4, from -6, to -4)`, `Figures = (10000, 2000, 1700, 0, 1700, 10300, 1700, 2)`, float balance 10000; `from=-1&to=+5&period=week` -> `("range", opening 10300, creditNotes 300, closing 10000)`; `from=to=today` -> `("day", today, today)`; 400s: `from` alone -> `Choose the first and last day.`; `from > to` -> `The first date cannot be after the last date.`; 401 days -> `Choose at most 367 days.`; `from` tomorrow -> `Choose a period that starts on or before today.` | no |
| `ApprovingAPeriodApprovesEveryDayInIt` **(2026-10-12)** | 482 | P01 P10 P02 | admin with `approve_day`; expenses 700 (-3), 1000 and 6000 (-1), 300 (today); overview `from=-3&to=-1` -> `(waiting 7700, waitingCount 3)`; `approve-day {date -3, to -1, holderId clerk}` -> `(2, 1700, 1)`; statuses 700 and 1000 approved, 6000 and 300 waiting; `date -1, to -3` -> 400 `The first date cannot be after the last date.` | no |
| `ApprovingTickedEntriesApprovesAllOfThemOrNone` **(2026-10-12)** | 510 | P11 P06 P02 | ticking 1000 and 6000 -> 403 `This entry is above your approval limit.`, nothing approved; ticking an entry changed since -> 409, nothing approved; ticking 1000, a 400 credit note and the edited 350 -> `(3, 1750, 0)`; again with the 1000 -> `(0, 0, 1)`; `entries: []` -> 400 `Choose the entries to approve.`; the clerk (no `approve_item`) -> 403 without `detail`; an unknown id -> 404 | no |
| `ARetryChecksTheFloatAgainstTheLatestBalance` | 481 | P05 | cash 5000 given, `issue_negative` denied; `Database.Interleave("Organizations", UPDATE "Organizations" SET "SettingsVersion" = "SettingsVersion" + 1)` forces one change-log collision; `BetweenAttempts(UPDATE "PettyCashEntries" SET "UnitAmount" = '1000.0', "Total" = '1000.0' WHERE "Kind" = 1)` lowers the cash between attempts; owner posts cash `-3000`: `Database.Transactions == 2`, status 400, `balanceAfter -2000` (balance after retry is 1000-3000), one cash entry listed | `txn count`, `SQL text` (SQLite-quoted decimals), `interleave`, `EF API` |

### 5.3 Other tests that touch petty cash

| Test | Ln | Ids | Decisive assertions | EF/SQLite-bound |
|---|---|---|---|---|
| `AccessAndSetupTests.PeopleManagersAssignRolesButOnlyAccessManagersChangeSinglePermissions` | 31 (call at 54) | people (S-series) | the owner may create an Office admin person with `adminDefaults + pettycash.approve_day` and `approvalLimit 5000` -> 200; a non-owner people manager sending an approval limit -> 403 (`:50-51`) | no |
| `AccessAndSetupTests.NonOwnersGiveOnlyRolesInsideTheirOwnPermissions` | 237 | people | Office admin cannot grant Fleet manager (its defaults include `dash.float`, `pettycash.spend`) -> 403 `You can only grant roles whose permissions you hold.`; after overrides `dash.float`, `pettycash.spend`, `revenue.capture`, `revenue.no_earnings` -> 200 | no |
| `AccessAndSetupTests.RoleDefaultsFollowWebV28` | 449 | none | `PermissionCatalog.DefaultsFor("Fleet manager")` contains `dash.float`; Owner = every key but `dash.capture` | no |
| `Phase1ContractTests` catalog test `TheCatalogKeepsItsShapeAndTheNamesThePhoneLooksFor` | 360 | access catalog | group names include `Petty cash`; keys include `pettycash.spend`, `pettycash.approve_item`, `pettycash.view_all` (`:384-393`) | no |
| `PermissionKeysTests.TheSharedKeyListMatchesTheCatalog` and siblings | 38 | none | `packages/shared/src/permissions.ts` key list equals `PermissionCatalog.All` (the six `pettycash.*` and two `dash.*` keys); dependencies name only catalog keys; `Refusal` text for an unlabelled key | no; untracked **(uncommitted)** |
| `MigrationSnapshotTests` / `SqlServerTests` | n/a | none | no petty-cash-specific assertion (grep found none); the two migrations are proven only by the snapshot check and, with a connection, by `SqlServerTests` generally | EnsureCreated |

### 5.4 Behaviours with no API test (the Python suite must add them)

- P03 options in full; P04 `sentBackCount` and `approvedThisMonth` other than 0; P02 `q`, `status`, `from`/`to` validation,
  `page`/`pageSize` validation, `kind=cash`, the 200-character `q` limit.
- Limits: note over 80, payee over 80, comment over 200, reason over 500, the ten-year date window, kind change on P06
  (`An entry cannot change between expense, credit note and cash. Remove it and record it again.`), holder change on P06
  (`An entry cannot move to another float. Remove it and record it again.`), P08 over-long comment, P07/P08 on a non-waiting
  entry (`Only an entry waiting for approval can be approved or sent back.`).
- Replays of approve and send back; P05 replay by the same actor after the entry was changed or removed.
- Credit note recorded by an issuer for another holder (used only incidentally at `:221`, never asserted on its own);
  `HolderFor` refusals other than cash (`Recording spending needs ...`, `Recording a credit note on your own float needs ...`,
  `... someone else's float needs ...`, `Choose who the cash goes to.`).
- `DbUpdateConcurrencyException` mapping (`This entry was changed by another save.`); the `Version` of a fresh entry (1);
  the audit event row (`pettycash.recorded`); the change-log `before`/`after` JSON; the section filter visibility for scoped
  viewers (PC-32); approve-day with `holderId` or with a hidden holder; approve-day writing one log row per entry.
- Removed entry excluded from holders, floats, dashboard and history counts other than the first remove test.

---

## 6. Client dependencies

All client files are **(uncommitted)** (untracked) unless marked. The clients depend on the contract of Section 4; they never
re-derive rules and show buttons from `canEdit`, `canRemove`, `canReview` and `permissions`.

### 6.1 Shared module `packages/shared/src/pettyCash.ts`

- Types mirror Section 4.4 (`Shared:7-272`). **(2026-10-12)** `PettyCashPeriod` adds `"range"`; `PettyCashFigures` adds `waiting`, `waitingCount`; `PettyCashOverviewQuery` adds `from`, `to`; `ApprovePettyCashDay` adds `to`; new `ApprovePettyCashEntries {entries: {id, version}[]}`; `withQuery` moved to `./query` (9276c51 and the working tree). `PettyCashBucket = 1 | 2 | 3`; `PettyCashKind = "cash" | "expense" | "credit"`;
  `PettyCashStatus = "waiting" | "approved" | "sentBack"`; `PettyCashPeriod = "day" | "week"`.
- Constants the server must stay in step with: `PETTY_CASH_NOTE_LIMIT 80`, `PAYEE_LIMIT 80`, `COMMENT_LIMIT 200`, `REASON_LIMIT 500`,
  `MAX_UNITS 999_999_999.999`, `PAGE_SIZE 100` (`:27-32`); kind labels `Cash given`/`Expense`/`Credit note`; status labels
  `Waiting`/`Approved`/`Sent back` (`:15-25`).
- `PETTY_CASH_PERMISSIONS = [pettycash.spend, pettycash.view_all, pettycash.approve_item, pettycash.issue]` and `canOpenPettyCash`
  (`:35-44`): any one opens the module. `pettycash.approve_day` and `issue_negative` alone do not (`pettyCash.test.ts:57-61`).
- Client-side validation text (differs from the server's): `Enter an amount other than zero, with at most two decimals. Use a minus sign for money coming back.`
  and `Enter units above zero, with at most three decimals.` (`:274-276`). Amount grammar `^-?\d{1,12}(\.\d{1,2})?$` or grouped
  `^-?\d{1,3}(,\d{3})+(\.\d{1,2})?$`; units `^\d{1,9}(\.\d{1,3})?$` or grouped (`:282-303`). `pettyCashTotal` repeats PC-3.
- Path builders `pettyCashEntriesPath(query)` -> `setup/pettycash/entries?...` and `pettyCashOverviewPath(query)` -> `setup/pettycash/overview?...`;
  empty values are dropped, arrays join with `,` (`kind=expense%2Ccredit`), `q` uses `+` for spaces (`:316-328`; tests `pettyCash.test.ts:42-55`).
- `packages/shared/src/permissions.ts` (untracked **(uncommitted)**): `NAV.pettycash = { label: "Petty cash", any: PETTY_CASH_PERMISSIONS }` (`:72`),
  `PRIMARY_NAV = [dashboard, revenue, pettycash]` (`:90-94`), `DASHBOARD_CARDS` entries `{dash.float, "My petty cash float"}` and
  `{dash.pettycash, "Petty cash to approve"}` (`:108,113`), `startsOnToday = can("dash.capture") || can("dash.float")` (`:121-122`).

### 6.2 Paths, fields, statuses and messages the clients use

| Client | Path (relative to the API root) | Sends | Reads |
|---|---|---|---|
| web `PettyCashPage.tsx:67-73` | `GET setup/pettycash/overview?date&period=week&holderId` (no `date` the first time; the answer teaches `businessDate`) | `period` only when `week` | `businessDate`, `date`, `period`, `from`, `to`, `permissions`, `holders`, `figures`, `floats` |
| web `PettyCashPage.tsx:105-121` | `GET setup/pettycash/entries?from&to&holderId&q&pageSize=100&kind&status` (`kind=cash` on the Cash tab; `kind=expense,credit` plus optional `status` on the Expenses tab; `q` debounced 300 ms) | no `page`: the web reads the first 100 only | `items[]` with all flags |
| web `EntryDialog.tsx:124,170-184` | `GET setup/pettycash/options?date`; `POST setup/pettycash/entries`; `PUT setup/pettycash/entries/{id}` | create: `id` (client UUID), `kind`, `date`, `unitAmount`, `note` (null if blank), expense `vehicleId`, `expenseItemId`, `units`, credit `payee`, `reimbursable`, `holderId` for cash and for an issuer's credit; change: `version` instead of `id` | `vehicles[]`, `items[]`, `holders[]` |
| web `PettyCashPage.tsx:151,169-175`; `ReasonDialogs.tsx:100,126` | `POST .../entries/{id}/approve {version}`; `POST .../approve-day {date, holderId?}`; `POST .../entries/{id}/send-back {version, comment}`; `POST .../entries/{id}/remove {version, reason}` | | `approved`, `total`, `skipped` for the day toast |
| web `AppShell.tsx:855-857` | `GET setup/pettycash/dashboard` only when the person has `dash.float` or `dash.pettycash` | | `float`, `approvals` (null = withheld; a 404 is tolerated, `PettyCashShell.test.tsx:112`) |
| mobile `client.ts:29-85` | `send(method, "setup/pettycash/" + path, body)` through `apiSendResult` | same bodies | `detail`, then `title`, of the problem body |
| mobile `PettyCashScreen.tsx:68-72,98-108` | `GET setup/pettycash/overview` (no params: all floats the person sees) and `GET ...overview?date&period&holderId={own}` for "My float" | `holderId` = `permissions.holderId` | `permissions`, `floats`, `figures`, `from`, `to` |
| mobile `sections.tsx:118-123,228,254` | `GET ...entries?from&to&holderId` per day or week (week computed on the phone from the organization's first day); `GET ...entries?status=waiting` for Approvals; paged with `page` (`client.ts:144-205` appends pages until `items.length >= total`) | `page` from 2 | `items`, `total` |
| mobile `forms.tsx:93` | `GET setup/pettycash/options?date=` | | options |
| mobile `forms.tsx:226-243,311-347,431-459,533-541`; `PettyCashScreen.tsx:159,173` | `POST entries`, `PUT entries/{id}`, `POST entries/{id}/approve`, `.../send-back`, `.../remove`, `POST approve-day {date}` | create sends `id` (expo-crypto UUID); change sends `version` | `PettyCashSaved`, `PettyCashDayApproved` |
| mobile `screens.tsx:224` | `GET setup/pettycash/dashboard` (not when offline) | | `float`, `approvals` |

Status handling on the clients:
- Web (`apiRequest`/`ApiError`, `request.ts:21`): 409 closes the dialog, shows the problem's message on the page and reloads
  (`useDialogAction.ts`, `PettyCashPage.tsx:130-136,158`); other statuses show the message. A 400 with `balanceAfter` is shown as its
  `detail` (fixture `PettyCash.test.tsx:336`).
- Mobile (`client.ts:40-72`): 2xx ok; 500 and above shows the `ServerError` message; 403 shows `detail || title || "You do not have permission to do this."`;
  409 and 404 show `detail || title || ("This entry was changed by someone else." | "This entry no longer exists.")` and reload;
  other 4xx show `detail || title || "The request could not be completed."`; a network failure shows `No internet connection. Nothing was saved.`.
  Clients therefore rely on `detail` for 400, 403 and 409 and fall back to `title`. The 404 problem has no `detail` (title
  `Record not found in your scope.`), so the phone shows that title.
- Fields clients depend on beyond display: `entry.version` (change, approve, send back, remove), `canEdit`, `canRemove`, `canReview`,
  `aboveLimit`, `permissions.holderId` (own float id), `permissions.canSpend|canViewAll|canIssue|canApproveItem|canApproveDay|approvalLimit`
  (mobile sections: My float = canSpend, Approvals = canApproveItem, Give cash = canIssue, All floats = canViewAll; `PettyCashScreen.tsx:83-92`),
  `holders[].active`, `bucket` (the web defaults it to 2 when the item is missing), `floats[].lastCashOn`, and `current` on a 409.
- Dashboard cards: web `dashboardCards.ts` and mobile `dashboard.ts` build their text from `float.balance`, `waitingCount`, `waitingTotal`,
  `sentBackCount`, `approvedThisMonth`, `approvals.count`, `total`, `approvalLimit`, `aboveLimit`, `holders[].{holderId,name,count,total,oldest}`.
  Card permissions: `dash.float` (card "My petty cash float", mobile action "Record spending" needing `pettycash.spend`, opens section `float`) and
  `dash.pettycash` (card "Petty cash to approve", action "Review entries" needing `pettycash.approve_item`, opens section `approvals`)
  (`apps/mobile/src/shell/access.ts:94-123`, **(uncommitted)** edit of a committed file).
- Web proxy: only listed first path segments are forwarded and `pettycash` is on the list (`route.ts:87`); `SetupProxy.test.ts:55-73` pins that all
  ten petty-cash paths are forwarded and that `pettycashx` and `petty-cash/overview` are 404. The Python API needs no change for this, but
  the proxy keeps the path names of Section 4.
- Navigation: the web menu item `Petty cash` shows for any of the four permissions (`Navigation.test.tsx:82` pins `pettycash.issue`); the mobile
  tab `Spend` shows for those four or `bills.view` (`access.ts:51`) and says `Office bills are not available from the current API yet.` for the bills part.
- Web `HistoryPage.tsx:30` labels the change-log section `pettycash` as `Petty cash`; `people/model.ts:11-15` lists `pettycash.approve_item` and
  `pettycash.approve_day` as "approvals" in the people editor.
- Client test fixtures word some refusals differently from the server (for example `You need Approve single entries to do this.`,
  `apps/mobile/tests/pettyCash.test.tsx:1181`); those are fixtures, not the contract.

---

## 7. Naming audit

| Item | Observation | Suggestion for the Python port |
|---|---|---|
| Route prefix | `/setup/pettycash` although petty cash is operational, not setup; kebab segments `send-back`, `approve-day` next to the one-word `pettycash` and the camelCase status `sentBack` | Keep the paths (clients and the web proxy allow-list depend on them); use snake_case internally, wire names unchanged |
| "float" vs "holder" | The API says holder (`holderId`, `PettyCashHolderDto`) and float (`PettyCashFloatDto`, `floats`, dashboard card `float`); the permission labels say "float" | Table `petty_cash_entries.holder_id`; keep both wire words |
| `float` as a JSON key | `PettyCashDashboardDto.float` | A Python field named `float` shadows the builtin; use an alias (`float_` serialised as `float`) |
| `from` as a query name | `GET entries?from=` and `to=` | `from` is a Python keyword; alias the query parameter |
| `kind` words | wire `cash`/`expense`/`credit`; UI "Cash given"/"Expense"/"Credit note"; message texts "credit note" | Store smallint 1/2/3 as in .NET; map words at the edge |
| `unitAmount` | UI label "Amount each"; `Total` is the money; `Units` is a decimal despite the name | Keep wire names |
| Audit action | `pettycash.recorded` is used for create, change, approve, send back and remove | Keep the string if audit consumers exist; otherwise decide (open question 12) |
| Change-log JSON | PascalCase property names and enum NAMES (`"Expense"`, `"Waiting"`) while the wire uses camelCase words | Reproduce byte-for-byte only if the history screen or the importer reads them (open question 11) |
| Table names | `PettyCashEntries` (plural) next to `FleetVehicle`, `ExpenseItem` (singular) and `Memberships` (plural) | Follow `docs/11-naming.md`; one table `petty_cash_entries` |
| Status column | null means "no review" (cash), not a fourth state | Keep nullable smallint, or a separate boolean; the wire needs `null` |
| `Period` | tally constants `Before=0`, `Within=1`, `After=2`; wire `period` is `day`/`week` (unrelated meaning) | Rename the internal one (`window_position`) |
| `Removed*` | `RemovedAt/By/Reason` soft delete on this table only | Reuse one soft-delete convention if the schema has one |
| Namespaces | `Auth.Application.PettyCash`, `Auth.Api` | Cited only; the product is xcode |

---

## 8. Open questions

For the planner (numbered; the first five block the conversion prompt):
1. **Freeze.** All of it is uncommitted and `PettyCashUseCases.cs` and `PettyCashRepository.cs` (19:37) are newer than `PettyCashTests.cs` (15:52), the model, the contracts and the migrations (15:44-15:48). Re-run the Section 4 and 5 reading against the commit that lands the feature before writing the Python prompt.
2. **Gate semantics.** `ReadAny`/`WriteAny` take a list of permissions, any one enough; the current Python plan has to offer that (the existing `Read`/`Write` take one). Decide the Python signature (`require_any(...)`).
3. **Retry on change-log collision.** Every write bumps `Organizations.SettingsVersion`, so all writes of an organization conflict on one row and the whole use case reruns from fresh reads (PC-24, test `ARetry...`). The retry count, back-off and the status after exhaustion live in `UnitOfWork` (not read here). Approve-day bumps it once per entry.
4. **Money and ordering on PostgreSQL.** `numeric(14,2)`/`numeric(12,3)`; rounding is half away from zero (`ROUND_HALF_UP` on Decimal), not banker's; `ORDER BY Id` as the third sort key orders `uniqueidentifier` in SQL Server by its internal byte groups, Postgres `uuid` bytewise, so ties on `(Date, Kind)` come in a different order; holder names sort with ordinal-ignore-case.
5. **Search.** `LIKE` with SQL Server bracket escaping and a case-insensitive collation (`Repo:88`); Postgres needs `ILIKE ... ESCAPE`. The bracket escape is not exercised on SQLite, so no test proves it.
6. **Create returns 200**, never 201, also for replays; keep or change (clients accept any 2xx).
7. **Missing `version`.** On P06-P09 a missing or wrong `version` is a 409 with `current`, not a 400 (`version` is a non-nullable `long` on P07-P09, so absent reads as 0).
8. **Replays bypass checks.** P06 replay (PC-16) answers 200 before the permission and version checks; P05 replay ignores the body; a removed entry still answers a retried create. Confirm these are intended.
9. **`current: null`.** The 409 for a foreign or vanished id carries `current: null` (an extension member with a null value); whether `Results.Problem` writes the key or omits it is framework behaviour that no test asserts (the stale-version test only reads a non-null `current`).
10. **Dashboard semantics.** `approvals` counts the viewer's own waiting entries and entries they cannot approve; `aboveLimit` only counts those over their limit; `float.sentBackCount` and `waiting*` are to date while `approvedThisMonth` is month to date; the month starts on the business date's month, not the calendar's. Confirm.
11. **History readers.** `OrganizationSettingsVersion.Before/After` hold the PascalCase snapshot (PC-25), and the history page shows `Reason`; whether any client parses `Before/After` for petty cash is not established (not found in the petty-cash client files; the History screen was not read).
12. **Audit action name.** Keep `pettycash.recorded` for every operation or split it (`created`, `changed`, `approved`, `sent_back`, `removed`).
13. **Unreachable branches.** `InvalidOperationException("This entry was removed.")`, the `Kind` defined check, and `Utc` offset checks are unreachable via HTTP; port as defensive assertions or drop.
14. **Holder resolution.** Holders are computed in application code from role names (`PermissionCatalog.DefaultsFor`), overrides and member activity (`Repo:27-48`), loading all members every call; the Python port needs the same resolver (an existing routine in the access inventory) and should decide whether to compute in SQL.
15. **Week start duplicated.** The server, the phone and the web each know the first day of week; a mismatch would show a different week than the figures. The server's answer (`from`/`to`) is authoritative for web; the phone recomputes.
16. **Untracked support files.** `SettingsChangeLog.cs`, `PermissionKeys.cs`, `permissions.ts` and `PermissionKeysTests.cs` are untracked refactors the feature depends on; `ChangeLogVehicle` (migration) must be in the Python schema before petty cash writes its `VehicleId` into the change log.
17. **Migrations never applied?** `Units` was `int` in the first migration and `decimal(12,3)` in the second (written 15:48, the same afternoon); if neither shipped, the Python schema takes the final type only (no data migration needed from this table).
18. **Doc drift.** `docs/petty-cash-contract.md` (untracked) is the authors' contract note; where it differs from the code (Section 1.3, PC-13), this inventory follows the code.
19. **Offline.** Petty cash is online-only on the phone; no queue or idempotent replay beyond the client `id` on create. Keep the `id` idempotency exactly.
20. **No hard limits on list size.** The web reads the first 100 entries of a day or week only (no paging control); the phone pages. A busy week with more than 100 rows would be cut on the web.

Anything unfinished seen in the feature: no TODO markers; gaps are the untested behaviours of 5.4, the online-only phone, the
office-bills half of the Spend tab (absent), and the late edit window noted in open question 1.

---

## Appendix: files read, modification times and git status

**(2026-10-12)** Re-read for the corrections, at `HEAD` 493bf82 plus the working tree (`M` = modified against `HEAD`; all were committed in ad2f1cc):

| File | Modified | git | Commits after the reading |
|---|---|---|---|
| `apps/api/Domain/PettyCash.cs` | 2026-10-10 22:20:56 | M | working tree only |
| `apps/api/Application/PettyCashUseCases.cs` | 2026-10-10 22:29:31 | M | 6f130aa, 9276c51 |
| `apps/api/Application/PettyCashContracts.cs` | 2026-10-10 22:22:12 | M | 6f130aa, 9276c51 |
| `apps/api/Api/PettyCashEndpoints.cs` | 2026-10-10 22:31:07 | M | 9276c51 |
| `apps/api/Infrastructure/PettyCashRepository.cs` | 2026-10-10 22:22:12 | M | 6f130aa, 9276c51 |
| `apps/api/Infrastructure/PettyCashModel.cs` | 2026-10-07 15:44:31 | | none |
| `tests/api/PettyCashTests.cs` | 2026-10-10 22:27:34 | M | 6f130aa, 9276c51 |
| `packages/shared/src/pettyCash.ts` | 2026-10-10 22:24:49 | M | 9276c51 |
| `apps/api/Infrastructure/Setup/SetupRepository.cs` | 2026-10-10 22:41:42 | M | 9276c51 |
| `apps/api/Infrastructure/Setup/FleetPostings.cs` | 2026-10-10 22:39:08 | M | 9276c51 (new) |
| `apps/api/Application/Setup/FleetPostings.cs` | 2026-10-09 18:59:04 | | 9276c51 (new) |

The 2026-10-08 reading:

Times are local (UTC+3) from `stat`, read 2026-10-08 about 00:13. `git` column is the `git status --short` code (`??` untracked, `M` modified, blank = tracked and unchanged). The directories `apps/web/components/pettycash/` (17 files, 2026-10-07 14:45 to 18:57) and `apps/mobile/src/pettycash/` (7 files, 14:48 to 21:46) are untracked as directories and were read only for paths, statuses and messages.

| File | Modified | git |
|---|---|---|
| `apps/api/Domain/PettyCash.cs` | 2026-10-07 15:44:31 | ?? |
| `apps/api/Application/PettyCashContracts.cs` | 2026-10-07 15:44:31 | ?? |
| `apps/api/Application/PettyCashUseCases.cs` | 2026-10-07 19:37:53 | ?? |
| `apps/api/Api/PettyCashEndpoints.cs` | 2026-10-07 15:44:31 | ?? |
| `apps/api/Infrastructure/PettyCashModel.cs` | 2026-10-07 15:44:31 | ?? |
| `apps/api/Infrastructure/PettyCashRepository.cs` | 2026-10-07 19:37:53 | ?? |
| `apps/api/Infrastructure/Migrations/20261007115030_PettyCash.cs` | 2026-10-07 14:50:31 | ?? |
| `apps/api/Infrastructure/Migrations/20261007124851_PettyCashDecimalUnits.cs` | 2026-10-07 15:48:51 | ?? |
| `apps/api/Infrastructure/Migrations/AuthDbModelSnapshot.cs` | 2026-10-07 21:15:24 | M |
| `apps/api/Infrastructure/Migrations/20261007052529_ChangeLogVehicle.cs` | 2026-10-07 13:13:55 | ?? |
| `apps/api/Infrastructure/Migrations/20261007181520_RenameUseGrouping.cs` | 2026-10-07 21:15:24 | ?? |
| `apps/api/Domain/PermissionKeys.cs` | 2026-10-07 18:27:34 | ?? |
| `apps/api/Application/AccessContracts.cs` | 2026-10-07 18:46:03 | M |
| `apps/api/Domain/Access.cs` | 2026-10-07 18:44:59 | M |
| `apps/api/Program.cs` | 2026-10-07 18:44:50 | M |
| `apps/api/Infrastructure/AuthDb.cs` | 2026-10-07 14:48:18 | M |
| `apps/api/Infrastructure/OrganizationModel.cs` | 2026-10-06 13:01:24 |  |
| `apps/api/Infrastructure/Setup/SetupRepository.cs` | 2026-10-07 18:55:09 | M |
| `apps/api/Infrastructure/Setup/SetupModel.cs` | 2026-10-07 08:16:50 | M |
| `apps/api/Infrastructure/Setup/SetupExecution.cs` | 2026-10-07 18:41:13 | M |
| `apps/api/Domain/Setup/OrganizationSettingsVersion.cs` | 2026-10-07 08:15:44 | M |
| `apps/api/Application/Settings/SettingsChangeLog.cs` | 2026-10-07 18:42:58 | ?? |
| `apps/api/Application/ISetupExecution.cs` | 2026-10-07 18:40:52 | M |
| `apps/api/Application/OrganizationPort.cs` | 2026-10-07 18:40:36 | M |
| `apps/api/Application/Setup/SetupContracts.cs` | 2026-10-07 14:52:09 | M |
| `apps/api/Api/SetupEndpoints.cs` | 2026-10-07 18:45:46 | M |
| `tests/api/PettyCashTests.cs` | 2026-10-07 15:52:22 | ?? |
| `tests/api/AccessAndSetupTests.cs` | 2026-10-05 09:20:14 |  |
| `tests/api/Phase1ContractTests.cs` | 2026-10-07 20:56:58 | M |
| `tests/api/PermissionKeysTests.cs` | 2026-10-07 18:44:06 | ?? |
| `packages/shared/src/pettyCash.ts` | 2026-10-07 15:49:47 | ?? |
| `packages/shared/src/permissions.ts` | 2026-10-07 19:54:16 | ?? |
| `packages/shared/tests/pettyCash.test.ts` | 2026-10-07 15:49:47 | ?? |
| `docs/petty-cash-contract.md` | 2026-10-07 15:56:57 | ?? |
| `apps/web/tests/pettyCashServer.ts` | 2026-10-07 16:05:17 | ?? |
| `apps/web/tests/PettyCash.test.tsx` | 2026-10-07 17:53:00 | ?? |
| `apps/web/tests/PettyCashShell.test.tsx` | 2026-10-07 17:53:00 | ?? |
| `apps/web/tests/SetupProxy.test.ts` | 2026-10-07 16:45:03 | M |
| `apps/web/components/AppShell.tsx` | 2026-10-07 18:47:06 | M |
| `apps/web/components/setup/HistoryPage.tsx` | 2026-10-07 15:03:44 | M |
| `apps/web/components/people/model.ts` | 2026-10-08 00:00:36 | ?? |
| `apps/web/app/api/setup/[...path]/route.ts` | 2026-10-07 16:44:49 | M |
| `apps/mobile/src/shell/access.ts` | 2026-10-07 19:57:20 | M |
| `apps/mobile/src/shell/screens.tsx` | 2026-10-07 19:10:16 | M |
| `apps/mobile/tests/pettyCash.test.tsx` | 2026-10-07 21:46:13 | ?? |
| `apps/web/components/pettycash/AmountInput.tsx` | 2026-10-07 14:47:00 | ?? |
| `apps/web/components/pettycash/CashTable.tsx` | 2026-10-07 17:45:17 | ?? |
| `apps/web/components/pettycash/DayNavigator.tsx` | 2026-10-07 18:57:57 | ?? |
| `apps/web/components/pettycash/EntriesTable.tsx` | 2026-10-07 17:44:43 | ?? |
| `apps/web/components/pettycash/EntryDialog.tsx` | 2026-10-07 17:45:20 | ?? |
| `apps/web/components/pettycash/FigureCards.tsx` | 2026-10-07 18:57:57 | ?? |
| `apps/web/components/pettycash/FiltersBar.tsx` | 2026-10-07 17:44:23 | ?? |
| `apps/web/components/pettycash/FloatsTable.tsx` | 2026-10-07 17:52:47 | ?? |
| `apps/web/components/pettycash/PettyCashPage.tsx` | 2026-10-07 17:44:11 | ?? |
| `apps/web/components/pettycash/ReasonDialogs.tsx` | 2026-10-07 17:45:20 | ?? |
| `apps/web/components/pettycash/RowActions.tsx` | 2026-10-07 17:44:52 | ?? |
| `apps/web/components/pettycash/StatusTag.tsx` | 2026-10-07 14:45:21 | ?? |
| `apps/web/components/pettycash/dashboardCards.ts` | 2026-10-07 17:52:47 | ?? |
| `apps/web/components/pettycash/labels.ts` | 2026-10-07 16:26:55 | ?? |
| `apps/web/components/pettycash/period.ts` | 2026-10-07 16:26:01 | ?? |
| `apps/web/components/pettycash/request.ts` | 2026-10-07 15:17:31 | ?? |
| `apps/web/components/pettycash/useDialogAction.ts` | 2026-10-07 14:45:20 | ?? |
| `apps/mobile/src/pettycash/PettyCashScreen.tsx` | 2026-10-07 16:11:06 | ?? |
| `apps/mobile/src/pettycash/client.ts` | 2026-10-07 14:55:55 | ?? |
| `apps/mobile/src/pettycash/dashboard.ts` | 2026-10-07 14:48:00 | ?? |
| `apps/mobile/src/pettycash/format.ts` | 2026-10-07 21:46:10 | ?? |
| `apps/mobile/src/pettycash/forms.tsx` | 2026-10-07 16:09:52 | ?? |
| `apps/mobile/src/pettycash/parts.tsx` | 2026-10-07 18:56:33 | ?? |
| `apps/mobile/src/pettycash/sections.tsx` | 2026-10-07 16:28:50 | ?? |
