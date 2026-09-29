# Phase 2 plan and handoff

Written 2026-09-29 by the review lead. It is also the handoff note: a new session continues from the **Status** section at the end, using the same instructions.

## Where things are

| Path | What it is |
|---|---|
| `C:/Users/user/Documents/Coding/PrioriTech/xcode` | Main folder, `settings` checked out, holding the **user's own uncommitted work** (design files moved to `docs/design`, review `.txt` files, an `Access.cs` fix, `InvariantGlobalization=false`). Never commit, reset or stash there. |
| `.../xcode-wt/access` | Worktree for branch `access` |
| `.../xcode-wt/settings` | Worktree for `origin/settings`, detached HEAD. Commit here, then `git push origin HEAD:settings` only when the user allows pushing, and move the local `settings` ref with `git update-ref` |
| `.../xcode-wt/revenue` | Worktree for branch `revenue` (top of the stack) |
| `.../xcode-wt/develop` | Read-only Phase 1 baseline (`origin/develop`) |

Stack: `develop` (Phase 1, PRs #1–#3 merged) → `access` → `settings` → `revenue`. Merge upward only (`Merge branch 'access' into settings`, then `'settings' into revenue`). No force pushes. `phase2/access-foundation` is to be deleted once its three tests are ported (WP-A).

Commits: author `Benson Kimathi <bensonkimkam@gmail.com>`, no Co-authored-by trailers. Never commit `apps/web/next-env.d.ts`, `apps/web/tsconfig.tsbuildinfo`, or `*_export.tar.gz`. Nothing is pushed until the user has tried the mobile build (standing rule).

Requirements: `docs/design/XCODE_Build Notes_v1.0.pdf` (addendum 1) and `docs/design/XCODE_Web_v1.0.html` (Web v2.8). Both are in the main folder only. Mobile v2.5 is not in the repo, so mobile follows `XCODE_Mobile_v0.9.html` plus the addendum rules. Reviews: `docs/reviews/*.txt` (main folder).

## Phase 1 summary

1. Shipped on `develop`: PIN authentication for web (httpOnly cookies through a Next.js proxy) and mobile (SecureStore), with device trust, email codes, refresh rotation and lockout.
2. Also shipped: organizations, people and access (roles, overrides, data scope), companies, vehicles with dated targets, recurring costs and savings, change log, and organization settings with appearance.
3. Architecture: one .NET 10 minimal API (EF Core, SQL Server, SQLite in tests), a Next.js single-page shell, an Expo app, and `@xcode/shared` for the auth client and PIN rules.
4. Decisions: serializable transactions for every setup call and every auth call; one process-wide auth semaphore; tenant query filters plus write-time tenant checks; append-only revisions for schedules and targets.
5. Debt: role defaults kept in two places (catalog code and the `RolePermissions` table); people list loads whole tables; contracts are hand-copied between web and mobile; no OpenAPI document; no CI; `/health` checks nothing.
6. Tests on develop: API 71/73 pass (both failures are SQL Server tests that need `SQLSERVER_TEST_CONNECTION`, and `InvariantGlobalization=true` breaks SqlClient). Web and mobile are recorded in Status.

## Assumptions (no blocking questions)

- A1. Phase 2 scope is addendum sections 1 to 3 (corrections, decisions, access fixes) plus section 4 (revenue on web and phone). Petty cash (section 5) and Reports (section 6) are later phases. Dashboard cards backed by revenue are connected. Every other card keeps a "connect revenue first" or "not available yet" state.
- A2. Schedule and target revisions are immutable history and are never rewritten. Legacy categories and daily schedules stay readable and keep posting. New saves use the three buckets and weekly, monthly or yearly. Legacy categories map to buckets for reporting as follows: RepairsAndUpkeep goes to Repairs and maintenance, and the other three go to Recurring charges. This mapping is a decision for the user.
- A3. A same-day change to revenue is an update, not an edit. Only a change to a past day sets `CorrectedAfterDate` ("edited after capture").
- A4. No new native mobile modules, so shipped binaries can take a JS update. Use `expo-secure-store` or `expo-network`, which are already installed.
- A5. Enums go over the wire as numbers, as they do today.

## Contracts (frozen; every package codes against these)

All errors are ProblemDetails from `WithSetupErrors`. `/auth/*` keeps the Phase 1 `{status,...}` JSON shapes byte for byte, because shipped phones depend on them.

### C1. 403 says why (WP-A)
`UnauthorizedAccessException` with a custom message gives `403 {title:"Not permitted in this organization or data scope.", detail:"<message>"}`. The default message gives no `detail`.

### C2. Revenue (WP-R)
- `GET /setup/revenue?weekStart=&companyId=&vehicleId=`. `vehicleId` is a new, optional filter. `RevenueCellDto` gains `version: number|null` at the end. `canEdit` becomes false for a missing day later than that vehicle's `earliestMissing`. `earliestMissing` must be computed from all of the vehicle's records, not only that week's.
- `PUT /setup/revenue/{vehicleId}/{yyyy-MM-dd}`, body `{amount?: number|null, reason?: "Garage"|"Arrest"|"No Crew"|"Other"|null, note?: string|null, version?: number|null}`.
  - 200 returns `{id, version}`. Repeating the same entry returns 200 with the current id and version (idempotent replay).
  - 409 when a record exists and differs, and either `version` is null or `version` does not match. Body: `{title, detail, status:409, current: RevenueCellDto}`.
  - 400 when an earlier day is missing. Body: `{title:"Invalid setup change", detail, earliestMissing:"yyyy-MM-dd"}`.
  - 403 when not permitted, 404 when the vehicle is outside scope.
- `GET /setup/revenue/dashboard?period=today|week|month` is unchanged.
- `RevenueWeekDto` also carries `currentWeekStart` (after `weekThrough`), which another session pushed at a9d88cf.
- TS types: **`packages/shared/src/index.ts`** holds `RevenueCell`, `RevenueVehicle`, `RevenueWeek`, `RevenueDashboard` and `SaveRevenue` (pushed by another session). C2 adds `version: number | null` to `RevenueCell` and `version?: number | null` to `SaveRevenue` there. Web and mobile import them from `@xcode/shared`; there is no per-app copy.
- Existing screens to build on, pushed at a55f451: web `apps/web/components/RevenuePage.tsx` and mobile `apps/mobile/src/shell/RevenueScreen.tsx`, which is online-only.

### C3. Expense categories and items (WP-S)
- Bucket enum `ExpenseBucket`: 1 = Repairs and maintenance, 2 = Recurring charges, 3 = Loan repayments.
- `ExpenseItemDto {id, categoryId, name, active, stoppedOn: string|null}`.
- `ExpenseCategoryDto {id, name, bucket: 1|2|3, active, stoppedOn: string|null, items: ExpenseItemDto[]}`.
- `ExpenseItemOption {id, name, categoryId, categoryName, bucket}` (active items in active categories).
- Routes, all under `/setup`:
  - `GET /expense-categories?page&pageSize` returns `Page<ExpenseCategoryDto>`. Needs `expenses.view`, `expenses.setup` or `commitments.view`.
  - `GET /expense-items/options` returns `ExpenseItemOption[]`. Needs `expenses.view`, `expenses.setup`, `commitments.view` or `commitments.manage`.
  - `POST /expense-categories {name, bucket}` returns `{id}`. `PUT /expense-categories/{id} {name, bucket}` returns `{id}`.
  - `POST /expense-categories/{id}/stop {}` and `/restore {}` return `{id}`.
  - `POST /expense-categories/{id}/items {name}` returns `{id}`. `PUT /expense-items/{id} {name}` returns `{id}`.
  - `POST /expense-items/{id}/stop {}` and `/restore {}` return `{id}`.
  - Every write needs `expenses.setup`. Names are 1–100 characters and unique, case-insensitive: category names within the organization, item names within their category. Reasons are automatic. Changes go to the change log with section `"expenses"`.

### C4. Scheduled expenses and savings (WP-S; the routes stay `/setup/recurring`)
- `RecurrenceFrequency`: 1 = Daily (legacy, read only), 2 = Weekly, 3 = Monthly, 4 = Yearly (new).
- `SaveRecurring` gains three optional fields at the end: `expenseItemId: string|null`, `note: string|null` (0–200 characters), `month: number|null` (1–12, yearly only).
- Cost kind: `expenseItemId` is required and must be an active item. The server derives the name from the item and the bucket from the item's category, and ignores `category`. Savings kind: `name` is required, and `expenseItemId` and `category` must be null.
- New saves: Daily is refused. Savings may only be Weekly or Monthly. Yearly needs `month` plus `day` 1–28 or `lastDay`.
- A start date earlier than the first day of the business date's month is refused, on create and when a start date changes.
- `RecurringDto` gains `expenseItemId, expenseItemName, bucket: 1|2|3|null, note, month` at the end. `category` stays for legacy rows.
- Stopping still needs a typed reason.

### C5. Investment (WP-S stores it, WP-X adds "come back")
- `InvestmentEntryDto {id, date, description, amount, recordedBy, recordedAt}`.
- `GET /setup/vehicles/{id}/investment` returns `{vehicleId, totalInvested, returned: number|null, percentPaidOff: number|null, entries: InvestmentEntryDto[]}`. It needs `invest.view`. `returned` and `percentPaidOff` stay null until WP-X.
- `POST /setup/vehicles/{id}/investment {date, description, amount}` returns `{id}`. `PUT /setup/investment/{entryId} {date, description, amount}` and `DELETE /setup/investment/{entryId}` also exist. All three need `invest.manage`.
- Investment is never counted as money out.

### C6. Vehicle report v2 (WP-X, revenue branch)
- `GET /setup/vehicles/{id}/report` keeps its query parameters. Response: `{vehicleId, from, through, moneyIn, target, repairs, charges, loans, moneyOut, net, savings, afterSavings, costs, postings: PostingDto[]}`.
- `costs` equals `moneyOut` and is kept for Phase 1 web. `PostingDto` gains `bucket` at the end.
- `net = moneyIn − moneyOut` and `afterSavings = net − savings`.

### C7. Typed reasons in four places only (addendum section 2)
Keep the automatic reason. `SaveCompany.Reason`, `CompanyLifecycleRequest.Reason`, `SaveVehicle.Reason`, `VehicleLifecycleRequest.Reason`, `VehicleRestoreRequest.Reason` and `SaveRecurring.Reason` become optional (`string?`, default null). When the reason is null or blank, the server writes an automatic reason, for example "Renamed company A to B", "Vehicle KDA 482M left the fleet on 2026-09-30" or "Changed the amount of Parking". A provided reason is still accepted (1–500 characters).

A typed reason stays required for: stopping a scheduled item (`StopRecurring.Reason`), removing access (person deactivation), and, later, deleting a petty cash entry and sending an entry back. The web shows a reason field only in those places.

## Work packages

The complexity target is written as input size, where P = people, V = vehicles, D = days in range, I = scheduled items, O = occurrences in range and H = history rows.

| WP | Branch / worktree | Goal | Depends on |
|---|---|---|---|
| WP-0 | all | Compile fixes (Access.cs; stray `)` in SetupRepository.cs), baselines, this plan | – (done by lead) |
| WP-A | access | Access and auth API fixes | WP-0 |
| WP-S | settings | Expense catalog, scheduled-item rework, investment storage, preference and partial-settings integrity | WP-0 |
| WP-R | revenue | Revenue API correctness and complexity (C2) | WP-0 |
| WP-WS | settings | Web: expense categories, scheduled editor, investment tab, change log diff, business date, "say why", proxy allowlist | contracts C1, C3–C5 |
| WP-M | revenue | Mobile: revenue tab (week detail, day list with one-tap capture, capture sheet), durable offline queue, business date, revenue home cards, offline PIN tries follow the organization's policy | contract C2 |
| WP-WR | revenue | Web: revenue week grid, vehicle week detail, capture dialog, revenue dashboard cards | C2; starts when a slot frees |
| WP-X | revenue (after merging settings into revenue) | Vehicle report v2 and investment "come back" | WP-S, WP-R merged |
| WP-I | lead | Merges access → settings → revenue, conflict resolution, migration snapshot check | WP-A, WP-S, WP-R |
| WP-V | revenue | Verification by three agents that wrote none of the code (API, web, mobile), a Phase 1 contract test, and one end-to-end pass | all |

Dependency graph: `WP-0 → {WP-A, WP-S, WP-R, WP-WS, WP-M} → WP-I → {WP-WR (can start earlier), WP-X} → WP-V`

### WP-A: access (API)
1. **One source for role permissions** (priority 1). Resolve role defaults only from `PermissionCatalog.RolePermissions`, in `OrganizationRepository.Permissions` and `AuthService.IssueTokens`. `EnsureRoles` stops writing `RolePermission` rows. The table stays (dropping it is deferred). Test: an extra or missing `RolePermissions` row changes neither the token nor request-time permissions.
2. Rename the catalog group and labels to "Scheduled expenses and savings". Diff the role defaults against the `ROLES` list in Web v2.8 and report the differences; do not change them silently.
3. **Role granting** (addendum section 2). Prove and test that a non-Owner may give only a role whose defaults all sit inside their own permissions, and that only an Owner may give Owner, both on create and on a role change.
4. **Say why** (C1), and leave the companies outside the editor's view untouched. Port the three tests from `phase2/access-foundation` (fix that branch's syntax error).
5. Wrong-PIN policy: prove the 3–10 tries and 1–60 minute bounds, and that an email reset lifts the pause.
6. **LoadPeople complexity**. Today every people call loads six whole tables and scans them per person, which is O(P·(P+R+O+S)). Target: `List` filters and pages in SQL and loads only the page's related rows, O(pageSize) plus a count. `Get`, `Save`, `SetActive` and `SignOut` load one person. Evidence: a command-counting interceptor test.
7. Memoize `Permissions(userId)` per request. It is called twice per setup call today.
8. Reads run without a serializable transaction and without `SaveChanges`. `Roles()` (which may create roles) stays on the write path. Grep every `Read`/`ReadAny` caller to confirm none of them writes.
9. Send the verification email **after** commit and outside `AuthGate`. On a send failure after commit: log it and consume the undelivered code so the cooldown does not block a retry. Test: a failed commit sends nothing, and the gate is not held during delivery.
10. Integrity migration `20260929200000_AccessIntegrity`: unique `PersonRoles(OrganizationId, UserId)` and a filtered unique `Memberships(UserId) WHERE Active = 1`, with a reversible `Down`.
11. `AddOpenApi()` and `MapOpenApi()` in Development and Testing only.

