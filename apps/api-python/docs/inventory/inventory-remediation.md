# Inventory: remediation program and review history of the .NET API

Digest for the people planning and auditing the Python + PostgreSQL rewrite (`apps/api-python/docs/`). It does not restate the audits: follow the citations. Written 2026-10-08 by a read-only reader. Conventions: `R:` = `.claude/remediation/`, `C:` = `CLAUDE.md`, `D:` = `docs/`. An audit id such as `security M2` means the finding with that id in `R:audit/security.md`. States come from `R:README.md` (status table, residuals) and the phase parent checklists; where I confirmed a state in the current code with grep it says "checked in code". Phase 6 is not closed (README status says Pending; `R:handoff/phase-6-parent.md` row V "in progress"), and the closure session (`R:closure.md`) has not run, so no closure crosswalk exists yet.

## 1. Purpose and sources

| Source | Last changed | Used for |
|---|---|---|
| `CLAUDE.md` ("Known traps", "Strengths to preserve") | 2026-10-07 23:36 | traps, strengths, house rules |
| `.claude/remediation/README.md` | 2026-10-07 23:37 | status table, handover mechanisms, residuals 1 to 13 |
| `.claude/remediation/closure.md` | 2026-10-06 13:45 | closure prompt only (no crosswalk exists) |
| `.claude/remediation/findings/phase-4.md` | 2026-10-06 14:08 | verified scalability findings (states are pre-fix) |
| `.claude/remediation/findings/phase-5-6.md` | 2026-10-06 14:21 | verified architecture/maintainability findings (pre-fix) |
| `.claude/remediation/audit/*.md` (7 reports) | 2026-10-06 13:43 | original findings, morning of 2026-10-06 |
| `.claude/remediation/handoff/phase-4-parent.md` | 2026-10-07 23:37 | Phase 4 checklist and evidence |
| `.claude/remediation/handoff/phase-5-parent.md` | 2026-10-07 19:59 | Phase 5 checklist and evidence |
| `.claude/remediation/handoff/phase-6-parent.md` | 2026-10-08 00:21 | Phase 6 checklist (in progress) |
| `docs/backlog.md` | 2026-10-06 19:14 | two unscheduled requests |
| `docs/reviews/phase-2-plan.md` | 2026-10-05 09:20 | frozen contracts C1 to C7 and decisions D1 to D16 |
| `docs/reviews/pr-3-codex-review.md` | 2026-09-29 22:37 | 24 PR review findings, all Fixed or Already fixed |
| `docs/reviews/settings-setup-review.md` | 2026-09-29 22:37 | S1 to S22 settings/setup findings |
| `docs/design/XCODE_Build Notes_v1.0.pdf` (4 pages, read through pdftotext, the Read tool could not render it) | 2026-10-05 09:20 | product vocabulary and rules (addendum 1, 28 Sep 2026) |

Cautions for the reader:
- The audits are static reviews from 2026-10-06 morning. Their line numbers have drifted; the `findings/` files re-verified them the same day, and every "Now: STILL PRESENT" there predates the fixes. Phase 4 and 5 states below come from the parent checklists (evidence per row), not from the findings files.
- Phase 1 to 3 have no checklist file in the folder. Their state is the README table plus the residual notes. Items I could not tie to a residual are marked "unverified" or "checked in code".
- `apps/api-python/docs/inventory/*` (the sibling inventories) still cite the deleted `AuthService.cs` (README residual 12). Authentication moved to `Application/Authentication/` (`SignInService`, `PinSetupService`, `SessionService`, `AuthAccounts`, `AuthCodes`, `SessionTokens`, `AuthPolicy`) and `Infrastructure/AuthUnitOfWork.cs`.
- Where this digest and the .NET code or tests disagree, the code and tests win (inventory README rule).
- Remediation phase status: 1 Safety and security Done; 2 Domain integrity Done; 3 Operability Done (2026-10-06); 4 Scalability Done (2026-10-07); 5 Architecture and DRY Done (2026-10-07); 6 Maintainability and CI Pending in README, mostly done in the parent checklist; Closure Pending. Everything is uncommitted on branch `fix/format` except phases 1 to 3 (commits 4318865, f7ecad7).

## 2. Invariants and strengths the rewrite must preserve

Rows S1 to S12 are the twelve bullets of `C:` "Strengths to preserve" (lines 78 to 92); S13 onward come from the audits' "good" sections and the later phases. Each needs a test that fails without it (see section 5).

| # | Invariant | .NET mechanism (one phrase) | Established by |
|---|---|---|---|
| S1 | Tenant query isolation; cross-tenant writes rejected | global query filter on `OrganizationId` (`OrganizationModel.Tenant()`); `AuthDb.ValidateWrites` rejects foreign-org writes and edits to the org row | `audit/security.md` "done well"; `docs/reviews/settings-setup-review.md` "What's solid" |
| S2 | No raw SQL | LINQ only; the one allowed SQL is public-const migration backfills (`NormalizeSecurityPolicy.ClampSql`, change-log `VehicleId` backfill), tested on SQLite | `audit/security.md` A03; `R:README.md` residual 13 |
| S3 | Token validation and refresh rotation | JWT checks issuer, audience, lifetime, key, zero skew; `OnTokenValidated` re-checks user status, `SecurityVersion` and device revocation on every request; refresh = 48 random bytes stored as HMAC, rotated on use, reuse of a revoked token revokes the device family | `audit/security.md` "Tokens are sound"; `SessionService.Refresh` |
| S4 | RevenueRecord domain invariants | private setters, validating constructor (UTC, immutable business date, tenant guard), `Version++` in `Replace`, idempotent replay (`Matches`), unique (Org, Vehicle, Date), decimal(14,2) | `audit/integrity.md` section 1 [OK]; `D:reviews/phase-2-plan.md` C2, A3 |
| S5 | Optimistic concurrency maps to 409 on revenue saves and setup writes | `DbUpdateConcurrencyException` to 409 in `RevenueEndpoints`; `WithSetupErrors`; `UnitOfWork.Execute` retries only change-log (Organization) collisions, 3 attempts, 5 to 25 ms | `audit/integrity.md` "HIGH, unverified" item; `R:README.md` handover "Concurrency"; `R:findings/phase-4.md` Observation |
| S6 | Capped paging and read patterns | `SetupPagination.Validate` (pageSize at most 100, 400 outside), `AsNoTracking` on reads, reads open no transaction (`PeopleQueryCostTests` asserts 0) | `audit/scalability.md` "already good" |
| S7 | Mobile offline queue crash-safety | per-slot writes then index, per-owner mutex, idempotent replay, conflict and blocked states, 500-entry cap; server must keep accepting an identical replay as 200 | `audit/integrity.md` "offline queue"; `D:reviews/phase-2-plan.md` D5, D8 |
| S8 | Clean shared-package module graph | no cycles, no cross-app imports, no React/Next/RN in shared (now lint-enforced); sub-path exports only | `audit/extensibility.md` section 6; `R:handoff/phase-6-parent.md` rows 2a to 2e. Client side, but the API contract it types is what Python must keep |
| S9 | Access anti-escalation | only Owner grants Owner; cannot edit yourself; only grant permissions you hold; non-Owner gives only roles whose defaults they hold; cannot deactivate an Owner | `docs/reviews/pr-3-codex-review.md` #9; `settings-setup-review.md` S1, S2; `phase-2-plan.md` D10 |
| S10 | Enumeration-resistant auth | unknown number, paused account and capped untrusted device answer identically; PIN-request response never leaks masked email | `pr-3-codex-review.md` #11; `C:` Known traps "Auth lockout model"; `AuthTests` `Seen` compares whole responses |
| S11 | Strong mobile queue and auth error-path tests | (tests, not code) | `audit/maintainability.md` T6 |
| S12 | Byte-for-byte `/auth/*` shapes | `{status,...}` JSON of Phase 1 kept so shipped phones work; new headers excluded from `Seen` | `phase-2-plan.md` Contracts preamble; `C:` Known traps "Byte-for-byte" |
| S13 | Contracts are additive only | `Phase1ContractTests` reads raw JSON: no renamed, removed or retyped property, no changed status; `Page<T>` keeps numeric `pageNumber/pageSize/total` | `R:findings/phase-4.md` section 0 "Additive contracts" |
| S14 | Append-only history | target and recurring versions never overwritten (`DueOn` picks latest revision effective on a date); change log append-only, `OrganizationSettingsVersion` not modifiable (`ValidateSetupWrites`); revenue records never deleted | `settings-setup-review.md` "What's solid"; `R:findings/phase-4.md` item 3 |
| S15 | Single change-log writer | `SettingsChangeLog.Record` is the only writer of change-log rows and the only place `SettingsVersion` moves (settings, setup, revenue, people, petty cash); idempotent replays write nothing | `R:handoff/phase-5-parent.md` rows 1a to 1f; `R:README.md` Phase 5 |
| S16 | Serializable transaction for writes, retried under the execution strategy | `IUnitOfWork` / `IAuthUnitOfWork`; tracker cleared per retry; mail sent only for the committed attempt | `R:README.md` residual 10; `phase-5-parent.md` 8b |
| S17 | Per-account auth lock and caps | `AuthGate` per account, no disposal of evicted semaphores; PIN capped at 8 before hashing; codes 5 per hour and 10 per day; device revoke locks on the account phone | `security M3, M4`; `phase-5-parent.md` 8c, 8d |
| S18 | Idempotent, authorisation-before-disclosure revenue save | permission checks run before the version check so a 409 `current` reaches only someone allowed to change it; identical replay returns 200 | `phase-2-plan.md` D5 |
| S19 | Recorded revenue never disappears | leave date on or before a recorded day, or join date after the first record, refused with 400 naming the day; away periods are neither expected nor missing | `phase-2-plan.md` D4 |
| S20 | One source of permission keys | `Domain/PermissionKeys.cs` (40 constants); `PermissionCatalog.Refusal(action,key)`; unknown key must not become a 500; shared TS mirrors it, drift test fails | `phase-5-parent.md` 6a, 6b; `phase-2-plan.md` D10 |
| S21 | Logo and brand safety | PNG/JPEG/WebP only, magic-byte check, 256 KB cap, SVG refused, data-URL regex, brand URLs HTTPS | `audit/security.md` "Logo upload is safe" |
| S22 | Money and amount rules | decimal, 2 dp stored, `Money()` caps at 999,999,999,999.99, more than 0; recurring shares sum exactly; display decimals are a setting only (D3) | `audit/integrity.md` 1 [LOW]; `phase-2-plan.md` D3 |

