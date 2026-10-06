SCALABILITY REVIEW (read-only; nothing modified). Line numbers are approximate; the repo has uncommitted edits. Overall: the code is already scale-conscious (AsNoTracking, grouped queries, tenant-first composite indexes, server paging capped at 100). The gaps are the unpaged revenue grid, the change-log query, and the lack of any caching or compression.

## HIGH

1. [HIGH | DB/API | apps/api/Api/RevenueEndpoints.cs:35 and apps/api/Infrastructure/RevenueRepository.cs:16-70] The weekly revenue grid has no paging and no row cap.
 - The query loads every active vehicle with Targets and AwayPeriods in one Include (a cartesian row explosion, with no AsSplitQuery).
 - It also loads every RevenueRecord for the week, and runs the EarliestMissing group-by.
 - The response carries V x 7 cells, each with 9 fields. Web (RevenuePage.tsx:325) and mobile render the whole array.
 - Impact: at 1,000 vehicles that is about 7,000 cells (roughly 1 MB of JSON), plus a join of targets x away periods per vehicle. Latency and memory grow linearly, and the saves that refetch the week repeat the cost.
 - Fix: add page and pageSize to the week endpoint, or move the week totals into a separate aggregate query and page the vehicle rows.
 - Fix: use .AsSplitQuery() or project to a DTO. The projection should select only the fields used and take targets effective on or before the week end (the latest one plus later ones).

2. [HIGH | DB | apps/api/Infrastructure/RevenueRepository.cs:75-125 (Dashboard)] The dashboard computes its aggregates in memory.
 - It loads all vehicles (with Include) and all RevenueRecord rows for the period into memory, then loops vehicle x day in C#.
 - For "month" this is V x 31 rows (30k records at 1,000 vehicles) on every dashboard load, and the dashboard is the home screen.
 - Fix: for revenue, captured-today, edited and missing counts, use SQL aggregates: GroupBy with Sum and Count over RevenueRecord joined to vehicles. Keep only the target (expected) calculation in memory, and cache that.
 - Fix: cache the dashboard per org/actor-scope/period for 30-60 s.

3. [HIGH | DB | apps/api/Infrastructure/Setup/SetupRepository.cs:280-310 (History)] The change-log query is heavy and its count runs a second time.
 - The filter OR-chain uses correlated subqueries: vehicles.Contains, VisibleCompanies (nested VisibleVehicles), completeItems with a triple-nested Any/NOT-Any, and revenueRecords.Contains over the whole RevenueRecord table. That last one is the worst, because RevenueRecord is the largest table and every revenue save writes a history row.
 - OrderByDescending(Version) is paged with Skip/Take, so deep pages are O(offset).
 - A second query, CountAsync, re-runs the whole expression for every page request. useStreamedList pages through everything in sequence, so this repeats once per page.
 - The Text filter uses LIKE '%x%', which cannot use an index and also runs a correlated subquery on Memberships.
 - Fix: store a denormalized VehicleId and CompanyId on OrganizationSettingsVersion at write time, and filter on those columns directly.
 - Fix: add indexes (OrganizationId, Section, EntityId) and (OrganizationId, OccurredAt). Only (OrganizationId, Version) exists (SetupModel.cs:80).
 - Fix: switch to keyset paging (Version < cursor).
 - Fix: skip the count after page 1, or return hasMore instead of a total.

4. [HIGH | Caching/Auth | apps/api/Program.cs:~75-90 (OnTokenValidated)] Every authenticated request runs 2 DB queries before the endpoint does.
 - They are Users.FindAsync and TrustedDevices.SingleOrDefault. The endpoint then runs its own queries, including SetupExecution (scopes, localization, business date, organization: about 5 more round trips; SetupExecution.cs:25-37). Per request that is about 7 queries of "context".
 - The first-page streamed lists and RevenuePage multiply this.
 - Fix: use IMemoryCache with a short TTL of 15-30 s, keyed by user and device, and bust it on revoke or SecurityVersion change.
 - Fix: cache the actor scope, localization and business date per org/user with the same TTL (a new SetupActor cache).

## MEDIUM

5. [MED | API | apps/web/lib/data/useStreamedList.ts:38-52] The streamed list is sequential, unbounded and cannot be cancelled mid-flight.
 - It loops page after page until items.length >= total, with no cap.
 - Each page runs a COUNT plus a page query (e.g. SetupRepository.Companies:28, Vehicles:77), so a 10k-vehicle fleet means 400 sequential requests and 400 COUNTs.
 - The accumulated array is copied on every progressive setLoaded ([...items]), which is O(n^2) over a load.
 - Every page lands in React state, and the page components then render all rows.
 - Impact: slow first-to-last load, and memory and re-render cost grow with fleet size.
 - Fix: use real "load more" or infinite scroll with server-side search and filter (VehiclesPage filters client-side by company).
 - Fix: once page 1 returns total, fetch the remaining pages in parallel (limited to 3-4 concurrent) and batch setState.
 - Fix: skip the COUNT on pages after 1 and cap pageSize to the server's limit (100).
 - Fix: cancel in-flight fetches with an AbortController when the effect cleans up (today only the `active` flag is checked).