Owns: `Domain/Access.cs`, `Application/{AccessContracts,AccessUseCases,AuthService,OrganizationPort}.cs`, `Api/AuthEndpoints.cs`, `Api/SetupEndpoints.cs` (the `WithSetupErrors` block and people routes only), `Infrastructure/{OrganizationRepository,UserProvisioning,Security,OrganizationModel,AuthDb}.cs`, `Infrastructure/Setup/SetupExecution.cs`, `Program.cs`, the new migration and snapshot, and `tests/api/{AccessAndSetupTests,AccessLifecycleTests,AuthTests,ChangeLogAndScopeTests,DomainRuleTests,AuthFactory}.cs` plus new test files.

### WP-S: settings (API)
C3, C4 and C5 storage, plus:
- Preference writes refuse or clear overrides the organization does not allow (Security review, High).
- Partial organization-settings payloads must not reset omitted fields (Integrity review, Medium-high).
- Migration `20260929210000_ExpenseCatalogAndInvestment`: new tables, new nullable version columns (`ExpenseItemId`, `Bucket`, `Note`, `Month`), and a derived `Bucket` backfill for legacy versions; reversible.
- Seed expense categories and items in the demo, following the Web v2.8 `EXPENSE_CATS` and `EXPENSE_ITEMS`.
- The vehicle report keeps compiling with minimal change; WP-X reworks it.
- Complexity: `IsDue` for yearly is O(1). Options lists are O(items) with one query.

