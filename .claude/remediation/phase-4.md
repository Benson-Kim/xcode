# Phase 4 — Scalability (prompt 4)

Implement Phase 4 of the Revenue App Remediation Plan completely. Do not optimize speculatively: work from the verified findings, measure before and after, and keep behavior identical unless an item says otherwise.

## Start here
1. Read CLAUDE.md, `.claude/remediation/README.md`, and all of `.claude/remediation/findings/phase-4.md`.
   - The findings were verified against the code on 2026-10-06 and cover 38 findings with file:line, pins, tests to add and pitfalls.
   - Its section 0 ("constraints that apply to every item") is mandatory. Re-verify line numbers, because they drift.
2. Run `git status` and check recent file times. Re-read `apps/api/Program.cs`, because Phase 3 left it in flux: no `AddMemoryCache` is registered, and `OperabilityTests` still expects a session cache. Never assume another phase's cache exists.
3. Record baselines before changing code (see "Measure"), plus the full validation path.
4. Make a checklist with one row per sub-finding (1a–8c) and per clause below.
5. Delegation:
   - `remediation-opus` only past the gate. Item 3 (schema, migration, backfill, keyset) and items 1+2 (shared aggregate, contract change, cache) qualify.
   - `remediation-sonnet` for items 4, 5, 7 and 8.
   - At most two helpers, with one writer per file set. File ownership is listed in the findings' "Cross-item dependencies".

## Decisions to make explicitly (state them in the report)
- **Item 1, default when no paging params are sent:** either the legacy full list under a hard cap with a `truncated` flag, or page 1. Released phones and web tabs read raw JSON (`Phase1ContractTests`), and web and mobile derive day totals, first gap, next-missing and the offline capture list from the whole vehicle list. So either ship those aggregates server-side or make the clients load all pages.
- **Item 3:** denormalize `VehicleId` only. A frozen `CompanyId` would change who sees old rows, because visibility follows the current scope. Choose otherwise only deliberately.
- **Item 8:** hand-rolled windowing, or add `@tanstack/react-virtual` (a lockfile change). Virtualize only above a row threshold.

## Order
1. Baselines.
2. Item 5.
3. Items 1+2 (they share the vehicle-calendar loader and aggregate).
4. Item 3, with its migration.
5. Item 4.
6. Items 6+7: after item 3's COUNT cache, and preferably after the N1 context-query work.
7. Item 8 last.

## Items (details, pins and tests are in the findings file under the same numbers)
1. **Weekly revenue grid.**
   - Add optional `page`/`pageSize` (`SetupPagination.Validate`) and additive DTO fields. Compute aggregates over all visible vehicles: totals summed unrounded then rounded once, `dayTotals`, `firstGap`.
   - Avoid the cartesian `Include`, using `AsSplitQuery` or filtered includes. Do not pass week-filtered AwayPeriods to `EarliestMissing`.
   - Project only the record columns the grid needs.
   - Keep `vehicleId` detail requests unpaged.
   - Migrate the web loader and mobile `loadWeek`. The capture list must still cover the whole fleet; keep the 8-week memory.