## 3. Findings by audit dimension

Severity is the audit's own. States: Fixed N = fixed in phase N (evidence in the parent checklist or README); Open = still present in the .NET code; Residual = tracked in README residuals; NR = not reproducible; Q = needs a product decision. "(code)" = I confirmed the state by grep on 2026-10-08. Client-only findings (web proxy, mobile, shared TS) are omitted unless they constrain the API; the audit files hold them. "Inherits" is what the Python API must reproduce or decide.

### 3.1 Security (`audit/security.md`; Phase 1, then 5; no per-item checklist exists)

| Id | Sev | State | Fix mechanism | Inherits |
|---|---|---|---|---|
| M1 Development environment = auth bypass (`developmentCode`, log mailer, demo users, random key) | M | Partly fixed 1; Residual 1 | web proxy forwards `developmentCode` only outside production; `options.DevelopmentMode = Development && IsLocalDatabase` (code: `Program.cs:28-39`) | Dev-only features need an explicit opt-in flag and startup must fail for dev + remote DB; .NET still matches substrings (`.db`, `localhost`), so do not copy it. Parse the host |
| M2 Anyone with a phone number can lock the account | M | Fixed 1 | per-account cap for untrusted devices `SignInService.UntrustedAttemptLimit = 10`; trusted-device failures pause per policy; cap resets only on `User.SetPin` or a verified new device; `ClearLockout` never resets it; `SessionTokens.Issue` does not clear lockout (callers do) | The whole lockout model (`C:` Known traps), including that capped untrusted devices get the unknown-number answer |
| M2b `ClearPause` zeroes `FailedAttempts`, so guessing resumes each lockout period | M | unverified (code: `Entities.cs` lockout reset zeroes both fields) | not recorded as changed | Decide: decaying counter or escalating pause (section 7, Q4) |
| M3 Rate limiting behind the proxy; global auth semaphore; 128-char PIN hashed | M | Fixed 1 (semaphore, PIN cap); Residual (N6, rate limit only on `/auth`) | `AuthGate.For(key)` per phone/device with eviction; PIN capped at 8 before hashing; `RateLimiting:AuthPermitLimit` configurable | Per-account lock; PIN cap 8; `TRUSTED_PROXY_HOPS` semantics (`ForwardedClientTests`) |
| M4 Unauthenticated code requests: email bombing, slow guessing | M | Fixed 1 | `AuthCodes.HourlyCodeLimit = 5`, `DailyCodeLimit = 10` per account; failed code guesses counted (Codex #3) | The caps; one resend per minute |
| M5 Mobile offline PIN check weak | M | Fixed 2 (client); Residual 4 | pure-TS PBKDF2-SHA256 100k (`src/lib/pbkdf2.ts`) | Nothing for the API. Server PIN hash is PBKDF2-SHA256 at 210,000 (code: `Security.cs:57`); keep the format or version it for data migration |
| L1 Trusted devices never expire | L | Open (code: `appsettings.json:9` `TrustLifetimeDays: null`, `AuthAccounts.cs:51`) | none | Q: default 30 to 90 days? Startup rejects zero or negative (exists) |
| L2 Access token valid after sign-out | L | Open (code: `SessionService.SignOut` revokes refresh tokens only) | none | Decide: bump `SecurityVersion` or track a session id |
| L3 Concurrent refresh signs the user out (reuse of a rotated token revokes the device family) | L | Open (code: `SessionService.Refresh`) | none | Decide: grace window of about 10 s |
| L6 No HTTPS redirect/HSTS, `AllowedHosts "*"`, `TrustServerCertificate=True` | L | Open (N8; code: `appsettings.json:22`) | none | Real hosts and TLS validation in the Python deployment |
| L8 One secret for JWT signing and token/code HMAC | L | Open (no HKDF in code) | none | Derive a separate hashing key |
| L9 "That mobile number or email already belongs to someone" reveals cross-tenant existence | L | Open (code: `AccessUseCases.cs:124`) | none | Generic message (only `people.manage` can reach it) |
| L10 `DotNetEnv.Env.TraversePath().Load()` in every environment | L | Open (N7; code: `Program.cs:20`) | none | No `.env` loading outside development |
| L11 PII in logs | L | unverified | dev mailer registered only for Development/Testing on a local DB (code: `Program.cs:73`) | No code or email in logs outside dev |
| L4, L5, L7, L12, L13 | L | web or mobile only | n/a | none |

Account lifecycle rules from the PR reviews in the same area: an access change bumps `SecurityVersion` so old tokens are refused (`pr-3-codex-review.md` PR #2 table); saved security policy (PIN length, lockout, token lifetimes) applies at sign-in (#4); lockout minimum three tries and pause capped at one hour (Build Notes section 2); `AllowPinSignIn = false` is refused with 400 (`phase-2-plan.md` D6).

### 3.2 Safety (`audit/safety.md`; API-relevant items only)

| Id | Sev | State | Fix mechanism | Inherits |
|---|---|---|---|---|
| M6 Two phone normalisers, C# E.164 vs TS local | M | Fixed 2 (C#); Residual 3 (TS) | `PhoneNumber` value object (E.164); the `+254...` digit-drop bug fixed (Codex #19) | E.164 canonical form; shared golden vectors were advised (`audit/integrity.md` section 4) |
| M17 Revenue `Save` race between `Record` and `Add` | M | Fixed 2 | unique (Org, Vehicle, Date) index plus `Version` token; concurrency and unique violations become `RevenueConflictException` / 409 | Unique index and 409 mapping; test with two concurrent first saves |
| M11 to M14 Organization endpoints use `AuthDb`, a section switch, a leaking `JsonDocument`, two error conventions | M | Fixed 5 | `OrganizationSettingsUseCases` over `ISetupExecution`; `ISettingsSection` strategies; `ArchitectureTests` forbids `AuthDb`/`IClock`/`IOrganizationRepository` in handlers | Layering rule; one error mapping (`WithSetupErrors`); DTOs serialise exactly as the old entities (`SettingsContractTests`, `Phase1ContractTests`) |
| M15 Anemic `Organization` entities | M | Open, low (`findings/phase-5-6.md` E-TDA-Organization); `ChangeTimeZone` wired in Fixed 5 | `Organization.ChangeTimeZone` called from the localization section, no extra version bump | Validate at construction; one version bump per change |
| M16 `ContrastValidator` checks two light surfaces only | M | Open, product question | none | Q: dark-theme contrast rule |
| L18 to L25 (note length 80, null-forgiving casts, `SingleAsync` gives 500 for missing org, tz lookup 400 vs 500) | L | Open, low | none | Explicit 404/500 mapping; note max 80 characters |

### 3.3 Integrity (`audit/integrity.md`)

| Id | Sev | State | Fix mechanism | Inherits |
|---|---|---|---|---|
| Anemic auth entities (`User`, `RefreshToken`, codes, devices, audit event) | H | Fixed 2 | behaviour methods, private setters (`User.RecordFailedAttempt`, `SetPin`, lockout reset) | Lockout rules live in the entity |
| No concurrency token on `User` / `RefreshToken` | M | Fixed 2 | `Version` token bumped by `AuthDb.BumpVersions()`; migration `20261006084351_UntrustedFailedAttempts` | A token that never changes is inert (`C:` trap): the rewrite needs a real bump on write |
| Revenue concurrent save not mapped to 409 | H | Fixed 2 | see Safety M17; contract C2 in `phase-2-plan.md` | 200 `{id,version}`, 409 `{title,detail,status,current}`, 400 `earliestMissing` |
| `NumberDecimals` (0 to 6) vs 2 dp storage; `kes()` shows no decimals on whole amounts | H | Residual 2, Q | D3 keeps 2 dp storage; display follows `numberDecimals` | Decide the display rule before porting formatted strings |
| `OrganizationMembership.Version` public setter; `SettingsVersion` bumped only if callers remember | M | Fixed 5 (single writer); setter open, low | `SettingsChangeLog.Record` is the only bumper; `Deactivate`/`Reactivate` bump `Version` | Same single-writer rule |
| Monthly schedules on day 29 to 31 skip short months (web presentation; server rule unverified) | M | unverified | `DueDateGenerator`, `ScheduledItemRulesTests` exist | Q: confirm the server clamps to the last day |
| TS amount parser vs C# `Money()`; reasons and periods lists in several places | M | Open, low (E-Reasons, E-Periods) | `CellStatusesMatchTheClients` covers statuses only | One source for reasons (Garage, Arrest, No Crew, Other; C# accepts "NoCrew" and "No Crew") and periods (today, week, month) |
| Test gaps: concurrent saves, `Money()` boundaries | M | Fixed 2 (unverified which tests) | see `inventory-tests.md` | Port boundaries: 999999999999.99, 0.001, negative, zero |

### 3.4 Operability (`audit/operability.md`; Phase 3, then 6)

| Id | Sev | State | Fix mechanism | Inherits |
|---|---|---|---|---|
| 1 No CI/CD, no deploy artifact | C | Phase 6 written, local run pending | `.github/workflows/ci.yml` jobs `js`, `mobile`, `api`, `api-sqlserver`; Dockerfiles; root scripts | The rewrite needs its own pipeline with the same gates |
| 2 Migrations run at startup in every replica | C | Fixed 3 | `--migrate` command; Production never creates or migrates (`ProductionStartupDoesNotCreateOrMigrateTheSchema`); only Development auto-migrates a local DB | Migrations as a separate deploy step |
| 3 Logging unstructured, no correlation | H | Fixed 3 | `X-Request-ID` middleware; JSON console with scopes outside Development; ProblemDetails carries `requestId` and `traceId` | Request id in every log line and error body; `X-Request-ID` excluded from byte-for-byte checks |
| 5 `/health` checks nothing | H | Fixed 3 | `DatabaseHealthCheck` (`CanConnectAsync`, 10 s) tagged "ready"; `/health/live`, `/health/ready`; `GET /health` unchanged (staging `start.js` depends on it) | Keep all three routes; readiness 503 when the DB is down |
| 6 Configuration not validated | H | Fixed 3 | `ProductionStartupTests`: missing `Email:Host`, `Email:From`, connection string, signing key under 32 bytes fail startup | Fail-fast config |
| 17 No DB retry; 2 queries per request in token validation | H | Retry Fixed 3; per-request cache deliberately not built (N1 open) | `EnableRetryOnFailure(3, 5 s)`; user transaction inside `CreateExecutionStrategy().ExecuteAsync`; the 30 s session cache existed ~13:35 on 2026-10-06 and accepted revoked tokens (`AccessLifecycleTests` x2, `Phase1AuthContractTests.SwitchUserRevokesThisPhone`) so it was removed | No auth cache unless it is invalidated on `SecurityVersion` change and revocation, with a test that a revoked token fails at once |
| 15, 16 Hardcoded limits, `AllowedHosts`, CORS | M | Partly (rate limit config); Open (N6, N8) | `RateLimiting:AuthPermitLimit` | Rate limit only `auth`; decide `/setup/*` limiter |
| 20, 21 PII in dev logs; no auth-event audit trail | M | unverified / Open | n/a | Q: auth-event logging (sign-in failures, lockouts, revocations) |
| 25, 26 Shutdown, `.env` loading | L | Open (26) | n/a | see Security L10 |
| 4, 7 to 14, 18, 19, 22 to 24 | | web/mobile or unverified | web proxy logging, mobile timeout, error boundaries (Fixed 3 per `findings/phase-4.md` "Seen fixed") | none for the API |

### 3.5 Scalability (`audit/scalability.md`; `findings/phase-4.md`; Phase 4, evidence in `handoff/phase-4-parent.md`)

Full API suite at the latest recorded run: 364/364 (`Category!=SqlServer`, 11 m 40 s, 2026-10-08, `phase-6-parent.md` row V).

| Id | Sev | State | Fix mechanism | Inherits |
|---|---|---|---|---|
| 1 Weekly grid unpaged, cartesian Include | H | Fixed 4 | `GET setup/revenue` takes `page`/`pageSize` (`SetupPagination.Validate`, 400 outside range); without them: page 1 of up to 500 vehicles (`RevenueWeekPage.LegacyLimit`) with `truncated` and `totalVehicles`; `dayTotals` and `firstGap` over the whole filtered, scoped grid; `firstGap` not permission-gated (clients gate on `revenue.capture`); `vehicleId` request never paged; clients merge pages at 100 | Yes: the additive paging contract, legacy cap 500, week totals summed unrounded then rounded once (2700/3000/90 pins), `counted = date < today or record exists` |
| 2 Dashboard aggregated in memory; no cache | H | Fixed 4 | SQL aggregation; `RevenueDashboardCache` decorator (`CachedRevenueRepository`) keyed org + `SettingsVersion` + business date + period + company + scope hash; unmasked figures cached, `Visible` (per-card masking) applied per request after; TTL 60 s bounds memory only | Cache the unmasked DTO, mask after; invalidation rides on `SettingsVersion`; any write that changes a figure must go through `SettingsChangeLog.Record`, else stale up to 60 s; per-day expected = sum of `TargetOn(d)/7`, one `decimal.Round(.,2)`, percent from unrounded values |
| 3 Change log OR-chain, missing indexes, OFFSET paging, COUNT per page | H | Fixed 4 | nullable `VehicleId` column (migration `20261007052529_ChangeLogVehicle`, batched backfill as public consts, `ONLINE` index); keyset paging (`before`, `hasMore`, `nextBefore`; legacy `page` kept); `HistoryCountCache` keyed on `SettingsVersion` and scope; `includeTotal=false`; company not denormalised (visibility follows the current scope) | Keyset on the per-org monotonic `Version`; `Page<T>` numeric fields kept; `total` not nulled on later pages (Phase 1 clients); SQL Server branch of the migration never ran (Residual 13) |
| 4 Two auth queries per request plus ~9 context queries | H | Open (N1) | none; first attempt broke revocation | Q: build a cache? If yes: key `SettingsVersion` + `SecurityVersion`, explicit invalidation, revoked-token test |
| 5 `useStreamedList` sequential, uncancellable | M | Fixed 4 (web) | pool of 3, abort, batched state | Complete lists stay complete (web duplicate checks rely on them); do not make lists infinite-scroll |
| 8 Visibility predicates, per-row subqueries | M | Open (N2) | none | Branch on `actor.AllCompanies` in code, not inside SQL (pattern `PeopleVisibility.cs:19-20`) |
| 9 No response compression | M | Fixed 4 | Brotli (Optimal) and Gzip on `/setup/*` only (`Program.cs`); `/auth/*` excluded (tokens in bodies, BREACH); web proxy streams the body | Compress `/setup/*` only; keep gzip for phones; body sizes: history 62,581 B to 6,483 gzip |
| 10 Whole-row `RevenueRecord` reads; no covering index | M | Projection planned with item 1 (not itemised in the checklist, unverified); optional INCLUDE index skipped (checklist item 2) | narrow projections | Index `(OrgId, BusinessDate)` without INCLUDE is accepted |
| 11 `EarliestMissing` join and big IN-list | M | Kept (O(V) with fallback); IN-list translation on EF 10 / SQL Server 2,100-parameter limit unverified | deliberate design | Same earliest-missing semantics over the vehicle's whole history, never only the week; PostgreSQL has no 2,100 limit but verify planner behaviour |
| 16 No ETag or reference-data cache | L | Open (N4); `/setup/appearance` embeds the logo as base64 up to 256 KB | none | Q: ETag keyed on `SettingsVersion` for `/setup/appearance` |
| 17 `Vehicles()`/`Recurring()` 3 to 4 round trips; `Report()` Include chain | L | Open (N3); allocation index claim NR (N3b) | none | none |
| 18 `Memberships` correlated lookup index | L | NR (3g) | PK `(OrganizationId, UserId)` serves it | none |
| 12 to 15, 6, 7 Intl cache, date arithmetic, client cache, virtualisation | L/M | Fixed 4 (client) | `intlCache.ts`, `weekDays()`, `useResource` cache, windowed grid above 60 vehicles | none for the API |

Observation worth carrying (`findings/phase-4.md` Observation; README residual 11): every audited write bumps one row, `Organization.SettingsVersion`, a concurrency token inside a serializable transaction. Collisions retry 3 times then a revenue save answers 409 "This day was changed by another save". Capture bursts serialize there and also move the dashboard cache key, so the dashboard is mostly computed fresh during a burst. A per-org sequence for change-log versions is the noted candidate; nothing measured.

### 3.6 Extensibility (`audit/extensibility.md`; Phase 5, evidence in `handoff/phase-5-parent.md`)

| Id | Sev | State | Fix mechanism | Inherits |
|---|---|---|---|---|
| Organization endpoints bypass the application layer | H | Fixed 5 | see 3.2 M11 to M14 | Endpoint = transport, use case = rules |
| Settings section switch; dead `SettingsSectionRegistry` | M | Fixed 5 | `ISettingsSection` strategies (`MergedSection<T>` x3, organization, businessDate); registry deleted | One strategy per settings section; unknown fields merged by name, case-insensitive, with legacy names accepted |
| Settings writes had no transaction or change-log retry | M | Fixed 5 (behaviour change) | settings, logo and preference writes via `execution.Write` (serializable, 3 retries); test `SettingsWritesRetryWhenOnlyTheChangeLogCollides`; slug 409 test | All writes in one transaction with change-log retry |
| Revenue cell status re-derived in four places | H | Fixed 5 | C# `CellStatus` enum, wire values `none`, `future`, `missing`, `amount`, `reason` via per-type converter (other enums stay numeric); `CellStatusesKeepTheirWireValues`, `CellStatusesMatchTheClients` | String statuses on the wire for cells; numeric for other enums (assumption A5) |
| Permission keys as bare strings | M | Fixed 5 | `Domain/PermissionKeys.cs`, `PermissionCatalog.Refusal`; `PermissionKeysTests.TheSharedKeyListMatchesTheCatalog` prints the list to paste | One key list; unknown key must not 500 |
| `AuthService` 9 operations, hidden `outgoing` mail state | M | Fixed 5 | split into `SignInService`, `PinSetupService`, `SessionService`; `AuthResult.Mail`; `ChangeTracker.Clear()` per retry; tests `ACodeFromARolledBackAttemptIsNeverSent`, `ARetriedAttemptStartsFromTheDatabase`, `RevokingADeviceWaitsForTheAccountsOtherAuthWork` | Mail only after commit and after the lock is released; never from a rolled-back attempt |
| `Program.cs` mixes env checks, DI, CLI, inline JWT validation | M | Partly (Phase 3 rewrote it); re-check pending (E-Program) | n/a | Separate startup, hosting and validators |
| Dead abstractions `IUnitOfWork`, `OrganizationUseCase<,>` | M | NR (live); `ChangeTimeZone` live after 5 | kept | Keep the pipeline |
| `RevenueUseCases.Save` mixes policy and text; `RevenueCellDto.For` computes `canEdit` | M | Open, low (E-RevenueSave) | none | A `RevenueCapturePolicy` shared by save and cell |
| Auth operations list in 5 places (E-AuthOps), `AuthError` ternary | L | Open, low | none | Single list of auth operations |

### 3.7 Maintainability (`audit/maintainability.md`; Phase 6; API-relevant items only)

| Id | Sev | State | Fix mechanism | Inherits |
|---|---|---|---|---|
| C1 `useGroupping` typo in the API contract | M | Fixed 6 (checklist rows 6b to 6f) | migration `20261007181520_RenameUseGrouping` (`RenameColumn` only; `MigrationSnapshotTests.TheGroupingColumnIsRenamedInPlace`); `OrganizationLocalization.UseGrouping`; `MergedSection` `legacyNames` accepts a PUT body field `useGroupping` (current name wins); `EffectiveFormats.UseGroupping` kept read-only as legacy output so installed clients still read `formats.useGroupping`; change-log label key renamed; phone cache and web fixtures accept both | Emit and accept both names for one release; new name wins when both are present; old change-log snapshots keep the old key (display-only history) |
| D5/T9 No CI; API test project named `Auth.Tests` with one trait | M/L | CI written (Phase 6 1a to 1g); test traits open, low | `Category!=SqlServer` filter; `api-sqlserver` job with `SQLSERVER_TEST_CONNECTION` | Mark slow DB-integration tests; run the migration test against the real engine in CI |
| D1 to D3 Toolchain split | M | Fixed 6 (client) | pins and guards in `eslint-rules/tests/toolchain.test.mjs` | none for the API |
| T1 to T8, C2 to C7, X1 to X4, U1 to U6 (test coverage, formatter, giant components, UI) | | Fixed 6 or open-low, client only | Prettier 3.9.9, coverage thresholds for shared, AuthFlow reducer, screen splits | none for the API |

Note on `Program.cs` hygiene: README residual 9 records plan IDs found in comments (`P3-*`) and their removal; house rule: no plan or provision IDs in code comments.

### 3.8 Earlier reviews (before the remediation program)

| Source and id | Area | State at review | What the rewrite inherits |
|---|---|---|---|
| `pr-3-codex-review.md` #1 to #5, #8, #9, #11, #19, #22 to #24 (24 findings, all Fixed or Already fixed on 2026-09-26) | API auth, access, settings, vehicles | Fixed | Phone lookup after normalisation; membership required for tokens (upgraded and provisioned users get one); failed code attempts counted; saved security policy applied; postponing a not-yet-started schedule supersedes the old version; `/setup/organization/*` errors map to 4xx not 500; `people.manage` alone cannot grant `access.manage`; PIN-request response identical for known and unknown numbers; inactive people keep their permissions on edit; moving `JoinedOn` earlier backfills the target; the required reason is stored in the audit event |
| `settings-setup-review.md` S1, S2 | Owner deactivation; identity change takeover | Fixed 2026-09-26 | Owner cannot be deactivated or signed out by a non-Owner; sign-in details change only for someone whose permissions the editor holds (Build Notes section 2, D10) |
| S9 Two sources of role permissions | access | Open at review; Build Notes priority 1 and D10 decided "one list" | Role defaults in one place; Owner = every key except `dash.capture`; Office admin drops `dash.capture`, `dash.investment`, `revenue.capture`, `revenue.no_earnings`, `bills.approve` |
| S10, S11, S12 Scoped admin saves, partly-visible recurring items fail 403, recurring list pages by GUID | access, recurring | Open at review (re-checked 2026-09-26); D12 limits `PersonDto` to the viewer's reach with `otherCompanies`/`otherVehicles` counts | State since then not recorded in this folder: check `inventory-domain.md` |
| S15 Vehicles cannot leave the fleet | vehicles | Question, then decided: "left the fleet" date (Build Notes section 2, D4) | Leave date ends target, stops share of scheduled items, keeps the vehicle in past reports |
| S17 One org-wide version for all setup writes | setup | Open; still true (README residual 11, hot `SettingsVersion` row) | see 3.5 Observation |
| S18 Reads run in serializable transactions; a GET writes | setup | Fixed (reads open no transaction, `PeopleQueryCostTests` `Transactions == 0`; a read that changes state throws) | Reads never write |
| S20 Unlimited backdating | recurring | Decided: scheduled items start no earlier than the first of the current month | C4 rule in `phase-2-plan.md` |
| S21 Lockout threshold of 1 | settings | Decided: minimum three tries, pause at most one hour; a reset by email lifts it | Clamp (`NormalizeSecurityPolicy.ClampSql`, `SecurityPolicyBounds.Clamp`) |
| S13, S16 Change log thin, raw request stored as "after"; no-op saves create versions | change log | Partly fixed; Phase 5 keeps "no-change save adds no version or log entry" (`ChangeLogAndScopeTests.SettingsHistoryRecordsWhatWasSavedAndSkipsUnchangedSaves`) | No-op saves write nothing |
| `phase-2-plan.md` D1 to D16, C1 to C7 | decisions and contracts | Frozen 2026-09-29/30 | See `inventory-http-contract.md`; notably C1 403 `detail`, C2 revenue, C3 expense catalog, C4 scheduled items, C5 investment, C6 vehicle report v2 (`net = moneyIn - moneyOut`, `afterSavings = net - savings`), C7 automatic reasons; D3 2 dp; D4 recorded revenue never disappears; D5 authorise before disclosing 409; D11 people section of the change log needs `people.view`; D15 `GET /setup/access/me` |

## 4. Open items

"Owner" is who the .NET program assigned it to. Action: BUILD = the rewrite should implement it correctly from the start; DEFER = not needed for parity; DECIDE = a planner or product decision is needed first (section 7 numbers the questions). Source for residuals 1 to 13: `R:README.md` lines 76 to 135.

### 4.1 README residuals

| # | Item (one line) | State on 2026-10-08 | Owner | Rewrite action |
|---|---|---|---|---|
| 1 | `IsLocalDatabase` matches substrings; no explicit opt-in for log mailer; no startup failure for Development + non-local DB | Open (code: `Program.cs:28`) | Closure | BUILD: parse host exactly; opt-in flag for dev code, log mailer, demo seed; fail startup otherwise |
| 2 | `kes()` shows whole amounts without decimals, others with `numberDecimals` | Open, product decision | Product | DECIDE Q2: affects every money string and test expectation |
| 3 | TS phone helpers keep local form, no TS E.164 type | Open, accepted | none | BUILD E.164 server side only; DEFER the TS mirror |
| 4 | Pure-TS PBKDF2 (100k) speed on low-end Android unmeasured | Open (mobile) | mobile | DEFER; do not lower iterations; server hash unchanged |
| 5 | AuthFlow recovery after a profile-load failure replays a consumed one-time code | Fixed 6 (checklist 3g: pad + message; the consuming endpoint is sent exactly once) | Phase 6 | BUILD: keep `verify-device`, `setup-pin/complete`, `pin-reset/complete` consuming the code exactly once |
| 6 | Web `API_URL` missing is a per-request 503, not a startup failure | Open (web) | none | DEFER (web) |
| 7 | Response-shape validation of session GET and shared auth client | Client Fixed 6 (3h: `unexpected_response` for 2xx non-JSON or unknown status); session GET body still unvalidated | Closure | BUILD: every `/auth/*` answer is JSON with a known `status`; never a 2xx HTML body |
| 8 | Mobile unlock on a 5xx | Fixed 2026-10-06 (client falls to offline unlock on `AuthError.httpStatus >= 500`) | Phase 2 | BUILD: server faults on `/auth/unlock` and `/auth/sign-in` must be 5xx, not 4xx |
| 9 | Phase 3 history (cache accepted revoked tokens; readiness never touched DB) | Closed in the Phase 3 closing note | Phase 3 | BUILD the lessons (3.4 rows 17 and 5) |
| 10 | Mail from a rolled-back retry attempt | Fixed 5 | Phase 5 | BUILD: send only the committed attempt's mail; clear tracked state per retry |
| 11 | Unowned: ~11 context queries per setup request; heavy visibility predicates; no ETag or reference caching; non-revenue lists unmemoised (web); rate limit only on `/auth`; `.env` loaded everywhere; `AllowedHosts "*"`, `TrustServerCertificate`, no HTTPS/HSTS; hot `SettingsVersion` row | Open (N1 to N8; N9 global semaphore Fixed) | none, for closure | see 4.2 |
| 12 | Phase 5 behaviour changes to confirm (mobile More lists Vehicles for `invest.view`; "Not yet" label; dark shade `#16202F`); compat re-exports; petty-cash private permission aliases; sibling inventories cite the deleted `AuthService.cs` | Open (client); inventories to refresh | conversion session | DEFER client items; refresh the sibling inventories (`inventory-auth.md` and others) |
| 13 | Phase 4: SQL Server branch of `ChangeLogVehicle` never run; one test retires a vehicle directly in the DB and calls `SettingsChanged()`; windowed-grid keyboard path untested; week pages offset-paged (a removal between requests can skip a vehicle, a duplicate is merged away); week query still reads every grid vehicle's calendar; no e2e test of proxy-requested compression; `clearDataCache()` leaves mounted hooks unsubscribed | Open | Phase 4 | DECIDE Q6 (week paging: offset or keyset); BUILD a compression test; DEFER the rest |

### 4.2 Owned by no phase (README residual 11; `findings/phase-4.md` N1 to N9)

| Id | Item | Owner | Rewrite action |
|---|---|---|---|
| N1 | ~11 context queries per setup request (membership, permissions, scope, localization tz, business date, token checks) | none | DECIDE Q5: cache per (org, user) keyed on `SettingsVersion` + `SecurityVersion`, or one query; the .NET attempt was removed for accepting revoked tokens |
| N2 | Visibility predicates (nested Any, repeated NOT-EXISTS "current version", per-row subqueries) | none | BUILD simpler: branch on all-companies in code, join company, one grouped count; optional `IsCurrent` flag |
| N3 / N3b | `Vehicles()` / `Recurring()` multiple round trips, `Report()` Include chain / allocation index claim not reproducible | none | DEFER; no extra allocation index |
| N4 / N4b | ETag and reference-data cache; logo is embedded in `GET /setup/appearance` (there is no logo GET) | none | DECIDE Q7 |
| N5 | Non-revenue web lists unmemoised | none | not an API item |
| N6 | Rate limiting only on `/auth` (fixed 1-minute window, configurable permit) | none | DECIDE Q8: add a `/setup/*` limiter? |
| N7 | `.env` loaded in every environment | none | BUILD: development only |
| N8 | `AllowedHosts "*"`, `TrustServerCertificate=True`, no HTTPS redirect/HSTS, CORS default localhost | none | BUILD real host, TLS, HSTS settings |
| N9 | Global auth semaphore | Fixed 1 | BUILD per-account lock |
| N-hot | One `Organization.SettingsVersion` row serialises capture bursts | none | DECIDE Q9: measure first; a per-org sequence is the candidate |

### 4.3 Unowned findings from `findings/phase-5-6.md` ("Unowned findings")

| Id | Item | Rewrite action |
|---|---|---|
| E-RevenueSave, E-Reasons, E-Periods | capture policy class; reasons and periods encoded in several places | BUILD one table each (reasons Garage, Arrest, No Crew, Other; periods today, week, month) |
| E-Program | startup and hosting separation | BUILD |
| E-TDA-Organization | public setters and validate-on-demand on org entities | BUILD validated at construction |
| S-M7, S-M8, S-keepSession | client auth validation, PIN minimum in client, empty tokens stored | client; API: keep `invalid_pin` consistent with the policy `pinLength`, never answer an authenticated 200 without both tokens |
| E-AuthOps, E-AuthError, E-FormatSplit, E-ApiTypes, E-ViewRegistry, E-UI-API, M-T7/8/9, M-C3/C7/D4/D5, M-U6, E-DIP-mobile, E-HTTP-web | client or tooling | DEFER |

### 4.4 Backlog (`docs/backlog.md`) and scope

| # | Item | Owner | Rewrite action |
|---|---|---|---|
| 2 | Revenue capture jumps to another vehicle after a save. Decided 2026-10-06: the person chooses "one day, all vehicles" or "one vehicle, all its days", always announced, remembered per person | web and mobile (after Phase 5 item 2, now done: rules in `@xcode/shared/capture`) | DEFER: no API change planned. Q10: is the choice stored server side (a preference) or on the client? |
| 1 | Bulk import and export of vehicles and history (xlsx, csv, txt, sql) with preview, all-or-nothing, repeat-safe (match by registration and by vehicle + date), change-log entry | unscheduled | DEFER the feature; DECIDE Q11 (SQL files, conflicts, fields, who may import, limits); BUILD the write path so a batch can be applied in one transaction through the domain model, keeping the ordered-backfill rule (`RevenueEarlierDayMissingException`), join and leave bounds, and the business date |
| Scope | Petty cash (Build Notes section 5) and Reports (section 6). Code has `PettyCashEntry`, `PettyCashKind`, `PettyCashStatus`, `PettyCashUseCases`, `PettyCashRepository`; `docs/petty-cash-contract.md` exists; Reports state not found in this folder | petty-cash session | Q12: which of petty cash and reports are in the first rewrite release |
| Closure | `closure.md` crosswalk (every audit finding with evidence), SqlServer test run, `REMEDIATION-CLOSURE.md` | closure session | Phases 1 to 3 have no checklist in the folder: treat their states as reported, not independently verified |

## 5. Lessons for the rewrite's own process

One line each. Sources: `C:` "Known traps" (lines 62 to 76), "Remediation execution rules" (46 to 60), "Working in a shared tree" (37 to 44), `R:README.md` handover and residual 9, `R:handoff/phase-4-parent.md`, `phase-6-parent.md`.

### 5.1 Known traps (each cost a previous session time)

| Trap | Lesson for Python + PostgreSQL |
|---|---|
| SQLite test DB stores Guids as uppercase TEXT, compares case-sensitively; raw SQL with `'{guid}'` fails | Do not test on a different engine than production. Run the integration suite on real PostgreSQL (UUID type) and keep SQLite out of it |
| SQLite cannot sum decimals or compare/order instants (`R:findings/phase-4.md` section 0) | Aggregates, ordering of instants and decimal sums need a real-engine test. Only `SqlServerTests` proved anything about SQL Server and it only applied migrations |
| `MigrationSnapshotTests` fails on any model change without a migration; never hand-edit the snapshot; tests use `EnsureCreated`, so only a real-engine test proves a migration applies | Same gate for Alembic: autogenerate-diff test in CI plus apply-from-empty and apply-over-data tests on PostgreSQL. Data backfills are explicit SQL, exposed as a constant and tested |
| An `IsConcurrencyToken()` property that never changes is inert | Every versioned row needs a test that a stale write fails. `RevenueRecord` and `OrganizationMembership` bump in domain methods; `User` and `RefreshToken` in `AuthDb.BumpVersions()` |
| Formatting: `createFormatter(formats)`, no module-level mutable formatter state (leaks across SSR requests) | No process-global per-tenant state in the Python app (locale, currency, org settings) |
| Auth lockout model (see section 3.1 M2) | Port the model exactly and test each branch: trusted pause, untrusted cap, unknown-number answer, cap reset only on `SetPin` or verified new device |
| AuthTests `Seen` compares whole responses byte for byte | Any new per-request header (for example `X-Request-ID`) must be excluded there; keep `/auth/*` bodies identical |
| Caches touching auth or permissions need explicit invalidation on `SecurityVersion` change and revocation, plus a test that a revoked token stops working immediately; `VehicleReportTests` asserts exact query counts | No auth cache without both. Keep query-count tests (`DatabaseProbe`, `RevenueComplexityTests`) and change counts deliberately |
| Next.js 16 and React Native/Hermes differ from training data; jest hides missing platform APIs | Client traps; the API side only needs to keep contracts stable |
| Machine load: 1 to 4 s waits time out; 8 HttpClient `TaskCanceledException` failures appeared under 1 h 15 m of load (`phase-6-parent.md` baseline) | Re-run a single file before diagnosing; do not shorten test timeouts to hide it |
| Full API suite takes 10 to 12 minutes; use `--blame`; isolate build output with `--artifacts-path` when another session builds | Plan for fast targeted runs first, full suite once at the end |

### 5.2 Test-evidence standard (`C:` lines 46 to 60)

| Rule | One line |
|---|---|
| Evidence per item | The code path (file and symbol) plus a test that would fail without the change; revert-check it |
| No inert helpers | A helper or type nothing calls is not an implementation |
| No self-faking tests | A test that fakes the capability being added is not evidence. Example: `ReadinessProbeChecksDatabase` asserted only a 200 and could not fail, so item 3 was not done (README residual 9) |
| Declared invariants enforced | A concurrency token must change, a cache must be invalidated, a cap must be checked |
| No weakening | Do not remove or loosen assertions; prove a wrong expectation against the HTTP or domain contract |
| No silent contract breaks | Migrate all callers (web and mobile) and stored client data (mobile secure-store JSON); additive changes only for shipped phones |
| Checklist per clause | One row per plan item and per clause; re-read each item's literal text before reporting done |
| Baseline first | Record relevant tests and typechecks before changing code, so failures can be attributed |

### 5.3 Shared-tree rules (`C:` lines 37 to 44)

Several sessions edit one worktree. `git status` and file times before changing anything; small targeted edits after re-reading; never revert, tidy or reformat other sessions' changes; attribute a failing test (file and code mtimes, diffs) before fixing it and report in-flight breakage instead; never kill `dotnet`/`testhost`/`node` you did not start; never bare `git stash` / `git stash pop`. House rules: no comments unless needed; no plan or provision IDs in code comments; commits authored by the configured user, no AI trailers.

### 5.4 What earlier sessions got wrong (README handover and residual 9; phase parents)

| What went wrong | Lesson |
|---|---|
| A 30 s per-request session cache accepted revoked tokens (broke `AccessLifecycleTests` x2, `SwitchUserRevokesThisPhone`, and the `VehicleReportTests` query counts) | Do auth caching last, with the invalidation test written first |
| `/health/ready` filtered on a tag with no check registered; its test could not fail | A probe test must fail when the dependency is down (`ReadinessProbeFailsWhenDatabaseIsUnreachable` asserts 503) |
| The "phase 1" commit 4318865 covered phases 1 to 3; Phase 1 had gaps closed during Phase 2 | Commit each phase on its own, including every new file |
| A mobile type error survived two phases because the mobile typecheck was skipped | All typechecks are mandatory; for Python, type-check (mypy or pyright) and lint in CI from day one |
| A retried transaction attempt re-used the rolled-back attempt's tracked rows and failed on `Version`; the retry also re-sent mail from the rolled-back attempt | Clear the unit-of-work state per retry; deliver mail after commit for the committed attempt only |
| Plan IDs (`P3-11`) left in comments in `Program.cs` and `OperabilityTests.cs` | Keep plan IDs out of code |
| A hung background command from one session copied a backup over `RevenuePage.tsx` while another session was editing (2026-10-07 21:41) | Never copy backups over files in a shared tree; one writer per file set |
| Draft phase prompts contained wrong claims: "build on the existing `SettingsSectionRegistry`" (dead and too thin), "`IUnitOfWork` is dead" (live), wiring `ChangeTimeZone` as written double-bumps `SettingsVersion`, `lint` script "missing" (it existed) | Re-verify every finding against current code before acting; line numbers drift within hours |
| The first verified-findings pass was written while another phase was editing the same files ("volatile") | Findings are a snapshot; record the time and the tree state |
| A cache test wrote behind the cache (direct DB helpers never bump `SettingsVersion`) | Tests that write around the application must go through the version bump or clear the cache; do not loosen assertions |
| Sibling inventories still cite the deleted `AuthService.cs` | Refresh inventories when code is split or deleted |
| An audit fix ("real load more or infinite scroll") would have broken web screens that need complete lists (`CompaniesPage` duplicate check, `VehiclesPage`) | Check callers (web and mobile) before changing list contracts (`findings/phase-4.md` section 0) |

## 6. Product vocabulary

Sources: `D:design/XCODE_Build Notes_v1.0.pdf` (addendum 1, 28 Sep 2026; "BN" with section), the audits, and .NET names I confirmed by grep in `apps/api/Domain` and `apps/api/Application`. The sibling `docs/11-naming.md` was deliberately not read; align it with this table. "Rewrite use" is a suggestion for the planner, not a decision.

| Term (product) | Meaning | .NET name | Rewrite use |
|---|---|---|---|
| Organization | The tenant: a transport business. Everything is scoped to it; the JWT carries an `org` claim | `Organization` (`Slug`, `Name`, `BusinessDate`, `SettingsVersion`); `IOrganizationEntity.OrganizationId` on every tenant row | `organization` / `organization_id`; keep the `org` claim name and the first-in-every-index rule |
| Organization settings | Sections: organization, localization, branding, securityPolicy, businessDate; GET/PUT `/setup/organization/settings/{section}`; partial sections keep omitted fields | `OrganizationLocalization`, `OrganizationBranding`, `OrganizationSecurityPolicy`, `UserPreference`, `ISettingsSection` | Keep section keys and merge-by-name; the personal preference may only choose what the organization allows (`EnsureAllowed`) |
| Business date | The organization's "today", held in the organization record; every screen takes today from it, never the computer clock (BN 3). Cannot be set to a date in the future in the organization's time zone | `Organization.BusinessDate` (`DateOnly?`), `SetupActor.Today`, `EnsureBusinessDateWithin`, `ChangeBusinessDate` | One function computes "today" per request from organization time zone plus the held date; changing the time zone re-checks the held date |
| PSV company | A public service vehicle operator the fleet belongs to (a matatu SACCO or company, for example "Zuri Genesis", "Metro Trans" in the demo seed). Archived, never deleted (BN 2). "SACCO" also appears as an expense item name ("SACCO fee") and a savings name in the design mockups; the word is not a type in the code | `PsvCompany`; scope as `SetupCompanyScope` | Table `psv_company`; keep "archived, never deleted"; do not name a type `Sacco` |
| Fleet vehicle | A vehicle with a unique registration per organization, joined date, optional "left the fleet" date; restorable. A departed vehicle stays in every past report (BN 2). Recorded revenue never disappears (D4) | `FleetVehicle` (`JoinedOn`, `LeftOn`, `ActiveOn`, `Retire`, `Restore`), `VehicleAwayPeriod` | Keep `ActiveOn`/`AwayOn` as the single source for expected and missing days |
| Weekly target | A dated weekly amount per vehicle; expected per day = target applying that day divided by 7. Targets are append-only history | `VehicleTarget`, `FleetVehicle.TargetOn(date)` (one pass, revision tie-break) | Keep dated, never overwritten; compute per day, round once |
| Revenue capture | Recording one `RevenueRecord` per vehicle per day: an amount, or a reason. A missing day must be filled before a later one for that vehicle; "after saving, move to the next vehicle still missing that day" is a client rule (BN 4, backlog 2) | `RevenueRecord`, `RevenueEntry`, `RevenueUseCases.Save`, `RevenueEarlierDayMissingException`; `GET /setup/revenue`, `PUT /setup/revenue/{vehicleId}/{yyyy-MM-dd}` | Server enforces order, bounds, version, replay; contract C2 |
| Correct revenue after the day | Changing a past day needs this permission and is recorded as an edit; a same-day change is an update (A3) | `RevenueRecord.CorrectedAfterDate`, permission `revenue.correct` | Keep "edited after capture" semantics for dashboard counts (D2) |
| No-earnings reason | Why a day has no amount: Garage, Arrest, No Crew, Other (Other needs a note up to 80 characters). Needs `revenue.no_earnings` | `RevenueNoEarningsReason`; request string accepts "No Crew" and "NoCrew" | One list, one parser; wire strings are the labels |
| Cell status | State of a vehicle-day in the grid: none, future, missing, amount, reason | `CellStatus` (string wire values via converter); `RevenueCellDto` (`canEdit`, `version`) | Keep string wire values; "not a shortfall": future days, days before joining, today before capture (BN 4) |
| Dashboard | Home screen cards by period today, week, month, per company and scope; each card behind its own permission (`dash.*`) | `RevenueDashboardDto`, `RevenueUseCases.Visible`, `RevenueDashboardCache` | Cache unmasked, mask per request |
| Change log (history) | Append-only record of every audited change with section, entity, actor, reason, before and after; keyset paged; the people section also needs `people.view` (D11) | `OrganizationSettingsVersion`, `SettingsChangeLog.Record`, `Organization.SettingsVersion`; `GET /setup/history` | `change_log` with per-org monotonic `version`; `vehicle_id` column; automatic reasons; typed reason only in four places (BN 2) |
| Settings version | Per-organization counter that moves on every audited write; used as concurrency token, history order, dashboard cache key | `Organization.SettingsVersion` | Decide whether to keep one hot row (Q9) |
| Data scope | Which companies and vehicles a person may see, kept separate from permissions; all-companies flag, company ids, vehicle ids | `SetupDataScope`, `SetupCompanyScope`, `SetupVehicleScope`; `actor.AllCompanies`, `CompanyIds`, `VehicleIds`; `GET /setup/access/me` | Branch on all-companies in code; scope hash in cache keys |
| Roles | Owner, Office admin, Fleet manager, Revenue clerk (defaults). A person gets only roles whose permissions all sit inside their own; only an Owner gives Owner (BN 2). Owner = every key except `dash.capture` (D10) | `Role`, `PersonRole`, `PersonPermissionOverride`, `PermissionCatalog.RolePermissions`, `OrganizationMembership` | Single source of role defaults; overrides on top |
| Permission groups and keys | 40 keys in 8 groups: Dashboard, Revenue, Expenses, Petty cash, Office bills, Scheduled expenses and savings, Reports, Setup; for example `revenue.view`, `revenue.capture`, `revenue.no_earnings`, `people.manage`, `access.manage`, `organization.manage`, `invest.view`, `invest.manage` | `PermissionKeys` (const strings), `PermissionCatalog` | Dotted lower-case keys are wire values: keep them exactly |
| Office bills | Permission group `bills.view`, `bills.capture`, `bills.approve`. Mobile says "Office bills are not available from the current API yet": no endpoints exist | `PermissionKeys.Bills*` only | Reserve the keys; do not invent endpoints (Q12) |
| Expense category / item / bucket | Setup list people pick from. Money out is tracked in three buckets only: repairs and maintenance, recurring charges, loan repayments. Fuel and crew pay are not tracked (the crew settle both from the day's takings) | `ExpenseCategory`, `ExpenseItem`, `ExpenseBucket` (1,2,3), `ExpenseBuckets.Of` | Stop and restore, never delete; names unique case-insensitively (category within org, item within category) |
| Scheduled expenses | Formerly "recurring costs": costs picked from an expense item, weekly, monthly or yearly on a month and day; start no earlier than the first of the current month (BN 2); the route stays `/setup/recurring` | `RecurringItem` with `RecurringKind.Cost`, `RecurrenceFrequency` (1 Daily legacy read-only, 2 Weekly, 3 Monthly, 4 Yearly), allocation per vehicle in whole cents, versions append-only | Keep the route name `recurring` and legacy Daily readable |
| Savings | Money set aside per vehicle share; weekly or monthly only; not money out | `RecurringKind.Savings` | After-savings figures: `net - savings` |
| Investment | Per vehicle: what went in, what came back, percent paid off; never counted as money out; permissions `invest.view`, `invest.manage` | `VehicleInvestment`, `InvestmentEntryDto` | Contract C5: `returned` and `percentPaidOff` null until revenue returns exist |
| Vehicle report | Money in, target, three buckets, money out, net contribution, savings, after savings | `GET /setup/vehicles/{id}/report` (C6) | `net = moneyIn - moneyOut` |
| Petty cash float | One float per manager; cash in hand = cash given - cash returned - everything recorded against it; expenses sit as Waiting, approving posts to the vehicle, sending back needs a comment; credit note = cash handed back, never touches a vehicle; a float cannot go below zero unless permitted (BN 5) | `PettyCashEntry`, `PettyCashKind` (Cash 1, Expense 2, Credit 3), `PettyCashStatus` (Waiting 1, Approved 2, SentBack 3), `pettycash.*` keys | See `inventory-petty-cash.md` (not read here); amounts are signed and never zero |
| Reports | Summary, By vehicle, By category over any date range, all from the same records without double counting (BN 6) | not found in this folder | Q12 |
| Trusted device / security version | A phone or browser trusted after an emailed code; revoking or changing access bumps `SecurityVersion` so old tokens stop working | `TrustedDevice`, `User.SecurityVersion` / `BumpSecurityVersion` | Keep `SecurityVersion` check on every request |
| Sign-in flow | Phone number + PIN (4 to 8 digits per policy); new device needs an emailed 6-digit code; PIN setup and reset by emailed code; `developmentCode` only in dev | `SignInService`, `PinSetupService`, `SessionService`; `/auth/*` operations | See `inventory-auth.md` |
| Money | Kenyan shillings by default (`KES`); decimal, 2 dp, positive, max 999,999,999,999.99 | `SetupValue.Money` | `numeric(14,2)` |

## 7. Open questions for the planner

| Q | Question | Why it matters | Evidence |
|---|---|---|---|
| Q1 | Does the rewrite reproduce the .NET API byte for byte (shipped phones read raw JSON) or may contracts change with a client release? | Constrains every rename, enum encoding and status | `phase-2-plan.md` contracts preamble; `Phase1ContractTests`; additive-only rule |
| Q2 | `kes()` display: always the same fraction digits, or whole amounts without decimals? And clamp `numberDecimals` (0 to 6 today) to storage precision (2)? | Changes every money string, test and report | README residual 2; `audit/integrity.md` section 4; D3 |
| Q3 | Trusted-device lifetime default, access-token lifetime, and sign-out invalidation (L1, L2) | Open security lows with no owner | 3.1 L1, L2 |
| Q4 | `ClearPause` resets `FailedAttempts`: keep, or use a decaying counter or escalating pause? Refresh reuse: add a grace window (L3)? | Brute-force rate and multi-tab sign-outs | 3.1 M2b, L3 |
| Q5 | Cache per-request context (membership, permissions, scope, business date)? | About 11 queries per setup request; the first attempt broke revocation | N1; 3.4 row 17 |
| Q6 | Week paging: offset (as .NET) or keyset? Keep the legacy cap of 500 and `truncated`? | A vehicle removed between page requests can be skipped | README residual 13; 3.5 row 1 |
| Q7 | ETag and conditional GET for `/setup/appearance` (logo up to 256 KB base64 inside it)? Separate logo endpoint? | Payload on every shell load | N4, N4b |
| Q8 | Rate limiting beyond `/auth`? Per account and per IP semantics behind a proxy (`TRUSTED_PROXY_HOPS`) | Only `auth` policy exists | N6; `ForwardedClientTests` |
| Q9 | Keep one hot `SettingsVersion` row per organization (serialises captures, moves the dashboard key) or a per-org sequence? | Burst capture at day close; 409 after 3 retries | 3.5 Observation |
| Q10 | Backlog 2 "one day, all vehicles" vs "one vehicle, all its days": is the per-person choice stored server side? | Possible preference field | `docs/backlog.md` 2 |
| Q11 | Bulk import/export: SQL files (data only or not at all), conflict policy, fields, who may import, limits | Shapes the batch write path | `docs/backlog.md` 1 |
| Q12 | Scope of release one: petty cash, reports, office bills (keys only), investment "returned" | Several areas have contracts but no source in this folder | 4.4 Scope; BN 5, 6 |
| Q13 | Test database: real PostgreSQL for all integration tests (recommended by traps 1 to 3) vs SQLite for speed? Run time target (the .NET suite takes 10 to 12 minutes) | Engine-specific behaviours (Guid case, decimal sums, instants, migrations) | 5.1 |
| Q14 | Data migration of existing PINs (PBKDF2-SHA256 210,000), refresh-token HMACs (keyed with the signing key) and change-log snapshots (old key `useGroupping` in text) from SQL Server | Users must keep signing in; history must still render | `Security.cs:57`; 3.7 C1; `docs/10-data-migration.md` is the planned home |
| Q15 | Monthly schedules on day 29 to 31: confirm the server rule (clamp to the last day or skip) | Web presentation skipped short months; server rule unverified | 3.3 row 6 |
| Q16 | Auth-event logging (sign-in failures, lockouts, device revocations, authorisation denials) | Audit found none | 3.4 row 20, 21 |
| Q17 | The sibling inventories still cite the deleted `AuthService.cs`: who refreshes them? | They feed `docs/07-auth.md` | README residual 12 |