Owns: `Domain/Setup/*`, `Application/Setup/*`, `Infrastructure/Setup/{SetupModel,SetupRepository}.cs`, `Infrastructure/DemoSeed.cs`, `Api/SetupEndpoints.cs` (new routes appended at the end of `MapSetup` only), `Api/OrganizationEndpoints.cs`, `Domain/Organization.cs`, its migration and snapshot, and `tests/api/{RecurringCrudTests,OrganizationSettingsTests,DemoSeedTests,AppearanceTests}.cs` plus new files.

### WP-R: revenue (API)
C2, plus:
- `earliestMissing` computed from per-vehicle aggregates (min, max and count of dates), falling back to that vehicle's dates only when there is a gap. That is O(V) rows instead of O(V·D), and `Save` becomes O(1) instead of O(D).
- Assumption A3.
- Offline-replay idempotency tests, including two clerks capturing the same day at once.

Owns: `Domain/Revenue.cs`, `Application/{RevenueContracts,RevenueUseCases}.cs`, `Api/RevenueEndpoints.cs`, `Infrastructure/{RevenueRepository,RevenueModel}.cs`, and `tests/api/RevenueTests.cs` plus new files.

### WP-WS: settings (web)
Owns:
- `apps/web/components/setup/*`, `RecurringEditor.tsx`, `recurringPresentation.ts`, `OrganizationSettingsView.tsx`, `PreferencesView.tsx`, `PeopleAccessView.tsx`
- `AppShell.tsx` (the nav array and view switch for setup views only; it must not touch `RevenueModule` or the dashboard cards)
- `lib/types.ts`, `lib/format.ts`, `app/api/setup/[...path]/route.ts` (the allowlist adds `revenue`, `expense-categories`, `expense-items` and `investment`)
- `apps/web/tests/*`