6. [MED | Frontend | apps/web/components/setup/VehiclesPage.tsx:76-170, CompaniesPage.tsx:138, RecurringPage.tsx:147-150, HistoryPage.tsx:281, ExpenseCategoriesPage.tsx:56-63,258-316] None of the lists is virtualized.
 - They render every row in full: VehiclesPage renders every vehicle with its targets, and HistoryPage renders ChangeTable for each row.
 - Filters and sorts re-run on every render with no useMemo: the vehicle filter, RecurringPage visible (3 filters plus sort plus localeCompare), and ExpenseCategories sort, filter and flatMap.
 - Impact: at a few thousand rows the DOM and render time degrade, and every keystroke or toggle re-sorts.
 - Fix: wrap derived lists in useMemo, use Intl.Collator for sorting, and add windowing (react-virtual) or make the lists server-paged.
 - Fix: HistoryPage's fieldChanges(row.before, row.after) re-parses and diffs on each render, so memoize per row.

7. [MED | Frontend | apps/web/components/RevenuePage.tsx:325-380] The grid table is one big component with no memoization.
 - Each vehicle row is inline in the .map(), not a React.memo component. Any state change re-renders all V x 9 cells. Such changes include expanding a row, opening a capture dialog, and typing in a filter.
 - There is no virtualization. The mobile equivalent already uses FlatList with memo(DayRow/WeekRow) (RevenueScreen.tsx:576-640, 734), so mobile is fine, but note the mobile FlatList has no getItemLayout/windowSize tuning.
 - Fix: extract <VehicleRow> as React.memo with stable callbacks, and virtualize with a sticky header. The dayTotals useMemo at line 150 is fine.

8. [MED | DB | apps/api/Infrastructure/Setup/SetupRepository.cs:16-20,77-120] Visibility predicates and the Vehicles page query are expensive.
 - VisibleRecurring has nested Any(Any(Any(VisibleVehicles))), VisibleCompanies nests VisibleVehicles, and the "current version" test is NOT EXISTS (other.Revision > v.Revision) repeated in Vehicles(), Recurring() and elsewhere.
 - Each page re-runs a correlated COUNT(*) per company/vehicle (Companies:35, the vehicle count) and a company-name subquery per vehicle row (Vehicles:~85).
 - `actor.CompanyIds.Contains(...)`/`VehicleIds.Contains(...)` become IN lists or OPENJSON, and these lists can be large for scoped users. The query plan changes with the list size, which fragments the plan cache.
 - Fix: add a denormalized `IsCurrent` flag or a Current pointer on RecurringItem, and a join to the company instead of a subquery.
 - Fix: group the active vehicle counts in one query. Where scope lists are large, load them into a temp/keyed table or filter by the CompanyId index.

9. [MED | API | whole API (apps/api/Program.cs)] There is no response compression.
 - AddResponseCompression and UseResponseCompression are absent (grep found nothing).
 - JSON for grids, the history Before/After snapshots and the people list is highly compressible. The Next proxy at apps/web/app/api/setup/[...path]/route.ts:84-104 buffers the entire upstream body with `await response.text()`, so there is no streaming and no passthrough of the encoding.
 - Fix: enable Brotli/Gzip in the .NET API. Alternatively, pipe response.body straight through the Next route (new NextResponse(response.body, ...)).
 - Fix: Next compresses its own output by default, but it only helps the browser leg.

10. [MED | DB | apps/api/Infrastructure/RevenueModel.cs:17-18] RevenueRecord has the right two indexes, but Week/Dashboard read whole-row entities.
 - The indexes are (OrgId, VehicleId, BusinessDate) unique and (OrgId, BusinessDate). Reading complete RevenueRecord entities includes the Note, Reason, Version and other columns the dashboard does not need.
 - Fix: project only (VehicleId, BusinessDate, Amount, CorrectedAfterDate) for the dashboard.
 - Fix: for the missing-days checks, add a covering INCLUDE(Amount) to the (OrgId, BusinessDate) index.

11. [MED | DB | apps/api/Infrastructure/RevenueRepository.cs:200-215 (ActiveRecords)] The EarliestMissing query joins RevenueRecord to FleetVehicle and filters with `ids.Contains(...)`.
 - This query runs on every week load, and its IN list grows with the fleet (a large literal parameter list; consider TVP/OPENJSON). With many vehicles the plan degrades.
 - The "holed" fallback loads every date for each vehicle with a gap.
 - Fix: persist `FirstMissingOn` or a "captured through" watermark per vehicle, updated on each Save, which turns the check into O(1) per vehicle.

## LOW

