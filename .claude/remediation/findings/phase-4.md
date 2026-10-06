# Phase 4 — verified findings (verified 2026-10-06 13:40-14:15 +03:00, against working tree on fix/format)

How to read: every "Now" was read from the working tree (not HEAD) while the Phase 3 session was still editing it. States: STILL PRESENT / PARTLY ADDRESSED / FIXED / CHANGED SHAPE / NOT REPRODUCIBLE.
Paths are repo-relative. "(volatile)" = Phase 3 is editing it; re-read before trusting line numbers. Audit refs: scalability #n, operability #n, security Mn/Ln (the morning reports).
Nothing was built or run. Anything marked "verify" is unexecuted. Tally at the end of the file. DECISION NEEDED marks choices the implementer must make explicitly.

## 0. Read first — constraints that apply to every item
- Phase 3 snapshot (volatile).
  - `apps/api/Program.cs` `OnTokenValidated` has NO cache now and `AddMemoryCache()` is absent. A read at ~13:35 showed a 30 s `IMemoryCache` (`session:{id}:{version}:{device}`); it was gone by 13:44.
  - `tests/api/OperabilityTests.cs` (untracked) still has `AuthValidationCachesPerSession` (expects fewer DB commands on the 2nd request) and `RevokedUserIsRejectedAfterCacheExpiry`/`CacheDoesNotSurviveDeviceRevocation` (clear `IMemoryCache`), so Phase 3 is mid-flight. `/health/ready` filters on tag "ready" but `AddHealthChecks()` registers no check yet.
  - Phase 4 must register its own cache (`AddMemoryCache()` is idempotent), use its own key prefix (e.g. `dash:`), and never assume Phase 3's cache exists.
- Phase 3 pieces already in the tree that Phase 4 must respect.
  - `EnableRetryOnFailure(3, 5s)` in `AddDbContext`: a user transaction must run inside `db.Database.CreateExecutionStrategy().ExecuteAsync` (as `UnitOfWork.Execute`, `apps/api/Infrastructure/OrganizationRepository.cs:58-81`, and `AuthEndpoints.Run` do); never populate caches inside the retried lambda.
  - `X-Request-ID` middleware (`context.Items["RequestId"]`, ProblemDetails `requestId`); web `withRetry` (`apps/web/lib/data/retry.ts`: 1 s/3 s delays on TypeError/503/status 0) and AbortController in `useResource`/`useStreamedList`.
  - Proxy `logProxyError` + `requestId` in 503 bodies; mobile `reach()` 15 s timeout (`apps/mobile/src/lib/api.ts:59-77`).
- Additive contracts only.
  - `tests/api/Phase1ContractTests.cs:12-17`: clients already in people's hands read raw JSON; a renamed/removed/retyped property or changed status fails ("New properties are fine").
  - `Page<T>` must keep numeric `pageNumber/pageSize/total` (`Phase1.Page` :52-58), including for `history?page=1&pageSize=25` and `history?pageSize=3` (:563-573). Legacy `page`/`pageSize` must keep working.
  - CLAUDE.md: no incompatible contract without migrating all callers (web AND mobile).
- Tests run on SQLite in-memory (`tests/api/AuthFactory.cs:149,163`): it cannot sum decimals or compare/order instants (comments `apps/api/Infrastructure/Setup/SetupRepository.cs:247,428`; `SetupModel.cs:81-85`). Spike any aggregate on EF 10.0.12 SQLite first.
  - Only `tests/api/SqlServerTests.cs` (category SqlServer, env `SQLSERVER_TEST_CONNECTION`) touches real SQL Server, and it only applies migrations.
- Migrations: `MigrationSnapshotTests.TheSnapshotMatchesTheModel` and `SetupMigrationSnapshotTests.TheMigrationSnapshotMatchesTheModel` fail on any un-migrated model/index change.
  - Every change needs a new migration + regenerated `AuthDbModelSnapshot.cs`/Designer; never edit existing migrations; raw SQL only when justified (CLAUDE.md). Follow `NormalizeSecurityPolicy.ClampSql` (public const SQL executed by a SQLite test, `MigrationSnapshotTests.cs:36-55`).
- Tests construct internals directly: `RevenueComplexityTests.Measure` (`tests/api/RevenueComplexityTests.cs:89-112`) does `new RevenueRepository(db, organizations, new UnitOfWork(...), clock)`, `new OrganizationRepository(db, resolvers)`, `new SetupActor(orgId, userId, today, true, [], [], "complexity", perms)`.
  - New ctor params break them: add optional trailing params or update deliberately; prefer a decorator for caches.
- Reads open no transaction: `PeopleQueryCostTests.cs:171-175` asserts `Transactions == 0` for `/setup/people, /access/catalog, /access/scope-options, /companies, /vehicles, /recurring, /history`.
- Tests write behind the app's back (`RevenueTestData.Records/SetBusinessDate/Vehicle/Grant/Deny/ScopeToCompany`, `app.WithDb`), so application-level invalidation hooks never run for them.
  - Worst case: `RevenueCaptureTests.DashboardEditsCountOnlyTheVehiclesActiveDaysLikeEveryOtherFigure` (:367-388) calls Dashboard, then `fleetVehicle.Retire(...)` + `SaveChanges` directly, then Dashboard again expecting new figures.
- Query-count tests compare consecutive requests.
  - `VehicleReportTests.TheReportReadsTheSameNumberOfTimes...` (:196-224) asserts equal `(Reads, Rows)` across two calls; its first Measure is the first authenticated request (SignIn only hits /auth).
  - `RecurringQueryCostTests.SavingAndStoppingReadTheSameNumberOfTimes...` (:33-56). A cache that makes request 1 differ from request 2 must be handled deliberately (warm first), never by loosening assertions.
- Full lists are load-bearing in the web UI: `CompaniesPage.add` duplicate check `rows.some` (`apps/web/components/setup/CompaniesPage.tsx:29-34`), `ExpenseCategoriesPage.clash` (:67-73), `RecurringPage` `items.find(editing)` (:42), `VehiclesPage` `rows.find` (:85-89).
  - `useStreamedList` must keep delivering complete lists; do not turn it into infinite scroll.
- Mobile offline capture needs every vehicle: `apps/mobile/src/revenue/week.ts:18-31,89-90` writes the capture list from the whole current-week response; offline cold start reads it (:98-100).
- Exact-URL tests.
  - Web `RevenuePage.test.tsx:134` asserts the grid's GET list equals `["/api/setup/revenue"]`; `History.test.tsx:47,53` pin `page=` URLs.
  - Mobile `tests/fakeApi.ts` routes are exact path strings (`"setup/revenue"`, `"setup/revenue?weekStart=..&vehicleId=.."`, `"setup/revenue/dashboard?period=.."`).
  - Web `tests/setup.ts` only runs `cleanup`: a module-level fetch cache would leak between `it`s unless reset in `afterEach`.