Tasks: the expense categories page; the scheduled editor (C4); the investment tab (C5); a change log with field-by-field before and after side by side; a paged history ("Load more", not streaming every page); every "today" taken from the appearance `businessDate`; and the 403 `detail` shown in PeopleAccessView.

### WP-M: revenue (mobile)
Owns `apps/mobile/**`.
- Durable offline queue: one small SecureStore entry per capture plus an index. Drain it in date order per vehicle.
- On a 409, keep the entry and show the conflict. Nothing is dropped except on a 200 or a user's explicit discard.
- Revenue home cards come from `/setup/revenue/dashboard`.
- Offline PIN tries use the organization's threshold and minutes, stored with the person.
- Tests use Jest with the existing `fakeApi`.

### WP-WR: revenue (web)
Builds on the pushed `apps/web/components/RevenuePage.tsx`. Owns it, the revenue and dashboard-card sections of `AppShell.tsx` (after WP-WS merges), and `apps/web/tests/Revenue*.test.tsx`. Tasks:
- C2 conflict handling (409 with `current`) and version on corrections.
- The earliest-missing-first rule, and moving to the next missing vehicle after a save.
- The business date.
- The vehicle week detail: expected, actual, difference, and a bar for each day.
- A match with the Web v2.8 week grid.
- Revenue dashboard cards, with a "connect revenue first" state for the other cards.

