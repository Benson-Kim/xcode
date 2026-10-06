SOLID/DRY/TDA audit. Paths are relative to C:\Users\user\Documents\Coding\PrioriTech\xcode-wt\revenue. I read the key files in full or in large part and grepped the rest. Line numbers come from `cat -n` on the working tree, which has uncommitted changes. I did not read apps/mobile/src/ui, apps/web/components/ui, RecurringEditor, PeopleAccessView or the setup/*Page components in depth. Severity is H/M/L.

## Top 5 to act on
1. Organization endpoints bypass the application layer and use AuthDb directly (SRP/DIP, H).
2. The revenue cell status and the capture rules are re-derived in four places across the API, web and mobile (DRY/OCP, H).
3. Web and mobile re-implement the same revenue capture logic and Appearance type (DRY, H/M).
4. Dead abstractions are registered but unused: SettingsSectionRegistry, OrganizationUseCase, IUnitOfWork, Organization.ChangeTimeZone (M).
5. `packages/shared/format.ts` holds mutable global state and mixes four concerns (SRP/DIP, M).

## 1. Single Responsibility

**[H] apps/api/Api/OrganizationEndpoints.cs:21-185 (SRP, DIP)**
- The endpoints inject `AuthDb` and `IClock` and run EF queries inline.
- They also do validation (slug regex at :52, `Save<T>` at :296-325), uniqueness checks (:54), the audit and change-log writes (`RecordChange` :188-203), message building (`AutomaticReason`/`SettingNames` :230-267), time-zone conversion (:205) and DTO shaping.
- Revenue, Setup and Access use the layered pattern: endpoint, `*UseCases`, repository interface, `ISetupExecution`. Organization is the outlier.
- The file is untestable without a DbContext.
- Refactor: add `OrganizationSettingsUseCases`, `AppearanceQuery` and `PreferencesUseCases` in Application/ behind `ISetupExecution` or the existing `IUnitOfWork`. Move `AutomaticReason`/`SettingNames` into a `SettingsChangeDescriber`. Move `RecordChange` into a `SettingsChangeLog` service. Leave the endpoints as routing only. The four copies of `EnsureMember` + `EnsurePermission` at :23, :41, :94 and :111 collapse into an endpoint filter or the use-case base.

**[M] apps/api/Api/OrganizationEndpoints.cs:45-78 (SRP, OCP)**
- A `switch (section)` runs inline: "organization", "localization", "branding", "securityPolicy", "businessDate".
- Adding a section means editing this handler and also `Save<T>`'s `if (value is OrganizationLocalization) ... Validate()` chain at :314-316.
- `apps/api/Infrastructure/SettingsSectionRegistry.cs` already models the right abstraction (`ISettingsSection` with Key, Defaults and Validate), but nothing reads it. Registered at Program.cs:38, no consumers, and it lives in Infrastructure while holding domain validation.
- Refactor: define `ISettingsSection { Key; Load/Merge/Validate/Describe }`, with one implementation per section including organization details and businessDate. The handler resolves the section from the registry. This also removes the type-switch validation chain. Add an `IValidatable` interface on the three entities, since they all have `Validate()`.

**[M] apps/api/Application/RevenueUseCases.cs:42-100 (SRP)**
- `Save` is a ~60-line lambda that mixes authorization policy (:61-68), conflict detection, ordering rules, record creation, snapshotting and change-log text building.
- Refactor: a `RevenueCapturePolicy` (can this actor write this cell) shared with `RevenueCellDto.For` (see DRY). Move the change-log phrasing to `RevenueChangeDescriber`.

**[M] apps/api/Application/RevenueContracts.cs:23-30 (SRP, DRY)**
- A DTO's static factory (`RevenueCellDto.For`) computes the status and the `canEdit` policy from raw permission strings.
- Move this to the domain or a policy class. The DTO should only carry data.

**[M] apps/api/Api/AuthEndpoints.cs:66-80 (SRP)**
- `Run` mixes input validation (an 8-clause boolean at :68), a global `AuthGate` semaphore, a Serializable transaction, SaveChanges and email delivery.
- `AuthGate` is a singleton `SemaphoreSlim(1,1)`, so every auth request on an instance is serialized, including slow DB work. That is a throughput ceiling.
- Refactor: an `AuthRequestValidator`, plus an endpoint filter or `IAuthUnitOfWork`.
- Positive: the endpoint list is declarative and clean.

**[M] apps/api/Application/AuthService.cs (357 lines, SRP)**
- One concrete class has 9 public operations plus the mailer, tokens, permission resolver and options.
- It is registered as a concrete type (Program.cs:34), so endpoints depend on the concrete class (DIP). It splits naturally into `PinSetupService`, `SessionService` (Refresh/SignOut/RevokeDevice) and `SignInService`.

**[M] Large client components**

| File | Lines | What it mixes |
|---|---|---|
| apps/mobile/src/shell/RevenueScreen.tsx | 1626 | Pure capture logic at :90-181 (`nextMissing`, `targetFor`, `nextTarget`), formatting, queue panel, capture sheet, layout hooks |
| apps/web/components/RevenuePage.tsx | 820 | Pure rules at :55-105 (`activeOn`, `missingOn`, `openAt`, `nextMissing`, `firstGap`, `opens`, `entryLabel`), `apiRequest` PUT at :689, week re-fetch at :202 and :413, rendering |
| apps/web/components/OrganizationSettingsView.tsx | 781 | `useState` x6, `apiRequest` at :245/264/297/301, form rendering |
| apps/web/components/RecurringEditor.tsx | 1030 | not read in depth |
| apps/web/components/PeopleAccessView.tsx | 1011 | not read in depth |

- Fix: extract the pure rules into `@xcode/shared/revenue-capture.ts` (see DRY) and data calls into hooks (`useRevenueWeek`, `useSaveRevenue`, `useOrganizationSettings`). Components then render only.
- The web `lib/data` hooks (`useResource`, `useStreamedList`, `apiRequest`) are a good boundary. RevenuePage and OrganizationSettingsView call `apiRequest` directly with hard-coded URL strings such as `setup/revenue/${vehicle.id}/${cell.date}` and `setup/organization/settings/...`. Wrap these in a typed `revenueApi` and `organizationApi` module.

**[L] apps/mobile/src/shell/AppShell.tsx and screens.tsx:176, 51**
- Screens call `apiGet<...>("setup/revenue/dashboard?period=...")` and `setup/access/catalog` inline. Same recommendation: typed endpoint modules.

## 2. Open/Closed

**[H] Revenue statuses are string literals decided in the API and re-switched in each client.**
- Server: apps/api/Application/RevenueContracts.cs:23-30 builds the status with a nested ternary (`"none"/"future"/"missing"/"amount"/"reason"`) and a `switch` on the string for `canEdit`.
- Shared: `RevenueStatus` union at packages/shared/src/revenue.ts:1.
- Web, `cell.status === ...` chains: RevenuePage.tsx:62, 84, 92, 103, 153, 446-456 and 525-545.
- Mobile: RevenueScreen.tsx:82, 106, 138, 166, 404, 674-694, 961-976, plus queue.ts:264 and week.ts:36.
- Adding a status (for example "pending_approval" or "disputed") touches about 12 places in 3 apps and has no exhaustiveness check.
- Refactor, server: make a `CellStatus` enum and a `CellStateRule` list. Each state owns its `CanEdit` and its tone.
- Refactor, shared: export `CELL_STATUS_META: Record<RevenueStatus, { counted: boolean; label; tone; recorded: boolean }>`. Export predicates `isRecorded(cell)`, `isMissing(cell)` and `isCounted(cell)`. Clients then consult metadata. A `Record<RevenueStatus, ...>` also gives compile-time exhaustiveness.

**[M] No-earnings reasons are encoded 4 times.**
- C# enum `RevenueNoEarningsReason` plus `Label()` at apps/api/Domain/Revenue.cs:5-51.
- A string-to-enum switch at RevenueContracts.cs:98-105, which also accepts "NoCrew" and "No Crew".
- `REVENUE_REASONS` at shared/revenue.ts:3.
- Mobile and web option lists.
- Adding a reason needs 3+ edits in lockstep.
- Fix: parse with `Enum.TryParse` over a `[Display]` attribute or a single table. Generate the shared TS list from OpenAPI, or at least add a contract test.

**[M] Dashboard periods are hard-coded in three places.**
- Server: apps/api/Infrastructure/RevenueRepository.cs:70-79 (`period is not ("today" or "week" or "month")` plus a switch).
- Shared: `REVENUE_PERIODS` at revenue.ts:553.
- Plus mobile, which has its own `Period` in apps/mobile/src/shell/access.ts.
- Fix: a `RevenuePeriod` strategy (`From(through, firstDay)`) registered by key. Adding "quarter" then means one class.

**[M] Adding an auth operation touches 5+ files.**
- The `AuthOperation` union at shared/auth.ts:73.
- The Next proxy allow-list at apps/web/app/api/auth/[...path]/route.ts:8-20, duplicated.
- The .NET endpoint list in AuthEndpoints.cs.
- AuthPanel.tsx:147, 227, 245-246, 460, which builds operations with string templates and `as AuthOperation` casts.
- Mobile api.ts:51.
- Better: derive `allowed` from a single exported `AUTH_OPERATIONS` const array in shared. Replace the casts with typed helpers like `pinFlowOp(flow, step)`.
- `createAuthClient` itself is open for extension (it is a generic POST of operation + body), which is good. `AuthOperation | \`devices/${string}/revoke\`` already weakens the type.

**[L] shared/auth.ts:86-103 `AuthError`.**
- The constructor holds a nested ternary of status/HTTP code to message. Use a `Record<status|http, string>` table.

**[L] AppShell view dispatch.**
- apps/web/components/AppShell.tsx:221-253 has a `NavItem[]` table (good), but the render at :528-553 is an if-chain on view id. Add a `View -> {label, permission, component}` registry so nav and render share one source.
- Mobile: apps/mobile/src/shell/access.ts has `TABS` and `SETUP_LINKS` tables that duplicate the web's permission-to-menu mapping (see DRY).

## 3. Dependency Inversion

**[M] apps/api/Program.cs (160 lines, SRP, DIP)**
- Mixed bag:
  - env checks and signing-key creation (:18-22);
  - DI;
  - CORS, forwarded headers, rate limiter and JWT config with an inline `OnTokenValidated` that queries `AuthDb` directly (:60-80);
  - migration, rename-SQL and CLI commands `--provision-user`/`--remove-user` (:100-148).
- `AuthService`, `TokenIssuer`, `AuthGate`, the resolvers and `VerificationMailer` are registered as concrete classes with no interface.
- `AuthDb` (the EF DbContext) is injected into endpoints and `AuthService` directly.
- Good: `IClock`, `IEmailSender`, `IOrganizationRepository`, `IRevenueRepository`, `ISetupRepository` and `ISetupExecution` are abstractions.
- Fix: extension methods (`AddAuthentication(options)`, `AddRateLimiting`, `AddForwardedHeaders`) in Infrastructure/Hosting. Move the CLI and bootstrap into a `StartupTasks` class. Extract the JWT session validation into `ISessionValidator`.
- Lowercase class `organizationContext` at Program.cs:29 is a naming slip.

**[M] apps/mobile/src/lib/api.ts (DIP)**
- It is a module with global singletons: `apiUrl` from `process.env`, `Platform`, `reach()` wrapping the global `fetch`, `authClient` created at import time, `renewing` module-level state.
- Not injectable. Tests must `jest.mock` modules.
- `createAuthClient(url, fetcher)` in shared is injectable, but mobile fixes it at import.
- Fix: `createApiClient({ baseUrl, fetcher, sessionStore, deviceIdProvider })` returning `{ authApi, apiGet, apiPutResult }`. Provide it through React context (`ApiProvider`). Pass `storage`/`vault` as ports.
- The same applies to `appearance.ts` (imports `apiGet`/`vault`/`savePinPolicy` directly), `session.ts` and `queue.ts`.

**[M] apps/web: two sibling HTTP stacks.**
- apps/web/lib/api.ts holds `authApi = createAuthClient("/api/auth")` (hard-coded base).
- lib/data/request.ts is a separate `apiRequest`.
- lib/session.ts uses raw `fetch("/api/auth/...")` at :7 and :38.
- Proxy routes read `process.env.API_URL || "http://localhost:5000"` in two files (auth route :41 and :135, and presumably setup route).
- Unify as a single `config.apiUrl` and a `fetchRefreshingOnce` that belongs to the client.

**[M] packages/shared/src/format.ts (DIP, SRP)**
- Module-level `let formats` mutated via `configureFormats()`, with free functions (`kes`, `money`, `formatDate`, ...) reading it.
- It is hidden global state shared by everything. Any non-React or concurrent use (SSR requests, tests) is unsafe. The web calls `configureFormats` "during render" by design.
- The module mixes four concerns: org format settings state, currency/number formatting, phone normalisation and validation, and `initials`.
- Fix: `createFormatter(formats): Formatter` returning pure functions. Provide it via context or hook in each app (`useFormatter()`). Move phone to `phone.ts` and `initials` to a misc or person helper. This is also a Next.js server-rendering hazard if any server component calls `kes()`.

**[L] shared/dates.ts:279-293 and format.ts.**
- `formatDateOnly(value, settings)` is parameterised (good), while `format.ts` re-wraps it with the global state. Moving to the formatter object resolves this.

## 4. DRY violations

**[H] Capture and queue logic is duplicated between web and mobile.**
- Web RevenuePage.tsx:55-105 versus mobile RevenueScreen.tsx:90-181 (`nextMissing`, `targetFor`/`openAt`, `nextTarget`/`firstGap`).
- Same domain rules ("a later missing day opens the earliest gap first", "next vehicle still missing for that day"), written twice with different algorithms and different results for out-of-week days. They already drift: web assumes capture is in date order and uses `earliestMissing`, while mobile loops dates with `shiftDate`.
- The server's `canEdit`/`earliestMissing` rule at RevenueContracts.cs:27 is a third copy of the rule.
- Fix: move `missingOn`, `firstGap`, `nextMissing` and `opens` to `@xcode/shared/capture.ts` as pure functions over `RevenueWeek`. Return `canOpen` and `redirectTo` from the server (`CanEdit` plus `OpensDate`) so clients stop recomputing.

**[M] Appearance type and theming are duplicated.**
- The `Appearance` type is defined separately in apps/web/lib/appearance.ts:7-27 and apps/mobile/src/appearance.ts:12-31. The shapes differ slightly: mobile has lockoutThreshold/lockoutMinutes, web adds weekNumbering and direction to `formats`. Both mirror the C# `AppearanceResponse` at OrganizationEndpoints.cs:337 by hand.
- `resolveTheme(mode, deviceDark)` is identical in both (web :59-63, mobile :197-204).
- The brand colour derivation (primary to blue, blueDark, blueTint, blueWash; accent to green, greenBg; same percentages 60/40/80/10/4/12/55) is expressed twice, as CSS `color-mix` strings on web and `mix()` on mobile. Only the mixing primitive differs.
- Fix: shared `appearance.ts` with the `Appearance` type, `resolveTheme` and a `deriveBrandTokens(branding, dark, surface)` returning semantic token names and mix specs `{colour, amount, towards}`. Each platform renders those specs.
- Better: generate the type from OpenAPI.
- `Formats` in shared/format.ts is the settings shape plus defaults. Appearance should reuse one `EffectiveFormats` type that mirrors the server record.

**[M] The permission-to-menu map is duplicated.**
- Web `topLevel`/`setupGroup` (AppShell.tsx:224-253) versus mobile `TABS`/`SETUP_LINKS` (access.ts:23-65). The same permission keys and labels appear twice, and the dashboard `PermissionGroup` type is redefined in mobile/access.ts:15-18 even though web/lib/types.ts:107-116 and the server catalog define it.
- The API's `PermissionCatalog.Groups` is the real authority. Permission keys are bare string literals across the code (for example "revenue.view" appears 10 times in Application/Domain). A typo compiles.
- Fix: `PermissionKey` constants in C# (`Permissions.RevenueView`) and an exported union in shared. Share the nav-visibility predicate.

**[M] Dates and number formatting overlap.**
- mobile/src/revenue/dates.ts `dayLabel`/`rangeLabel`/`longDayLabel`/`shortDayLabel` re-wrap `mediumDateLabel`/`compactDateRange` and ignore the org's `datePattern`, always "medium".
- Web revenueFormat.ts `shortDate`/`longDate`/`rangeLabel` call the settings-aware `formatDate` and `formatDateRange`.
- So mobile revenue dates ignore a short or long org pattern while the web honours it. This is a behavioural drift caused by two modules (the correctness angle is out of scope here).
- Both re-export `shiftDate`, `weekday` and so on.
- Fix: one `RevenueDateFormatter` in shared, built from `Formats`, used by both.
- `figure()` at revenueFormat.ts:32-33 slices the currency prefix off the `kes()` string (`kes(value).slice(currencyCode().length + 1)`). That is fragile for any currency symbol/locale. Add `formatNumber` and have `kes` compose it.

**[M] Revenue reason and `entryLabel` text is repeated.**
- RevenuePage.tsx:96-105 `entryLabel`/`cellState` versus mobile RevenueScreen.tsx:84 `valueText` and :961-976. Put `describeEntry(cell)` in shared/revenue.ts.

**[M] Phone handling is split three ways.**
- Shared `normalisePhone` yields local "07..." (format.ts:422), the API `PhoneNumber.Normalize` yields "+2547..." (Domain/PhoneNumber.cs), and `phoneError` has its own regex. The rules (07/01, 10 digits, 254 prefix) live in two languages. Add a shared spec or a conformance test with a vector table used by both. The mobile `lib/phone.ts` was deleted in the working tree, so check nothing still reimplements it.

**[L] Mobile `RevenueDashboard` override at apps/mobile/src/revenue/types.ts:17-28.**
- It re-declares the eight figures as `number | null`, but the shared type already has exactly that. It is dead noise, so replace it with a plain re-export.

**[L] Web `View` and `Person` types.**
- web/lib/types.ts:7, 141 mix UI routing types (`View`) with API DTOs. `View` is navigation state, not a type for types.ts. web/lib/types.ts and shared/revenue.ts do not overlap on revenue types, because web imports revenue types from shared.
- The other DTOs (`Permission`, `Role`, `Person`, `ExpenseCategory`, `Page<T>`, `ScopeOptions`) exist only in web. Mobile redefines `PermissionGroup`. If mobile will grow Settings or People screens, move the API DTOs to `@xcode/shared/api-types`.

**[L] UI components.**
- Web `components/ui/*` (12 files, about 1350 lines) and mobile `src/ui/*` (about 590 lines) both define Button with a `tone` prop (web `primary` and more, mobile `primary | outline`), Field, Feedback, Brand, Segmented and similar.
- Names align and tokens are duplicated (`navy #14213D`, `palette` in mobile/ui/theme.tsx:5-41 versus CSS vars in web globals.css:14).
- Native and DOM can't share components, but the design tokens (palette, dark palette, tone and variant names) belong in `@xcode/shared/tokens.ts`. Web's globals.css could be generated from it. That removes a light/dark drift risk.

## 5. Tell, Don't Ask

**apps/api/Domain/Organization.cs (383 lines)** is mixed: some real behaviour, but more validation and data bags, and callers still ask.

**[M] `Organization` (:78-111).**
- Good: `ChangeBusinessDate` and `EnsureBusinessDateWithin` enforce invariants, and `BusinessDate`/`SettingsVersion` have private setters. `OrganizationMembership.Deactivate()` and `Reactivate()` are idempotent and bump the version (good).
- But `Name` and `Slug` are public setters, and the endpoint validates and assigns them inline (OrganizationEndpoints.cs:50-57). Add `organization.Rename(name, slug)` that validates and returns a changed flag, plus a `Slug` value object like the existing `Locale`/`TimeZoneId`/`HexColour` records.
- `SettingsChanged()` is called by the endpoint's `RecordChange` (:190). Callers must remember to call it, so it is invisible coupling. A `Record(change)` method on a `SettingsHistory` aggregate would own the version bump and the log entry.
- The endpoint asks `before != after` on serialized JSON (:80) to decide whether anything changed. The entity or section should report `Changed`.

**[M] `ChangeTimeZone` (Organization.cs:103-109).**
- It looks like the correct Tell-style API, but nothing calls it (grep: no callers). The live path is the endpoint's `Save(db.Localizations...)` followed by `organization.EnsureBusinessDateWithin(...)` at OrganizationEndpoints.cs:61-65, i.e. ask-then-act in the handler. It is also an unusual design, because it takes the other entity (`localization`) as a parameter. Use it, or delete it.

**[M] `OrganizationLocalization`, `OrganizationBranding`, `OrganizationSecurityPolicy`, `UserPreference` are validate-on-demand bags.**
- All fields have public setters, so invariants only hold if someone remembers `Validate()`. The endpoint's `Save<T>` does `if (value is X) x.Validate()` at :314-316. `EffectiveSettingsResolver.Resolve` re-validates everything on every read (Organization.cs:357-366).
- `UserPreference.Validate()` mutates fields (normalises Locale and TimeZone), so validation has side effects.
- `localization.EnsureAllowed(preference)` at the call site (OrganizationEndpoints.cs:181) is good TDA.
- Fix: private setters plus `Apply(patch)` methods, or make validation part of the type through the value objects. `OrganizationSecurityPolicy.Validate` at :288 forbids `AllowPinSignIn = false` but the property is still public and settable, which is a smell.

**[L] Organization.cs structure.**
- One file holds about 15 types: value objects, the contrast validator, 6 entities, `EffectiveFormats`/`EffectiveSettings` and the resolver. The resolver (`EffectiveSettingsResolver`) is application logic, not domain. Split it per aggregate and move the resolver to Application.

**[M] PhoneNumber.cs.**
- A static class with a single `Normalize(string)` that returns `""` for invalid input. Callers must then ask `PhoneNumber.Normalize(x) == ""` (AccessUseCases.cs:342) or `is { Length: > 0 }` (AuthService.cs:16). This is ask-then-decide, and an empty string is a "magic null".
- The `digits.Length == 10` and `StartsWith("0")` branches are repeated.
- Fix: a `readonly record struct PhoneNumber` with `TryParse(string, out PhoneNumber)` and `Parse` (throws `ArgumentException`), a `Value` in E.164 and a `ToString`. Entities and `AuthRequest` then carry the type, and "invalid phone" becomes unrepresentable past the boundary. `AuthEndpoints.cs:68` then no longer needs the `PhoneNumber.Length > 14` check.

**Revenue domain (better, with leaks).**
- `RevenueRecord` has private setters, a constructor that validates, `Replace()`, `Matches()` and `CorrectedAfterDate`. This is good TDA. The use case still decides date and permission rules (RevenueUseCases.cs:53-72), and `RevenueEntry.Validate()` is called both in `SaveRevenue.Entry()` (RevenueContracts.cs:107) and again in the `RevenueRecord` constructor and `Replace`, so it runs 2-3 times per save.
- `vehicle.ActiveOn(date)` and `vehicle.AwayOn(date)` ask the vehicle, then the use case decides the message (:55-58). Let `FleetVehicle.EnsureAcceptsRevenueOn(date)` throw.
- `RevenueUseCases.Visible` (:23-40) is an ask chain: it checks 4 permissions and nulls fields. Consider `dashboard.RedactedFor(permissions)` on the DTO or a policy.

## 6. Package module design (packages/shared/src)

- Module graph: `auth.ts` has no imports (clean). `dates.ts` has no imports (clean). `format.ts` imports `dates` (one-way, good). `revenue.ts` has no imports and is pure (clean). There are no cycles and no apps/ imports. The graph is a DAG.
- Boundary smells:
  - `format.ts` is a grab bag (global state, number and date wrappers, phone, initials). Split into `format/number.ts`, `format/date.ts`, `phone.ts`, `person.ts`, or turn it into a `createFormatter`.
  - `auth.ts` mixes PIN validation (`validatePin`, `PIN_HELP`, `pinHelp`), DTO types, the error class, the client factory and `pauseSeconds`. Split it to `pin.ts`, `auth-types.ts` and `auth-client.ts`.
  - `PIN_HELP` and `pinHelp()` duplicate strings (":1-2 vs :62-66"), and `validatePin` uses `PIN_HELP` rather than `pinHelp(minLength)`, so the minimum-length policy (server `PinLength` 4-8) is not honoured client-side.
  - `dates.ts` mixes pure UTC calendar arithmetic with Intl formatting driven by settings. Split into `calendar.ts` (shiftDate, daysBetween, startOfWeek) and `dateFormat.ts`.
  - `revenue.ts` mixes types, constants and validation (`parseRevenueAmount`). That is fine, but add the capture rules and cell status metadata (see OCP).
- The `./auth` etc. subpath exports plus `./src/index.ts` as main: **index.ts is listed in package.json but does not exist** in packages/shared/src (listing shows only auth.ts, dates.ts, format.ts, revenue.ts). `import "@xcode/shared"` would fail, so either add the barrel or drop it from `main`, `types` and `exports["."]`.
- Missing shared concerns, per the DRY section: appearance and theme tokens, API DTO types, permission keys, and capture rules.

## 7. eslint-rules/import-order.mjs

- It is a formatter-style `layout` rule that autofixes the order into three groups (installed, `@xcode/*`, relative), alphabetical by source. It bails out when comments sit between imports or the imports aren't one contiguous block (:35-47), so it silently skips files.
- Assessment: it enforces order, not module boundaries. It does nothing against the architectural risks:
  - mobile importing web or vice versa;
  - `components/*` importing `lib/api` internals;
  - the `@xcode/shared` internals (`import ".../shared/src/..."`);
  - `shared` importing from apps;
  - UI primitives importing feature modules;
  - the `src/shell` to `src/lib` direction.
- Notes: `groupFor` classes `"node:..."`, `react` and `next/*` as the same group. `localeCompare` is locale-dependent, so order can differ across machines. It is also applied to apps/web and apps/mobile only, not packages/shared, and a hand-rolled fixer is a maintenance cost compared with `eslint-plugin-import` or `simple-import-sort`.
- Recommend adding enforcement: `no-restricted-imports` or `eslint-plugin-boundaries`/`import/no-restricted-paths` zones:
  - `packages/shared` imports nothing from apps;
  - `apps/mobile` does not import `apps/web` (and the reverse);
  - `components/ui` does not import feature components;
  - features import `lib/data` only through its barrel.
- The same dependency discipline should be applied in .NET with an architecture test (NetArchTest or similar): Domain does not reference Infrastructure/Application, Api does not reference AuthDb (which would currently fail for OrganizationEndpoints and AuthEndpoints).

## Cross-cutting notes
- API: two parallel use-case styles exist. Setup/Revenue use `ISetupExecution`, while `OrganizationUseCase<,>` and `IUnitOfWork` (Application/OrganizationPort.cs) have zero subclasses or consumers. They are dead abstractions beside the real one, and both `IUnitOfWork`/`UnitOfWork` are registered at Program.cs:31. Consolidate on one and delete the other.
- API errors are mapped by exception type (`WithSetupErrors`, `RevenueEndpoints` filter). That is workable, but `ArgumentException` to 400 and `UnauthorizedAccessException` to 403 are generic framework exceptions. Domain-specific exception types, or a `Result`, would make this safer to extend.
- Several modules use `any`-ish string typing between the layers: statuses, periods, permissions, section names, theme modes (`themeMode: string` in both Appearance types rather than `"light" | "dark" | "system"`). Tightening these gives OCP exhaustiveness checks for free.