- Tooling: `apps/web/package.json` has no virtualization or SWR/TanStack dependency (adding one changes the lockfile). `npm run lint` enforces `local/import-order` (installed, then `@xcode/`, then relative) and react-hooks rules (`eslint.config.mjs`).
- Preserve (CLAUDE.md strengths): tenant filters (`OrganizationModel.cs:12-16` `Tenant()`; no `IgnoreQueryFilters` in new read paths; caches keyed by org), pageSize <= 100 (`SetupContracts.cs:97-100`), AsNoTracking reads, RevenueRecord invariants and idempotent replay (`RevenueUseCases.cs:50-51`).

## Item 1 — Weekly revenue grid: bound rows, no cartesian Include, separate totals, keep web/mobile semantics
### 1a. Unpaged grid and cartesian Include (scalability #1; audit cited RevenueEndpoints.cs:35, RevenueRepository.cs:16-70)
- Audit: no paging/cap; V x 7 cells x 9 fields; one Include of Targets+AwayPeriods without AsSplitQuery; web and mobile render everything.
- Now: STILL PRESENT.
  - `apps/api/Api/RevenueEndpoints.cs:38-41` takes only `weekStart/companyId/vehicleId`.
  - `RevenueRepository.Week` (`apps/api/Infrastructure/RevenueRepository.cs:33-38`): `Include(Targets).Include(AwayPeriods).AsNoTracking().OrderBy(Registration).ToListAsync`, no Take. `grep AsSplitQuery|QuerySplittingBehavior` over apps/api finds nothing.
  - `BuildWeek` (:215-247) emits 7 `RevenueCellDto` (9 fields, `RevenueContracts.cs:8-17`) per vehicle. About 6-8 repository commands per call (FirstDayOfWeek, vehicles, companies :43-53, records :54-57, companyNames :60-62, EarliestMissing 1-2).
- Do (contract; DECISION NEEDED, it affects released phones/tabs):
  - Add optional `page`/`pageSize` (reuse `SetupPagination.Validate`) and additive fields on `RevenueWeekDto` (`RevenueContracts.cs:52-61`): `pageNumber`, `pageSize`, `totalVehicles` plus the aggregates below.
  - When the params are absent: either the legacy full list under a hard server cap with a `truncated` flag, or page 1. Keep every existing field and do not drop null fields (web `entry.amount !== null` `RevenuePage.tsx:98`; mobile `cell.amount ?? 0`).
- Do (aggregates over ALL visible vehicles in the company filter, not just the page):
  - Week `totalAmount/totalExpected/percent`. BuildWeek (:238-246) sums UNROUNDED values then rounds once: keep that, do not sum per-vehicle rounded values. Pinned by `RevenueTests.RevenueCaptureRequiresOrderedBackfill...` (2700/3000/90), `VehicleAwayTests.cs:69`, `VehicleReportTests.cs:106-108`.
  - Per-day totals (web derives `dayTotals` from rows, `RevenuePage.tsx:152-158`); first gap (`first`, :160-166); next vehicle still missing a day (web `nextMissing` :76-81 used in `advance` :209; mobile `nextTarget` `RevenueScreen.tsx:153-177`, `earliest` banner :405-411, default-day effect :285-296).
  - Either ship `dayTotals[7]` and `firstGap{vehicleId,date}` in the response, or keep those features working by loading all pages.
  - One `Aggregate(from, through, today)` can serve week and dashboard if it keeps `counted = date < today || record exists` (week sums include records after a moved-back business date; the dashboard window stops at today).
- Do (query):
  - Bounded page ordered by Registration (unique index, `SetupModel.cs:23`) + `AsSplitQuery()`, or filtered includes (Targets `EffectiveFrom <= through`, AwayPeriods overlapping the week).
  - Pitfall: `EarliestMissing` reads `vehicle.AwayPeriods` over the vehicle's whole history (`RevenueRepository.cs:166`); never pass it vehicles whose AwayPeriods were filtered to the week.
  - Keep `FleetVehicle.ActiveOn/TargetOn` (`apps/api/Domain/Setup/FleetVehicle.cs:48,113-118`) as the single source of truth; compute `TargetOn(date)` once per day (BuildWeek :233 and `RevenueCellDto.For` :33 each call it).
- Do (callers):
  - Web `useResource<RevenueWeek>(query)` (`RevenuePage.tsx:136`) -> a paged loader that merges pages and keeps page-1 aggregates and `companies` (:143,:241).
  - Mobile `loadWeek` (`week.ts:74-103`) must still build the whole-fleet capture list and the 8-week in-memory copies (`KEEP=8` :7).
  - `vehicleId` detail requests stay unpaged: web `vehicleWeekPath` (:54), mobile `RevenueScreen.tsx:840`, queue `savedNow` (`queue.ts:264-276`); 404 via `AnyAsync` (`RevenueRepository.cs:39-40`).
- Pins: `RevenueCaptureTests` (`EarliestMissingComesFromTheWholeHistory...`, `TheGridListsOnlyVehiclesActiveThatWeek...`, `TheVehicleFilterServesTheDetailAndHonoursDataScope`, `WeeksStartOnTheOrganizationsFirstDay...`, `CompanyOptionsKeepArchivedCompanies...`); `VehicleAwayTests.AwayDaysAreNeitherExpectedNorMissing...`; `RevenueComplexityTests.WeekAndDashboardIssueTheSameCommandsWhateverTheFleetSizeAndHistory` (:44-61, `Reads <= 10*12+10`); web `RevenuePage.test.tsx` (19 tests); mobile `revenue.test.tsx`, `captureList.test.ts`, `shell.test.tsx`, `queue.test.ts`.
- Add: page 2 content/order; totals identical across pages and equal to the unpaged result; company filter + page; scoped actor + page; `vehicleId` ignores paging; command count independent of V (extend RevenueComplexityTests with V=100 vs 500, bound `Reads` by page size); a Phase1-style raw-JSON test that old fields remain; web/mobile multi-page merge and server-aggregate tests.
### 1b. Whole-row RevenueRecord reads in Week (scalability #10, first half)
- Now: STILL PRESENT. `RevenueRepository.cs:54-57` materializes full `RevenueRecord` entities (CapturedAt/By, UpdatedAt/By are unused by the grid); indexes unchanged (`RevenueModel.cs:17-18`).
- Do: project `(VehicleId, BusinessDate, Amount, Reason, Note, CorrectedAfterDate, Version)`; `RevenueCellDto.For` (:20-36) needs only those. Small win; do it with 1a.
### 1c. EarliestMissing join and IN-list (scalability #11)
- Now: STILL PRESENT, but it is the deliberate "O(V) with fallback" design.
  - `RevenueRepository.cs:146-190`: one grouped query (V rows of First/Last/Count) plus per-holed-vehicle date loads; `ids.Contains` over every vehicle (:148,:195).