## Remote activity
Another session pushes to `origin/revenue` (3 commits at 22:44–22:49 on 2026-09-29). The lead fetches before each integration step and before briefing each agent, and fast-forwards worktrees (with autostash) when a remote moves.

### WP-X: revenue (API, after WP-I)
C6 and C5's `returned` and `percentPaidOff`.
- The report posts due dates arithmetically per version, O(I·O) instead of O(I·D).
- `returned` is the net contribution since the vehicle joined.

## File-ownership rules
- At any moment, one agent owns each file. Agents on the same worktree own disjoint files.
- `Api/SetupEndpoints.cs` is split by region (WP-A: `WithSetupErrors` and people; WP-S: appended routes). `AppShell.tsx` is split by region and sequenced (WP-WS, then WP-WR).
- Migrations: only WP-A (on access) and WP-S (on settings) add one, with IDs ordered access < settings. The lead reconciles `AuthDbModelSnapshot.cs` during merges and checks it with `dotnet ef migrations has-pending-model-changes` (or a model-diff test).

## Checks (defined before implementation)
1. API: `dotnet build` with 0 errors, and `dotnet test tests/api` all green except the SQL Server category, which needs `SQLSERVER_TEST_CONNECTION` (recorded as environment-blocked).
2. Web: `npm run typecheck -w @xcode/web`, `npm run test -w @xcode/web` and `npx eslint apps/web`.
3. Mobile: `npm run typecheck -w @xcode/mobile` and `npm run test -w @xcode/mobile`.
4. Contract: a new test calls every Phase 1 endpoint (`/auth/*`, `/auth/session`, `/setup/appearance`, `/setup/access/catalog`) and asserts the develop-era JSON property names and types. OpenAPI is served in Testing.
5. Every Blocker, High and logic-gap fix has a test that fails without the fix. The agent states how they showed this: the test was run before the fix, or the reasoning.
6. Complexity claims come with query counts, rows loaded or a complexity argument.
7. End to end: sign in, capture revenue (web and phone, including an offline replay and a conflict), and check the dashboard numbers, a scheduled item with an expense item, and the vehicle report.