2. **Dashboard.**
   - Aggregate in SQL. SQLite cannot `Sum` decimals: spike first, with a narrow projection or integer-cents fallback, never `double`.
   - Cache through a decorator on `IRevenueRepository`. Store the UNMASKED DTO and apply `RevenueUseCases.Visible` after the cache.
   - Key: org + `Organization.SettingsVersion` (read in `SetupExecution.Actor`'s existing organization query and carried on `SetupActor` as an optional trailing parameter) + today + period + company + scope key. This makes invalidation replica-safe; the TTL only bounds memory. Use `SizeLimit`, and compute once per key under concurrency.
   - Adapt `RevenueCaptureTests.DashboardEditsCount...` deliberately: retire through the API so the version moves. Do not weaken it.
3. **Change log.**
   - Add a nullable `VehicleId` to `OrganizationSettingsVersion`, set by the four writers.
   - Add indexes `(OrganizationId, Section, VehicleId)` and `(OrganizationId, OccurredAt)`.
   - Migration order: columns, then backfill (raw SQL, because EF forbids modifying history rows; `public const`, tested on SQLite like `ClampSql`), then indexes.
   - Add keyset paging `before=<version>` with `hasMore`/`nextBefore`, keeping `page`.
   - Keep `total` on every page for old clients, and cache the count per (org, SettingsVersion, scope, filter). Add `includeTotal=false` for People's 3-row call.
   - Recurring and people sections keep their own predicates.
4. **HTTP/proxy.**
   - Add Brotli + Gzip with `EnableForHttps`. Compress `/setup/*` only, leaving `/auth/*` alone (token bodies, BREACH).
   - Keep gzip for React Native.
   - Stream the setup proxy's upstream body. Keep the 5xx → 503 `service_unavailable` + `requestId` mapping, and cancel unread bodies.
   - Never forward `Content-Encoding`, `Content-Length` or `Transfer-Encoding`.
   - Split the time-to-headers timeout from body streaming, and log mid-stream failures.
   - Leave the auth route buffered.
5. **Formatting hot paths.**
   - Use module-level maps of immutable `Intl` instances keyed by locale and options, bounded in size. Negative-cache `safeTimeZone` so an invalid zone still falls back.
   - Precompute per-week day labels.
   - Do not cache `Date` objects.
   - Keep `createFormatter`/`useFormats()` as the API.
   - Check the `formatDateOnly` time-zone pitfall noted in the findings before keying a cache on it.
6. **Client caching (web).**
   - Build a keyed store in `apps/web/lib/data`: cached data plus in-flight promises keyed by path, a ref-counted abort, an SWR-style return, and no cached errors.
   - Successful non-GETs through `apiRequest` invalidate by prefix (default: everything under `setup/`).
   - Clear the store on session end, sign-out and user switch.
   - Add `clearDataCache()` to `apps/web/tests/setup.ts`.
   - Keep `withRetry` and the single-flight 401 refresh.
7. **useStreamedList.**
   - Fetch page 1, then pages 2..N through a pool of 3–4 workers, each via `withRetry` and the shared controller.
   - Commit only the contiguous prefix, with one `setLoaded` per commit.
   - Add a `partial` flag on failure, de-duplicate by id, and derive the page count from the echoed `pageSize`.
   - Lists must stay complete: no infinite scroll.
8. **Web revenue grid.**
   - Memoize rows and cells with stable callbacks.
   - Window virtualization only above about 60 rows: spacer rows, `aria-rowcount`/`aria-rowindex`, row + detail as one item, the sticky column and `tfoot` totals from data.
   - Focus must still return to the opener after scrolling.
   - Mobile 8c: memoize the per-render `nextMissing` scans.

## Measure (before and after; report real numbers only)
- Use `DatabaseProbe` (Commands, Rows, Transactions, Sql) and `RevenueComplexityTests.Measure` (extend to V=100/500).
- Query-count tests compare consecutive requests, so warm caches deliberately and never loosen assertions.
- Use `ToQueryString()` tests for the SQL shape: `Contains` translation, the `AllCompanies` branch, keyset vs OFFSET.
- On the web, use the counting and gating fetch mocks; take render timings as relative only (jsdom).
- Measure payload sizes before and after compression and paging.

## Done means
- All eight items are implemented with evidence: file + symbol, and a test that fails without the change (query counts, bounds, invalidation, ordering, the contract staying additive).
- Snapshot tests are green, with new migrations added and the backfill SQL tested.
- The full validation path is green, including the mobile typecheck, apart from attributed failures that belong to other sessions.
- A `remediation-auditor` pass over items 1–8 reports no PARTIAL.
- The N1–N9 findings are either folded in (say which) or left in the README residuals for closure.
- Update `.claude/remediation/README.md` and the `remediation-program` memory.

End with:
- an eight-item matrix;
- the decisions taken;
- before/after measurements;
- the migrations added;
- any genuine blocker.
