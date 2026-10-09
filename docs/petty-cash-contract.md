# Petty cash: API contract and rules

Types: `packages/shared/src/pettyCash.ts` (import from `@xcode/shared/pettyCash`). Design reference: the Petty cash
module in `docs/design/XCODE_Web_v1.0.html` (search `Petty cash ----------`, `pettyCards`, `expensesTab`, `cashTab`,
`savePettyDialog`, and the dashboard cards `dash.float` / `dash.pettycash`). Where this file and the prototype differ,
this file wins.

## Model

- One float per holder. A holder is an active person with `pettycash.spend`, or anyone who already has entries.
- Three kinds of entry, all with a signed, non-zero amount:
  - `cash`: cash given to a float by someone with `pettycash.issue`. Negative = cash taken back. Never reviewed.
  - `expense`: spending against a vehicle (required) and an expense item (required), `units` x `unitAmount`.
    Units are above zero with up to three decimals (4.5 litres of oil, 11.875 litres of fuel); the total is rounded
    to the cent, halves away from zero. Recorded by the holder on their own float, for a vehicle in their data scope.
    Negative = refund.
  - `credit` (credit note): money paid out of the float that belongs to no vehicle, e.g. "pay so-and-so". Needs a
    payee and a reason (`note`). `reimbursable` marks money the payee should pay back. Recorded by the holder, or by
    an issuer on any float.
- `balance = cash - credit - expense` over every entry that is not removed, whatever its status.
- A float may go below zero: a holder can pay from their own pocket before cash reaches them, and records the
  spending anyway. Only cash taken back is held at zero (see `pettycash.issue_negative`).
- Expenses and credit notes start `waiting`. A reviewer approves (`approved`) or sends back with a comment
  (`sentBack`; the holder sees the comment on the row). Any edit puts the entry back to `waiting`.
- Only an approved expense posts to its vehicle's costs (vehicle report, under the item's category bucket).
- Removing is soft and needs a typed reason. Removed entries leave every list and total.

## Permissions (existing catalog, no new keys)

| Action | Needs |
|---|---|
| Open Petty cash | any of `pettycash.spend`, `view_all`, `approve_item`, `issue` |
| See own float | `pettycash.spend` |
| See every float | `pettycash.view_all` (expenses on vehicles outside the viewer's data scope are not listed) |
| Record expense / credit note on own float | `pettycash.spend` |
| Give cash, record a credit note on any float | `pettycash.issue` |
| Approve or send back one entry | `pettycash.approve_item`, total (ignoring sign) within the person's approval limit, not on their own float, not an entry they recorded |
| Approve a whole day | `pettycash.approve_day`; approves what the same person could approve one by one and skips the rest |
| Take cash back below zero | `pettycash.issue_negative` ("Send money that takes a float below zero"). Applies only to cash entries (giving, changing or removing cash). Expenses and credit notes may always take a float below zero. |
| Edit / remove expense or credit note | the holder (or recorder) while `waiting` or `sentBack`; reviewers (`approve_item`) any status |
| Edit / remove cash | `pettycash.issue` |
| Dashboard "My petty cash float" | `dash.float` |
| Dashboard "Petty cash to approve" | `dash.pettycash` |

The approval limit is set per person in People and access by someone with "Change single permissions and approval
limits" (`access.manage`). It is empty by default, which means no limit; there is no built-in amount.

Each entry carries `canEdit`, `canRemove`, `canReview` and `aboveLimit` for the signed-in person. Clients show
buttons from these flags and from `overview.permissions`; they never re-derive the rules.

## Endpoints

All under `setup/pettycash` (web: `/api/setup/pettycash/...` through the existing proxy; mobile: `setup/pettycash/...`
through `apiGet`/`apiRequest`). JSON is camelCase; dates are `yyyy-MM-dd`.

| Method and path | Body / query | Returns |
|---|---|---|
| `GET overview` | `date?` (default business date), `period?` (`day` default, or `week`), `holderId?` | `PettyCashOverview` with `period`, `from`, `to` and `figures`. A week starts on the organization's first day of the week and contains `date`. Without `holderId` the figures sum every float the person sees, so "my float" screens pass their own `holderId` |
| `GET entries` | `from? to? holderId? kind? status? q? page? pageSize?` (pageSize at most 100, default 100; `kind` may list several, `expense,credit`) | `PettyCashEntryPage`, oldest date first |
| `GET options` | `date?` | `PettyCashOptions` |
| `GET dashboard` | none | `PettyCashDashboard` |
| `POST entries` | `SavePettyCashEntry` (optional client `id` for safe retry) | `PettyCashSaved` |
| `PUT entries/{id}` | `SavePettyCashEntry` with `version` | `PettyCashSaved` |
| `POST entries/{id}/approve` | `{ version }` | `PettyCashSaved` |
| `POST entries/{id}/send-back` | `{ version, comment }` | `PettyCashSaved` |
| `POST entries/{id}/remove` | `{ version, reason }` | `PettyCashSaved` |
| `POST approve-day` | `{ date, holderId? }` | `PettyCashDayApproved` |

Errors are problem+json: 400 validation (`detail` is a sentence to show), 403 missing permission (`detail` names
the permission label), 404 unknown or out of scope, 409 conflict (`current` holds the entry as it now is when it
still exists; reload and retry otherwise). Cash taken back below zero without the permission is a 400 with
`balanceAfter`.

Limits: note 80, payee 80, send-back comment 200, removal reason 500, units above zero with up to three decimals,
dates not after the business date.