- Do:
  - With a bounded page `ids <= pageSize`, so the IN-list risk disappears for Week; the fleet-wide first gap still needs the O(V) aggregate.
  - A persisted `FirstMissingOn` watermark would have to be maintained in the Save transaction and on retire/restore/away/join-date edits: defer unless measurement demands it.
  - Verify with `ToQueryString()` how EF 10 SQL Server translates `Contains` over big lists (OPENJSON vs expanded parameters; SQL Server's 2,100-parameter limit). It affects Dashboard today (ids = all vehicles) and scoped actors' `CompanyIds/VehicleIds.Contains` (`RevenueRepository.cs:14`, `SetupRepository.cs:14-15`). Unverified.

## Item 2 — Dashboard: DB aggregation, short-lived org/period cache with correct invalidation
### 2a. Everything aggregated in memory (scalability #2; audit cited RevenueRepository.cs:75-125)
- Now: STILL PRESENT.
  - `RevenueRepository.Dashboard` (`RevenueRepository.cs:68-131`) loads all active vehicles with Include (:86-91) and every `RevenueRecord` entity in the window (`ids.Contains`, :93-95), builds a dictionary, then loops vehicle x day in C# (:104-127). Month = V x 31 records.
  - Web fires up to 2 dashboard calls per load (`AppShell.tsx:782-791`); mobile 1-2 per period change (`apps/mobile/src/shell/screens.tsx:178-196`); the page remounts on every navigation (`AppShell.tsx:480` `key={visit}`).
- Do (DB side): replace the entity load with aggregates over `RevenueRecords` joined to `FleetVehicle` using the exact active-day rule (`FleetVehicle.ActiveOn` + no `VehicleAwayPeriod` covering the date). Section 0's `DashboardEditsCount...` (a direct `Retire` leaving records on or after the leave date) proves records on non-active days must be excluded.
  - `capturedToday` = count of today's records on active vehicles; `edited` = count of `CorrectedAfterDate` records on active days in the window.
  - Per-vehicle recorded-day count (GroupBy VehicleId = V narrow rows): `missingDays = sum(activeDays(from..today-1) - recorded)`, `missingVehicles` = vehicles with a positive difference. activeDays is arithmetic over JoinedOn/LeftOn/AwayPeriods, no rows.
  - Revenue sum: SPIKE `Sum` of decimal on SQLite first (comments say unsupported). Fallbacks: a narrow `(VehicleId, Amount)` projection summed in memory (never entities), or an integer-cents `Sum`. NOT `double` (a day's amount has no upper limit, `apps/api/Domain/Revenue.cs:19-21`).
- Do (memory side): keep the per-day expected accumulation (`sum TargetOn(d)/7m`, one `decimal.Round(..,2)`, `Percent` from the unrounded values) because results are pinned (`WeeksStartOn...` 4142.86m, `RevenueTests` 2700/3000/90, `VehicleAwayTests.cs:69`, `AHugeRecord...` `int.MaxValue`).
  - Feed it only vehicle calendars plus a "has record today" flag, and sort Targets once per vehicle (`TargetOn` sorts per call, `FleetVehicle.cs:113-118`).
- Do (index, optional, needs a migration): `RevenueRecords (OrganizationId, BusinessDate) INCLUDE (VehicleId, Amount, CorrectedAfterDate)`; `RevenueModel.cs:18` has no INCLUDE today (scalability #10, second half).
- Pins: `RevenueDashboardCardTests` (per-card masking), `RevenueCaptureTests.DashboardFiguresAreShownOnlyToPeopleWhoMaySeeTheirCard` and `DashboardEditsCount...`, `RevenueComplexityTests` (:57-60 Commands equal, small vs large), web `RevenueDashboard.test.tsx` (:121 "never asks for the month twice"), mobile `appearance.test.tsx:93,133`.
### 2b. No dashboard cache (scalability #2 fix; #4 fix)
- Now: STILL PRESENT. No `IMemoryCache`/output cache/response cache anywhere in apps/api (grep); Phase 3's session cache is not in the tree (section 0).
- Do (shape):
  - Decorate `IRevenueRepository` (registered in `RevenueEndpoints.AddRevenue`, :9-14) so `RevenueComplexityTests` keeps constructing the plain repository.
  - Cache the UNMASKED `RevenueDashboardDto` and keep `RevenueUseCases.Visible` (:23-40) applied after the cache, so per-card masking is untouched.
  - Key = orgId + data version + `actor.Today` + period + companyId + scope key (AllCompanies, or hash of sorted CompanyIds+VehicleIds). Never share across orgs.
- Do (invalidation correct across replicas, no TTL needed for freshness): use `Organization.SettingsVersion` as the data version.
  - Every audited write bumps it in the same serializable transaction (`RevenueRepository.RecordChange` :205, `SetupRepository.RecordChange` :443-451, `Organization.cs:85-86`); idempotent replays write nothing (`RevenueUseCases.cs:50-51`).
  - `SetupExecution.Actor` already reads the Organization row for BusinessDate (`apps/api/Infrastructure/Setup/SetupExecution.cs:37`): select `SettingsVersion` in the same query (no extra round trip) and carry it on `SetupActor` as an optional trailing param (keeps `RevenueComplexityTests` compiling). Read the version BEFORE computing the data.
  - TTL (30-60 s) then only bounds memory; set `SizeLimit`, and compute once per key under concurrency (Lazy/SemaphoreSlim) to avoid stampedes.
- Callers: none to migrate (the `RevenueDashboardDto` contract is unchanged for web `AppShell` and mobile `screens.tsx`).
- Required test change (deliberate, not weakened): `DashboardEditsCount...` writes behind the cache. Do the retire through `POST /setup/vehicles/{id}/retire` (bumps the version) or clear the cache via the factory services. Direct-DB helper writes never bump the version.
- Add: a hit issues fewer commands (DatabaseProbe); revenue save, vehicle retire, business-date change and first-day-of-week change each invalidate; two scopes and two orgs never share an entry; masking per permission still applies on a hit.

## Item 3 — Change log: denormalize, index, keyset paging, avoid repeated COUNT, safe migrations
### 3a-c. Heavy OR-chain, missing indexes, OFFSET paging (scalability #3; audit cited SetupRepository.cs:280-310, SetupModel.cs:80)
- Now: STILL PRESENT (three findings).
  - `SetupRepository.History` (`apps/api/Infrastructure/Setup/SetupRepository.cs:280-306`): per-section OR chain with `vehicles.Contains`, `companies.Contains`, `completeItems` (:284, triple-nested NOT-Any), `people.Contains` and `revenueRecords.Contains(v.EntityId)` (:285,:298) against the largest table; `OrderByDescending(Version).Skip().Take()` (:300).
  - `OrganizationSettingsVersion` (`apps/api/Domain/Setup/OrganizationSettingsVersion.cs:12-23`) has no VehicleId/CompanyId; its only indexes are unique `(OrganizationId, Version)` and FK `(OrganizationId, ActorId)` (`SetupModel.cs:80`; `AuthDbModelSnapshot.cs:676-678`).
- Writers to change (4): `SetupRepository.RecordChange` (:443-451; `ISetupRepository.cs:45`), `RevenueRepository.RecordChange` (:202-210; `RevenueContracts.cs:121`), `AccessUseCases.RecordHistory` (:588-594), `OrganizationEndpoints.RecordChange` (:188-203).
  - `EntityId` per section: revenue = RevenueRecord.Id (not the vehicle), vehicles/investment = vehicle id, companies = company id, recurring = item id, people = person id, expenses = category/item id, settings/logo = organization id.
- Do (schema):
  - Add nullable `VehicleId` set at write (revenue: `RevenueUseCases.Save` already holds `vehicle`; vehicles/investment: the vehicle) via an optional trailing ctor param (`OrganizationSettingsVersion.cs:24-25`).
  - Do NOT denormalize CompanyId blindly: today visibility follows the CURRENT scope (`VisibleVehicles/VisibleCompanies`, :282-283), so a vehicle that changes company changes who sees its old rows; a frozen CompanyId changes that. Resolve company through the current FleetVehicle (index `(OrganizationId, CompanyId)`, snapshot :620): `VehicleId IN visibleVehicleIds`. DECISION NEEDED if a frozen company is wanted.
  - Recurring (`completeItems`) and people (`PeopleVisibility.People`) cannot use one VehicleId: keep their subqueries only for rows of those sections, or add a link table.
  - Branch on `actor.AllCompanies` in C# as `PeopleVisibility.People` does (`PeopleVisibility.cs:19-20`); today `actor.AllCompanies ||` sits inside the SQL predicate (:294; verify with `ToQueryString()`).
- Do (indexes): `(OrganizationId, Section, VehicleId)` and `(OrganizationId, OccurredAt)`. The audit said `(OrganizationId, Section, EntityId)`, but EntityId is the record id for revenue, so VehicleId is the useful column.
- Do (migration, safe): nullable columns -> backfill -> indexes.
  - EF cannot backfill: `ValidateSetupWrites` forbids Modified on `OrganizationSettingsVersion` (`SetupModel.cs:124-125`). Use raw SQL in the migration: revenue rows from `RevenueRecords` on `(OrganizationId, Id = EntityId)` (records are never deleted, `SetupModel.cs:126`); vehicles/investment `VehicleId = EntityId`.
  - Batch it on SQL Server (`suppressTransaction`), expose it as a `public const string` and test it on SQLite like `ClampSql`. Build indexes `ONLINE` only where the edition supports it.
- Do (keyset): `Version` is unique and monotonic per org (written from `Organization.SettingsVersion` in the same serializable transaction, `Organization.cs:85-86`, `OrganizationRepository.cs:58-81`).
  - Add optional `before=<version>` (composes with section/date/text filters); keep `page` for old clients; add `hasMore/nextBefore` additively. Web `useHistoryPages` (`HistoryPage.tsx:141-184`) migrates to it; mobile never calls `/setup/history` (grep of `apps/mobile/src`: none), so web (`HistoryPage`, `PeopleAccessView`) is the only caller set.
### 3d. COUNT on every page (audit: "useStreamedList repeats it once per page")
- Now: CHANGED SHAPE (client trigger) / server COUNT still runs per request (`SetupRepository.cs:305`).
  - Current web `HistoryPage` does not stream: first page, then explicit Load more (`HistoryPage.tsx:141-184`), so COUNT repeats per click. `PeopleAccessView.tsx:82-84` fires `history?pageSize=3` (COUNT included) on every People load for audit viewers.
  - Phase 1 web bundles still stream every page (`Phase1ContractTests.cs:562-563` comment) and read `total` each time.
- Do: do NOT null `total` on later pages (Phase 1 clients, `HistoryPage.tsx:154`, `Phase1.Page`).
  - Cache the count per (org, SettingsVersion, scope key, filter): cluster-safe because the version is read per request. And/or accept `includeTotal=false` for People's 3-row call.
  - `ChangeLogAndScopeTests.TheChangeLogIsNarrowedByItsFilters` (:239-259) pins `Total` semantics (narrowed total equals narrowed count; a day range equals all).
### 3e-g. Text filter, actor-name lookup, and audit #18's index worry (scalability #3 last bullets, #18)
- Now (3e): STILL PRESENT. Leading-wildcard `EF.Functions.Like` plus a correlated `Memberships.Any` (`SetupRepository.cs:341-343`); `Narrow` adds a Localizations query when a date filter is set (:317-318).
- Now (3f): STILL PRESENT, low. Actor name is a per-returned-row correlated subquery (:302; at most pageSize rows).
- Now (3g): NOT REPRODUCIBLE as an index problem. Memberships has PK `(OrganizationId, UserId)` and the global filter always adds OrganizationId, so the lookup is a PK seek (`OrganizationModel.cs:27`).
- Do: pre-resolve matching actor ids in one small query (or join on the PK) for 3e; batch actor names only if the query is touched anyway.
- Pins/tests: API `ChangeLogAndScopeTests` (:222-270), `PeopleHistoryTests` (:52,63), `InvestmentTests` (:51 owner, :148 clerk), `RevenueTests` (:106-115), `RevenueCaptureTests` (:179-186), `Phase1ContractTests` (:563-573), `PeopleQueryCostTests` (:171-175). Web `History.test.tsx` (:42-62: URL + "Showing 25 of 60 changes").
- Add: a scoped viewer sees revenue history only for visible vehicles (no such test exists for the revenue section today); backfill SQL on SQLite; command count independent of table size; `before=` returns the same rows as `page=`.

## Item 4 — HTTP/proxy: response compression, stream upstream responses, keep error/correlation handling
### 4a. No response compression (scalability #9)
- Now: STILL PRESENT. No `AddResponseCompression/UseResponseCompression` anywhere in apps/api (grep). `apps/web/next.config.ts` sets only security headers (no `compress` key, so Next's default applies on the browser leg).
- Do:
  - `AddResponseCompression` (Brotli + Gzip, add `application/problem+json`) and `UseResponseCompression` early (after forwarded headers/request-id, before endpoints).
  - `EnableForHttps` defaults to false and production `API_URL` must be HTTPS (`apps/web/app/api/body.ts:13-23`), so enable it deliberately. `/auth/*` bodies carry tokens (BREACH): compress only `/setup/*` (`UseWhen`). Node `fetch` negotiates and decodes automatically (verify), so the proxy needs no change for this leg.
  - Mobile calls the API directly (`apiUrl`, `apps/mobile/src/lib/api.ts:24-35`), so compression also reaches phones: keep Gzip enabled next to Brotli (React Native's fetch stacks reliably decode gzip; Brotli support there is unverified).
- Add: a test sending `Accept-Encoding: gzip` asserting `Content-Encoding`/`Vary` on `/setup/*` and none on `/auth/*` (the test HttpClient sends no Accept-Encoding, so existing tests are unaffected). Measure body size before/after for week, history, people.
### 4b. Proxy buffers the whole upstream body (scalability #9)
- Now: STILL PRESENT. `apps/web/app/api/setup/[...path]/route.ts:105` `const result = await response.text()`.
  - Only Content-Type (default application/json) and `Cache-Control: no-store` are copied (:106-113); 5xx -> generic 503 (:100-104) without cancelling the unread upstream body; `AbortSignal.timeout(15_000)` (:97).
- Do: `return new NextResponse(response.body, {status, headers})`.
  - Keep: 5xx -> `{status:"service_unavailable", requestId}` 503 + `no-store` (add `await response.body?.cancel()`), `X-Request-ID` upstream (:91), `logProxyError` (:115).
  - Add: echo `X-Request-ID` on proxied responses; never forward upstream `Content-Encoding/Content-Length/Transfer-Encoding` (undici already decoded); 204/304 have a null body.
- Pitfalls: the 15 s signal now also covers body streaming (a slow large body is cut mid-stream; split time-to-headers from idle timeout). An error after the Response is returned cannot become a 503: wrap the stream to call `logProxyError` and abort.
  - The auth route (`app/api/auth/[...path]/route.ts:49`) buffers tiny bodies on purpose; leave it.
- Pins: `apps/web/tests/SetupProxy.test.ts` (:23 forwards with token, :110 no empty body, :120 5xx -> 503 with request id, :131 unreachable -> 503 + log); mocks use `new Response(...)`, so streams work.
- Add: first chunk reaches the caller before the upstream stream closes; mid-stream failure is logged; no encoding header leaks.

## Item 5 — Formatting hot paths: memoize Intl by key, precompute weekly-day structures (on top of Phase 2 `createFormatter`)
### 5a. Intl objects built per call (scalability #12)
- Now: STILL PRESENT.
  - `packages/shared/src/dates.ts`: `dateParts` builds a new `Intl.DateTimeFormat` per call (:109-130); `safeTimeZone` builds one only to validate (:132-140); `formatCalendarDate` builds another for non-medium patterns (:142-154); `formatTimestamp` therefore builds three per timestamp (:172-185).
  - `packages/shared/src/format.ts` `kes()` calls `amount.toLocaleString(locale, opts)` per call (:38-47). `createFormatter` (:30-67) is built once per formats change (`apps/web/components/AppShell.tsx:298-301`, `apps/mobile/App.tsx:141`) but caches nothing.
- Hot callers: web `DayCell` aria-label per clickable cell `longDate(formats, date)` + `cellState` -> `kes` (`RevenuePage.tsx:477`; helpers `apps/web/components/revenueFormat.ts:18-27`) and `figure()` per amount; `HistoryPage` `display()`/`formatDateTime` per row and field (:41-47,:289); mobile `DayRow/WeekRow/DayBar` `formats.kes`. The cost for 7k cells is an estimate: measure.
- Do:
  - Module-level `Map` of immutable instances (allowed by Phase 2): `Intl.DateTimeFormat` keyed `locale|timeZone|variant`, `Intl.NumberFormat` keyed `locale|minFrac|maxFrac|useGrouping` (integer vs fractional amounts = two entries); negative-cache `safeTimeZone` (an invalid zone must keep falling back to the host zone); bound the map size.
  - Alternative: lazily create the two NumberFormats inside `createFormatter`. No module-level mutable config; `format.test.ts:54-74` pins instance independence. Invalid locale tags throw today from `toLocaleString`; keep, or test the chosen behavior.
- Pitfall (pre-existing, verify before touching): `formatDateOnly` passes the organization's time zone for a date-only string parsed at UTC midnight (`format.ts:61-62` -> `dates.ts:157-159`), so zones west of UTC would render the previous day; `formatDate` defaults to UTC to avoid this. Do not cement it into a cache key without a test.
- Tests: `packages/shared/tests/format.test.ts`, `dates.test.ts`, `apps/web/tests/format.test.ts`, mobile `format.test.ts`/`appearance.test.tsx:82-83`.
- Add: spy the `Intl` constructors and assert formatting N values constructs a small constant number; invalid time zone falls back; two formatters with different options never share output.
### 5b. Date arithmetic allocates per call (scalability #13)
- Now: STILL PRESENT. `shiftDate` runs `isDate` (new Date) then `calendarDate` (another) (`dates.ts:54-63,75,94-99`); `startOfWeek` = `weekdayIndex` + `shiftDate` (:104-105); `weekdayShortName/dayOfMonth` parse a Date per call (:77-92). Mobile `nextMissing` steps `shiftDate` per day per vehicle (`RevenueScreen.tsx:93-112`).
- Do: epoch-day integer math or memoize on the input string; per-week precomputed arrays (web `days` exists, `RevenuePage.tsx:151`; add `dayLabels`/`weekday`/`dayOfMonth` per week).
  - Never cache `Date` instances (callers mutate: `setUTCDate` in `shiftDate`); cache primitives. Server twin: `BuildWeek` can compute the 7 dates and `TargetOn` once.
### 5c. `revenuePeriodLabel` linear find (scalability #14)
- Now: STILL PRESENT, negligible. `packages/shared/src/revenue.ts:110-112` (3 entries; used by `VehiclesPage.tsx:623`, imported `AppShell.tsx:23`). Swap to a lookup while touching the file.

## Item 6 — Client caching/SWR with request dedupe and explicit invalidation after mutations (web)
### 6a. No cache or dedupe (scalability #15)
- Now: STILL PRESENT. `apps/web/lib/data/useResource.ts:10-43` fetches on mount and on path/version change with no cache and no in-flight sharing; `apiRequest` (`request.ts:19-47`) is a plain wrapper. `AppShell.tsx:480` remounts the page on every navigation, so everything refetches.
  - Duplicate fetches: dashboards (`AppShell.tsx:782-791`); `setup/recurring` streamed by `RecurringPage.tsx:30` and again in `VehicleRecurringCard` (`VehiclesPage.tsx:691`, filtered client-side at :694); `setup/companies` (`CompaniesPage.tsx:20`, `VehiclesPage.tsx:75`); roles/catalog (`PeopleAccessView.tsx:77-78`, AccessDialog `AppShell.tsx:906`); appearance (:295).
- Do (store): add it inside `apps/web/lib/data` (no new dependency needed): results + in-flight promises keyed by path; ref-counted abort (abort only when the last subscriber unmounts); `isValidating`; SWR return (cached data at once, `loading` only without data); `reload()` stays a forced refetch; do not cache errors.
  - Keep `withRetry` and `fetchWithSession`'s single-flight 401 refresh (`apps/web/lib/session.ts:6-24`).
- Do (invalidation): single choke point `apiRequest`: any successful non-GET invalidates by prefix. Safe default = everything under `setup/` (a vehicle save touches vehicles, companies' vehicleCount, recurring, revenue, history, dashboard; a revenue PUT touches revenue, dashboard, history; preferences/organization/logo touch `setup/appearance`).
  - 19 mutation call sites: PeopleAccessView :488,:530; RecurringEditor :433,:476,:498; PreferencesView :81; OrganizationSettingsView :246,:265,:298,:302; RevenuePage :695; VehiclesPage :307,:326,:370; VehicleInvestment :76; ExpenseCategoriesPage :86; CompaniesPage :37,:71,:89. Existing `reload()` calls stay.
  - MUST clear everything on session end/sign-out/user switch (`onSessionExpired`, `session.ts:44-47`): cached data is permission- and scope-specific per user.
- Tests: add `clearDataCache()` to `apps/web/tests/setup.ts` `afterEach`. `RevenueDashboard.test.tsx:121` and `RevenuePage.test.tsx:134` count fetches; `hooks.test.ts` covers retry/abort (keep green).
  - Add: dedupe (two mounts, one fetch), stale-then-fresh, invalidate-after-PUT, StrictMode double effect.
### 6b. No AbortController (scalability #15 last bullet; operability #11)
- Now: FIXED (Phase 3). `useResource.ts:16-33` and `useStreamedList.ts:34,70-73` abort on cleanup; `apiRequest` maps TypeError to `ApiError(...,0)` (`request.ts:29-33`).
- Not covered: `HistoryPage.useHistoryPages` and the `RevenuePage` `apiRequest` calls (:204,:415) have no signal.
### 6c. Mobile (note, not an audit finding)
- `apiGet` takes no signal (`apps/mobile/src/lib/api.ts:163-173`); `loadWeek` keeps 8 weeks in memory only as an offline fallback (`week.ts:7-8`). Optional.

## Item 7 — useStreamedList: bounded concurrency (3-4), batched setState, cancellation, ordering/error semantics
- Audit: sequential, unbounded, not cancellable, `[...items]` per page (scalability #5); a partial result looks complete and may loop (operability #11).
- Now (`apps/web/lib/data/useStreamedList.ts`):
  - 7a STILL PRESENT: strictly sequential `for (page=1;;page++)` (:40-59); termination trusts `total` or an empty page (:53).
  - 7b FIXED (Phase 3): cancellation (controller :34, `withRetry` per page :42-49, abort :70-73).
  - 7c STILL PRESENT: `setLoaded({items:[...items]})` per page (:56); no list row is memoized, so each page re-renders every row so far.
  - 7d PARTLY ADDRESSED: retry added; on failure `done:true` + `error` and the prefix stays (:60-68), but there is no `partial` flag (consumers show only a Banner, e.g. `CompaniesPage.tsx:105`; `DataTable failed` matters only when empty, `ui/table.tsx:76`).
  - 7e STILL PRESENT: default `pageSize = 25` (:20) against a server cap of 100, and COUNT + correlated counts per page (`SetupRepository.cs:29,78,172,384`, `AccessUseCases.cs:69`).
- Do:
  - Page 1 first (needs `total`), then pages 2..N through a pool of 3-4 workers, each through `withRetry` and the shared controller. Derive the page count from the echoed `Page.pageSize`, not the requested one.
  - Keep results per page and commit only the contiguous prefix (order and the shrinking `pendingRows` placeholders :86 stay as `Streaming.test.tsx` expects); one `setLoaded` per commit with a single concat, optionally throttled (rAF/~50 ms). The quadratic cost is probably the re-render of all rows after each page, not the array copy (measure).
  - Semantics: a page failing after retries aborts the pool, keeps the committed prefix, sets `error`, `done:true` and a new `partial:true`; de-duplicate by `id` on merge (offset paging under concurrent writes can repeat or skip a row); cap pages at ceil(total/pageSize); keep `reload()` (background refetch, swap when complete: `progressive` :35,54-57).
  - Consumers: Companies, Vehicles (+companies, +`VehicleRecurringCard`), Recurring, ExpenseCategories (pageSize 100), PeopleAccessView.
- Pitfalls:
  - `Streaming.test.tsx`'s mock ignores the requested `pageSize` (always serves 25 per page, echoes `pageSize: 25`, total 60). Changing the default pageSize passes only if the page count comes from the echoed size (verify); otherwise update the mock deliberately.
  - Server load: each page costs about 9 context queries (N1) + COUNT + page, so 4 concurrent pages quadruple per-user DB concurrency; do item 3's COUNT caching and N1 first or together.
  - Do not replace with "load more" (section 0, full lists).
- Tests to add (hook-level, `renderHook` like `hooks.test.ts`): max in-flight <= cap (counter in the fetch mock); a later page resolving first still renders in order; unmount aborts every in-flight page; failing page k keeps the prefix + `partial`; reload swaps only when complete; drift de-dupe.
  - Existing: `Streaming.test.tsx:30-48` (expected to pass unchanged if pages 2..N are requested right after page 1 renders, because its gates are released in request order; verify), `hooks.test.ts` (useResource only).

## Item 8 — Web revenue grid: memoized rows, virtualization for large row counts; keep editing/focus/keyboard/a11y/totals
- Audit: single big component, inline rows, no memo, no virtualization (scalability #7); mobile already uses FlatList + memo.
- Now: STILL PRESENT (8a memo, 8b virtualization).
  - `apps/web/components/RevenuePage.tsx:327-380` renders each vehicle inline in `data.vehicles.map` (Fragment per vehicle: row + optional detail row). `DayCell` (:434-485) and `VehicleWeek` (:488-613) are plain components; no `memo`/`React.memo` anywhere in `apps/web/components` (grep).
  - Per-cell closures `onOpen={(from) => open(openAt(formats,item,day.date), from)}` (:352) are new every render and `open` reads `capture` state (:185-188).
  - Only `query`, `days`, `dayTotals` are memoized (:128-158); `first` (:160-166) and the `gridVehicle/gridCell` lookups (:168-175) run every render. Any `expanded`/`capture`/`stale` change re-renders all V x 9 cells.
- Do (memo): extract `VehicleRow = memo(...)` with `(item, isOpen, today, canCapture, onToggle(id), onOpenDay(vehicleId, date, el))`; stable callbacks via `useCallback` + refs; `memo` `DayCell`/`VehicleWeek`; per-week `dayLabels` computed once (Item 5); `useMemo` for `first`.
- Do (virtualization): only above a threshold (e.g. > 60 rows) so the 2-3 vehicle tests keep a full DOM.
  - Vertical scroll is the window (the grid div is only `overflow-x-auto`, :291): use a window virtualizer with spacer `<tr aria-hidden>` and `aria-rowcount/aria-rowindex`; keep `<caption>`, the sticky first column (`sticky left-0 z-1`, :296,:332,:385) and `tfoot` totals computed from `data`, not the DOM.
  - The expanded detail row (`aria-controls` <-> `id="revenue-detail-..."`, :336,:366) has variable height: measure it and treat row + detail as one virtual item.
- Invariants to keep: focus returns to the opener or the grid (:178-183; with virtualization the opener may be unmounted, so scroll to index and then focus); Save/Enter fires once (`CaptureForm.settle` :675-685); conflict and earlier-day flows; `canEdit`/`opens` rules (:90-95).
- Dependency: none installed; add `@tanstack/react-virtual` (lockfile) or hand-roll windowing. jsdom has no layout, so tests must mock element sizes.
- Pins: `RevenuePage.test.tsx` :91 grid/totals/company filter, :269 next vehicle after save, :295 earlier gap, :320 and :346 versions, :513 save once, :536 returns focus.
- Add: 500 vehicles -> DOM rows << 500 with totals unchanged; expand/capture on an off-screen row; focus return after scroll.
- 8c (mobile; audit said "mobile is fine"): STILL PRESENT, minor. `DayRow/WeekRow/DayBar` are memoized and rows are `useMemo`'d, but the FlatLists set no `getItemLayout/windowSize/initialNumToRender` (`RevenueScreen.tsx:584-621`), and `earliest` (:405-411) plus the default-day effect (:285-296) call `nextMissing` for every vehicle on every week/`waiting` change, in render (date-stepping strings). Memoize them.

## Cross-item dependencies (suggested order)
- Baselines first (Measurement hooks). Then Item 5 (self-contained, shrinks per-cell cost); Items 1+2 (share the vehicle-calendar loader and the aggregate; Item 2's `SettingsVersion` key is reusable by Item 3's COUNT cache and by N1); Item 3 (migration); Item 4 (independent); Items 6+7 (client; 7 should land with or after Item 3's COUNT cache and N1); Item 8 last (needs Item 5's labels and Item 1's final row shape).
- File ownership: Items 1/2 touch `RevenueRepository.cs`/`RevenueContracts.cs`/`RevenueUseCases.cs`; Item 3 touches `SetupRepository.cs`, `SetupModel.cs`, migrations and `AuthDbModelSnapshot.cs`; Items 6/7 touch `apps/web/lib/data`; Item 8 and the web half of Item 1 both touch `RevenuePage.tsx` and Item 5 touches `packages/shared`: use one writer at a time per file set (CLAUDE.md delegation rule).

## Not owned by any phase (scalability/operability/security) — Phase 7 closure must handle unless a Phase 4 session folds them in
- N1 Per-request "context" queries (scalability #4, second half). STILL PRESENT.
  - `OrganizationUseCase.Run` (`apps/api/Application/OrganizationPort.cs:36-53`) = Membership + `Permissions` (Membership again, PersonRoles join, PermissionOverrides) = 4 queries; `SetupExecution.Actor` (`apps/api/Infrastructure/Setup/SetupExecution.cs:23-44`) = scope, company scope, vehicle scope, localization tz, organization business date = 5; plus 2 token-validation queries (Phase 3's cache for those is not in the tree). About 11 per setup call before the endpoint's own.
  - Do: cache scope/permissions/localization/business date per (org, user) keyed on `SettingsVersion` (+ SecurityVersion for token checks); explicit invalidation and tests; `Grant/Deny/ScopeToCompany` write directly (verify no test mutates access after its first request). Coordinate with Phase 3's token cache.
- N2 Visibility predicates (scalability #8). STILL PRESENT. `SetupRepository.cs:13-24` (`VisibleRecurring` nested `Any(Any(Any(VisibleVehicles)))`), repeated NOT-EXISTS "current version" (:100,:180-182), per-row company-name subquery (:87,:160), per-company correlated vehicle count (:36).
  - Do: branch on `actor.AllCompanies` in C# (pattern `PeopleVisibility.cs:19-20`), join the company instead of a subquery, one grouped count, optionally an `IsCurrent` flag (migration).
- N3 `Vehicles()`/`Recurring()` 3-4 round trips and the `Report()` Include chain (scalability #17). STILL PRESENT: `SetupRepository.cs:75-130,169-228`; `Report` `Include(Versions).ThenInclude(Allocations)` (:243-246) without AsSplitQuery.
- N3b Allocation index claim (scalability #17: "no matching leading column"). NOT REPRODUCIBLE: the snapshot has `RecurringAllocation (OrganizationId, VehicleId)` (`AuthDbModelSnapshot.cs:769`) next to `(OrganizationId, VersionId, VehicleId)` (:771), and the global filter always adds OrganizationId. No index needed.
- N4 Server reference-data caching/ETag (scalability #16). STILL PRESENT: no ETag/Cache-Control anywhere in apps/api (grep finds only `X-Request-ID` headers); the proxy forces `no-store`.
- N4b "Logo endpoint has no Cache-Control/ETag" (scalability #16). CHANGED SHAPE (the claim as stated, an endpoint, is not reproducible): there is no logo GET endpoint (only PUT/DELETE `/organization/logo`). `GET /setup/appearance` embeds the logo as a base64 data URL up to 256 KB (`OrganizationEndpoints.cs:130-136`; the response carries `SettingsVersion` :134) on every shell load (`AppShell.tsx:295`), and the phone stores it in the vault (`apps/mobile/src/appearance.ts:49-54`).
  - Do: ETag/304 keyed on SettingsVersion (+ the preference row) for `/setup/appearance`; compression; keep `no-store` for data that must stay fresh.
- N5 Non-revenue web lists unmemoized/unvirtualized (scalability #6). STILL PRESENT: `VehiclesPage.tsx:84,109-111,225` (filter + `companyChoices` sort every render), `RecurringPage.tsx:83-91` (3 filters + `localeCompare` sort + `recurringNextPosting` per row), `ExpenseCategoriesPage.tsx:58-65`, `PeopleAccessView.tsx:89-93`, `HistoryPage.tsx:285` (`fieldChanges` parses/diffs every row every render).
  - Pitfall: `VehiclesPage` and `RecurringPage` return early (`if (editing)`), so `useMemo` must sit before those returns. Do: `useMemo`, `Intl.Collator`, `memo` rows, memoize `fieldChanges` per row. Virtualize only after Item 8's approach is proven (DataTable rows are variable height and stack below 720 px, `ui/table.tsx`).
- N6 General API rate limiting (operability #15). PARTLY ADDRESSED: the permit limit is configurable (`RateLimiting:AuthPermitLimit`, `Program.cs` volatile) but only the `auth` policy exists (fixed 1-minute window); no limiter for `/setup/*`.
- N7 `DotNetEnv.Env.NoClobber().TraversePath().Load()` loads `.env` in every environment (operability #26, security L10). STILL PRESENT: `Program.cs:18`.
- N8 Host/TLS config (operability #16, security L6). STILL PRESENT: `apps/api/appsettings.json` has `AllowedHosts: "*"` and `TrustServerCertificate=True`, the default CORS origin is localhost, and `Program.cs` has no `UseHttpsRedirection/UseHsts`.
- N9 Global auth semaphore (security M3, second half). FIXED: `AuthGate.For(key)` is per phone/device with eviction (`apps/api/Api/AuthEndpoints.cs:14-50,103-113`).
- Seen fixed in the tree while verifying (owned by Phase 3, not re-audited): operability #7 mobile timeout (`api.ts:59-77`), #10 error boundaries (`apps/web/app/error.tsx`, `global-error.tsx`, `apps/mobile/src/ui/ErrorBoundary.tsx`), #12 proxy logging, #13 `renew()` maps only 401/403 to session end (`api.ts:134-139`), #17 `EnableRetryOnFailure`, #2 `--migrate` (dev auto-migrate remains). Still open at last look: #5 readiness has no DB check, #3 console logging only.
- Treated as owned by Phases 1-3/5-6 and not verified here: operability #1, #4, #6, #8, #9, #14, #18-#25; security M1, M2, M3 (proxy-hops half), M4, M5, L1-L5, L7-L9, L11-L13.
- Observation (not in the audit): every audited write bumps one row, `Organization.SettingsVersion` (concurrency token, `OrganizationModel.cs:23`; `RevenueRepository.cs:205`), inside a serializable transaction.
  - Collisions retry 3 times with 5-25 ms backoff, then fail (`OrganizationRepository.cs:49,73-78`; `ChangeLogAndScopeTests.WritesToDifferentRecordsRetryWhenOnlyTheChangeLogCollides`), and a revenue save then answers 409 "This day was changed by another save" (`RevenueEndpoints.cs:27-30`). Bursts of captures (day close) serialize here.
  - Measure under concurrency before acting; candidate = a per-org sequence/table for change-log versions (touches item 3's keyset and item 2's version key).

## Measurement hooks (use for before/after numbers; none exist for browser render time)
- `DatabaseProbe` (`tests/api/AuthFactory.cs:42-128`, `app.Database`): `Reset()`, `Commands`, `Rows` (rows read, via DataReaderDisposing), `Transactions`, `Sql` (queue of CommandText, SQLite dialect).
  - Pattern: `Reset(); await client.GetAsync(...); read counters`, printed with `ITestOutputHelper` (`PeopleQueryCostTests.cs:56-71`). Counts include auth/context queries: warm the session first or compare two calls (`VehicleReportTests.cs:196-224`, `RecurringQueryCostTests.cs:30-56`).
- `RevenueComplexityTests.Measure` (`tests/api/RevenueComplexityTests.cs:89-112`): repository-level `Commands` + `Reads` through a `DbCommandInterceptor`, no HTTP/auth noise; fleets built by `Fleet(name, prefix, vehicles, days, today)` (:71-80).
  - Extend sizes (V=100/500, D=150) and print baselines; existing bounds `Reads <= 10*12+10` (:55) and Commands equal small vs large (:52,:60). It counts reader/scalar commands only.
- Baselines from reading the code (verify with the probe): Week 6-8 repository commands, Dashboard 3; setup read context about 9 (+2 token validation); each streamed list page = context + COUNT + page.
- SQL shape: `tests/api` has no `ToQueryString()` or EF logging today; add `ToQueryString()` in a test to check `Contains` translation, `actor.AllCompanies` parameterization, OFFSET vs keyset. Real SQL Server plans/indexes only via `SqlServerTests` (`SQLSERVER_TEST_CONNECTION`); add an opt-in test that applies the new migration and checks the indexes exist.
- Web: gating/counting fetch mocks (`Streaming.test.tsx` gates, `SetupProxy.test.ts` mocked `fetch`, `RevenuePage.test.tsx` `serveWeek`/`gets`), `hooks.test.ts` for hook-level tests.
  - Render cost: a vitest test rendering `RevenuePage` with N generated vehicles (the `vehicle()`/`week()` helpers are local to `RevenuePage.test.tsx`; extract them), timed against a baseline, or React Profiler `onRender`; jsdom numbers are relative only.
- Shared: spy `Intl.DateTimeFormat`/`Intl.NumberFormat` constructors (`vi.spyOn(Intl, ...)`) to count constructions. Mobile: `tests/fakeApi.ts` (`api.calls`, `api.sent`) counts requests; no render benchmark exists.
- Payload size: no tooling; use `curl -H 'Accept-Encoding: br' -w '%{size_download}'` against `/setup/revenue`, `/setup/history?pageSize=100`, `/setup/people` before and after compression/paging.

## Tally
Findings verified: 38. STILL PRESENT 29: 1a, 1b, 1c, 2a, 2b, 3a, 3b, 3c, 3e, 3f, 4a, 4b, 5a, 5b, 5c, 6a, 7a, 7c, 7e, 8a, 8b, 8c, N1, N2, N3, N4, N5, N7, N8.
PARTLY ADDRESSED 2: 7d, N6. FIXED 3: 6b, 7b, N9. CHANGED SHAPE 2: 3d, N4b. NOT REPRODUCIBLE 2: 3g, N3b.
Not counted: 6c and the Observation (extra notes, not audit findings); the "seen fixed" and "treated as owned" lists (other phases).