12. [LOW | Shared | packages/shared/src/dates.ts:100-121,123-131,133-175 and format.ts:240-249] Intl objects are created on every call.
 - dateParts() builds a new Intl.DateTimeFormat on each call, and safeTimeZone builds another one (just to validate). formatCalendarDate builds another one for short/long styles. kes() uses amount.toLocaleString with options on every call.
 - Constructing Intl formatters costs on the order of microseconds to tens of microseconds, so a 1,000-vehicle x 7-day grid (7k+ calls) plus history rows adds noticeable render time.
 - Fix: memoize formatters by key (locale|timeZone|options), for example a small Map cache or `configureFormats` building them once. Then call `formatter.format()` or `formatToParts()`. Cache safeTimeZone results as well.

13. [LOW | Shared | packages/shared/src/dates.ts:67-96] The date arithmetic allocates a Date and a string on each call.
 - calendarDate parses a string into a Date, and the shiftDate chain (startOfWeek calls weekdayIndex, then shiftDate) creates 2-3 Dates per call. In a loop of V x 7 this is thousands of throwaway objects.
 - Fix: compute from integer epoch days (Date.UTC(y,m,d)/DAY) or memoize on the input string; share a per-week precomputed `days` array rather than recalculating per cell.

14. [LOW | Shared | packages/shared/src/revenue.ts:437] `revenuePeriodLabel` does a linear find on a 3-element array. Negligible, but a lookup map is trivial. parseRevenueAmount is fine.

15. [LOW | Frontend | apps/web/lib/data/useResource.ts and request.ts] There is no client-side cache or request de-duplication.
 - Each useResource runs its own fetch on mount and on every path/version change. Navigating away and back refetches everything (companies, vehicle-options, expense-items, week).
 - VehiclesPage and RecurringPage each stream the full companies/recurring lists independently (VehiclesPage.tsx:79 and :689 both stream "setup/recurring" in full).
 - Several places call useResource for the same option lists.
 - There is also no AbortController, so a stale request still completes.
 - Fix: adopt SWR or TanStack Query (stale-while-revalidate, dedup, keyed invalidation on save), or add a module-level Map<path, {data, ts}> with a TTL to this hook. Reuse the same cached data for the "options" endpoints.

16. [LOW | Caching | apps/web/app/api/setup/[...path]/route.ts:87,104 and apps/web/next.config.ts] Everything is cache: "no-store" with Cache-Control: no-store. There is no ETag / If-None-Match support.
 - No server-side caching exists anywhere (no IMemoryCache, no OutputCache, no response caching). Reference data that changes rarely (company options, vehicle options, expense catalog, localization, branding, the logo) is re-read on each request.
 - Static assets: next.config.ts sets only security headers. Next serves its hashed /_next/static immutable assets by default, so that is fine. The organization logo, which is served from the DB (OrganizationLogo.Data), has no Cache-Control or ETag (an endpoint in OrganizationEndpoints.cs).
 - Fix: add ETag/304 handling plus `Cache-Control: private, max-age=30, stale-while-revalidate` for reference-data GETs. Cache the logo with a version-based ETag and `Cache-Control: private, max-age=86400`. Add IMemoryCache for localization, scope and permission lookups, and short OutputCache for GET list endpoints, varying by org and user.

17. [LOW | DB | apps/api/Infrastructure/Setup/SetupRepository.cs:99-110, 180-210] Vehicles() and Recurring() each run 3-4 sequential round trips per page, and the Vehicles "current" recurring query runs `Any(vehicleIds.Contains)` over allocations without covering the access path. The allocations index is (OrgId, VersionId, VehicleId), so a lookup by VehicleId alone has no matching leading column.
 - Fix: add an index on RecurringAllocation (OrganizationId, VehicleId, VersionId).
 - Also use `.AsSplitQuery()` in Report() at ~line 233 (Include Versions then Allocations).

18. [LOW | DB | apps/api/Infrastructure/AuthDb.cs and AuthDb tenant filters] The global query filter on OrganizationId is combined with composite keys that lead with OrganizationId, which is fine. However, `Memberships.Where(m => m.UserId == v.ActorId)` correlated subqueries (the History actor-name lookup, and the Narrow text filter) rely on the (UserId) index, not the (OrganizationId, UserId) PK prefix. They are fine today. Prefer a join or a single batched actor-name lookup per page (the History page runs this subquery 25-100 times).

## What is already good
- AsNoTracking is used consistently on reads, and page size is capped at 100 (SetupPagination.Validate).
- The access-people Load() and ExpenseCategories use a bounded query per table (no N+1).
- EarliestMissing is deliberately O(V) with a fallback.
- Mobile uses FlatList with memoized rows and useMemo'd derived rows.
- The history date filter runs in the database (UTC converter).
- Tenant-leading composite unique indexes exist on most tables.

## Suggested priority
1. Page or aggregate the weekly grid and the dashboard (#1, #2).
2. Denormalize and index the history log, and use keyset paging (#3).
3. Cache the per-request auth and actor lookups (#4).
4. Add response compression, ETags and reference-data caching (#9, #16).
5. Parallelize or replace useStreamedList, and add a client cache (#5, #15).
6. Memoize the Intl formatters (#12), then add virtualization or memoized rows on the web lists (#6, #7).