## Standing instructions added by the user mid-run
- When a branch's work is done: commit, push, and open a PR into `develop` (same pattern as PRs #1–#3). Author: Benson-Kim (`bensonkimkam@gmail.com`). No Co-authored-by or other attribution anywhere.
- Commits referencing another user are to be rewritten to benson-kim. Checked on 2026-09-29: all 46 commits use `bensonkimkam@gmail.com` ("Benson" or "Benson Kimathi"), and the 3 `GitHub` committers are PR merge commits. So none reference another user and no rewrite or force push is needed.
- If time allows: fetch the Codex reviews on each PR. Fix every finding, and every similar code smell across the codebase, not only the flagged lines. Then push and verify.
- The final subagent tasks: open a browser and visit every page and workflow on web (desktop and responsive widths) and on mobile. Take screenshots and check each against the designs (Web v2.8 and Mobile), fixing anything that looks wrong or improving on the design.
- If the context grows large: compact, update this Status section, and continue in a new session from this file with the same instructions.
- Note: an earlier commit attempt made before this instruction was blocked by the permission check. Until a commit succeeds, all work lives uncommitted in the worktrees, and integration moves between worktrees as `git diff` / `git apply` patches.

## Status (update after every stage)
- [x] WP-0: compile fixes applied in the three worktrees (not yet committed). Baselines are in `xcode-wt/baseline-*.txt`.
- [ ] Wave 1: WP-A, WP-S, WP-R, WP-WS, WP-M
  - The revenue worktree was fast-forwarded to origin/revenue a9d88cf (3 commits pushed by another session).
  - **WP-R done**: 93 passed and 6 failed of 99. The failures are 2 SQL Server tests (environment) plus AccessLifecycleTests ×2, AppearanceTests.LogoUploads and AuthTests.Reprovisioning, all outside revenue and pre-existing. All 15 revenue tests pass.
    - Fixed: earliestMissing from full history, canEdit after the gap, 409 with `current`, 400 with `earliestMissing`, the past-day-only edit flag, an identical replay returning 200, the vehicleId filter, the grid excluding inactive vehicles, mid-week normalization, blank note → null, and a race test giving 409.
    - Follow-ups sent: dashboard masking by permission, and week company options.
  - Change-log sequence contention: `Organization.SettingsVersion` is bumped on every write, so concurrent writes collide (a deadlock on SQL Server). Sent to WP-A as task 13 (a retry in UnitOfWork).
  - **WP-A done and committed** on access (314b4fb, 8a1d4f0), pushed, **PR #4** into develop. API tests: 107 passed, 2 failed (SQL Server environment only).
  - **WP-WS done** (uncommitted in the settings worktree): 83 of 83 web tests, typecheck and lint clean. Includes C7 on the web: reasons removed except for stopping a scheduled item and removing access.
  - WP-WR (web revenue) launched on the revenue worktree.
  - Next: when WP-S finishes, commit settings, merge access into settings (resolve the snapshot and SetupEndpoints conflicts), run the checks, push, and open the PR. Then merge settings into revenue.

- **Settings committed and pushed:** 6d8c2bd, c8aa1dd, 3471615, 9b22352, then merge 9707033 (access into settings) and 71e15c1 (lockout fields in appearance). **PR #5**. API tests: 143 passed, 2 failed (SQL Server only). The local `settings` ref is NOT moved, because the main folder holds the user's work. Use `origin/settings`.
- **Codex round 1 on PR #4:** three P1s (the permission memo surviving a retry, stored lockout values outside the bounds, pause enumeration). Sent to WP-A round 2, codebase-wide. PR #5's Codex review was still running.
- WP-S follow-up: the N+1 in recurring save and stop (settings worktree).
- Pending: WP-WR (revenue web). Then commit revenue (WP-R, WP-M, WP-WR), merge settings into revenue, WP-X (report v2 and investment returned), the mobile lockout follow-up, verification, and the screenshot pass.

- **Round 2:**
  - Codex fixes committed and pushed. Access a841202 (PR #4, re-review requested) holds 3 P1s plus 2 more account-existence leaks. Settings dc9ad9e (PR #5, re-review requested) holds calendarDate, activeAmount, invest.view read-only vehicles and the vehicle picker rule.
  - Revenue: merges 80d2264 and cfed27b (settings into revenue), plus 207291e. Not pushed yet. All green: API 176 passed and 2 failed of 178 (the 2 are SQL Server), web 111/111, mobile 40/40, typecheck and eslint clean.
  - Running: WP-X (report v2 and investment returned, API and web) and the WP-M follow-up (offline lockout policy, wording, 503 message).
- **Verification setup:**
  - SQL Server is at localhost,1433 (sqlcmd available). Use throwaway databases only; never the user's `XCode` database.
  - Browsers: Playwright's Chromium is cached in `%LOCALAPPDATA%/ms-playwright` and Edge is installed. Use `npx -y playwright` in a scratch folder with `channel: "msedge"`.
  - The design HTML files can be opened in the same browser for side-by-side screenshots.

### Decisions for the user (collected)
- D1. Legacy cost category → bucket mapping (A2).
- D2. `EditedRecords` counts records for days in the period, while the design counts edits made in the period. Counting edits needs the business date of each edit, which isn't stored.
- D3. Rounding: cells are shown to 2 dp, while the prototype rounds each day to whole KES.
- D4. Vehicle lifecycle and revenue:
  - A leave date in the past hides revenue already recorded.
  - Moving the join date later hides earlier records.
  - Restoring a vehicle turns its away days into missing days that block capture.
- D5. An identical replay returns 200 even when the person could no longer make that change, and 409 is checked before 403 (both accepted for now).
- D6. `AllowPinSignIn` is stored but not enforced, and PIN is the only sign-in method.
- D7. How old mobile offline access may be before it is refused (Security review, High).
- D8. Unsent phone captures are keyed by phone number and survive Switch user; they stay on the phone until that person signs in again. The alternative is a warning plus an explicit discard.
- D9. Weeks are cached only in memory on the phone. After a cold start with no network, there is nothing to capture against. Persisting the vehicle list means caching finance data on the device (Safety SAFE-09).
- D10. Align the role default lists with Web v2.8? The Office admin has 5 extra permissions, and the design's Owner includes dash.float and pettycash.spend.

### Progress
- **WP-M done** (uncommitted, revenue worktree): 40 of 40 mobile tests, shared 22 of 22, eslint clean, mobile typecheck clean.
- **Environment:** the revenue worktree's `node_modules` is now a junction to `xcode-wt/nm-rev`, built by `xcode-wt/nm-build.cjs`, so that `@xcode/shared` resolves to the worktree's own packages/shared. Do the same for any worktree whose shared package differs from the main folder's.
- **Contract gap:** the phone needs `lockoutThreshold` and `lockoutMinutes` in `/setup/appearance`. Asked of WP-S, with a mobile follow-up after the merge.
- [ ] WP-I merges
- [ ] WP-WR, WP-X
- [ ] WP-V verification and the final report
