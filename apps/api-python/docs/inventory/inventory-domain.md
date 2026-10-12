# Domain inventory of the .NET API (`apps/api`): entities, rules, computations, flows

Purpose: let a later agent write PostgreSQL routines and their tests for the xcode rewrite without reading the C#.
Scope: `apps/api/Domain`, `apps/api/Domain/Setup`, `apps/api/Application`, `apps/api/Application/Setup`, plus the behaviour that lives in
`Infrastructure/*Repository.cs`, `Infrastructure/Setup/*`, `Infrastructure/Security.cs`, `Infrastructure/UserProvisioning.cs`,
`Application/Settings/*` (organization settings, logo and preferences; `Api/OrganizationEndpoints.cs` is transport only), `Infrastructure/RevenueRepository.cs`,
`Infrastructure/RevenueDashboardCache.cs`, `Infrastructure/OrganizationRepository.cs` (permission resolution and `UnitOfWork`) and `Program.cs` (session validation).
Petty cash (`Domain/PettyCash.cs`, `Application/PettyCash*.cs`, `Api/PettyCashEndpoints.cs`) and the authentication flows (`Application/Authentication/*`) are inventoried by other readers and are only mentioned. HTTP shapes and table layouts are covered by the other two inventories and are only quoted where a rule needs them.

Snapshot: worktree `xcode-wt/revenue`, branch `fix/format`, HEAD `3253914` plus the uncommitted working tree of another session. Read-only inventory.
Facts that exist only in uncommitted or untracked files are marked **(uncommitted)**. They are: `OrganizationSettingsVersion.VehicleId`, `SetupActor.SettingsVersion`,
the paged/seek change log (`HistoryPage`, `before`, `includeTotal`), `HistoryCountCache`, the `ChangeLogVehicle` migration, `RevenueRepository.RecordChange` writing the vehicle id,
and the tests `ChangeLogPagingTests` and `RevenueDashboardCacheTests`.
The Phase 4 to 6 work is also uncommitted: every file under `Application/Settings/` and `Application/Authentication/` is untracked, as are `Domain/PermissionKeys.cs`, `Infrastructure/RevenueDashboardCache.cs`
and the petty-cash files; `AuthService.cs` and `SettingsSectionRegistry.cs` are deleted in the working tree; and `Application/AccessContracts.cs`, `AccessUseCases.cs`, `OrganizationPort.cs`, `RevenueContracts.cs`,
`RevenueUseCases.cs`, the five `Application/Setup/*UseCases.cs`, `Domain/Organization.cs`, `Domain/Access.cs`, `Domain/Setup/FleetVehicle.cs`, `Infrastructure/RevenueRepository.cs`,
`Infrastructure/OrganizationRepository.cs`, `Infrastructure/Setup/SetupExecution.cs` and `SetupRepository.cs` carry uncommitted edits. Citations into those files are the working tree as read on 2026-10-07/08 (see Appendix B); they are not
tagged row by row. Rows that changed after the first reading are listed in section 10.

## Conventions

- Paths are relative to the repository root. `file:line` is the line in the working tree when read (mtimes in Appendix B). `Domain/...` means `apps/api/Domain/...`.
- Rule ids: `ID-n` identity and sessions, `AC-n` access, `OS-n` organization settings and change log, `SU-xn` setup (`C` company, `V` vehicle, `A` away, `E` expense catalog,
  `R` recurring, `I` investment, `X` execution and data scope), `RV-n` revenue.
- Tests are cited as `Class.Method` (all in `tests/api/`). A cell that says `none` means no test asserts that rule directly.
- Enums are stored as integers (no value converters; `Infrastructure/Migrations/AuthDbModelSnapshot.cs` lists them as `int`) and go over the wire as integers
  (plan assumption A5, `docs/reviews/phase-2-plan.md:35`), with two exceptions: the no-earnings reason is a string on the wire (section 1.4), and the revenue cell `CellStatus` is serialized as the strings
  `none|future|missing|amount|reason` by a per-type `JsonStringEnumConverter<CellStatus>` with `JsonStringEnumMemberName` values (`Application/RevenueContracts.cs:19-28`). Every other enum stays an integer.
- "Decision" tags in code comments (`D4`, `D5`, `D10`, `D11`, `D15`, `D16`, contracts `C1`..`C7`, "addendum 1") are explained in Appendix A.
- Exceptions: `ArgumentException` becomes HTTP 400, `UnauthorizedAccessException` 403, `KeyNotFoundException` 404, concurrency conflicts 409
  (full table in section 6). A "refusal" in this document is one of those.

## Contents

1. Entity catalogue
2. Business rules catalogue
3. Computations that must be reproduced exactly
4. Use-case flows
5. Permissions and roles
6. Error vocabulary
7. Time and clock
8. Naming audit
9. Open questions
10. Corrections after Phases 4 to 6
- Appendix A decision and contract tags; Appendix B files read and mtimes; Appendix C database-enforced invariants

---

# 1. Entity catalogue

Tenancy: every type that implements `IOrganizationEntity` (`Domain/Organization.cs:72-75`) carries `OrganizationId` and has a global query filter
`OrganizationId == CurrentOganizationId` (`Infrastructure/OrganizationModel.cs:12-16`); `Organization` is filtered by `Id` (`:24`).
`User`, `VerificationCode`, `TrustedDevice`, `RefreshToken` and the three lookup types are not tenant-scoped. On a write, `AuthDb.ValidateWrites`
(`Infrastructure/OrganizationModel.cs:87-114`) rejects any tenant row whose `OrganizationId` differs from the current one (`UnauthorizedAccessException("Cross-organization write rejected.")`),
any non-add change to an `AuditEvent` (`InvalidOperationException("Audit events are append-only")`), any `DateTimeOffset` with non-zero offset (`ArgumentException("Instants must be UTC.")`),
and re-runs `Validate()` on localization, branding, security policy and user preference. The operator flows set `AuthDb.Provisioning = true` to bypass the tenant check
(`Infrastructure/AuthDb.cs:10`). `ValidateSetupWrites` (`Infrastructure/Setup/SetupModel.cs:122-133`) is listed with the setup entities (section 1.6).

## 1.1 Identity (`Domain/Entities.cs`, `Domain/PhoneNumber.cs`)

### Enumerations

| Enum | Values (stored int = wire int) | Source |
|---|---|---|
| `UserStatus` | `Active=0`, `Removed=1` | `Domain/Entities.cs:3` |
| `CodePurpose` | `FirstSetup=0`, `NewDevice=1`, `PinReset=2` | `Domain/Entities.cs:4` |

### `User` (`Domain/Entities.cs:6-50`), not tenant scoped, unique across the whole database

| Field | Type | Null | Setter | Default / notes |
|---|---|---|---|---|
| `Id` | Guid | no | public | `Guid.NewGuid()` |
| `Email` | string | no | public | `""`; column max 320, unique index (`Infrastructure/AuthDb.cs:40-41`) |
| `PhoneNumber` | string | no | public | `""`; stored normalized `+254...`; column max 13; unique where not empty (`AuthDb.cs:43-45`) |
| `PinHash` | string | yes | private | `base64(salt).base64(hash)`; max 256 (`AuthDb.cs:47`) |
| `Status` | UserStatus | no | public | `Active` (0) |
| `FailedAttempts` | int | no | private | wrong PINs on a trusted device since the last clear |
| `PausedUntil` | DateTimeOffset | yes | private | pause end instant |
| `SecurityVersion` | int | no | private | starts 0; copied into the access token as claim `version` |
| `UntrustedFailedAttempts` | int | no | private | wrong PINs on untrusted devices (per account cap) |
| `Version` | long | no | private | concurrency token (`AuthDb.cs:48`); bumped by `AuthDb.BumpVersions` on every modified `User` row (`AuthDb.cs:67-74`: `CurrentValue = OriginalValue + 1`) |

Methods (all in `Domain/Entities.cs`):

| Method | State change |
|---|---|
| `HasPin` (`:19`) | `PinHash != null` |
| `IsPaused(now)` (`:20`) | `PausedUntil != null && now < PausedUntil` (the end instant itself is not paused) |
| `SetPin(hash)` (`:22-27`) | `PinHash = hash`; `UntrustedFailedAttempts = 0`; `SecurityVersion++`. Does **not** clear `FailedAttempts` or `PausedUntil` (callers do). No precondition |
| `ClearLockout()` (`:29-33`) | `FailedAttempts = 0`; `PausedUntil = null`. Never touches `UntrustedFailedAttempts` |
| `RecordFailedAttempt()` (`:35`) | `FailedAttempts++` |
| `RecordUntrustedFailedAttempt()` (`:37`) | `UntrustedFailedAttempts++` |
| `ClearUntrustedFailedAttempts()` (`:39`) | `UntrustedFailedAttempts = 0` |
| `Pause(until)` (`:41`) | `PausedUntil = until` |
| `BumpSecurityVersion()` (`:43`) | `SecurityVersion++` |
| `Remove()` (`:45-49`) | `Status = Removed`; `SecurityVersion++` |

`Status` is also assigned directly by `AccessUseCases.SetActive` (`Application/AccessUseCases.cs:222`) and `UserProvisioning.Provision` (`Infrastructure/UserProvisioning.cs:43`).
No constructor validation exists. A person created from `AccessUseCases.Save` is `new User { PhoneNumber = phone, Email = email }` (`:127`): `Active`, no PIN.
Tests: `DomainRuleTests.UserBehaviorMethodsEnforceDomainRules`.

### `VerificationCode` (`Domain/Entities.cs:52-81`), one-time e-mail code

| Field | Type | Setter | Notes |
|---|---|---|---|
| `Id` | Guid | public | |
| `UserId` | Guid | public | FK; index `(UserId, Purpose)` (`AuthDb.cs:55`) |
| `DeviceId` | string | public | max 128 |
| `Purpose` | CodePurpose | public | |
| `CodeHash` | string | public | uppercase hex HMAC-SHA256, 64 chars (`AuthDb.cs:54`, `Infrastructure/Security.cs:76`) |
| `CreatedAt` | DateTimeOffset | public | |
| `ExpiresAt` | DateTimeOffset | public | issue time + 10 minutes (`Application/AuthService.cs:66`) |
| `Consumed` | bool | private | |
| `FailedAttempts` | int | private | |

| Method | Behaviour |
|---|---|
| `IsUsable(now)` (`:64`) | `!Consumed && now <= ExpiresAt && FailedAttempts < 5` (expiry instant inclusive) |
| `RecordFailedAttempt()` (`:66-70`) | `FailedAttempts++`; when it reaches 5 or more, `Consumed = true` |
| `Consume()` (`:72`) | `Consumed = true` |
| `Withdraw()` (`:74-78`) | `Consumed = true; ExpiresAt = CreatedAt` (a code that could not be e-mailed) |
| `IsWithdrawn` (`:80`) | `Consumed && ExpiresAt <= CreatedAt` |

### `TrustedDevice` (`Domain/Entities.cs:83-100`)

Fields: `Id`, `UserId`, `DeviceId` (max 128; unique `(UserId, DeviceId)`, `AuthDb.cs:50-51`), `TrustExpiresAt DateTimeOffset?` (private), `Revoked bool` (private).
`IsValid(now)` = `!Revoked && (TrustExpiresAt == null || now < TrustExpiresAt)` (`:91`). `Revoke()` sets `Revoked = true`. `Trust(expiresAt)` sets `Revoked = false; TrustExpiresAt = expiresAt` (`:95-99`).

### `RefreshToken` (`Domain/Entities.cs:102-113`)

Fields: `Id`, `UserId`, `DeviceId` (max 128), `TokenHash` (64, unique index, `AuthDb.cs:57-59`), `ExpiresAt`, `Revoked` (private), `Version long` (private, concurrency token, bumped on every modified row by `BumpVersions`).
`Revoke()` sets `Revoked = true`. The raw token is never stored; the hash is `HMAC-SHA256(SigningKey, raw)` as uppercase hex.

### `PhoneNumber` value object (`Domain/PhoneNumber.cs:5-54`)

`readonly record struct` with `Value`. `TryCreate(input, out result)` is false when `Normalize` returns `""` (`:13-23`). `Normalize` is specified in section 3.7. `ToString()` and the implicit string conversion return `Value`.
Tests: `DomainRuleTests.PhoneNumbersNormalizeToTheFullKenyanPrefix`, `DomainRuleTests.PhoneNumberTryCreateMirrorsNormalize`.

## 1.2 Access (`Domain/Access.cs`)

| Type | Fields | Notes |
|---|---|---|
| `Role` (`:3-8`) | `OrganizationId`, `Id`, `Name` (max 100) | unique `(OrganizationId, Name)` (`OrganizationModel.cs:55-58`). Rows are created lazily per organization from the four catalog roles (`UserProvisioning.EnsureRoles`, `Infrastructure/UserProvisioning.cs:102-112`) |
| `RolePermission` (`:13-18`) | `OrganizationId`, `RoleId`, `Permission` | **Legacy** (comment `:11-12`): nothing reads or writes it; kept until a migration drops it. Role defaults come only from `PermissionCatalog` (`Application/AccessContracts.cs:104-131`). Test: `AccessAndSetupTests.RoleDefaultsComeOnlyFromTheCatalog` |
| `PersonRole` (`:21-26`) | `OrganizationId`, `UserId`, `RoleId` | unique `(OrganizationId, UserId)`: exactly one role per person (`OrganizationModel.cs:65-70`) |
| `PersonPermissionOverride` (`:29-35`) | `OrganizationId`, `UserId`, `Permission` (max 100), `Granted bool` | PK `(OrganizationId, UserId, Permission)`; stores only deviations from the role defaults (`AccessUseCases.Overrides`, `Application/AccessUseCases.cs:470-482`) |
| `AuditEvent` (`:38-49`) | `OrganizationId`, `Id`, `ActorId`, `Action` (max 100), `Entity` (max 200), `Before?`, `After?`, `CorrelationId` (max 100), `OccuredAt` (sic) | append-only; index `(OrganizationId, OccuredAt)` (`OrganizationModel.cs:77-83`) |
| `PermissionDependencies` (static, `:52-109`) | the dependency graph (section 5.2) | `DirectFor(permission)` returns the direct list or empty; `Expand(permissions)` is the transitive closure (`:99-108`) |
| `EffectivePermissionResolver` (`:112-137`) | `Resolve(rolePermissions, overrides, active = true)` | algorithm in section 3.8 |

## 1.3 Organization (`Domain/Organization.cs`)

### Value objects

| Type | Rule | Source |
|---|---|---|
| `TimeZoneId(value)` | blank -> `ArgumentException("Time zone identifier cannot be empty.")`; unknown to `TimeZoneInfo.TryFindSystemTimeZoneById` -> `ArgumentException("'{value}' is an unknown or invalid time zone identifier.")`; `Value` is the canonical `TimeZoneInfo.Id` | `:6-23` |
| `Locale(value)` | must match `^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$` else `ArgumentException("Use BCP 47 locale.")`; `Direction` is `rtl` when the first subtag lowercased is `ar`, `fa`, `he` or `ur`, else `ltr` | `:25-37` |
| `HexColour(value)` | must match `^#[0-9a-fA-F]{6}$` else `ArgumentException("Use a six-digit hex colour")` | `:39-48` |
| `ContrastValidator` | contrast of the colour against `#FFFFFF` **and** against the surface `#F6F3EC` must both be >= 4.5, else `ArgumentException("Brand colors must meet WCAG AA (4.5:1) against the fixed surfaces")`; formula in section 3.9 | `:50-69` |

### `Organization` (`Domain/Organization.cs:83-116`)

| Field | Type | Setter | Notes |
|---|---|---|---|
| `Id` | Guid | public | |
| `Slug` | string | public | max 100, unique index (`OrganizationModel.cs:20-21`) |
| `Name` | string | public | max 200 |
| `BusinessDate` | DateOnly? | private | `null` follows the organization time-zone calendar; a value is an explicit, audited accounting date (comment `:88`) |
| `SettingsVersion` | long | private | starts at **1**; concurrency token (`OrganizationModel.cs:23`); also the change-log version counter |

| Method | Preconditions | State change / result |
|---|---|---|
| `SettingsChanged()` (`:91`) | | `SettingsVersion++`. Called only by `SettingsChangeLog.Record` (`Application/Settings/SettingsChangeLog.cs:15`) |
| `ResolveBusinessDate(calendarDate)` (`:92`) | | returns `BusinessDate ?? calendarDate` |
| `ChangeBusinessDate(businessDate, calendarDate)` (`:93-100`) | when a date is given: `date == default (0001-01-01)` or `date > calendarDate` -> `ArgumentException("The business date cannot be in the future.")` | returns `false` when unchanged, else sets and returns `true`; `null` clears the hold |
| `EnsureBusinessDateWithin(calendarDate)` (`:103-107`, **private** since Phase 5) | `BusinessDate > calendarDate` -> `ArgumentException("The held business date would be in the future in that time zone. Change the business date first.")` | none |
| `ChangeTimeZone(localization, timeZone, calendarDateInThatZone)` (`:108-115`) | `localization.OrganizationId != Id` -> `InvalidOperationException("Organization mismatch")`; then `EnsureBusinessDateWithin` | sets `localization.TimeZone = timeZone.Value` and **no longer moves `SettingsVersion`** (comment `:108`: the change-log entry of the save moves it, once). Called by the `localization` section's `afterMerge` hook (`Application/Settings/SettingsSections.cs:36`, OS-4) and by a test |

Tests: `DomainRuleTests.BusinessDateCannotMoveIntoTheFutureAndCanFollowTheOrganizationClock`, `OrganizationSettingsTests.ChangingTheTimeZoneChecksTheHeldBusinessDate`.

### `OrganizationMembership` (`Domain/Organization.cs:119-144`): the person inside an organization

| Field | Type | Setter | Notes |
|---|---|---|---|
| `OrganizationId`, `UserId` | Guid | public | PK `(OrganizationId, UserId)` |
| `FirstName`, `LastName` | string | public | `""`; validated 1..100 by `AccessUseCases.Validate` |
| `ApprovalLimit` | decimal? | public | precision (14,2); `>= 0` when set (`AccessUseCases.cs:351`) |
| `Active` | bool | private | default `true` |
| `Version` | long | public | default **1**; concurrency token (`OrganizationModel.cs:28`) |

`Deactivate()` (`:128-134`): no-op if inactive, else `Active = false; Version++`. `Reactivate()` (`:135-142`): no-op if active, else `Active = true; Version++`. `AccessChanged()` (`:143`): `Version++`.
Unique filtered index `IX_Memberships_UserId_Active` on `UserId` where `Active = 1`: at most one active membership per user (`OrganizationModel.cs:31-34`).

### `OrganizationLocalization` (`Domain/Organization.cs:147-184`), one row per organization (PK `OrganizationId`); implements `IValidatable` (`Domain/Organization.cs:77-80`, as do branding and security policy; the generic settings merge needs it)

| Field | Type | Default | `Validate()` rule (`:163-169`) |
|---|---|---|---|
| `Locale` | string | `en-GB` | `Locale` pattern |
| `TimeZone` | string | `Africa/Nairobi` | must resolve as a `TimeZoneId` |
| `DatePattern` | string | `medium` | one of `short`, `medium`, `long` |
| `Hour12` | bool | false | |
| `FirstDayOfWeek` | int | 1 | 0..6 (0 = Sunday) |
| `WeekNumbering` | string | `iso8601` | one of `iso8601`, `local` (stored only; no server computation uses it) |
| `Currency` | string | `KES` | `^[A-Z]{3}$` |
| `UseGrouping` | bool | true | **(uncommitted, phase 6)** renamed from the misspelt `UseGroupping` (column renamed by migration `20261007181520_RenameUseGrouping`, `Infrastructure/Migrations/20261007181520_RenameUseGrouping.cs`) |
| `NumberDecimals` | int | 2 | 0..2 |
| `AllowLocaleOverride` | bool | true | |
| `AllowTimeZoneOverride` | bool | false | |
| `AllowHour12Override` | bool | true | |
| `AllowThemeOverride` | bool | true | |

A range or enumeration violation throws `ArgumentException("Invalid format settings")` (one message for all of them). `EnsureAllowed(preference)` (`:173-183`) throws `ArgumentException`:
"Your organization does not allow a personal locale." / "...a personal time zone." / "...a personal clock format." / "...a personal theme." when the matching `Allow...Override` is false and the preference value is non-null.
Tests: `DomainRuleTests.NumberDecimalsIsCappedAtTwo`, `OrganizationSettingsTests.PreferenceWritesRefuseOverridesTheOrganizationDoesNotAllow`.

### `OrganizationBranding` (`Domain/Organization.cs:188-223`), PK `OrganizationId`

Fields and defaults: `DisplayName "XCODE"`, `LegalName "XCODE"`, `LogoLight?`, `LogoDark?`, `LogoAlt "XCODE"`, `Favicon?`, `Primary "#1D5FD6"`, `Secondary "#14213D"`, `Accent "#1E6B3A"`, `Domain?`, `SupportEmail?`, `TermsUrl?`, `PrivacyUrl?`.
`Validate()` (`:205-222`):
- `DisplayName` non-blank and <= 100, `LegalName` non-blank and <= 200, `LogoAlt` non-blank and <= 200, else `ArgumentException("Brand names and logo alt text are required.")`.
- `Primary`, `Secondary`, `Accent` must each be a `HexColour` and pass `ContrastValidator.Validate`.
- each non-null of `LogoLight`, `LogoDark`, `Favicon`, `TermsUrl`, `PrivacyUrl` must be an absolute `https` URI of at most 2048 chars, else `ArgumentException("Brand URLs must use HTTPS.")`.
- `Domain` non-null: at most 253 chars and a DNS host name (`Uri.CheckHostName == Dns`), else `ArgumentException("Invalid domain.")`.
- `SupportEmail` non-null: at most 320 chars and accepted by `MailAddress.TryCreate`, else `ArgumentException("Invalid support email.")`.

### `OrganizationLogo` (`Domain/Organization.cs:227-278`), PK `OrganizationId`; `ContentType` max 50; `Data` max 262144 bytes

Constants: `MaxBytes = 256 * 1024 = 262144`; private `MaxDataUrlLength = (MaxBytes + 2) / 3 * 4 + 64 = 349592`.
Fields: `OrganizationId`, `ContentType`, `Data byte[]`, `UpdatedAt`. `FromDataUrl(organizationId, dataUrl, now)` (`:245-275`) and `ToDataUrl()` (`:277`: `data:{ContentType};base64,{base64(Data)}`). Rules in OS-13.

### `OrganizationSecurityPolicy` (`Domain/Organization.cs:280-300`), PK `OrganizationId`

| Field | Default | Valid range (`Validate()` `:293-299`; the same bounds are DB CHECKs, `OrganizationModel.cs:40-44`, `Infrastructure/Security.cs:25-32`) |
|---|---|---|
| `PasswordMinLength` | 12 | 12..128 |
| `PasswordComplexity` (bool) | true | |
| `PasswordHistory` | 5 | 0..24 |
| `PinLength` | 4 | 4..8 |
| `LockoutThreshold` | 5 | 3..10 |
| `LockoutMinutes` | 15 | 1..60 |
| `AccessTokenMinutes` | 10 | 1..15 |
| `RefreshTokenDays` | 30 | 1..90 |
| `IdleUnlockSeconds` | 300 | 30..3600 |
| `AllowPinSignIn` (bool) | true | must be true: `ArgumentException("PIN sign-in cannot be disabled.")` |

Out of range: `ArgumentException("Invalid security policy.")`. The password fields and `IdleUnlockSeconds` are stored and bounded but no server code uses them (section 9).
Tests: `DomainRuleTests.SecurityPolicyRequiresThreeAttemptsAndCapsPauseAtOneHour`, `DomainRuleTests.SecurityPolicyBoundsAgreeWithValidation`, `DomainRuleTests.WrongPinPolicyBounds`, `OrganizationSettingsTests.SecurityPolicyCannotDisablePinSignIn`.

### `UserPreference` (`Domain/Organization.cs:302-329`), PK `(OrganizationId, UserId)`

Fields: `Locale?`, `TimeZone?`, `Hour12 bool?`, `ThemeMode?`, `ReducedMotion bool` (false), `FontScale double` (1). FK to the membership.
`Validate()` (`:307-323`): non-null `Locale` must be a valid `Locale`; non-null `TimeZone` must be a `TimeZoneId` and is **replaced by the canonical id**; `ThemeMode` must be null, `light`, `dark` or `system`;
`FontScale` must be finite and within 1..3, else `ArgumentException("Invalid accessibility preferences")`.

### `EffectiveFormats`, `EffectiveSettings`, `EffectiveSettingsResolver` (`Domain/Organization.cs:327-384`)

`EffectiveFormats(Locale, TimeZone, DatePattern, Hour12, FirstDayOfWeek, WeekNumbering, Currency, UseGrouping, NumberDecimals, Direction)` plus a computed read-only `UseGroupping` (`Domain/Organization.cs:345-347`, **(uncommitted, phase 6)**) that serializes the same value under the legacy name for apps released before the rename;
`EffectiveSettings(Formats, Branding, SecurityPolicy, ThemeMode, ReducedMotion, FontScale)`. `Resolve(localization?, branding?, securityPolicy?, userPreference?)` validates every input (defaults when null) and applies the override rules of OS-16.

## 1.4 Revenue (`Domain/Revenue.cs`)

### `RevenueNoEarningsReason` (`Domain/Revenue.cs:5-11`)

| Name | Stored int | Wire request `SaveRevenue.Reason` (`Application/RevenueContracts.cs:154-170`) | Wire response `RevenueCellDto.Reason` (`RevenueEntry.Label`, `Revenue.cs:44-51`) | Change-log snapshot `Reason` (`Application/RevenueUseCases.cs:111`) |
|---|---|---|---|---|
| `Garage` | 1 | `"Garage"` | `"Garage"` | `"Garage"` |
| `Arrest` | 2 | `"Arrest"` | `"Arrest"` | `"Arrest"` |
| `NoCrew` | 3 | `"No Crew"` or `"NoCrew"` | `"No Crew"` | `"NoCrew"` |
| `Other` | 4 | `"Other"` | `"Other"` | `"Other"` |

Request parsing trims the text; `null` or `""` means no reason; anything else gives `ArgumentException("Choose a valid no-earnings reason.")`. Matching is case-sensitive.

### `RevenueEntry(decimal? Amount, RevenueNoEarningsReason? Reason, string? Note)` (`Domain/Revenue.cs:13-52`), value object

`Validate()` (`:15-37`):
1. `Amount != null`: `SetupValue.Money(Amount)` (positive, <= 999999999999.99, at most two decimals, else `ArgumentException("Amount must be positive with at most two decimal places.")`); and no reason and no non-blank note, else `ArgumentException("Revenue amount cannot have a no-earnings reason.")`. Returns.
2. `Amount == null`: `Reason` must be non-null and a defined enum value, else `ArgumentException("Enter revenue or choose a no-earnings reason.")`.
3. note = `Note?.Trim()`. `Reason == Other` and blank note -> `ArgumentException("Explain what happened when choosing Other.")`. Note longer than 80 -> `ArgumentException("The no-earnings note must be at most 80 characters.")`. `Reason != Other` and non-blank note -> `ArgumentException("Only Other may have a no-earnings note.")`.

`CleanNote` (`:40`): blank or null -> `null`, else trimmed. `DisplayReason` (`:42`) = `Label(Reason)` (`""` for null).
Tests: `RevenueCaptureTests.CaptureFollowsTheBusinessDateAndTheVehiclesActiveDays` (reason Other without note, note of 81 characters, amount 0, note of spaces stored as null).

### `RevenueRecord` (`Domain/Revenue.cs:54-120`), PK `(OrganizationId, Id)`; unique `(OrganizationId, VehicleId, BusinessDate)` (`Infrastructure/RevenueModel.cs:11-18`)

| Field | Type | Null | Setter | Notes |
|---|---|---|---|---|
| `Id` | Guid | no | private | `Guid.NewGuid()` |
| `OrganizationId` | Guid | no | private | the interface setter throws `InvalidOperationException("Tenant cannot change.")` (`:56-60`) |
| `VehicleId` | Guid | no | private | FK to `FleetVehicle`, restrict delete |
| `BusinessDate` | DateOnly | no | private | never changes |
| `Amount` | decimal | yes | private | precision (14,2) |
| `Reason` | RevenueNoEarningsReason | yes | private | |
| `Note` | string | yes | private | max 80; stored via `CleanNote` |
| `CapturedAt`, `UpdatedAt` | DateTimeOffset | no | private | UTC |
| `CapturedBy`, `UpdatedBy` | Guid | no | private | actor user ids |
| `CorrectedAfterDate` | bool | no | private | "edited after capture"; once true it stays true |
| `Version` | long | no | private | starts at **1**; concurrency token (`RevenueModel.cs:16`); bumped by `Replace` |

Constructor `RevenueRecord(organizationId, vehicleId, businessDate, entry, capturedAt, actorId)` (`:78-96`): any empty Guid or `businessDate == default` -> `ArgumentException("Organization, vehicle, date and actor are required.")`;
`capturedAt.Offset != 0` -> `ArgumentException("Revenue instants must be UTC.")`; then `entry.Validate()`; copies `Amount`, `Reason`, `CleanNote`; `UpdatedAt = CapturedAt`, `UpdatedBy = CapturedBy`; `Version = 1`; `CorrectedAfterDate = false`.

| Method | Behaviour |
|---|---|
| `Matches(entry)` (`:98-101`) | `Amount == entry.Amount && Reason == entry.Reason && Note == entry.CleanNote` (ordinal string equality; `null == null` is true) |
| `Replace(entry, businessDate, today, updatedAt, actorId)` (`:104-119`) | `businessDate != BusinessDate` -> `InvalidOperationException("A revenue record's business date cannot change.")`; `updatedAt.Offset != 0` or empty actor -> `ArgumentException("Revenue updates must have a UTC timestamp and actor.")`; `entry.Validate()`; sets `Amount`, `Reason`, `Note = CleanNote`, `UpdatedAt`, `UpdatedBy`; **if `BusinessDate < today` then `CorrectedAfterDate = true`**; `Version++` |

Tests: `RevenueCaptureTests.OnlyAChangeToAPastDayIsAnEditAfterCapture`, `RevenueCaptureTests.ChangingARecordNeedsItsCurrentVersionAndAnIdenticalReplayIsIdempotent`.

## 1.5 Setup enumerations and value rules (`Domain/Setup`)

| Enum / helper | Values (stored int = wire int) and rule | Source |
|---|---|---|
| `RecurrenceFrequency` | `Daily=1` (legacy, refused for new saves), `Weekly=2`, `Monthly=3`, `Yearly=4` | `RecurringSchedule.cs:3-10` |
| `RecurringKind` | `Cost=1`, `Savings=2` | `RecurringSchedule.cs:12-16` |
| `ExpenseBucket` | `RepairsAndMaintenance=1`, `RecurringCharges=2`, `LoanRepayments=3`; labels "Repairs and maintenance", "Recurring charges", "Loan repayments"; undefined value -> `ArgumentException("Choose repairs and maintenance, recurring charges or loan repayments.")` | `ExpenseCatalog.cs:5-26` |
| Lookup tables | `RecurrenceFrequencyLookup`, `RecurringKindLookup`, `ExpenseBucketLookup` `{Id, Name = enum name}` seeded from the enums; FKs from `RecurringVersion.Frequency/Kind/Bucket` and `ExpenseCategory.Bucket` | `SetupDataScope.cs:27-46`, `SetupModel.cs:111-118` |
| `SetupValue.Name(value, max=160)` | trim; blank or longer than `max` -> `ArgumentException("Name must contain 1-{max} characters.")` | `PsvCompany.cs:58-65` |
| `SetupValue.Money(value)` | `value <= 0` or `> 999999999999.99` or `Round(value,2) != value` -> `ArgumentException("Amount must be positive with at most two decimal places.")` (all amounts are decimal(14,2)) | `PsvCompany.cs:66-72` |
| `VehicleRegistration(value)` | trim, upper-case invariant, remove every `" "`; must match `^K[A-Z]{2}[0-9]{3}[A-Z]$` else `ArgumentException("Use the registration format KDA 482M.")`; `Value` = first 3 chars + `" "` + rest (`"KDA 482M"`) | `FleetVehicle.cs:4-14` |
| `NormalizedName` (company, category, item) | `Name.ToUpperInvariant()`; uniqueness is on `(OrganizationId, NormalizedName)`; items on `(OrganizationId, CategoryId, NormalizedName)` | `PsvCompany.cs:32`, `ExpenseCatalog.cs:61,111`, `SetupModel.cs:18,53,59` |

## 1.6 Setup entities (`Domain/Setup`); all are tenant rows with a private-set model and a `Tenant cannot change.` interface setter

| Entity (source) | Fields (type; limits) | Constructor and methods (precondition -> message) |
|---|---|---|
| `PsvCompany` (`PsvCompany.cs:3-54`) | `Id`, `OrganizationId`, `Name` (<=160), `NormalizedName`, `ArchivedOn DateOnly?` | ctor: empty org -> "Organization is required."; then `Rename`. `ActiveOn(d)` = `ArchivedOn == null || ArchivedOn > d`. `Rename(name)`: `SetupValue.Name`; returns false if equal. `Archive(d)`: `d == default` -> "Archive date is required."; already archived on another date -> "The company is already archived."; on the same date returns false. `Restore()`: false if not archived, else clears |
| `FleetVehicle` (`FleetVehicle.cs:16-124`) | `Id`, `OrganizationId`, `CompanyId`, `Registration` (<=8, unique per org, immutable), `JoinedOn`, `LeftOn?`, `Targets`, `AwayPeriods` | ctor(org, company, registration, joinedOn, weeklyTarget): empty org/company -> "Organization and company are required."; `joinedOn == default` -> "Join date is required."; adds target rev 1 effective `joinedOn` with `Money(weeklyTarget)`. Methods in SU-V rules |
| `VehicleTarget` (`:126-142`) | `Id`, `OrganizationId`, `VehicleId`, `EffectiveFrom`, `WeeklyAmount` (14,2), `Revision` int | append-only (history); unique `(org, vehicle, revision)` |
| `VehicleAwayPeriod` (`:144-162`) | `Id`, `OrganizationId`, `VehicleId`, `LeftOn`, `ReturnedOn` | `Covers(d)` = `d >= LeftOn && d < ReturnedOn`; append-only; unique `(org, vehicle, LeftOn)` |
| `ExpenseCategory` (`ExpenseCatalog.cs:30-82`) | `NameLength = 100`; `Id`, `OrganizationId`, `Name`, `NormalizedName`, `Bucket`, `StoppedOn?` | ctor: empty org -> "Organization is required."; `Change(name, bucket)`: bucket validated first, then `Name(.., 100)`; false if both equal. `ActiveOn(d)` = `StoppedOn == null || StoppedOn > d`. `Stop(today)`: stopped on another date -> "It is already turned off. Turn it on first to cancel that."; same date false. `Restore()` |
| `ExpenseItem` (`:84-132`) | `Id`, `OrganizationId`, `CategoryId`, `Name` (<=100), `NormalizedName`, `StoppedOn?` | ctor(category, name) -> `Rename`; same `ActiveOn`, `Stop`, `Restore` rules as the category |
| `ExpenseBuckets.Of(kind, stored)` (`:16-17`) | | `null` for savings; for a cost: `stored ?? RecurringCharges` |
| `VehicleInvestment` (`VehicleInvestment.cs:4-43`) | `DescriptionLength = 160`; `Id`, `OrganizationId`, `VehicleId`, `Date`, `Description`, `Amount` (14,2), `RecordedBy`, `RecordedAt` | ctor(vehicle, date, description, amount, today, recordedBy, recordedAt): empty `recordedBy` -> "The person recording it is required."; then `Change`. `Change`: `date == default` or `> today` -> "An investment date is required and cannot be after the business date."; trimmed description blank or > 160 -> "Say what it was, in 1-160 characters."; `Money(amount)`; returns false if date, description and amount are unchanged |
| `SetupDataScope` / `SetupCompanyScope` / `SetupVehicleScope` (`SetupDataScope.cs:4-25`) | `(OrganizationId, UserId, AllCompanies)` / `(.., CompanyId)` / `(.., VehicleId)` | PKs `(org,user)`, `(org,user,company)`, `(org,user,vehicle)`; FKs to membership and company/vehicle |

### Vehicle methods (`Domain/Setup/FleetVehicle.cs`)

| Method | Rule (precondition -> message) and effect |
|---|---|
| `ActiveOn(d)` (`:48`) | `JoinedOn <= d && (LeftOn == null || d < LeftOn) && !AwayOn(d)`. Callers that ask about a past date must load `AwayPeriods` (comment `:45-47`) |
| `AwayOn(d)` (`:50`) / `ActiveOn(joined, left, d)` static (`:55`) | any away period `Covers(d)`; static form has no away check |
| `TargetOn(d)` (`:114-123`) | `0` if `!ActiveOn(d)`; else the `WeeklyAmount` of the target with the greatest `EffectiveFrom <= d` (ties: greatest `Revision`); `0` if none. One pass over `Targets` with that tie-break since Phase 4 (was sort and first); same result |
| `Update(companyId, joinedOn, weeklyTarget, today)` (`:57-82`) | empty company -> "Company is required."; `joinedOn == default` or `> today` -> "A vehicle cannot join after the business date."; `LeftOn != null` -> "Retired vehicles must be restored before they can be edited."; `Money(weeklyTarget)`. `changed = company or join date differs`. `targetAtOldJoin = TargetOn(oldJoin)` is read **before** the join date moves. If the join date moved earlier and every target starts after the new join date, add a target `(effectiveFrom = new join, amount = targetAtOldJoin, revision = max+1)`. `effectiveToday = max(today, joinedOn)`; if `TargetOn(effectiveToday) != weeklyTarget`, add target `(effectiveToday, weeklyTarget, max+1)` and `changed = true`. Returns `changed` |
| `Retire(leftOn, today)` (`:84-98`) | `leftOn == default`, `> today` or `< JoinedOn` -> "A vehicle's leave date must be from its join date through the business date."; away periods exist and `leftOn < max(ReturnedOn)` -> "A vehicle's leave date must be on or after the day it last returned to the fleet."; already retired: different date -> "The vehicle is already retired.", same date returns false; else sets `LeftOn`, returns true |
| `Restore(returnedOn, today)` (`:103-111`) | `LeftOn == null` -> returns false (nothing validated); `returnedOn == default`, `< LeftOn` or `> today` -> "A vehicle's return date must be from the day it left through the business date."; `returnedOn > LeftOn` adds an away period `(LeftOn, returnedOn)`; then `LeftOn = null`, returns true (a return on the leave date adds no away period) |

### Recurring entities (`Domain/Setup/RecurringItem.cs`, `RecurringSchedule.cs`)

| Entity (source) | Fields | Constructor / methods |
|---|---|---|
| `RecurringItem` (`RecurringItem.cs:5-90`) | `Id`, `OrganizationId`, `StoppedFrom DateOnly?`, `Versions` | ctor(org, definition): empty org -> "Organization is required."; adds version revision 1 with `EffectiveFrom = definition.Start`. `Revise`, `Stop`, `CancelStop`, `DueOn`, `DueBetween` in SU-R rules and section 3.1 |
| `RecurringDefinition` record (`:96-138`) | `Name`, `Kind`, `Amount`, `Schedule`, `Start`, `End?`, `Allocations`, `ExpenseItemId?`, `Bucket?`, `Note?`; `NoteLength = 200` | `Validate()` and `ValidateNew(today, currentStart)`: SU-R1, SU-R2 |
| `VehicleShare(VehicleId, Amount)` (`:92`) | | |
| `RecurringVersion` (`:140-182`) | `Id`, `OrganizationId`, `ItemId`, `Revision`, `EffectiveFrom`, `Name` (<=160), `Kind`, `Amount` (14,2), `Frequency`, `Day int?`, `LastDay bool`, `Start`, `End?`, `ExpenseItemId?`, `Bucket?`, `Note` (<=200), `Month int?`, `Allocations` | ctor re-runs `definition.Validate()`. `Schedule()` = `new RecurringSchedule(Frequency, Day, LastDay, Month)`. `ReportedBucket()` = `ExpenseBuckets.Of(Kind, Bucket)`. Append-only; unique `(org, ItemId, Revision)` |
| `RecurringAllocation` (`:184-199`) | `Id`, `OrganizationId`, `VersionId`, `VehicleId`, `Amount` (14,2) | append-only; unique `(org, VersionId, VehicleId)` |
| `RecurringSchedule` record (`RecurringSchedule.cs:19-70`) | `Frequency`, `Day int?`, `LastDay bool`, `Month int?` | ctor rule below; `IsDue(date)`, `Occurrences(first, last)`, private `DueDay(date)` = `LastDay ? DaysInMonth : Day` (section 3.1) |

`RecurringSchedule` constructor (`:26-37`): refuses (`ArgumentException("Choose a weekday (0–6), a month day (1–28 / last), or for yearly a month (1–12) and a day.")`, the dash is U+2013) when:
frequency undefined; `month != null` and frequency is not Yearly; Daily with a day or `LastDay`; Weekly with `Day` null, `< 0`, `> 6` or `LastDay`; Monthly where `monthDay` is false; Yearly with `Month` null, `< 1`, `> 12` or `monthDay` false.
`monthDay` = `LastDay ? Day == null : Day in 1..28`.

### Change-log entry `OrganizationSettingsVersion` (`Domain/Setup/OrganizationSettingsVersion.cs:4-42`), append-only

| Field | Type | Limit / meaning |
|---|---|---|
| `Id`, `OrganizationId`, `ActorId` | Guid | actor FK to membership |
| `Version` | long | the organization's `SettingsVersion` after the bump; unique per organization (`SetupModel.cs:80`) |
| `Section` | string | `SetupValue.Name(section)` so 1..160; values written: `companies`, `vehicles`, `recurring`, `expenses`, `investment`, `people`, `revenue`, `organization`, `localization`, `branding`, `securityPolicy`, `businessDate`, `logo`, and `pettycash` (petty-cash feature, `Infrastructure/PettyCashRepository.cs:155`) |
| `EntityId` | Guid | changed record id (organization id for settings sections; vehicle id for `investment`) |
| `VehicleId` | Guid? | **(uncommitted)** `:18-19`; set for sections `vehicles`, `investment` (= entity id), `revenue` (= record's vehicle, `RevenueRepository.cs:244-246`) and `pettycash` (= entry's vehicle) |
| `OccurredAt` | DateTimeOffset | UTC; stored as UTC datetime (`SetupModel.cs:88-91`) |
| `EffectiveFrom` | DateTimeOffset? | UTC; no caller ever sets it |
| `Before`, `After` | string | JSON text (`"null"` when absent); default System.Text.Json options (PascalCase for application snapshots, camelCase for settings sections) |
| `Reason` | string | trimmed, 1..500 |
| `CorrelationId` | string | max 100 |

Constructor refusals: any empty org/actor/entity or `version < 1` -> "Organization, actor, entity and a positive version are required."; blank or > 500 trimmed reason -> "A reason of 1–500 characters is required."; non-UTC instants -> "History instants must be UTC."; `vehicleId == Guid.Empty` -> "A vehicle id cannot be empty." **(uncommitted)**.
Setup write guard (`SetupModel.cs:122-133`): modifying or deleting `OrganizationSettingsVersion`, `VehicleTarget`, `VehicleAwayPeriod`, `RecurringVersion`, `RecurringAllocation` -> `InvalidOperationException("Setup versions and allocations are append-only.")`; deleting `PsvCompany`, `FleetVehicle`, `RecurringItem`, `RevenueRecord`, `ExpenseCategory`, `ExpenseItem` -> `InvalidOperationException("Setup records cannot be deleted.")`; modifying a vehicle `Registration` -> `InvalidOperationException("Registration cannot change.")`. `VehicleInvestment` is the only setup row that may be edited and deleted.

### `SetupActor` (`Application/ISetupExecution.cs:3-5`)

`SetupActor(OrganizationId, UserId, Today DateOnly, AllCompanies bool, CompanyIds, VehicleIds, CorrelationId, Permissions, SettingsVersion long? = null)`; `SettingsVersion` is **(uncommitted)** (null means unknown and nothing is cached). Built per request by `SetupExecution.Actor` (flow SU-X2).

---

# 2. Business rules catalogue

Columns: rule (inputs in brackets) | where enforced | how a violation surfaces | tests. `AuthService.cs` = `Application/AuthService.cs`, **deleted in the working tree**: its code now lives in `Application/Authentication/*` (see section 10; the `ID-` and 1.1 line citations to `AuthService.cs` and `Api/AuthEndpoints.cs` are as read before the split; `AuthEndpoints.cs` is now 85 lines).

## 2.1 Users, identity and sessions (`ID-`)

| # | Rule [inputs] | Where | Violation | Tests |
|---|---|---|---|---|
| ID-1 | A phone number is normalized before any lookup; input that does not normalize reaches no account [phone text] | `Domain/PhoneNumber.cs:25-49`; `AuthService.cs:13-15` | `Find` returns null, so the generic 401 | `DomainRuleTests.PhoneNumbersNormalizeToTheFullKenyanPrefix`, `AuthTests.ANumberThatIsNotAPhoneNumberReachesNoAccount` |
| ID-2 | Unknown number, removed user, user without PIN, paused account seen from an untrusted device and a capped untrusted device all answer identically [user, status, PIN, device trust] | `AuthService.cs:16,24-26,186-187,197-198`; `Application/AuthContracts.cs:34` | HTTP 401 body `{"status":"authentication_failed"}` | `AuthTests.APauseLooksLikeAnUnknownNumberExceptOnATrustedDevice`, `AuthTests.AUTH12_RemovedUserCannotSignInRefreshOrUseAccessToken` |
| ID-3 | The PIN hash is always verified, against a dummy hash when there is no user or no PIN, to equalize timing [pin, PinHash] | `AuthService.cs:184`; `Infrastructure/Security.cs:55-72` | none visible | none |
| ID-4 | A new PIN is 4 to 8 ASCII digits, not all the same digit, not a full +1 or -1 sequence (`1234`, `9876`; `7890` is allowed) [pin] | `Application/AuthContracts.cs:39-51`; `AuthService.cs:259` | 400 `{"status":"invalid_pin","minimumPinLength":4}` | `AuthTests.AUTH10_AUTH11_WeakPinsRejectedOnSetupAndReset`, `AuthTests.PinLongerThanMaximumIsRejectedBeforeHashing` |
| ID-5 | The organization's `PinLength` raises the minimum for a new PIN; the policy minimum is disclosed only to someone holding a valid unconsumed code [pin length, policy, code] | `AuthService.cs:267-271` | valid code: 400 `invalid_pin` with `minimumPinLength = policy.PinLength` (code not consumed); otherwise 401 generic | `AuthTests.PolicyPinLengthAppliesToNewPinsAndIsOnlyDisclosedWithAValidCode` |
| ID-6 | PIN storage: PBKDF2-HMAC-SHA256, 210000 iterations, 16-byte random salt, 32-byte hash, text `base64(salt).base64(hash)`; fixed-time compare [pin] | `Infrastructure/Security.cs:57-72` | verify false | `AuthTests` (all sign-in tests) |
| ID-7 | Code issuance: 6 random digits (`0..999999` zero-padded), expires 10 min after issue; at most one non-withdrawn code per (user, purpose) per 60 s (skipped in development mode); at most 5 non-withdrawn codes per user per rolling hour and 10 per rolling 24 h across all purposes; issuing consumes every earlier code of that (user, purpose) [user, purpose, now] | `AuthService.cs:42-44,46-71` | no code is issued and none is mailed; the response is still the normal 202 | `AuthTests.PurposeBindingGenericRequestsAndResendCooldown`, `AuthTests.HourlyCodeIssuanceLimitPreventsExcessiveCodes`, `AuthTests.DailyCodeIssuanceLimitPreventsExcessiveCodes` |
| ID-8 | A code is checked against the newest unconsumed code for (user, device, purpose); it must be usable (`!Consumed && now <= ExpiresAt && FailedAttempts < 5`); the comparison is fixed-time; a wrong code adds a failed attempt and the fifth consumes the code; a correct check alone does not consume it [code, device] | `AuthService.cs:86-105`; `Domain/Entities.cs:64-70` | `Matching` returns null -> generic 401 | `AuthTests.AUTH06_CodeExpiry_OPEN04_InclusiveBoundary`, `AuthTests.AUTH07_WrongCodeDoesNotTrustAndFiveWrongCodesInvalidateChallenge`, `AuthTests.SetupAndResetCodeChecksCountFailedAttempts`, `AuthTests.CorrectCodeCheckDoesNotConsumeTheCode` |
| ID-9 | Code purpose is bound to account state: `FirstSetup` only for a user without a PIN, `PinReset` and `NewDevice` only for a user with one; a request for a wrong state or unknown user still answers 202 `check_email` and sends nothing [user, purpose] | `AuthService.cs:109-116,242-250,257-266` | generic 202 (request) or 401 (verify/complete) | `AuthTests.PurposeBindingGenericRequestsAndResendCooldown`, `AuthTests.PinResetCannotCreateTheFirstPin`, `AuthTests.AUTH08_FirstPinRequired_AUTH09_SetupRequiresEmailCode` |
| ID-10 | Delivery: a `NewDevice` code is mailed before the reply (mail failure -> 503 `service_unavailable`); other codes are mailed after the reply; a code that cannot be sent is withdrawn (`Consumed`, `ExpiresAt = CreatedAt`) so it never counts for the cooldown or limits; nothing is mailed when the transaction fails [purpose] | `AuthService.cs:73-84`; `Infrastructure/Security.cs:116-177`; `Api/AuthEndpoints.cs:127` | 503 only for `NewDevice` | `AuthTests.ACodeRequestDoesNotWaitForTheMailServer`, `AuthTests.AFailedCommitSendsNoEmail`, `AuthTests.AnUndeliveredCodeIsWithdrawnSoARetryCanSendAnother`, `AuthTests.ACodeRequestWhoseEmailFailsLooksLikeAnyOtherRequest` |
| ID-11 | Correct PIN on a trusted device clears the lockout (`FailedAttempts = 0`, `PausedUntil = null`) and issues tokens; the untrusted counter is untouched [pin, device] | `AuthService.cs:223-224` | | `AuthTests.AUTH01_TrustedSignInIssuesTokens_And_OPEN05_ResetsFailures` |
| ID-12 | Correct PIN on an untrusted device issues a `NewDevice` code and answers 202 `verification_required` with `maskedEmail` = first character + `***` + the text from `@` (`***` when there is no `@` after position 0); the response is the same when no code could be issued [pin, device] | `AuthService.cs:214-222,252-256` | | `AuthTests.AUTH13_NewDevice_OPEN01_VerificationPersistsTrustAndConsumesCode`, `Phase1ContractTests.ANewPhoneVerifiesWithAnEmailCode` |
| ID-13 | Wrong PIN on a trusted device: `FailedAttempts++`; below the policy `LockoutThreshold` the answer is the generic 401; at or above it the account is paused until `now + LockoutMinutes` and the answer is 423 `paused` with `retryAfterSeconds` [policy, device trust] | `AuthService.cs:200-210` | 401 / 423 | `AuthTests.AUTH02_WrongPinIncrementsAndUsesGenericFailure`, `AuthTests.AUTH03_FifthFailurePauses_AUTH04_ExpiryResetsAtFifteenMinutes`, `AuthTests.TheWrongPinThatStartsAPauseShowsTheTimerOnATrustedDevice`, `AuthTests.SavedSecurityPolicyControlsLockoutAndTokenLifetimes`, `AuthTests.ConcurrentFailuresCannotLoseAttempts` |
| ID-14 | While `now < PausedUntil` a trusted device gets 423 `paused` with `retryAfterSeconds = ceil((PausedUntil - now) seconds)` and an untrusted device the generic 401; once `now >= PausedUntil` the next sign-in clears the pause first [user, device, now] | `AuthService.cs:24-26,189-193` | 423 / 401 | `AuthTests.APauseLooksLikeAnUnknownNumberExceptOnATrustedDevice`, `Phase1ContractTests.APausedAccountShowsTheTimerOnItsTrustedPhone` |
| ID-15 | Wrong PIN on an untrusted device never pauses the account: `UntrustedFailedAttempts++`; at 10 or more (`UntrustedAttemptLimit`) an untrusted device gets the generic 401 even for the right PIN; the counter resets only on `SetPin` or a successful `VerifyDevice`, never on `ClearLockout` [counter, device] | `AuthService.cs:44,197-198,211`; `Domain/Entities.cs:22-39` | 401 generic | `AuthTests.UntrustedDeviceWrongPinsDoNotLockTheAccount`, `AuthTests.PastTheAccountLimitAnUntrustedDeviceLearnsNothingFromThePin` |
| ID-16 | `VerifyDevice`: user active, has a PIN, not paused, and a matching `NewDevice` code (consumed here); then lockout and untrusted counter are cleared, the device is trusted (`TrustExpiresAt = now + TrustLifetimeDays` days, or never when the option is null) and tokens are issued [code, device, option] | `AuthService.cs:227-241,27-40` | generic 401 | `AuthTests.AUTH13_NewDevice_OPEN01_VerificationPersistsTrustAndConsumesCode`, `AuthTests.OPEN02_ConfiguredTrustExpiryRequiresVerificationAtExpiry` |
| ID-17 | `CompletePin` (FirstSetup or PinReset): valid PIN, correct purpose state, code consumed; then `SetPin` (`SecurityVersion++`, untrusted counter 0), `ClearLockout` (so a reset lifts a pause), every refresh token of the user revoked, every unconsumed code of the user consumed, device trusted, tokens issued [pin, code] | `AuthService.cs:257-284` | 400 invalid_pin / 401 | `AuthTests.AUTH05_ResetClearsPause_AUTH14_ChangesPinAndInvalidatesOldTokens`, `AuthTests.AnEmailResetLiftsTheLongestPause`, `Phase1ContractTests.AFirstPinIsSetWithAnEmailCode`, `Phase1ContractTests.AForgottenPinIsResetWithAnEmailCode` |
| ID-18 | Tokens need the user's single active membership and a role (else the generic 401); permissions = `Resolve(DefaultsFor(role), overrides, membership.Active)`; refresh token = base64 of 48 random bytes, stored as hash, expires `now + RefreshTokenDays` days; access token = HS256 JWT, issuer `xcode-api`, audience `xcode-clients`, claims `sub`, `device`, `version` (SecurityVersion), `org`, `role`, `first_name`, `last_name`, one `permission` per key, lifetime `AccessTokenMinutes` [policy] | `AuthService.cs:127-179`; `Infrastructure/Security.cs:74-91`; `Application/AuthContracts.cs:14-15` | generic 401 | `AuthTests.SavedSecurityPolicyControlsLockoutAndTokenLifetimes`, `Phase1ContractTests.TheSessionNamesThePersonAndTheirPermissions` |
| ID-19 | Refresh: token must exist and belong to the sent device; unknown/other device -> 401; owner not active -> revoke all of the user's tokens, 401; token already revoked (replay) -> revoke every token of that user on that device, 401; expired (`now >= ExpiresAt`), paused or untrusted device -> 401; else revoke this token and issue a new pair [hash, device] | `AuthService.cs:293-319` | 401 | `AuthTests.RefreshRotatesRejectsReplayAndSignOutRevokesSession`, `AuthTests.OPEN02_RevocationInvalidatesRefreshAndRequiresVerificationAgain` |
| ID-20 | Sign-out revokes the user's tokens on that device and always answers 200 `signed_out`; device revoke (own device only) revokes the trusted device, its tokens and its unconsumed codes, answers 200 `device_revoked`; another device id -> 403 [token, device] | `AuthService.cs:321-342`; `Api/AuthEndpoints.cs:80-86` | 403 for foreign device | `AuthTests.DeviceCannotRevokeAnotherDevice`, `Phase1ContractTests.SwitchUserRevokesThisPhone` |
| ID-21 | Every authenticated request re-checks: user exists and `Active`; token claim `version` equals `SecurityVersion`; the trusted device row exists, is not revoked and not expired; zero clock skew [claims, user, device] | `Program.cs:98-128` | 401 | `AuthTests.AUTH12_RemovedUserCannotSignInRefreshOrUseAccessToken`, `AccessLifecycleTests.ChangingSignInDetailsEndsSessionsButKeepsThePin` |
| ID-22 | `SecurityVersion` increases when: a PIN is set, a user is removed, a person's name/role/single permissions change, sign-in details change, or provisioning changes phone/status/membership/role; the old access token then fails and the client refreshes [events] | `Domain/Entities.cs:22-49`; `Application/AccessUseCases.cs:158,192-193`; `Infrastructure/UserProvisioning.cs:67-75` | 401 on next request | `AccessLifecycleTests.ChangingSomeonesAccessRenewsTheirTokenWithoutSigningThemOut`, `AuthTests.ReprovisioningAnExistingAccountRevokesItsOldSession` |
| ID-23 | The policy used by auth is read without tracking, clamped into the bounds (8 columns, section 1.3) and replaced by defaults when no row exists; the user's policy is the one of their single active membership, defaults when none [policy] | `AuthService.cs:118-125`; `Infrastructure/Security.cs:34-52` | | `AuthTests.AStoredPolicyOutsideTheBoundsIsEnforcedWithinThem`, `AccessAndSetupTests.AnOlderOutOfRangePolicyDoesNotBreakEveryonesScreens` |
| ID-24 | Auth requests are validated before any work: `DeviceId` 1..128 chars, `PhoneNumber` <= 14, `Email` <= 320 and a valid address when not empty, `Pin` <= 8, `Code` <= 32, `RefreshToken` <= 256 [request] | `Api/AuthEndpoints.cs:108-110` | 400 `{"status":"invalid_request"}` | `Phase1ContractTests.AnIncompleteRequestIsInvalid` |
| ID-25 | Auth work for one account is serialized (key = normalized phone, else `device:{id}`; at most 10000 keys) and runs in one serializable transaction; `User.Version` and `RefreshToken.Version` are bumped on each modification [phone] | `Api/AuthEndpoints.cs:14-50,103-126`; `Infrastructure/AuthDb.cs:67-74` | | `AuthTests.AStaleWriteToAPersonOrTheirSessionConflictsRatherThanOverwrites`, `AuthTests.TwoDifferentPhoneNumbersCanSignInConcurrently` |
| ID-26 | Rate limit: fixed window of 1 minute per client IP, 30 permits (10000 in `Testing`), no queue, on every `/auth/*` route [ip] | `Program.cs:90-98`; `Api/AuthEndpoints.cs:56-57` | HTTP 429, no body | none |
| ID-27 | Operator provisioning: valid e-mail; phone must normalize; role (when named) must be one of the four catalog roles (case-sensitive key lookup) else `ArgumentException("Unknown role. Use one of: Owner, Office admin, Fleet manager, Revenue clerk.")`; e-mail lower-cased; phone already used by another e-mail -> "That mobile number already belongs to someone else."; only one organization may exist; reactivates an inactive membership; keeps the existing role unless named (default role `Owner`); invalidates all credentials when phone, status, membership or role changed; Owner and Office admin get an `AllCompanies` scope when they have none; name defaults come from the e-mail (`first.last@` -> "First Last", else "New Member") [request] | `Infrastructure/UserProvisioning.cs:16-120` | `ArgumentException` | `AuthTests.ProvisionedPeopleCanSetAPinAndSignIn_AndReprovisioningKeepsTheirRole`, `AuthTests.ReprovisioningAnExistingAccountRevokesItsOldSession` |
| ID-28 | New organization defaults (provisioning): name `My fleet` (or the given name trimmed), slug `my-fleet`, default localization, branding and security policy rows [name] | `Infrastructure/UserProvisioning.cs:86-98` | | none |
| ID-29 | `--remove-user <email>`: marks the user removed (`Remove()`) and revokes all their refresh tokens (trusted devices stay, but the security version already invalidates access tokens) [email] | `Program.cs:224-236` | `ArgumentException` for an invalid e-mail | none |

## 2.2 Access: roles, permissions, anti-escalation, people, visibility (`AC-`)

`AccessUseCases.cs` = `Application/AccessUseCases.cs`.

| # | Rule [inputs] | Where | Violation | Tests |
|---|---|---|---|---|
| AC-1 | The permission catalog is exactly 40 keys in 8 groups (section 5.1), each key a constant of `Domain/PermissionKeys.cs:4-53`; any active member may read it | `Application/AccessContracts.cs:26-96`; `Domain/PermissionKeys.cs:4-53`; `AccessUseCases.cs:14` | | `AccessAndSetupTests.EveryMemberCanReadPermissionLabelsButNotPeople`, `Phase1ContractTests.TheCatalogKeepsItsShapeAndTheNamesThePhoneLooksFor` |
| AC-2 | Permissions depend on other permissions (30 direct edges from 27 keys, section 5.2); a granted permission brings its transitive dependencies | `Domain/Access.cs:55-103` | | `DomainRuleTests.PermissionDependenciesAreTransitiveAndDenyingARequiredPermissionRemovesDependents` |
| AC-3 | Effective permissions = closure(role defaults + granted overrides) minus denied overrides, then repeatedly drop any permission with a missing direct dependency; an inactive membership has none [role, overrides, active] | `Domain/Access.cs:109-131`; `Infrastructure/OrganizationRepository.cs:24-34` | | same as AC-2; `RevenueRefusalTests` (uses `Deny`) |
| AC-4 | A role's defaults come only from `PermissionCatalog.RolePermissions` (four roles, names matched ignoring case) expanded with dependencies; an unknown role name has no defaults; the legacy `RolePermission` table is ignored [role name] | `AccessContracts.cs:104-131` | | `AccessAndSetupTests.RoleDefaultsComeOnlyFromTheCatalog`, `AccessAndSetupTests.RoleDefaultsFollowWebV28` |
| AC-5 | Request-time authorization: caller must be an **active member** and hold **at least one** of the required permissions (none required = any active member; an empty set resolves no permissions at all, `OrganizationPort.cs:46-50`); permissions are re-resolved from the database on every request (once per request), never taken from the token [member, permissions] | `Application/OrganizationPort.cs:34-60`; `Infrastructure/OrganizationRepository.cs:17-34` | `UnauthorizedAccessException` -> 403, no `detail` | `AccessAndSetupTests.APlainRefusalGivesNoDetail`, `InvestmentTests.ViewingNeedsInvestViewAndChangingNeedsInvestManage`, `PeopleQueryCostTests.PermissionsAreResolvedOncePerRequest` |
| AC-6 | The four catalog roles are created per organization on demand (`EnsureRoles`); a role named in a save is matched ignoring case, else `ArgumentException("Unknown role.")`; listing roles is therefore a write that needs `people.view` | `AccessUseCases.cs:17-24,560-565`; `Infrastructure/UserProvisioning.cs:102-112` | 400 | `AccessAndSetupTests.RoleDefaultsComeOnlyFromTheCatalog` |
| AC-7 | A person has exactly one role; a user has at most one active membership | `OrganizationModel.cs:31-34,65-70` | DB unique violation -> 409 "A conflicting record exists. Reload before saving." | none |
| AC-8 | Person input: first and last name 1..100 after trim ("First and last name are required."); e-mail <= 320 and parseable ("A valid email is required."); phone must normalize ("A valid mobile number is required."); scope mode in `all`/`companies`/`vehicles` ("Choose a data scope."); `companies` or `vehicles` needs at least one id ("Choose at least one item in the data scope."); ids distinct ("Data scope items must be distinct."); permissions non-empty, distinct (ordinal) and `ApprovalLimit >= 0` ("Permissions and approval limit are invalid.") [SavePerson] | `AccessUseCases.cs:329-353` | `ArgumentException` -> 400 | `AccessAndSetupTests` (Person helper); no per-message test |
| AC-9 | Only an actor who sees every company can give scope `all` [actor, mode] | `AccessUseCases.cs:357-358` | 403 "Only someone who can see every company can give access to every company." | none |
| AC-10 | Company scope: every id must exist in the organization ("Choose companies in your organization."); a non-organization-wide actor may give only companies in their own scope, plus ones the person already holds outside it (retained) [company ids] | `AccessUseCases.cs:360-375` | 400 / 403 "You can only give access to companies in your own data scope." | `AccessAndSetupTests.ScopedEditorsCannotEraseAssignmentsOutsideTheirScope` |
| AC-11 | Vehicle scope: every id must exist ("Choose vehicles in your organization."); the actor may give only vehicles they can see (own vehicle or vehicle of an own company), plus retained ones [vehicle ids] | `AccessUseCases.cs:377-400` | 400 / 403 "You can only give access to vehicles in your own data scope." | `AccessLifecycleTests.SignInDetailsRequireTheEditorToSeeTheTargetsFullDataScope`, `AccessAndSetupTests.PeopleShowOnlyTheCompaniesAndVehiclesTheViewerCanReach` |
| AC-12 | Assignments outside the editor's reach are preserved on save (appended to the submitted list); when such items exist the editor cannot change the kind of scope [target, actor] | `AccessUseCases.cs:403-433` | 403 "This person's data scope includes companies or vehicles outside your own, so you cannot change which kind of scope they have. Their companies and vehicles outside your view are kept as they are." | `AccessAndSetupTests.ScopedEditorsCannotEraseAssignmentsOutsideTheirScope`, `AccessAndSetupTests.PeopleShowOnlyTheCompaniesAndVehiclesTheViewerCanReach` |
| AC-13 | Nobody edits, deactivates or signs out themselves through the people API [id vs actor] | `AccessUseCases.cs:98-99,202-203,238-239` | 400 "You cannot change your own access here." / "You cannot deactivate your own access." / "Use sign out for your own session." (the save check runs after scope validation) | none |
| AC-14 | Only an Owner gives the Owner role (create or role change); only an Owner changes, removes or signs out an Owner (role named `Owner`, ignoring case) [role, actor] | `AccessUseCases.cs:101-105,514-518,558` | 403 "Only an Owner can give the Owner role." / "Only an Owner can change, remove or sign out an Owner." | `AccessAndSetupTests.OnlyAnOwnerGivesTheOwnerRole`, `AccessLifecycleTests.OnlyOwnersCanDeactivateOrSignOutAnOwner` |
| AC-15 | A non-Owner may give a role (on create and on a role change) only if they hold every default permission of that role after expansion [role defaults, held] | `AccessUseCases.cs:495-500` | 403 "You can only grant roles whose permissions you hold." | `AccessAndSetupTests.NonOwnersGiveOnlyRolesInsideTheirOwnPermissions`, `AccessAndSetupTests.PeopleManagersAssignRolesButOnlyAccessManagersChangeSinglePermissions` |
| AC-16 | Single-permission deviations from the role and any approval-limit change need `access.manage` unless the actor is an Owner; granted deviations must be permissions the actor holds; no change in deviations and the same limit passes [deviation before/after, limit] | `AccessUseCases.cs:490-511,623-631` | 403 `Changing single permissions or an approval limit needs "Change single permissions and approval limits for a person".` / "You can only grant permissions you hold." | same two tests; `AccessAndSetupTests.EditingAnInactivePersonKeepsTheirAssignedPermissions` |
| AC-17 | Requested permissions are expanded with dependencies and every key must be in the catalog [permissions] | `AccessUseCases.cs:107-109` | 400 "Unknown permission." | none |
| AC-18 | Changing a person's e-mail or phone needs an Owner, or an editor who sees the person's whole scope (no `all` scope, every company and vehicle in reach) and holds every permission the person holds and `access.manage` when the person has an approval limit [target, actor] | `AccessUseCases.cs:119-122,523-556` | 403 "Only an Owner, or someone who can see this person's full data scope, can change their email or mobile number." / "Only an Owner, or someone who holds everything this person holds, can change their email or mobile number." | `AccessLifecycleTests.SignInDetailsOfSomeoneHoldingMoreThanTheEditorCanGrantNeedAnOwner`, `AccessLifecycleTests.SignInDetailsRequireTheEditorToSeeTheTargetsFullDataScope` |
| AC-19 | E-mail (trim, lower-case) and normalized phone must not belong to any other user [email, phone] | `AccessUseCases.cs:112-113,123-124` | 400 "That mobile number or email already belongs to someone." | none |
| AC-20 | Updating a person needs the version they were loaded at: missing -> 400 "Reload this person before saving."; different from `Membership.Version` -> `DbUpdateConcurrencyException("This person's access changed. Reload before saving.")` -> 409 [version] | `AccessUseCases.cs:91-94` | 400 / 409 | `AccessLifecycleTests.StaleAccessFormsCannotOverwriteNewerChanges`, `Phase1ContractTests.EditingAPersonFromTheDevelopWebAsksForAReload`, `ChangeLogAndScopeTests.AStaleRecordStillConflictsAtOnce` |
| AC-21 | Create: new `User` (Active, no PIN), membership (version 1, `ApprovalLimit`), one `PersonRole`, scope rows for the chosen mode, overrides only where the requested set differs from role defaults; audit `person.created`; history "Added {First Last} as {Role}" [SavePerson] | `AccessUseCases.cs:126-149,262-268,467-482` | | `ChangeLogAndScopeTests.PeopleAndAccessChangesJoinTheChangeLog` |
| AC-22 | Update replaces role, overrides and scope rows wholesale; membership `Version++` (`AccessChanged`) only when something changed (`name`, `sign-in details`, `role`, `single permissions`, `data scope`, `approval limit`); `SecurityVersion++` when name, role or single permissions changed; sign-in details change always bumps it and revokes every device and refresh token (PIN kept); audit `person.updated` (and `person.sign_in_details_changed`); history "Changed {a, b and c} for {Name}" [diff] | `AccessUseCases.cs:151-196,593-621` | | `AccessLifecycleTests.ChangingSignInDetailsEndsSessionsButKeepsThePin`, `AccessLifecycleTests.ChangingSomeonesAccessRenewsTheirTokenWithoutSigningThemOut` |
| AC-23 | Deactivate: needs the loaded version unless already inactive (idempotent no-op); typed reason 1..500 required (kept after the automatic text "Removed access for {Name}"); `Membership.Deactivate()`, `User.Remove()` (security version bump), every device and refresh token revoked; audit `person.deactivated`. Activate: `Membership.Reactivate()`, `User.Status = Active`, no session change; reason "Restored access for {Name}"; audit `person.activated` [id, version, reason] | `AccessUseCases.cs:199-234` | 409 "This person's access changed. Reload before saving."; 400 reason | `AccessLifecycleTests.BodylessLifecycleCallsFromOlderClientsGetAReloadProblem`, `AutomaticReasonTests.ATypedReasonFollowsTheAutomaticOne`, `Phase1ContractTests.RemovingAccessFromTheDevelopWebAsksForAReload` |
| AC-24 | Sign a person out of every device: revoke all their trusted devices and refresh tokens; audit `person.sessions_revoked`; history "Signed {Name} out of every device" [id] | `AccessUseCases.cs:236-247,568-574` | | `AccessLifecycleTests.OnlyOwnersCanDeactivateOrSignOutAnOwner`, `ChangeLogAndScopeTests.PeopleAndAccessChangesJoinTheChangeLog` |
| AC-25 | People visibility (list, get, save, lifecycle, change log): only people who have a role; an organization-wide actor sees all; otherwise the actor themself, anyone whose company scope meets the actor's companies or the companies of the actor's own vehicles, and anyone whose vehicle scope holds a vehicle in `vehicles(id in actor vehicles or company in actor companies)` [actor scope] | `Application/PeopleVisibility.cs:16-31` | 404 for a hidden id | `PeopleQueryCostTests.ScopedPeopleListsShowExactlyThePeopleInScope`, `AccessAndSetupTests.PeopleShowOnlyTheCompaniesAndVehiclesTheViewerCanReach` |
| AC-26 | A person's DTO lists only the companies and vehicles within the viewer's reach and counts the rest (`otherCompanies`, `otherVehicles`); permissions are the person's effective set even when inactive; list order = last name, first name, user id [viewer] | `AccessUseCases.cs:66-78,279-327` | | `AccessAndSetupTests.PeopleShowOnlyTheCompaniesAndVehiclesTheViewerCanReach` |
| AC-27 | `people.manage` needed for save, lifecycle and scope options; `people.view` for list, get and roles; any active member for the catalog and `/setup/access/me` (own scope) [permission] | `AccessUseCases.cs:14-81` | 403 | `AccessAndSetupTests.MeListsTheCompaniesAndVehiclesTheCallerWouldSee`, `AccessAndSetupTests.EveryMemberCanReadPermissionLabelsButNotPeople` |
| AC-28 | There is no invitation entity. A person is created directly with e-mail and phone; they set their first PIN with an e-mailed `FirstSetup` code (ID-9, ID-17) [flow] | `AccessUseCases.cs:126-149`; `AuthService.cs:242-284` | | `AuthTests.AUTH08_FirstPinRequired_AUTH09_SetupRequiresEmailCode` |

## 2.3 Organization settings, business date, preferences and the change log (`OS-`)

`Settings/` = `Application/Settings/` **(uncommitted, untracked)**: `OrganizationSettingsUseCases.cs`, `SettingsSections.cs` (`ISettingsSection`, `MergedSection<T>`, `OrganizationDetailsSection`, `BusinessDateSection`), `SettingsText.cs` (`AutomaticReason`, `CalendarDate`, `DescribeLogo`), `SettingsContracts.cs` (DTOs) and `SettingsChangeLog.cs`. `Api/OrganizationEndpoints.cs` is transport only. Settings, logo and preference writes run through `execution.Write` and so through `UnitOfWork.Execute` (serializable transaction, change-log collision retry, 409 after four attempts); reads run through `execution.Read` and are `AsNoTracking`.

| # | Rule [inputs] | Where | Violation | Tests |
|---|---|---|---|---|
| OS-1 | "Today" for every setup and revenue calculation is the organization's business date: `Organization.BusinessDate` when held, else the calendar date in the **organization** time zone (never the person's time zone) [business date, zone, clock] | `Infrastructure/Setup/SetupExecution.cs:41-49`; `Domain/Organization.cs:92` |  | `OrganizationSettingsTests.BusinessDateUsesTheServerDateForSetupAndIsAudited` |
| OS-2 | A held business date cannot be `0001-01-01` or later than the organization's calendar date; `null` returns to the calendar; unchanged -> no-op. Payload must be `null` or a parseable date string [value] | `Domain/Organization.cs:93-100`; `Application/Settings/SettingsSections.cs:112-137` | 400 "The business date cannot be in the future." / "Business date must be a valid calendar date or null." | `DomainRuleTests.BusinessDateCannotMoveIntoTheFutureAndCanFollowTheOrganizationClock`, `OrganizationSettingsTests.SettingsShowTheCalendarDateAFrozenBusinessDateCanAdvanceTo` |
| OS-3 | The business date may move backward and forward (up to the calendar date) at any time; records already captured are not touched [date] | `Application/Settings/SettingsSections.cs:116-126` |  | `RecurringCrudTests.OwnerCanCreateReadUpdateAndStopARecurringItem` |
| OS-4 | After a localization save that changed anything, the held business date must not be later than the calendar date in the **saved** time zone [zone, business date, clock]. The version moves once for the whole save, by the section change-log entry (OS-19), not by the zone change | `Application/Settings/SettingsSections.cs:35-36` (`afterMerge` hook of the `localization` section, run only when the merge changed something); `Domain/Organization.cs:103-115` | 400 "The held business date would be in the future in that time zone. Change the business date first."; the section is not saved | `OrganizationSettingsTests.ALocalizationSaveCannotLeaveAHeldBusinessDateInTheFuture` |
| OS-5 | The calendar date of a zone is `date(convert(now UTC, zone))`; an unknown or invalid stored zone -> "The organization time zone is not available." / "...is invalid." [zone] | `Application/Settings/SettingsText.cs:13-27` | 400 | none |
| OS-6 | Section `organization`: name trimmed 1..200; slug trimmed, lower-cased, 1..100, `^[a-z0-9]+(?:-[a-z0-9]+)*$`; slug unique across all organizations [name, slug] | `Application/Settings/SettingsSections.cs:91-109`; `Api/OrganizationEndpoints.cs:23-29` | 400 `{ "detail": "Enter an organization name and a lowercase slug using letters, numbers, and hyphens." }`; 409 `{ "detail": "This organization slug is already in use." }` (plain JSON, not problem details: a `SectionRefusal(Detail, Conflict)` returned by the section and mapped by the endpoint, `Api/OrganizationEndpoints.cs:26-28`). A value that deserializes to `null` is `ArgumentException("Invalid organization details.")` (problem 400) | `OrganizationSettingsTests.OrganizationAndLocalizationSettingsPersistCamelCaseValues`, `OrganizationSettingsTests.ASlugAnotherOrganizationUsesIsRefused` |
| OS-7 | Sections `localization`, `branding`, `securityPolicy`: the sent fields are merged onto the saved row (or defaults) so a partial payload never resets omitted fields; the merged row is validated with the entity's `Validate()`; payload must be an object with correctly typed values; property names match case-insensitively; a field sent under a legacy name counts as the current name unless the current name is sent too (only `localization` maps one: `useGroupping` -> `useGrouping`, case-insensitive) **(uncommitted, phase 6)** [section JSON] | `Application/Settings/SettingsSections.cs:45-89` (`MergedSection<T>.Apply`; sections registered at `:31-42`) | 400 "Send the section's settings as an object." / "A setting has the wrong type of value." / "Invalid settings." plus the entity messages (section 1.3) | `OrganizationSettingsTests.APartialSectionKeepsTheFieldsItOmits`, `OrganizationSettingsTests.SecurityPolicyCannotDisablePinSignIn`, `OrganizationSettingsTests.GroupingSentUnderItsOldNameIsSavedAndBothNamesAreServed` **(uncommitted)**, `AccessAndSetupTests.OrganizationSettingsFailuresMapToClientErrors` |
| OS-8 | Saving what is already stored (before JSON equals after JSON) changes nothing: no version bump, no history row, no audit row; answers 200 `{section}` [before, after] | `Application/Settings/OrganizationSettingsUseCases.cs:39-44` (`ChangeTracker.Clear()`, then `SettingsSaveResult(section)`) |  | `ChangeLogAndScopeTests.SettingsHistoryRecordsWhatWasSavedAndSkipsUnchangedSaves` |
| OS-9 | A changed section bumps `SettingsVersion` exactly once (inside `SettingsChangeLog.Record`), writes one change-log row (entity id = organization id, `Before`/`After` camelCase JSON) and one audit row `organization.settings.updated` (`Entity` = section, `After` = `{"value": <after JSON>, "reason": <final reason text>}`) [section] | `Application/Settings/OrganizationSettingsUseCases.cs:45,133-149`; `Application/Settings/SettingsChangeLog.cs:11-19` |  | `AccessAndSetupTests.OrganizationSettingsChangesKeepTheirReason` |
| OS-10 | Settings need `organization.manage`; unknown section name -> `KeyNotFoundException` -> 404, raised inside the use case after the reason check (a bad reason answers 400 first) and after the organization row is loaded; there is no endpoint switch any more [section] | `Application/Settings/OrganizationSettingsUseCases.cs:16,33,37` | 403 / 404 | `AccessAndSetupTests.OrganizationSettingsFailuresMapToClientErrors` |
| OS-11 | Reasons: a typed reason is optional, trimmed, 1..500 (blank = none); the change log always gets an automatic reason and the typed one follows as `{automatic}. Reason: {typed}.` (no second full stop when the typed text ends in `.`, `!` or `?`); when both exceed 500 characters the automatic part is cut first (`room = max(500 - suffixLength, 100)`, cut text ends in `...`) and the result is clipped to 497 + `...` [reason] | `Application/Setup/SetupContracts.cs:106-124`; typed reason read first at `OrganizationSettingsUseCases.cs:35` | 400 "A reason of 1–500 characters is required." | `AutomaticReasonTests.ATypedReasonIsStillCheckedAndUsed`, `AutomaticReasonTests.ATypedReasonIsKeptWholeWithinTheChangeLogsLimit`, `AutomaticReasonTests.ATypedReasonFollowsTheAutomaticOne` |
| OS-12 | Automatic reason for a settings section: business date -> `Set the business date to {yyyy-MM-dd}` or `Returned the business date to the calendar`; otherwise `Changed ` + the changed top-level fields (ignoring `organizationId`) as `{setting name} to {value}` joined by `, ` and ` and ` (section 3.11 for names and values); `Changed the {section} settings` when no field differs [before, after] | `Application/Settings/SettingsText.cs:30-75` (names `:30-54`, `AutomaticReason` `:56-65`, `SettingValue` `:67-75`); `SettingsSections.cs:128-129` (business date) |  | `OrganizationSettingsTests.SettingsSavedWithoutAReasonGetAnAutomaticOne`, `AccessAndSetupTests.OrganizationSettingsChangesKeepTheirReason` |
| OS-13 | Logo upload: reason checked first; data URL longer than 349592 chars -> "The logo must be at most 256 KB." before decoding; must match `^data:(image/(?:png|jpeg|webp));base64,([A-Za-z0-9+/=]+)$` ("Upload a PNG, JPEG or WebP image."); decode failure "The image could not be read."; decoded size 0 or > 262144 -> "The logo must be at most 256 KB."; magic bytes must match (png `89 50 4E 47 0D 0A 1A 0A`; jpeg `FF D8 FF`; webp `52 49 46 46` and bytes 8..11 = `WEBP`) else "The file is not the image type it claims to be."; SVG refused; always writes history `logo` (shape only: `{contentType, bytes, updatedAt}`), reason `Uploaded a new logo` [data URL] | `Domain/Organization.cs:229-275`; `Application/Settings/OrganizationSettingsUseCases.cs:49-61`; `Application/Settings/SettingsText.cs:77-79` | 400; 403 without `organization.manage` | `AppearanceTests.LogoUploadsAreCheckedRecordedAndShownToMembers`, `ChangeLogAndScopeTests.OversizedLogosAreRefusedBeforeTheyAreRead` |
| OS-14 | Logo delete: no logo -> 200 `{logo:null}` and nothing logged; else removed, history `logo` with `After = "null"`, reason `Removed the logo` (typed reason via `?reason=`) [reason] | `Application/Settings/OrganizationSettingsUseCases.cs:63-72` |  | `AppearanceTests.LogoUploadsAreCheckedRecordedAndShownToMembers` |
| OS-15 | Preferences: any active member reads and writes their own; the write replaces every field (null clears), validates it (`UserPreference.Validate`), then refuses non-null values the organization does not allow; no change-log row, no version bump (the write still runs in `UnitOfWork.Execute`). On read, values for withdrawn overrides are returned as null [preference, localization] | `Application/Settings/OrganizationSettingsUseCases.cs:95-131`; `Domain/Organization.cs:173-183,312-328` | 400 with the `EnsureAllowed` messages | `OrganizationSettingsTests.PreferenceWritesRefuseOverridesTheOrganizationDoesNotAllow`, `ChangeLogAndScopeTests.PreferencesSayWhichOverridesTheOrganizationAllows` |
| OS-16 | Effective settings: `locale` = override allowed ? (preference ?? org) : org; `timeZone` and `hour12` likewise; `themeMode` = override allowed ? (preference ?? `system`) : `light`; `reducedMotion` = preference ?? false; `fontScale` = preference ?? 1; `direction` from the locale; all other formats come from the organization. Every input is validated on every read (branding colour contrast included) and the security policy is clamped [localization, branding, policy, preference] | `Domain/Organization.cs:353-384`; `Infrastructure/OrganizationRepository.cs:36-45` | `ArgumentException` -> 400 if stored data is invalid | `AppearanceTests.EveryMemberSeesTheOrganizationsSavedBrandingAndFormats` |
| OS-17 | Appearance (any active member) exposes organization name, `SettingsVersion`, business date (held or calendar), branding, formats, theme, motion, font scale, `lockoutThreshold`, `lockoutMinutes` and the logo data URL; `formats` carries both `useGrouping` and the legacy `useGroupping` with the same value **(uncommitted, phase 6)** [member] | `Application/Settings/OrganizationSettingsUseCases.cs:74-93`; `Application/Settings/SettingsContracts.cs:16-18` | 403 for non-members | `AppearanceTests.EveryMemberSeesTheWrongPinPolicy`, `Phase1ContractTests.AppearanceKeepsEveryFieldTheClientsRead` |
| OS-18 | Every change-log row: positive version, non-empty org/actor/entity, reason 1..500, UTC instants, non-empty vehicle id when given **(uncommitted)**; rows are append-only; `Version` is unique per organization; `Version` = `SettingsVersion` after `SettingsChanged()` in the same transaction [row] | `Domain/Setup/OrganizationSettingsVersion.cs:26-40`; `SetupModel.cs:78-80,122-133` | `ArgumentException` / `InvalidOperationException` | `ChangeLogPagingTests` **(uncommitted)** |
| OS-19 | Writers that log a change (settings, setup, revenue, people, petty cash) all increment the one `Organization.SettingsVersion`, always through `SettingsChangeLog.Record`, the only writer of change-log rows and the only caller of `Organization.SettingsChanged()` (`Application/Settings/SettingsChangeLog.cs:11-19`) (a concurrency token), so concurrent writers collide on that row; the unit of work retries the whole use case when **only** `Organization` entries conflict (or SQL error 1205), up to 3 retries (4 attempts), after clearing tracked state and resolved permissions and waiting `Random(5..24) * (attempt + 1)` ms; access is re-checked on each attempt; any other conflict (a stale record) surfaces at once [writers] | `Infrastructure/OrganizationRepository.cs:48-92`; `Application/Settings/SettingsChangeLog.cs:11-19` | 409 "Settings changed. Reload before saving." after the fourth failure | `ChangeLogAndScopeTests.WritesToDifferentRecordsRetryWhenOnlyTheChangeLogCollides`, `ChangeLogAndScopeTests.SettingsWritesRetryWhenOnlyTheChangeLogCollides`, `ChangeLogAndScopeTests.ARetryChecksAccessAgain`, `ChangeLogAndScopeTests.AStaleRecordStillConflictsAtOnce`, `OrganizationSettingsTests.ALocalizationSaveMovesTheVersionOnce` |
| OS-20 | Change-log visibility ("history" use case needs `audit.view`): rows of section `people` need `people.view` for everyone; an organization-wide actor then sees all rows; any other actor sees only `companies` rows for companies in reach, `vehicles`/`investment`/`revenue`/`pettycash` rows whose `VehicleId` is a vehicle in reach (current company membership, **(uncommitted)**; HEAD joins through the entity id and the revenue record), `recurring` rows for items all of whose shares are in reach, every `expenses` row, `people` rows for people they may see (AC-25); the settings sections (`organization`, `localization`, `branding`, `securityPolicy`, `businessDate`, `logo`) are visible only to organization-wide actors [actor, rows] | `Infrastructure/Setup/SetupRepository.cs:291-313`; `Api/SetupEndpoints.cs:132-140` | rows silently absent | `PeopleHistoryTests.ScopedAuditorsSeeChangesToVisiblePeopleWithHiddenScopeRedacted`, `ChangeLogPagingTests.ScopedViewersSeeRevenueOnlyForTheVehiclesTheyCanSeeToday` **(uncommitted)**, `InvestmentTests.AScopedPersonSeesAndChangesOnlyTheirVehiclesInvestment` |
| OS-21 | For a viewer who is not organization-wide, `people` snapshots are redacted: `CompanyIds` and `VehicleIds` in `Before` and `After` keep only ids in the viewer's reach [snapshots] | `SetupRepository.cs:380-405` |  | `PeopleHistoryTests.ScopedAuditorsSeeChangesToVisiblePeopleWithHiddenScopeRedacted` |
| OS-22 | History filters (all optional, combined with AND, applied before paging and counting): `section` (exact), `from`/`to` (days in the **organization** zone, both included: `OccurredAt >= midnight(from)` and `< midnight(to + 1 day)`), `text` (case-insensitive substring of the reason or of the actor's "First Last", wildcard characters taken literally); `from > to` -> 400 "The first date cannot be after the last date."; text trimmed > 200 -> 400 "Search for 200 characters or fewer."; blanks mean unset [filter] | `Application/Setup/SetupContracts.cs:26-40`; `SetupRepository.cs:338-378` (the actor-name match is a first query for membership ids, `:372-375`) | 400 | `ChangeLogAndScopeTests.TheChangeLogIsNarrowedByItsFilters` |
| OS-23 | History paging: newest first by `Version`; page 1..100000, size 1..100; `before` (a positive version) seeks `Version < before` without an offset **(uncommitted)**, else offset `(page-1)*size`; `hasMore` is true when one more row exists and `nextBefore` is then the last returned version; `total` is the filtered count unless `includeTotal=false` **(uncommitted)**; `before < 1` -> 400 "Before must be a change log version." [page, size, before] | `SetupRepository.cs:316-335`; `Api/SetupEndpoints.cs:132-140`; `SetupContracts.cs:102-105` | 400 "Page must be 1–100000 and page size 1–100." | `ChangeLogPagingTests.PagingByVersionReturnsTheSameRowsAsPagingByNumber` **(uncommitted)** |
| OS-24 | The history count is cached per (organization, settings version, viewer scope string, sees-people flag, filter) for 5 minutes, at most 10000 entries; a changed version means a different key; skipped when `SettingsVersion` is unknown **(uncommitted)** | `Infrastructure/Setup/HistoryCountCache.cs:10-57` | | `ChangeLogPagingTests.TheCountIsSkippedOnRequestAndCountedOncePerChange` **(uncommitted)** |
| OS-25 | Tenant isolation and write guards: queries are filtered to the caller's organization; writes to another organization's row, to a non-add audit row or with a non-UTC instant are refused; operator flows bypass with `Provisioning` [org context] | `Infrastructure/OrganizationModel.cs:12-16,87-114` | 403 "Cross-organization write rejected." / 500 / 400 "Instants must be UTC." | `ChangeLogAndScopeTests` (scope), `AuthTests` |
| OS-26 | Audit trail is a second store: every logged change also adds an `AuditEvent` (setup: `setup.{section}`; revenue: `revenue.recorded`; settings: `organization.settings.updated`; people: `person.*`) with JSON before/after, the actor, correlation id and UTC time [change] | `SetupRepository.cs:475-481`; `Infrastructure/RevenueRepository.cs:241-248`; `Application/Settings/OrganizationSettingsUseCases.cs:133-149`; `Infrastructure/OrganizationRepository.cs:104-114`; `AccessUseCases.cs:575-587` |  | `AccessLifecycleTests.ChangingSignInDetailsEndsSessionsButKeepsThePin`, `AccessAndSetupTests.OrganizationSettingsChangesKeepTheirReason` |
| OS-27 | `SettingsSectionRegistry` no longer exists: the type (`Infrastructure/SettingsSectionRegistry.cs`) and its registration were deleted. The section list is `SettingsSections.All()`: `organization`, `localization`, `branding`, `securityPolicy`, `businessDate`; each `ISettingsSection` is registered as a singleton and the use case looks the section up by key | `Application/Settings/SettingsSections.cs:31-42`; `Api/OrganizationEndpoints.cs:8-15`; `Application/Settings/OrganizationSettingsUseCases.cs:14,37` |  | `AccessAndSetupTests.OrganizationSettingsFailuresMapToClientErrors` (unknown section), `OrganizationSettingsTests.SettingsUseCasesSaveASectionWithoutHttp` |

## 2.4 Setup: companies, vehicles, away periods (`SU-C`, `SU-V`, `SU-A`)

Sources: `Application/Setup/CompanyUseCases.cs`, `Application/Setup/VehicleUseCases.cs`, `Infrastructure/Setup/SetupRepository.cs` (`SetupRepository.cs`).

| # | Rule [inputs] | Where | Violation | Tests |
|---|---|---|---|---|
| SU-C1 | A company name is trimmed, 1..160; unique per organization ignoring case (`NormalizedName = upper(name)`), excluding itself [name] | `CompanyUseCases.cs:18,26-27`; `PsvCompany.cs:27-34` | 400 "Name must contain 1-160 characters." / "Another company already has this name." | `AutomaticReasonTests.CompanyChangesWithoutAReasonGetAnAutomaticOne` |
| SU-C2 | Creating a company needs an organization-wide actor [actor] | `CompanyUseCases.cs:22-23` | 403 (no detail) | none |
| SU-C3 | An archived company (or one with an archive date of today) cannot be renamed; renaming to the same name is a no-op (no log) [company] | `CompanyUseCases.cs:24-25,30-31` | 400 "Archived companies cannot be renamed. Restore it first." | none |
| SU-C4 | Archive is refused while the company has a vehicle that is not retired as of the business date (`LeftOn` null or `> today`, including vehicles not yet joined); the archive date is the business date; archiving again on the same date is a no-op, on another date refused; restore clears the archive (also a scheduled one) [company, vehicles] | `CompanyUseCases.cs:48-58`; `SetupRepository.cs:56-59`; `PsvCompany.cs:36-53` | 400 "Retire every vehicle in this company before archiving it." / "The company is already archived." | `AccessAndSetupTests.RetiringVehiclesStopsPostingAndAllowsCompanyArchiving`, `AccessAndSetupTests.AnArchiveOnAnotherDateIsRefusedAndRestoreCancelsAScheduledArchive` |
| SU-C5 | A company is active on a date when it is not archived or archived after that date; the company list counts its visible vehicles that are joined and not left (away ignored); order name then id [today] | `SetupRepository.cs:28-42` |  | `RecurringCrudTests.AVehicleThatHasNotJoinedYetIsInactiveInEveryList` |
| SU-C6 | Reasons: `Added company {Name}`, `Renamed company {old} to {new}`, `Archived company {Name}`, `Restored company {Name}`; change-log section `companies`, entity = company id [typed reason] | `CompanyUseCases.cs:35,61` | | `AutomaticReasonTests.CompanyChangesWithoutAReasonGetAnAutomaticOne` |
| SU-V1 | Registration normalizes to `AAA 999A` (pattern `^K[A-Z]{2}[0-9]{3}[A-Z]$`), is immutable after creation and unique per organization [registration] | `FleetVehicle.cs:4-14`; `VehicleUseCases.cs:31,43-45`; `SetupModel.cs:22-23,130` | 400 "Use the registration format KDA 482M." / "Registration cannot change after a vehicle is added." / "This registration already exists." | `AutomaticReasonTests.VehicleChangesWithoutAReasonSayWhatChanged` |
| SU-V2 | Weekly target is a `Money` value; join date not default and not after the business date; the chosen company must be visible (else 404) and active [target, join, company] | `VehicleUseCases.cs:32-37` | 400 "A vehicle cannot join after the business date." / "Choose an active PSV company."; 404 | `RecurringCrudTests.ThePickerOffersOnlyVehiclesANewShareCanUse` |
| SU-V3 | Creating a vehicle needs an organization-wide actor or the vehicle's company in the actor's own company scope (a vehicle-only scope cannot create) [actor] | `VehicleUseCases.cs:38` | 403 | `InvestmentTests.AnInvestmentViewerFindsTheirVehiclesButCannotChangeThem` |
| SU-V4 | A retired vehicle cannot be edited until restored [vehicle] | `VehicleUseCases.cs:41-42`; `FleetVehicle.cs:63-64` | 400 "Retired vehicles must be restored before they can be edited." | none |
| SU-V5 | Moving the join date later than a day that already has revenue is refused, naming the first recorded day [join date, first record] | `VehicleUseCases.cs:46-51` | 400 `{Reg} has revenue recorded on {yyyy-MM-dd}. A vehicle cannot join the fleet after a day it has a record for.` | `RevenueCaptureTests.ALifecycleChangeCannotHideADayThatHasARecord` |
| SU-V6 | Target history is append-only: a changed weekly target adds `(effectiveFrom = max(today, joinedOn), amount, revision+1)` (a repeat of the current target adds nothing); moving the join date earlier backfills a target for the new earlier days equal to the target at the old join date; an unchanged edit returns without a log row (section 3.2) [target, join] | `FleetVehicle.cs:57-82`; `VehicleUseCases.cs:54` | | `DomainRuleTests.MovingTheJoinDateEarlierBackfillsTheTargetThatAppliedAtTheOldJoinDate`, `RevenueCaptureTests.WeeksStartOnTheOrganizationsFirstDayAndExpectedFollowsDatedTargets` |
| SU-V7 | Retire is refused when any revenue record exists on or after the leave date; leave date between join date and business date; not before the end of the last away period; same date again is a no-op; another date refused [leave date] | `VehicleUseCases.cs:77-87`; `FleetVehicle.cs:84-98` | 400 `{Reg} has revenue recorded on {last}. A vehicle cannot leave the fleet on or before a day it has a record for.` plus the domain messages (section 1.6) | `RevenueCaptureTests.ALifecycleChangeCannotHideADayThatHasARecord`, `DomainRuleTests.AReturnDateOutsideTheTimeAwayIsRefusedAndASecondLeaveCannotOverlapTheFirst` |
| SU-V8 | Restore: the vehicle's company must be visible (404) and active ("Restore the vehicle's archived company first."); return date defaults to the business date and lies between the leave date and the business date; restoring a vehicle that is not retired is a no-op (nothing validated, no log) [return date] | `VehicleUseCases.cs:94-110`; `FleetVehicle.cs:103-111` | 400 | `VehicleAwayTests.AReturnDateOutsideTheTimeAwayIsRefused`, `AccessAndSetupTests.RetiringVehiclesStopsPostingAndAllowsCompanyArchiving` |
| SU-V9 | Vehicle visibility: organization-wide, or the vehicle is in an actor company, or listed in the actor's vehicle scope; anything else is 404 [actor] | `SetupRepository.cs:15-17,134-137` | 404 | `InvestmentTests.AScopedPersonSeesAndChangesOnlyTheirVehiclesInvestment`, `RevenueCaptureTests.TheVehicleFilterServesTheDetailAndHonoursDataScope` |
| SU-V10 | Listing vehicles needs `vehicles.manage` or `invest.view` (checked after the pipeline, through `SetupPermissions.RequireAny`); page 1..100000, size 1..100; ordered by registration; each row carries company name, `Active` (joined and not left on the business date; away periods are ignored by this flag), the current target (the target with the greatest `EffectiveFrom <= business date`, highest revision on a tie; 0 when not active), every target revision, the away periods and the count of scheduled items still posting to it. Without `vehicles.manage` the weekly target, the target history and the scheduled-item count are blanked (null / empty) [actor, page] | `VehicleUseCases.cs:10-23`; `SetupRepository.cs:77-132`; `Application/Setup/SetupPermissions.cs:7-12` | 403 (no detail) / 400 "Page must be 1–100000 and page size 1–100." | `InvestmentTests.AnInvestmentViewerFindsTheirVehiclesButCannotChangeThem`, `InvestmentTests.AnInvestmentViewerFindsTheVehiclesWithoutTheirTargetsOrScheduledItems`, `RecurringCrudTests.AVehicleThatHasNotJoinedYetIsInactiveInEveryList` |
| SU-V11 | The scheduled-items count of a vehicle counts distinct items whose latest version allocates to it, has not ended before the business date, and is not stopped on or before it; only vehicles active today are counted [vehicles on the page] | `SetupRepository.cs:98-116` | | `RecurringCrudTests.OwnerCanCreateReadUpdateAndStopARecurringItem` |
| SU-V12 | Company picker for vehicles needs `vehicles.manage`; it lists companies in the actor's reach that are not archived on the business date, by name then id [actor] | `VehicleUseCases.cs:25-26`; `SetupRepository.cs:47-54` | 403 | `AccessAndSetupTests.RetiringVehiclesStopsPostingAndAllowsCompanyArchiving` |
| SU-V13 | Saving a vehicle with nothing changed (same company, join date and current target) is a no-op: no write, no log row; the id is returned [input vs vehicle] | `VehicleUseCases.cs:54`; `FleetVehicle.cs:57-82` | | `AutomaticReasonTests.VehicleChangesWithoutAReasonSayWhatChanged` |
| SU-V14 | Automatic reasons: create `Added vehicle {Reg} to {Company} with a weekly target of {CUR} {amount} from {yyyy-MM-dd}`; edit joins the applicable parts with `; ` (`moved {Reg} to {Company}`, `changed when {Reg} joined the fleet to {date}`, `changed the weekly target of {Reg} to {CUR} {amount} from {date}`, else `changed vehicle {Reg}`) and upper-cases the first letter; retire `Vehicle {Reg} left the fleet on {date}`; restore `Vehicle {Reg} returned to the fleet on {date}` plus `; it was away from {from} to {returnedOn - 1 day}` when a stretch was recorded. `{CUR}` is the organization currency (default `KES`), `{amount}` is `#,##0` when whole else `#,##0.00`, culture-invariant; a typed reason follows (OS-11). Change-log section `vehicles`, entity = vehicle id [typed reason] | `VehicleUseCases.cs:56-69,87,108,125-128` | | `AutomaticReasonTests.VehicleChangesWithoutAReasonSayWhatChanged`, `VehicleAwayTests.RestoringAVehicleRecordsTheDaysItWasAwayAndNamesThemInTheChangeLog` |
| SU-V15 | Vehicle report: needs `vehicles.manage`; either a `period` (`week` or `month`, up to the business date; a week starts on the organization first day of week) or an explicit `from` and `through`; `through` may not precede `from`, the span is at most 367 days (`through - from <= 366`), and `through` may not be after the business date; the vehicle must be in the actor reach (404); figures in section 3.3 [id, from, through, period] | `VehicleUseCases.cs:113-123`; `Application/Setup/SetupContracts.cs:89-98`; `SetupRepository.cs:235-289` | 400 "Choose a period, or a from and through date." / "Report range must be at most 367 days and cannot include the future." / "Period must be week or month."; 404 | `VehicleReportTests.TheReportKeepsTheContractShape`, `VehicleReportTests.AReportOutsideThePersonsDataScopeIsNotFound`, `DomainRuleTests.ReportPeriodsRunFromTheStartOfTheCurrentWeekOrMonthToToday` |
| SU-V16 | A vehicle that left stays in every past report; its active days end the day before `LeftOn`; days before the join date and after the business date never count [vehicle, window] | `SetupRepository.cs:237-241` | | `VehicleReportTests.AVehicleThatLeftPostsNothingFromItsLeaveDateAndStaysInPastReports` |
| SU-V17 | Vehicle snapshot written to the change log (`Before`/`After`, PascalCase keys, dates `yyyy-MM-dd`): `Id`, `Registration`, `CompanyId`, `JoinedOn`, `LeftOn`, `Targets[{EffectiveFrom, WeeklyAmount, Revision}]`, `Away[{LeftOn, ReturnedOn}]` ordered by `LeftOn` (section 3.12) [vehicle] | `VehicleUseCases.cs:130-139` | | none asserts the key names directly |
| SU-A1 | Away periods are created only by restoring a retired vehicle: restore with `returnedOn > LeftOn` adds the period `[LeftOn, returnedOn)` (returned day is active again); `returnedOn == LeftOn` adds nothing; the period is append-only and unique per `(vehicle, LeftOn)` [restore] | `FleetVehicle.cs:100-111,144-162`; `Infrastructure/Setup/SetupModel.cs:122-133` | | `VehicleAwayTests.RestoringAVehicleRecordsTheDaysItWasAwayAndNamesThemInTheChangeLog`, `DomainRuleTests.AVehicleBackInTheFleetKeepsTheDaysItWasAwayOutOfEveryReport` |
| SU-A2 | A date is away when it falls in `[LeftOn, ReturnedOn)` of any period; an away day is not active: no target (`TargetOn` = 0), cannot be captured, is neither expected nor missing in the week grid, the dashboard, the report or the earliest-missing search [date] | `FleetVehicle.cs:48-50,161`; `RevenueUseCases.cs:57-60`; `RevenueRepository.cs:135-140,192,229-237`; `SetupRepository.cs:279-280` | capture on an away day: 400 "The vehicle was away from the fleet on this day, so it is not a day revenue is recorded for." | `VehicleAwayTests.AwayDaysAreNeitherExpectedNorMissingInTheWeekTheDashboardOrTheReport`, `VehicleAwayTests.ADayTheVehicleWasAwayCannotBeCapturedAndDoesNotHoldUpTheDaysAfterIt` |
| SU-A3 | A second leave cannot overlap an earlier absence: a retire date earlier than the latest `ReturnedOn` is refused [leave date] | `FleetVehicle.cs:84-98` (check at `:89-90`) | 400 "A vehicle's leave date must be on or after the day it last returned to the fleet." | `DomainRuleTests.AReturnDateOutsideTheTimeAwayIsRefusedAndASecondLeaveCannotOverlapTheFirst` |
| SU-A4 | A return date must lie between the leave date and the business date; a return on the leave date leaves no away period; restoring needs the vehicle company to be active (SU-V8) [return date] | `FleetVehicle.cs:103-111`; `VehicleUseCases.cs:94-110` | 400 "A vehicle's return date must be from the day it left through the business date." | `VehicleAwayTests.AReturnDateOutsideTheTimeAwayIsRefused` |
| SU-A5 | A vehicle with away periods is not checked against a continuous run of records: `EarliestMissing` walks its own dates and skips away days [vehicle] | `RevenueRepository.cs:172-217` | | `RevenueCaptureTests.EarliestMissingComesFromTheWholeHistoryAndLaterMissingDaysCannotBeOpened`, `VehicleAwayTests.ADayTheVehicleWasAwayCannotBeCapturedAndDoesNotHoldUpTheDaysAfterIt` |

## 2.5 Setup: expense catalog (`SU-E`)

Sources: `Application/Setup/ExpenseCatalogUseCases.cs` (`ExpenseCatalogUseCases.cs`), `Domain/Setup/ExpenseCatalog.cs` (`ExpenseCatalog.cs`), `SetupRepository.cs:413-452`. Reasons are always automatic here: the save contracts carry no `Reason`.

| # | Rule [inputs] | Where | Violation | Tests |
|---|---|---|---|---|
| SU-E1 | Reading categories needs one of `expenses.view`, `expenses.setup`, `commitments.view`; the item picker (`options`) needs one of those or `commitments.manage`; every write needs `expenses.setup`. The catalog is organization-wide: it has no data scope [permission] | `ExpenseCatalogUseCases.cs:11-25,27,49,59,69,81`; `Application/Setup/SetupPermissions.cs:7-12` | 403 (no detail) | `ExpenseCatalogTests.ReadingNeedsExpenseOrScheduleAccessAndWritingNeedsExpenseSetup` |
| SU-E2 | A category name is trimmed, 1..100, unique per organization ignoring case (`NormalizedName = upper(name)`), excluding itself; an item name is trimmed, 1..100, unique within its category ignoring case, excluding itself [name] | `ExpenseCatalogUseCases.cs:29,32-33,71,92-96`; `ExpenseCatalog.cs:56-63,107-113`; `SetupRepository.cs:448-452` | 400 "Name must contain 1-100 characters." / "That category already exists." / "That item already exists in this category." | `ExpenseCatalogTests.CategoriesAndItemsAreNamedOnceIgnoringCaseAndEveryChangeIsLogged` |
| SU-E3 | A category counts as exactly one bucket (`RepairsAndMaintenance=1`, `RecurringCharges=2`, `LoanRepayments=3`); an undefined value (including a missing field, which reads as 0) is refused before the name is checked [bucket] | `ExpenseCatalog.cs:12-26,56-58` | 400 "Choose repairs and maintenance, recurring charges or loan repayments." | `ExpenseCatalogTests.CategoriesAndItemsAreNamedOnceIgnoringCaseAndEveryChangeIsLogged` |
| SU-E4 | Saving a category with the same name and bucket is a no-op (no log). Changing the bucket does not touch scheduled versions already saved: each cost version carries the bucket it was saved with [category] | `ExpenseCatalogUseCases.cs:36-37`; `ExpenseCatalog.cs:60`; `RecurringItem.cs:95,163` | | `ExpenseCatalogTests.CategoriesAndItemsAreNamedOnceIgnoringCaseAndEveryChangeIsLogged` |
| SU-E5 | Turning off (stop) uses the business date: an item or category with no stop date gets `StoppedOn = today`; stopped on the same date again is a no-op; stopped on another date is refused until turned on; turning on clears the stop, including one dated in the future; `ActiveOn(d)` holds when `StoppedOn` is null or after `d` [today] | `ExpenseCatalogUseCases.cs:49-57,81-89`; `ExpenseCatalog.cs:54,65-81,105,115-131` | 400 "It is already turned off. Turn it on first to cancel that." | `ExpenseCatalogTests.AFutureStopIsExplicitAndRestoreCancelsItWhenTheBusinessDateMovesBack`, `DomainRuleTests.StoppingSomethingAlreadyStoppedOnAnotherDateIsRefusedAndRestoreCancelsIt` |
| SU-E6 | The picker lists only items in use in categories in use (both `StoppedOn` null or after today), ordered by category name, item name, id; nothing is deleted, so a stopped category or item stays on the records that use it [today] | `SetupRepository.cs:427-440` | | `ExpenseCatalogTests.StoppedItemsAndItemsInStoppedCategoriesLeaveTheOptionsUntilRestored`, `ExpenseCatalogTests.OptionsTakeOneQueryAndAPageOfCategoriesThreeHoweverLargeTheCatalog` |
| SU-E7 | Category list: page 1..100000, size 1..100 (endpoint default 25), ordered by name then id; each category carries its items ordered by name then id and the `Active` flag computed on the business date [page] | `ExpenseCatalogUseCases.cs:14-19`; `SetupRepository.cs:413-425` | 400 "Page must be 1–100000 and page size 1–100." | `ExpenseCatalogTests.CategoriesArePagedByName` |
| SU-E8 | Adding an item needs an existing category (404 otherwise) but does not check that the category is in use; an item cannot move to another category [item] | `ExpenseCatalogUseCases.cs:59-67,69-79` | 404 | `ExpenseCatalogTests.CategoriesAndItemsAreNamedOnceIgnoringCaseAndEveryChangeIsLogged` |
| SU-E9 | Reasons (change-log section `expenses`, entity = category or item id): `Added expense category {Name}`; `Changed {Name} to count as {bucket label lower-cased}`; `Renamed expense category {old} to {new}`; `Renamed expense category {old} to {new}, counted as {bucket}`; `Turned off`/`Turned on` + ` expense category {Name}`; `Added expense item {Name} under {Category}`; `Renamed expense item {old} to {new}`; `Turned off`/`Turned on` + ` expense item {Name}`. Snapshots: category `Id, Name, Bucket, StoppedOn`; item `Id, CategoryId, Name, StoppedOn` [change] | `ExpenseCatalogUseCases.cs:40-47,55,65,77,87,98-112` | | `ExpenseCatalogTests.CategoriesAndItemsAreNamedOnceIgnoringCaseAndEveryChangeIsLogged` |

## 2.6 Setup: scheduled expenses and savings, `Recurring*` (`SU-R`)

Sources: `Application/Setup/RecurringUseCases.cs` (`RecurringUseCases.cs`), `Domain/Setup/RecurringItem.cs` (`RecurringItem.cs`), `Domain/Setup/RecurringSchedule.cs` (`RecurringSchedule.cs`), `SaveRecurring` in `Application/Setup/SetupContracts.cs:50-56`. The product calls these scheduled expenses and savings; the permission group is `commitments.*`.

| # | Rule [inputs] | Where | Violation | Tests |
|---|---|---|---|---|
| SU-R1 | A definition is valid when: name trimmed 1..160; total `Amount` is `Money`; `Kind` defined; a cost has a defined `Bucket`, a saving has neither bucket nor expense item; note at most 200 characters (the note is trimmed first, blank becomes null); `End >= Start`; 1..500 distinct non-empty vehicle ids; every share is `Money`; the shares add up to the total exactly (decimal equality) [definition] | `RecurringItem.cs:102-119`; `SetupContracts.cs:54-55` | 400 "Name must contain 1-160 characters." / "Costs need an expense item; savings must not have one." / "A note can have at most 200 characters." / "End date must be on or after start date." / "Choose 1-500 distinct vehicles." / "Amount must be positive with at most two decimal places." / "Vehicle shares must equal the total exactly." | `RecurringCrudTests.OwnerCanCreateReadUpdateAndStopARecurringItem`, `ScheduledItemRulesTests.CostsNeedAnExpenseItemInUseAndSavingsNeverHaveOne` |
| SU-R2 | Rules for what may be saved from now on (create and revise): no daily schedule; a saving is weekly or monthly; a cost needs an expense item; the start date is required and, unless it equals the current version start, is on or after the first day of the business month. Older versions (daily, older starts) are never re-checked [definition, today, current start] | `RecurringItem.cs:121-137` | 400 "Daily schedules are no longer offered. Choose weekly, monthly or yearly." / "Savings are set aside weekly or monthly." / "Choose the expense item this cost is for." / "Start date is required." / "A schedule can start no earlier than the first of the current month." | `ScheduledItemRulesTests.NewSchedulesAreWeeklyMonthlyOrYearlyAndSavingsWeeklyOrMonthly`, `ScheduledItemRulesTests.SchedulesStartNoEarlierThanTheFirstOfTheBusinessMonth`, `ScheduledItemRulesTests.LegacyDailyVersionsKeepPostingAndOnlyNewRevisionsFollowTheNewRules` |
| SU-R3 | A schedule is `Frequency` (+ `Day`, `LastDay`, `Month`): weekly needs `Day` 0..6 (0 = Sunday) and no `LastDay`; monthly needs `Day` 1..28 or `LastDay` with no `Day`; yearly needs `Month` 1..12 plus the monthly day rule; `Month` is allowed only for yearly; daily takes neither [schedule] | `RecurringSchedule.cs:26-37` | 400 "Choose a weekday (0–6), a month day (1–28 / last), or for yearly a month (1–12) and a day." (en dash U+2013) | `ScheduledItemRulesTests.YearlyItemsPostOnTheirDayWithTheirBucket`, `ScheduledItemRulesTests.YearlyIsDueOnlyOnItsMonthAndDay` |
| SU-R4 | A cost is named after its expense item and counted in that item category bucket at the time of saving; the item and its category must be in use on the business date; a saving keeps the typed name and must not name an expense item. Costs saved with no stored bucket report as `RecurringCharges`; savings report under no bucket [kind, item] | `RecurringUseCases.cs:97-109`; `ExpenseCatalog.cs:16-17`; `SetupRepository.cs:439-440` | 400 "Choose an expense item that is in use." / "Savings must not have an expense item." | `ScheduledItemRulesTests.CostsNeedAnExpenseItemInUseAndSavingsNeverHaveOne`, `ScheduledItemRulesTests.CostsWithoutAStoredBucketStillReportAsRecurringCharges`, `ScheduledItemRulesTests.OnlyCostsReportUnderABucket` |
| SU-R5 | Every share vehicle must be in the actor reach and so must its company (else 404); a new share needs an active vehicle (`FleetVehicle.ActiveOn(today)`: joined and not left; the away periods are not loaded on this path) and an active company unless that vehicle is already in the latest version (retained shares may be retired) [shares, scope] | `RecurringUseCases.cs:26-38` | 404; 400 "New recurring shares must use active vehicles and companies." | `RecurringQueryCostTests.ShareChecksKeepTheirScopeAndRetiredVehicleRules`, `RecurringCrudTests.ThePickerOffersOnlyVehiclesANewShareCanUse` |
| SU-R6 | To revise an item the actor must reach every vehicle of its latest version, otherwise 403 (not 404); the same applies to stop and cancel-stop. The item itself must be in reach (any version allocates to a visible vehicle) or 404 [item, scope] | `RecurringUseCases.cs:23,46-50,66-71,84-88`; `SetupRepository.cs:24-26,232-233` | 403 (no detail) / 404 | `ChangeLogAndScopeTests.SharedRecurringItemsAreMarkedPartialForScopedViewers` |
| SU-R7 | Revising: a stop already in effect (`StoppedFrom <= today`) cannot be edited; if the current version started before today ("running") its start date cannot change; the new version takes effect (`EffectiveFrom`) today when the item is running or the new start is today or later, else on the earlier new start (backdating); the revision number is the highest + 1. Versions and their shares are append-only [definition, today] | `RecurringItem.cs:24-38,171-181` | 400 "Stopped items cannot be edited." / "An already running item's start date cannot change." | `DomainRuleTests.ARunningItemKeepsItsStartDate`, `DomainRuleTests.PostponingAPendingItemStopsTheOldScheduleAndKeepsItEditable`, `DomainRuleTests.BackdatingAPendingItemPostsFromTheEarlierStart` |
| SU-R8 | A revise that changes nothing (same name, kind, amount, schedule, start, end, expense item, bucket, note and shares) writes nothing and logs nothing [definition vs latest version] | `RecurringUseCases.cs:51,130-139` | | `RecurringCrudTests.OwnerCanCreateReadUpdateAndStopARecurringItem` |
| SU-R9 | Stop: a typed reason of 1..500 is required and `Confirmed` must be true (checked before the item is loaded); stopping sets `StoppedFrom = today`; stopping again on the same date is a no-op; an earlier-or-later different date is refused (a stop is cancelled, never re-dated) [reason, confirmed, today] | `RecurringUseCases.cs:61-78`; `RecurringItem.cs:39-53` | 400 "A reason of 1–500 characters is required." / "Confirm stopping this item. Past postings are retained; no posting occurs from today." / "This item is already due to stop on a later date. Cancel that stop first." / "The item is already stopped." | `RecurringCrudTests.OwnerCanCreateReadUpdateAndStopARecurringItem`, `DomainRuleTests.StoppingSomethingAlreadyStoppedOnAnotherDateIsRefusedAndRestoreCancelsIt`, `AutomaticReasonTests.ScheduledItemsSayWhatChangedButStoppingStillNeedsATypedReason` |
| SU-R10 | Cancel stop (`POST /recurring/{id}/restore`): only a stop dated after the business date can be cancelled; one in effect is final; nothing to cancel is a no-op without a log; no typed reason (automatic only) [today] | `RecurringUseCases.cs:80-94`; `RecurringItem.cs:54-63` | 400 "This item has already stopped. Add a new scheduled item instead." | `AutomaticReasonTests.ScheduledItemsSayWhatChangedButStoppingStillNeedsATypedReason`; none asserts the refusal of an effective stop directly (the catalog analogue is `ExpenseCatalogTests.AFutureStopIsExplicitAndRestoreCancelsItWhenTheBusinessDateMovesBack`) |
| SU-R11 | Due dates: a date is due for an item when it is not on or after `StoppedFrom`, the version in charge on that date (highest revision with `EffectiveFrom <= date`) has `Start <= date <= End` and its schedule `IsDue(date)`; `DueBetween(from, through)` returns the same dates without testing each day (section 3.1) [item, window] | `RecurringItem.cs:64-89`; `RecurringSchedule.cs:39-69` | | `DueDateGeneratorTests.EveryFrequencyARevisionAStopAndAnEndPostOnTheSameDaysAsDueOn`, `DueDateGeneratorTests.RandomItemsPostOnTheSameDaysAsDueOnInAnyWindow`, `ScheduledItemRulesTests.YearlyOnTheLastDayFollowsLeapYears` |
| SU-R12 | List: needs `commitments.view`; page 1..100000, size 1..100; ordered by the latest version name then item id; one row per item = its latest version, with the shares on vehicles in reach (retired ones included, flagged `Active=false`), `Partial` true when some shares are hidden, `Amount` = sum of the listed shares, `ActiveAmount` = the part on active vehicles, `Bucket` = reported bucket [actor, page] | `RecurringUseCases.cs:9-13`; `SetupRepository.cs:171-230` | 403 / 400 | `RecurringCrudTests.RetiredSharesStayInTheTotalAndActiveAmountSaysWhatStillPosts`, `ChangeLogAndScopeTests.SharedRecurringItemsAreMarkedPartialForScopedViewers`, `RecurringQueryCostTests.SavingAndStoppingReadTheSameNumberOfTimesForTwoOrTwoHundredVehicles` |
| SU-R13 | The vehicle picker for a new share needs `commitments.manage` and lists vehicles joined by the business date and not left, whose company is not archived, ordered by registration (away is not considered) [actor] | `RecurringUseCases.cs:15-16`; `SetupRepository.cs:156-163` | 403 | `RecurringCrudTests.ThePickerOffersOnlyVehiclesANewShareCanUse` |
| SU-R14 | Reasons (change-log section `recurring`, entity = item id): create `Added scheduled saving {name}` or `Added scheduled expense {name}`; revise `Changed the {list} of {previous version name}` where the list holds, in this order and joined `a, b and c`: `type`, `expense item` (or `name`), `bucket`, `amount`, `schedule`, `start date`, `end date`, `vehicles`, `note` (`Changed {name}` if none); stop `Stopped {name} from {yyyy-MM-dd}` + typed reason; cancel `Cancelled the stop of {name}` [change] | `RecurringUseCases.cs:54-56,76,92,111-128`; `SetupContracts.cs:126-127` | | `AutomaticReasonTests.ScheduledItemsSayWhatChangedButStoppingStillNeedsATypedReason` |
| SU-R15 | Snapshot (`Before`/`After`, PascalCase): `Id`, `StoppedFrom`, `Versions[{Id, Revision, EffectiveFrom, Name, Kind, Amount, Frequency, Day, LastDay, Month, Start, End, ExpenseItemId, Bucket, Note, Allocations[{VehicleId, Amount}]}]` with enums as integers (section 3.12) [item] | `RecurringUseCases.cs:141-164` | | none asserts the key names directly |

## 2.7 Setup: vehicle investment (`SU-I`)

Sources: `Application/Setup/InvestmentUseCases.cs` (`InvestmentUseCases.cs`), `Domain/Setup/VehicleInvestment.cs` (`VehicleInvestment.cs`), `SetupRepository.cs:454-473`.

| # | Rule [inputs] | Where | Violation | Tests |
|---|---|---|---|---|
| SU-I1 | Viewing a vehicle investment needs `invest.view`; add, change and remove need `invest.manage` (which depends on view) [permission] | `InvestmentUseCases.cs:14,27,37,47` | 403 (no detail) | `InvestmentTests.ViewingNeedsInvestViewAndChangingNeedsInvestManage` |
| SU-I2 | The vehicle must be in the actor reach; an entry is found through its vehicle, so an entry on a vehicle out of reach is 404 like the vehicle [vehicle, scope] | `InvestmentUseCases.cs:16,29,56-62` | 404 | `InvestmentTests.AScopedPersonSeesAndChangesOnlyTheirVehiclesInvestment` |
| SU-I3 | An entry has a date (not default, not after the business date), a description (trimmed, 1..160) and an amount (`Money`); the recorder is the actor and the instant is the clock, both fixed at creation [entry] | `VehicleInvestment.cs:22-42`; `InvestmentUseCases.cs:30` | 400 "An investment date is required and cannot be after the business date." / "Say what it was, in 1-160 characters." / "Amount must be positive with at most two decimal places." | `InvestmentTests.EntriesAreRecordedChangedAndRemovedWithTheirHistory` |
| SU-I4 | Changing an entry to the same date, description and amount is a no-op (no log). Removing an entry deletes the row: it is the only setup row that may be deleted, and the removal is logged with `After = "null"` [entry] | `VehicleInvestment.cs:39`; `InvestmentUseCases.cs:37-54`; `SetupRepository.cs:473` | | `InvestmentTests.EntriesAreRecordedChangedAndRemovedWithTheirHistory` |
| SU-I5 | Investment changes are logged against the vehicle: section `investment`, entity id = vehicle id, `VehicleId` = vehicle id; reasons `Recorded investment {Description} on {Reg}`, `Changed investment {Description} on {Reg}`, `Removed investment {Description} on {Reg}`; snapshot `Id, VehicleId, Date, Description, Amount`; no typed reason [change] | `InvestmentUseCases.cs:32-33,42-43,51-52,64-71`; `SetupRepository.cs:477-479` | | `InvestmentTests.EntriesAreRecordedChangedAndRemovedWithTheirHistory` |
| SU-I6 | The summary returns `TotalInvested` (sum of entries), `Returned` = the vehicle net contribution (money in less money out, as its report counts them) from its join date through the business date, which may be negative, and `PercentPaidOff` = null when nothing went in, else `Round(Returned / TotalInvested * 100, 0)` away from zero; entries ordered by date then recorded instant, each with the recorder name (empty when the membership is gone). Investment is never money out [vehicle] | `InvestmentUseCases.cs:12-25`; `SetupRepository.cs:454-462`; `SetupContracts.cs:73-77` | | `VehicleReportTests.WhatHasComeBackIsTheNetContributionSinceJoiningAgainstWhatWentIn` |

## 2.8 Setup execution and data scope (`SU-X`)

Sources: `Application/OrganizationPort.cs` (`OrganizationPort.cs`), `Application/ISetupExecution.cs`, `Infrastructure/Setup/SetupExecution.cs` (`SetupExecution.cs`), `Infrastructure/Setup/SetupRepository.cs`, `Infrastructure/Setup/SetupModel.cs`.

| # | Rule [inputs] | Where | Violation | Tests |
|---|---|---|---|---|
| SU-X1 | Every setup, access, revenue and settings use case runs through one pipeline: organization and actor ids non-empty; (validation hook, empty for setup); the actor has an **active** membership; one of the required permissions is held (an empty required set means any active member and resolves no permissions); then the body; for a write, `SaveChanges` and commit in a serializable transaction, with the change-log retry of OS-19; for a read, no transaction and a guard that fails if the read tracked a change [context, permissions] | `Application/OrganizationPort.cs:34-60`; `Infrastructure/Setup/SetupExecution.cs:11-27,56-69`; `Infrastructure/OrganizationRepository.cs:59-102` | 403 (plain `UnauthorizedAccessException`, no detail); `InvalidOperationException("A read changed state. Run it as a write.")` is a 500 | `AccessAndSetupTests.APlainRefusalGivesNoDetail`, `PeopleQueryCostTests.PermissionsAreResolvedOncePerRequest` |
| SU-X2 | The `SetupActor` is built inside the authorized body: scope rows (`AllCompanies`, company ids, vehicle ids of the caller), the business date (`Today`: held date or the calendar date in the organization zone, default zone `Africa/Nairobi` when no localization row exists), the permission set and the organization `SettingsVersion` read together with the business date and before any figures [caller] | `SetupExecution.cs:32-54`; `Application/ISetupExecution.cs:1-5` | an unknown stored time zone id raises `TimeZoneNotFoundException` here (500), unlike the settings path (OS-5, 400) | `OrganizationSettingsTests.BusinessDateUsesTheServerDateForSetupAndIsAudited`, `RevenueDashboardCacheTests.WithoutASettingsVersionNothingIsKept` |
| SU-X3 | Data scope: a vehicle is visible when the actor is organization-wide, or its company is in the actor company scope, or its id is in the actor vehicle scope; a company is visible when organization-wide, in the company scope, or holding a visible vehicle; a scheduled item is visible when organization-wide or any of its versions allocates to a visible vehicle. Anything outside is indistinguishable from missing (404) [actor scope] | `SetupRepository.cs:15-26` | 404 | `InvestmentTests.AScopedPersonSeesAndChangesOnlyTheirVehiclesInvestment`, `RecurringQueryCostTests.ShareChecksKeepTheirScopeAndRetiredVehicleRules`, `RevenueCaptureTests.TheVehicleFilterServesTheDetailAndHonoursDataScope` |
| SU-X4 | Reads and writes that any one of several permissions opens use `ReadAny`/`WriteAny` (revenue save: capture or correct; dashboard: the four `dash.*` card keys) or the pipeline with no permission followed by `SetupPermissions.RequireAny` (vehicle list, expense lists) [permissions] | `Application/ISetupExecution.cs:7-13`; `RevenueUseCases.cs:10-11`; `SetupPermissions.cs:7-12` | 403 | `ExpenseCatalogTests.ReadingNeedsExpenseOrScheduleAccessAndWritingNeedsExpenseSetup` |
| SU-X5 | Setup rows are append-only or never deleted: modifying or deleting `OrganizationSettingsVersion`, `VehicleTarget`, `VehicleAwayPeriod`, `RecurringVersion`, `RecurringAllocation`, deleting `PsvCompany`, `FleetVehicle`, `RecurringItem`, `RevenueRecord`, `ExpenseCategory`, `ExpenseItem`, or changing a vehicle registration is refused at save time; `VehicleInvestment` is the only row that is edited and deleted [write set] | `Infrastructure/Setup/SetupModel.cs:122-133` | `InvalidOperationException` (500; unreachable from the API) | none asserts the guards directly |
| SU-X6 | Paging for every setup list: page 1..100000 and size 1..100 (400 otherwise); endpoints default to page 1, size 25; the revenue week grid defaults differ (RV-13) [page, size] | `Application/Setup/SetupContracts.cs:100-105`; `Api/SetupEndpoints.cs:105,132` | 400 "Page must be 1–100000 and page size 1–100." | `ExpenseCatalogTests.CategoriesArePagedByName` (size 101 refused), `RevenueWeekPagingTests.PagingOutsideItsLimitsIsRefused` |
| SU-X7 | Reasons: a typed reason is trimmed and must be 1..500 characters; it is optional on company, vehicle, scheduled save, settings, logo; required on stop-scheduled and deactivate-person; the stored reason is always `automatic` plus the typed text (OS-11) [reason] | `Application/Setup/SetupContracts.cs:106-124` | 400 "A reason of 1–500 characters is required." | `AutomaticReasonTests.ATypedReasonIsStillCheckedAndUsed` |
| SU-X8 | Every recorded setup change adds a change-log row (moves `SettingsVersion`, OS-19) and an audit event `setup.{section}` with JSON before and after; `VehicleId` is set for `vehicles` and `investment` [section, entity] | `SetupRepository.cs:475-481` | | `ChangeLogAndScopeTests.PeopleAndAccessChangesJoinTheChangeLog` |
| SU-X9 | Two small reads feed other rules: first day of week (default 1) and currency (default `KES`) come from the localization row, or from the defaults when the row is missing [organization] | `SetupRepository.cs:165-169` | | `RevenueCaptureTests.WeeksStartOnTheOrganizationsFirstDayAndExpectedFollowsDatedTargets` |

## 2.9 Revenue: capture, replay, no-earnings reasons, week grid, dashboard (`RV`)

Sources: `Application/RevenueUseCases.cs` (`RevenueUseCases.cs`), `Application/RevenueContracts.cs` (`RevenueContracts.cs`), `Domain/Revenue.cs` (`Revenue.cs`, entity rules in section 1.4), `Infrastructure/RevenueRepository.cs` (`RevenueRepository.cs`), `Infrastructure/RevenueDashboardCache.cs` (`RevenueDashboardCache.cs`), `Api/RevenueEndpoints.cs:19-38` (error filter). Business date = `actor.Today` (OS-1).

| # | Rule [inputs] | Where | Violation | Tests |
|---|---|---|---|---|
| RV-1 | Saving a day needs `revenue.capture` or `revenue.correct` (any one); the vehicle must be in the actor reach (404). The order of the checks inside the body is in section 4.4 [actor, vehicle id, date] | `RevenueUseCases.cs:10,44-48` | 403 (no detail) / 404 | `RevenueCaptureTests.EachCapturePathChecksItsOwnPermission` |
| RV-2 | The request is validated before anything is loaded: reason text parsed (`Garage`, `Arrest`, `No Crew` or `NoCrew`, `Other`, trimmed, case-sensitive; blank = none), then `RevenueEntry.Validate()` (amount rules, reason rules, note rules of section 1.4) [amount, reason, note] | `RevenueContracts.cs:154-170`; `Revenue.cs:15-37` | 400 "Choose a valid no-earnings reason." / "Amount must be positive with at most two decimal places." / "Revenue amount cannot have a no-earnings reason." / "Enter revenue or choose a no-earnings reason." / "Explain what happened when choosing Other." / "The no-earnings note must be at most 80 characters." / "Only Other may have a no-earnings note." | `RevenueCaptureTests.CaptureFollowsTheBusinessDateAndTheVehiclesActiveDays` |
| RV-3 | Idempotent replay: when a record already exists for the vehicle and day and the request equals it (amount, reason, trimmed note), the save succeeds at once and returns the existing id and version, before the date, activity, permission and version checks; nothing is written or logged. A phone draining a queue late therefore always succeeds [entry vs record] | `RevenueUseCases.cs:49-53`; `Revenue.cs:98-101` | | `RevenueCaptureTests.ChangingARecordNeedsItsCurrentVersionAndAnIdenticalReplayIsIdempotent`, `RevenueCaptureTests.AClerksOfflineReplayIsAcceptedUntilSomeoneElseChangesTheDay` |
| RV-4 | A day cannot be default or after the business date, and the vehicle must be active on it (joined, not left, not away) [date, vehicle] | `RevenueUseCases.cs:55-60` | 400 "Revenue cannot be recorded for a future date." / "The vehicle was away from the fleet on this day, so it is not a day revenue is recorded for." / "Revenue can only be recorded while the vehicle is active." | `RevenueCaptureTests.CaptureFollowsTheBusinessDateAndTheVehiclesActiveDays`, `VehicleAwayTests.ADayTheVehicleWasAwayCannotBeCapturedAndDoesNotHoldUpTheDaysAfterIt` |
| RV-5 | Per-path permissions, checked before any state is disclosed: a reason needs `revenue.no_earnings`; a day with no record yet needs `revenue.capture`; changing an existing record on a day before the business date needs `revenue.correct`; today's existing record may be changed by capture or correct (the pipeline gate) [permissions, record, date] | `RevenueUseCases.cs:61-70` | 403 with detail `Recording a no-earnings reason needs the permission "Record a no earnings reason".` / `Recording a day that has no record yet needs the permission "Capture revenue".` / `Changing a past day needs the permission "Correct revenue after the day".` | `RevenueRefusalTests.ANoEarningsReasonWithoutThatPermissionSaysSo`, `RevenueRefusalTests.ADayWithNoRecordYetWithoutCaptureSaysSo`, `RevenueRefusalTests.ChangingAPastDayWithoutCorrectSaysSo` |
| RV-6 | Optimistic concurrency: changing an existing record needs the version the client saw; a missing or different version raises the conflict, whose body carries the current cell (`RevenueCellDto.For`) so the client can show it. A concurrent write that slips past the check fails on the `Version` token or on the unique `(vehicle, day)` index [version] | `RevenueUseCases.cs:72-74`; `RevenueContracts.cs:140-144`; `Api/RevenueEndpoints.cs:22-32` | 409 problem "This day already has a different record." + extension `current`; token race 409 "This day was changed by another save." (detail "Reload the current record and try again."); unique race 409 "A conflicting record exists. Reload before saving." | `RevenueCaptureTests.TwoClerksCapturingTheSameDayAtOnceGetAConflictNotAServerError`, `RevenueCaptureTests.AConcurrentUpdateRaceReturns409NotAServerError` |
| RV-7 | Days in any order (since 9276c51, which removed the ordered-backfill refusal): a new record is accepted whatever earlier active day is still missing; the week keeps naming each vehicle's earliest missing day (RV-8) [vehicle, date] | `RevenueUseCases.cs:130-131` | none (was 400 `Record {yyyy-MM-dd} before this date first.` with `earliestMissing`) | `RevenueCaptureTests.SavingPastAGapIsAllowedAndTheGapStaysVisible`, `RevenueTests.RevenueCaptureTakesDaysInAnyOrderAndKeepsCorrectionHistory` |
| RV-8 | Earliest missing day of a vehicle before a date: the first active day (joined, not away, before the leave date or the date) with no record. Fast path from one grouped query (first day, last day, count of recorded active days); a vehicle with away periods overlapping its history or with a count showing a hole walks its own dates (section 3.5) [vehicle, before] | `RevenueRepository.cs:172-217` | | `RevenueCaptureTests.EarliestMissingComesFromTheWholeHistoryAndLaterMissingDaysCannotBeOpened`, `RevenueComplexityTests.SaveFindsTheEarliestMissingDayFromOneAggregateRowWhateverTheHistoryLength` |
| RV-9 | Creating a record: `Version = 1`, `CapturedAt = UpdatedAt = clock.UtcNow`, `CapturedBy = UpdatedBy = actor`; changing: amount, reason, note, `UpdatedAt`, `UpdatedBy` replaced, `Version++`, and `CorrectedAfterDate` becomes true (and stays true) when the record day is before the business date [record] | `RevenueUseCases.cs:84-92`; `Revenue.cs:78-119` | | `RevenueCaptureTests.OnlyAChangeToAPastDayIsAnEditAfterCapture` |
| RV-10 | Logging: section `revenue`, entity = record id, `VehicleId` = the record vehicle; reason `Recorded revenue for {Reg} on {d MMM yyyy}`, `Recorded no revenue for {Reg} on {date}: {Label}` (Label: `Garage`, `Arrest`, `No Crew`, `Other`), `Corrected revenue ...` when the record day is before the business date, else `Updated revenue ...` (`d MMM yyyy` invariant, e.g. `28 Sep 2026`); audit event `revenue.recorded`; snapshot keys `Id, VehicleId, BusinessDate, Amount, Reason (string name, NoCrew not "No Crew"), Note, CapturedAt, CapturedBy, UpdatedAt, UpdatedBy, CorrectedAfterDate, Version` (section 3.12). A typed reason is not accepted [change] | `RevenueUseCases.cs:94-119`; `RevenueRepository.cs:241-248` | | `RevenueTests.RevenueCaptureRequiresOrderedBackfillAndKeepsCorrectionHistory` |
| RV-11 | A cell: status `none` when the vehicle is not active that day, `future` after the business date, `missing` with no record, `amount` when the record has an amount, else `reason`; `expected = round(target / 7, 2)`; `canEdit`: for `missing`, capture permission (any missing day since 9276c51); for `amount`/`reason`, on the business date capture or correct, before it correct only; never for `none`/`future`; `editedAfterCapture` = `CorrectedAfterDate` [vehicle, day, record, permissions] | `RevenueContracts.cs:40-65` | | `RevenueCaptureTests.EarliestMissingComesFromTheWholeHistoryAndEveryMissingDayCanBeOpened`, `RevenueCaptureTests.EachCapturePathChecksItsOwnPermission` |
| RV-12 | Week request: any `weekStart` date names its week, which starts on the organization first day of week (default Monday, 0 = Sunday); the week may not be after the current week nor start more than 3650 days before the current week start; omitted = current week [weekStart] | `RevenueRepository.cs:20-25,327-339` | 400 "Choose a week from the last ten years through the current week." | `RevenueCaptureTests.WeeksStartOnTheOrganizationsFirstDayAndExpectedFollowsDatedTargets` |
| RV-13 | Grid membership: vehicles in the actor reach, optionally one company (`companyId`), that joined on or before the week end and had not left by the week start (a vehicle away all week is still listed), ordered by registration then id; a `vehicleId` request returns that one vehicle for any week (404 when not in reach) [filters] | `RevenueRepository.cs:27-47` | 404 | `RevenueCaptureTests.TheGridListsOnlyVehiclesActiveThatWeekButTheDetailShowsAnyVehicleInScope`, `RevenueCaptureTests.TheVehicleFilterServesTheDetailAndHonoursDataScope` |
| RV-14 | Week paging: without `page` and `pageSize` the response is page 1 of up to 500 vehicles (`RevenueWeekPage.LegacyLimit`) with `truncated` true when the grid is larger and `totalVehicles` the grid size; if either is given the other defaults (page 1, size 100) and `SetupPagination.Validate` applies; a `vehicleId` request is never paged. Totals, percent, `dayTotals` and `firstGap` always cover the whole filtered, scoped grid, not the page [page, pageSize] | `RevenueUseCases.cs:14-16`; `RevenueContracts.cs:80-121`; `RevenueRepository.cs:48-49,318-324` | 400 "Page must be 1–100000 and page size 1–100." | `RevenueWeekPagingTests.PagesSplitTheGridInRegistrationOrderAndEachCarriesTheWholeWeeksFigures`, `RevenueWeekPagingTests.AVehiclesOwnWeekIgnoresPaging`, `RevenueWeekPagingTests.PagingOutsideItsLimitsIsRefused`, `RevenueWeekPagingTests.TheWeekWithoutPagingKeepsItsReleasedShape`, `RevenueWeekPagingTests.TheWeekWithoutPagingStopsAtItsLimitAndSaysSo`, `RevenueWeekPagingTests.ACompanyFilterAndADataScopeEachNarrowThePagesAndTheirFigures` |
| RV-15 | Week figures (rows, totals, percent, `dayTotals`, `firstGap`) follow section 3.4; `firstGap` is not permission-gated: it is computed for every caller (only a cell `canEdit` depends on permissions) [week] | `RevenueRepository.cs:255-325` | | `RevenueWeekPagingTests.TheFirstGapIsTheEarliestMissingDayAndTheFirstVehicleInGridOrderOnATie` |
| RV-16 | Company options on the week: companies in the actor reach that are not archived on the business date, or that had a visible vehicle running during the shown week; ordered by name then id [week] | `RevenueRepository.cs:50-61` | | `RevenueCaptureTests.CompanyOptionsKeepArchivedCompaniesOnlyForWeeksTheyHadAVehicleRunning` |
| RV-17 | Dashboard: needs one of `dash.capture`, `dash.revenue`, `dash.gaps`, `dash.edits`; `period` is `today`, `week` (endpoint default) or `month`; `companyId` only narrows the actor reach. The window is `from..through` where `through` = business date and `from` = today / start of week / first of month [period, company] | `RevenueUseCases.cs:11,20-21`; `RevenueRepository.cs:88-106`; `Api/RevenueEndpoints.cs:46-47` | 403 / 400 "Period must be today, week or month." | `RevenueCaptureTests.DashboardFiguresAreShownOnlyToPeopleWhoMaySeeTheirCard` |
| RV-18 | Dashboard masking is applied per request after the (cached) figures: `revenue`, `expected`, `percent` need `dash.revenue`; `capturedToday`, `vehiclesToday` need `dash.capture`; `missingDays`, `missingVehicles` need `dash.gaps`; `editedRecords` needs `dash.edits`; any card the caller may not see is null. The clerk capture card never reveals revenue totals [permissions] | `RevenueUseCases.cs:23-42` | | `RevenueDashboardCardTests.EachCardsFiguresNeedThatCardsOwnPermission`, `RevenueDashboardCardTests.TheRevenueClerksCaptureCardDoesNotRevealRevenueTotals` |
| RV-19 | Dashboard figures are computed from SQL aggregates (one row per vehicle: revenue sum, count before today, count today, edited count) plus per-vehicle calendars, and cached in memory per (organization, `SettingsVersion`, business date, period, company id, scope) for 60 seconds, at most 10000 entries. Scope = `all` for an organization-wide actor, else a SHA-256 hex of the sorted company ids and vehicle ids. The version is read with the actor before any figures, and every write that changes an input (revenue, vehicle dates/target/company/away, business date, first day of week) adds a change-log row and so moves the version, so an entry is never older than its version. Single flight: concurrent requests for a key wait for one computation; a failed or cancelled computation is not kept; with `SettingsVersion` unknown nothing is cached. Each replica keeps its own cache [figures] | `RevenueRepository.cs:88-156`; `RevenueDashboardCache.cs:10-83,89-109`; `Api/RevenueEndpoints.cs:10-16` | | `RevenueDashboardCacheTests.ARepeatedDashboardIsServedFromTheCache`, `RevenueDashboardCacheTests.SavingRevenueGivesFreshFigures`, `RevenueDashboardCacheTests.RetiringAVehicleGivesFreshFigures`, `RevenueDashboardCacheTests.MovingTheBusinessDateGivesFreshFigures`, `RevenueDashboardCacheTests.ChangingTheFirstDayOfTheWeekGivesFreshFigures`, `RevenueDashboardCacheTests.MovingAVehicleToAnotherCompanyGivesFreshFigures`, `RevenueDashboardCacheTests.TheOwnerAndAClerkScopedToOneCompanyKeepTheirOwnFigures`, `RevenueDashboardCacheTests.TwoOrganizationsNeverShareAnEntry`, `RevenueDashboardCacheTests.ConcurrentRequestsForOneEntryWorkTheFiguresOutOnce`, `RevenueDashboardCacheTests.AFailedComputationIsNotKept`, `RevenueDashboardCacheTests.WithoutASettingsVersionNothingIsKept` |
| RV-20 | Dashboard figure definitions (revenue, expected, percent, captured today, vehicles today, missing days, missing vehicles, edited records) are in section 3.6; the percent clamps to the `int` range instead of failing [figures] | `RevenueRepository.cs:107-156,330-333` | | `RevenueTests.AHugeRecordAgainstATinyTargetShowsAtTheLargestPercentInsteadOfFailingTheWeekAndDashboard`, `RevenueCaptureTests.DashboardEditsCountOnlyTheVehiclesActiveDaysLikeEveryOtherFigure`, `VehicleAwayTests.AwayDaysAreNeitherExpectedNorMissingInTheWeekTheDashboardOrTheReport` |
| RV-21 | Query cost is bounded: week and dashboard issue the same number of commands whatever the fleet size or history (targets, away periods and the needed record columns are read in split queries) [fleet] | `RevenueRepository.cs:35-45,62-75` | | `RevenueComplexityTests.WeekAndDashboardCommandsStayFlatFromTwoToFiveHundredVehicles`, `RevenueComplexityTests.WeekAndDashboardIssueTheSameCommandsWhateverTheFleetSizeAndHistory`, `RevenueWeekPagingTests.TheWeekReadsTargetsAndAwayPeriodsApartAndOnlyTheRecordColumnsItShows` |

---

# 3. Computations that must be reproduced exactly

Money is `decimal` (28 to 29 significant digits), stored `decimal(14,2)`. Rounding rules are in 3.10: read them before porting any figure.

## 3.1 Schedule maths and the due-date generator (`RecurringSchedule.cs`, `RecurringItem.cs`)

Day numbering: `Day` for weekly is .NET `DayOfWeek` (Sunday 0 .. Saturday 6). `DueDay(date)` = `LastDay ? days_in_month(date) : Day`.

| Function | Definition |
|---|---|
| `IsDue(date)` (`RecurringSchedule.cs:39-46`) | Daily: always. Weekly: `dow(date) == Day`. Monthly: `date.Day == DueDay(date)`. Yearly: `date.Month == Month && date.Day == DueDay(date)`. Anything else: false |
| `Occurrences(first, last)` (`:49-68`) | Empty when `first > last`. Daily: every date `first..last`. Weekly: start at `first + ((Day - dow(first) + 7) mod 7)` days, step 7, while `<= last`. Monthly/yearly: walk month starts, from `(first.Year, first.Month, 1)` step 1 month (monthly) or from `(first.Year, Month, 1)` step 12 months (yearly), while the month start is `<= last`; the due day is `DueDay(month)` (at most 28, or the last day of that month); yield it when inside `first..last`. It yields exactly the dates for which `IsDue` is true |
| `DueOn(date)` (`RecurringItem.cs:64-71`) | `null` when `StoppedFrom != null && date >= StoppedFrom`. Else the version in charge = highest `Revision` among versions with `EffectiveFrom <= date`; due when `date >= version.Start`, `version.End` is null or `date <= End`, and `version.Schedule().IsDue(date)`; returns that version |
| `DueBetween(from, through)` (`:76-89`) | `end = StoppedFrom <= through ? StoppedFrom - 1 day : through`. Versions are visited by descending revision with `supersededFrom = +infinity`; for each: `first = max(from, EffectiveFrom, Start)`, `last = min(end, supersededFrom - 1, End or +infinity)`; then `supersededFrom = min(supersededFrom, version.EffectiveFrom)`; when `first <= last` yield `Occurrences(first, last)` with that version. Result equals calling `DueOn` on each day of the window (property test `DueDateGeneratorTests.RandomItemsPostOnTheSameDaysAsDueOnInAnyWindow`); the order is per version, descending revision, so callers sort (the vehicle report orders by date, name ordinal, item id) |

A scheduled posting for a vehicle is the due date, the version name, the kind, the vehicle share of that version and `ReportedBucket()` (cost: stored bucket or `RecurringCharges`; saving: none). Tests: `DueDateGeneratorTests.*`, `ScheduledItemRulesTests.YearlyOnTheLastDayFollowsLeapYears`.

## 3.2 Vehicle targets and the weekly target history (`FleetVehicle.cs`)

- Daily expected figure = `TargetOn(d) / 7` (decimal division, not rounded until shown; 3.10).
- `TargetOn(d)` = 0 unless `ActiveOn(d)` (joined, not left, not away); else `WeeklyAmount` of the target with the greatest `EffectiveFrom <= d`, ties broken by the greatest `Revision`; 0 when no target qualifies (`FleetVehicle.cs:114-123`).
- Create: one target `(revision 1, effectiveFrom = joinedOn, amount = weeklyTarget)`.
- `Update(company, joinedOn, weeklyTarget, today)` (`:57-82`), in this order: company required; `joinedOn` not default and not after `today`; not retired; `Money(weeklyTarget)`; `changed = company differs or join date differs`; `previous = JoinedOn`; `targetAtPrevious = TargetOn(previous)` (read before the move); set company and join date; if the join date moved earlier and every target has `EffectiveFrom > joinedOn`, add `(effectiveFrom = joinedOn, amount = targetAtPrevious, revision = max + 1)`; `effectiveToday = max(today, joinedOn)`; if `TargetOn(effectiveToday) != weeklyTarget` add `(effectiveToday, weeklyTarget, max + 1)` and set `changed`. Return `changed`. Tests: `DomainRuleTests.MovingTheJoinDateEarlierBackfillsTheTargetThatAppliedAtTheOldJoinDate`, `DomainRuleTests.TheLastTargetSetOnADayHoldsFromThatDay`, `DomainRuleTests.LeavingTheFleetEndsTargetsUntilTheVehicleIsRestored`.
- Repository `Vehicles` list recomputes the current target without the away check (`SetupRepository.cs:118-131`): same value except for a vehicle currently inside an away period (impossible for an open vehicle).

## 3.3 Vehicle report (`SetupRepository.cs:235-289`, contract C6)

1. `first = max(from, JoinedOn)`; `last = min(through, Today)`; if `LeftOn != null && LeftOn <= last` then `last = LeftOn - 1 day`. (The returned `From` and `Through` are the requested values.)
2. `moneyIn` = sum of `Amount` (null counts as 0) of the vehicle revenue records with `first <= BusinessDate <= last` (no rounding; each amount has two decimals).
3. `target` = sum, over every day in `first..last` where `day < Today` or a record exists on that day, of `TargetOn(day) / 7`; returned as `Round(target, 2)` (banker's rounding, 3.10).
4. Postings = `DueBetween(first, last)` of every item having a version that allocates to this vehicle, taking the vehicle share of the version in charge (items whose version-in-charge has no share for this vehicle are skipped), plus approved petty-cash expenses of the vehicle (petty-cash feature: `Source = "pettycash"`, bucket of the item category). Ordered by date, then name (ordinal), then item id. Away days do not remove postings; only the leave date and the window do.
5. `repairs`, `charges`, `loans` = sums of cost postings per bucket; `savings` = sum of saving postings; `moneyOut = repairs + charges + loans`; `net = moneyIn - moneyOut`; `afterSavings = net - savings`; `costs = moneyOut` (duplicate field for old clients). Investment never counts.
Tests: `VehicleReportTests.*` (including query counts).

## 3.4 Week grid (`RevenueRepository.cs:17-83,255-339`)

Inputs: `Today`; `start` = week start (3.4a); `through = start + 6`; the whole filtered grid `V` (all vehicles, ordered by registration then id, with targets `EffectiveFrom <= through` and all away periods); the listed page `shown`; records of the shown vehicles for the week; per-day tallies of the whole grid.
- 3.4a Week start: `start = date - ((dow(date) - firstDay + 7) mod 7)` days, `firstDay` = localization `FirstDayOfWeek` (default 1). The current week start is that of `Today`.
- `counts(vehicle, date, recorded)` = `vehicle.ActiveOn(date) && (date < Today || recorded)`: future days, days outside the fleet, away days and today before capture are not shortfalls.
- Tally = records of the whole grid inside the week on each vehicle active days (joined, before the leave day, not away), grouped by `(date, vehicleId)` for dates `>= Today` and by `date` alone for earlier dates; each group's sum of `Amount`.
- `totalAmount` = sum of all tally amounts; `dayAmount[date]` = the same restricted to `date <= Today`.
- Expected: for each vehicle of `V` and each of the 7 days with `counts` true (a day `>= Today` counts only when that vehicle has a record that day): `e = TargetOn(date) / 7`; `dayExpected[date] += e`; `totalExpected += e`.
- `firstGap`: for each vehicle of `V` in grid order, `opens = earliestMissing(vehicle)` (3.5, strictly before `Today`) else `Today` when `Today` is inside the week, the vehicle is active today and has no record today; keep the smallest `opens`, the first vehicle in grid order on a tie. It can lie before the displayed week. Null when no vehicle qualifies.
- Row of a shown vehicle: for each day, `target = TargetOn(date)`; a cell via `RevenueCellDto.For` (RV-11); if `counts(vehicle, date, hasRecord)` then `expected += target / 7` and, when the record has an amount, `amount += Amount`. Row `totalAmount = Round(amount, 2)`, `totalExpected = Round(expected, 2)`, `percent = Percent(amount, expected)`; `earliestMissing` = 3.5 for that vehicle.
- Response: `totalAmount`, `totalExpected` rounded once at the end from the unrounded sums, `percent = Percent(totalAmount, totalExpected)` from the unrounded sums, `dayTotals[7]` as `{date, Round(dayAmount, 2), Round(dayExpected, 2)}`, `totalVehicles = |V|`, `truncated = (no paging requested) && |V| > 500`, `pageNumber`/`pageSize` of the page used (page 1, 500 when not paged).
- `Percent(amount, expected)` = `null` when `expected == 0`, else `Round(amount / expected * 100, away from zero)` clamped to the `int` range.

## 3.5 Earliest missing day (`RevenueRepository.cs:165-217`)

For a vehicle and a `before` date (the business date for the week and for a save that creates a record on the date `d`: then `before = d`):
1. `end` = `LeftOn` when `LeftOn < before`, else `before`.
2. `end <= JoinedOn` -> none.
3. The vehicle has an away period with `LeftOn < end && ReturnedOn > JoinedOn` -> walk (step 6).
4. Aggregate over the vehicle records with `JoinedOn <= date < before` and (`LeftOn` null or `date < LeftOn`) (away not filtered): `First`, `Last`, `Count`. No records or `First > JoinedOn` -> `JoinedOn`.
5. `Count == Last - First + 1` (an unbroken run from `First`) -> `Last + 1` when that is `< end`, else none; otherwise walk.
6. Walk: from `JoinedOn`, skip days that have a record or are not `ActiveOn` (away); the first remaining day `< end` is the answer, else none.
Since 9276c51 only the week reads it (`before` = the business date); a save no longer does. Tests: `RevenueCaptureTests.EarliestMissingComesFromTheWholeHistoryAndEveryMissingDayCanBeOpened`, `RevenueComplexityTests.TheWeekFindsTheEarliestMissingDayFromOneAggregateRowWhateverTheHistoryLength`, `VehicleAwayTests.ADayTheVehicleWasAwayCannotBeCapturedAndDoesNotHoldUpTheDaysAfterIt`.

## 3.6 Dashboard (`RevenueRepository.cs:88-156`)

`through = Today`; `from` = `Today` (today) / week start of `Today` (week) / first of the month of `Today` (month). Fleet = vehicles in reach (and company filter) with `JoinedOn <= through` and (`LeftOn` null or `LeftOn > from`). For each vehicle, with `tally` = its records inside `from..through` on active days: `RecordedBefore` (date `< through`), `RecordedToday` (date `== through`), `Edited` (`CorrectedAfterDate`), `Revenue` (sum of amounts).
- For each day `d` in `from..through-1` with `ActiveOn(d)`: `activeBefore++`, `expected += TargetOn(d) / 7`.
- If `ActiveOn(through)`: `vehiclesToday++`; when `RecordedToday > 0`, `expected += TargetOn(through) / 7`.
- `missing = activeBefore - RecordedBefore` (not clamped); `missingDays += missing`; `missingVehicles++` when `missing > 0`.
- `revenue += Revenue`; `capturedToday += RecordedToday`; `editedRecords += Edited`.
- Output: `revenue = Round(revenue, 2)`, `expected = Round(expected, 2)`, `percent = Percent(revenue, expected)` (unrounded sums), then masked per card (RV-18).

## 3.7 Phone normalisation (`Domain/PhoneNumber.cs:25-49`)

Null, empty or whitespace -> `""`. Remove every non-digit (`\D`). Then, with `subscriber` matching `^[17][0-9]{8}$`: 12 digits starting `254` and `digits[3..]` a subscriber -> `"+" + digits`; 10 digits starting `0` and `digits[1..]` a subscriber -> `"+254" + digits[1..]`; exactly 9 digits that are a subscriber -> `"+254" + digits`; anything else -> `""` (not a phone number). Stored form is always `+254` + 9 digits (13 characters). Tests: `DomainRuleTests.PhoneNumbersNormalizeToTheFullKenyanPrefix`, `DomainRuleTests.PhoneNumberTryCreateMirrorsNormalize`.

## 3.8 Effective permissions (`Domain/Access.cs:52-132`)

`Expand(S)` = transitive closure of `S` under `DirectFor` (section 5.2). `Resolve(roleDefaults, overrides, active)`: inactive -> empty set. Else `result = Expand(roleDefaults union {granted overrides})`; `result -= {denied overrides}`; then repeat until stable: remove any key one of whose direct dependencies is no longer in `result`. Role defaults are the union over the person roles (exactly one) of `PermissionCatalog.DefaultsFor(name)` = `Expand(RolePermissions[name])` (name matched ignoring case; unknown name -> empty). Tests: `DomainRuleTests.PermissionDependenciesAreTransitiveAndDenyingARequiredPermissionRemovesDependents`.

## 3.9 Brand colour contrast (`Domain/Organization.cs:50-69`)

For `#RRGGBB`: each channel `c = byte / 255`; `lin = c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055)^2.4`; `L = 0.2126 R + 0.7152 G + 0.0722 B`; `ratio(a, b) = (max(La, Lb) + 0.05) / (min(La, Lb) + 0.05)` (IEEE double). A colour is valid when `ratio(colour, #FFFFFF) >= 4.5` **and** `ratio(colour, #F6F3EC) >= 4.5` (applied to `Primary`, `Secondary`, `Accent`). Tests: `OrganizationSettingsTests`, `Phase1ContractTests`.

## 3.10 Money and rounding

| Where | Rule |
|---|---|
| Input amounts | `SetupValue.Money`: `0 < v <= 999999999999.99` and `Round(v, 2) == v` (any rounding mode gives the same answer for that equality) |
| Display figures | `decimal.Round(x, 2)` with the .NET default, **banker's rounding** (`MidpointRounding.ToEven`): cell `expected` (`target / 7`), row and week totals, `dayTotals`, dashboard `revenue`/`expected`, report `target`. A PostgreSQL `round(numeric, 2)` rounds half away from zero, which differs on exact midpoints (for example 0.125 -> 0.12 here, 0.13 there) |
| Percentages | `Math.Round(x, MidpointRounding.AwayFromZero)` to an integer (`Percent`, `PercentPaidOff`), then, for `Percent`, clamped to `int.MinValue..int.MaxValue` |
| Division | `target / 7m` is decimal division (about 28 digits); it is summed unrounded and rounded once, at the end |
| Sums | revenue amounts, bucket sums, shares: exact decimal sums (SQLite cannot sum decimals, so tests sum in memory) |

## 3.11 Automatic reasons of settings sections (`Application/Settings/SettingsText.cs`)

Reason for a changed section = `AutomaticReason(section, before, after)`: take the top-level fields of the `after` object except `organizationId`; keep those whose value is not deep-equal to the same field of `before` (`before` absent or `"null"` -> every field); for each: `{display name} to {value}`; `Changed ` + the list joined `a, b and c`; no field differs -> `Changed the {section} settings`. Then `SetupPagination.Automatic(reason, typed)` (OS-11). Business date: `Set the business date to {yyyy-MM-dd}` or `Returned the business date to the calendar` (`SettingsSections.cs:128-129`). Logo: `Uploaded a new logo` / `Removed the logo`.
- Display name: the table below, else `the ` + the camelCase field with a space inserted before each capital that follows a lower-case letter, lower-cased (`timeZone` -> `the time zone`, `legalName` -> `the legal name`).
- Value: JSON null -> `none`; `true` -> `on`; `false` -> `off`; `firstDayOfWeek` number -> the English `DayOfWeek` name (`0` Sunday); string -> the text; anything else -> its JSON text.

| Field | Name | Field | Name |
|---|---|---|---|
| `name` | the organization name | `logoLight` | the light logo |
| `hour12` | the 12-hour clock | `logoDark` | the dark logo |
| `datePattern` | the date format | `primary` | the primary colour |
| `firstDayOfWeek` | the first day of the week | `secondary` | the secondary colour |
| `weekNumbering` | week numbering | `accent` | the accent colour |
| `useGrouping` | digit grouping | `passwordComplexity` | password complexity |
| `numberDecimals` | the decimal places | `pinLength` | the PIN length |
| `allowLocaleOverride` | personal locales | `lockoutThreshold` | the wrong PIN tries before a pause |
| `allowTimeZoneOverride` | personal time zones | `lockoutMinutes` | the pause in minutes |
| `allowHour12Override` | personal clock formats | `allowPinSignIn` | PIN sign-in |
| `allowThemeOverride` | personal themes | `logoAlt` | the logo text |

The legacy key `useGroupping` has no entry any more: a saved section carries `useGrouping`, so a change reads `Changed digit grouping to off` **(uncommitted, phase 6)**.

## 3.12 Snapshot JSON keys (change-log `Before`/`After`)

- Setup, revenue and people snapshots are written with `JsonSerializer.Serialize(obj)` (default options): **PascalCase** keys, enums as integers, `DateOnly` as `yyyy-MM-dd`, GUIDs lower-case hyphenated, decimals as JSON numbers, nulls written, no entry for an absent object (`"null"`). An unchanged record is not logged at all.
- Settings sections are written with `JsonSerializerDefaults.Web` (**camelCase**): `organization` `{name, slug}`; `localization` `{organizationId, locale, timeZone, datePattern, hour12, firstDayOfWeek, weekNumbering, currency, useGrouping, numberDecimals, allowLocaleOverride, allowTimeZoneOverride, allowHour12Override, allowThemeOverride}`; `branding` and `securityPolicy` the entity properties (section 1.3); `businessDate` a `"yyyy-MM-dd"` string or `null`; `logo` `{contentType, bytes, updatedAt}` or `null`. The first save of a missing row has `Before = "null"`.
- Rows (values in section 2): `companies` SU-C6 snapshot `{Id, Name, ArchivedOn, Active}`; `vehicles` SU-V17; `recurring` SU-R15; `expenses` SU-E9; `investment` SU-I5; `revenue` RV-10; `people` `{FirstName, LastName, Email, PhoneNumber, Role, Active, ScopeMode, CompanyIds[], VehicleIds[], Permissions[], ApprovalLimit, Name}` (ids and permissions sorted; `Name` is a computed `"{First} {Last}"` that is serialized too; `AccessUseCases.cs:598-612`).
- Audit events (`AuditEvent.Before`/`After`) use the same serializer as their caller; the settings audit `After` is `{"value": <after JSON>, "reason": "<final reason>"}` (OS-9).
- The history endpoint returns `Before` and `After` as the stored JSON text; for people entries seen by a scoped viewer the id arrays are filtered (OS-21).

---

# 4. Use-case flows

Each flow is the order in which the C# checks things; the first failure wins and nothing later runs. Status codes are the mapping of section 6 (400 `ArgumentException`, 403 `UnauthorizedAccessException`, 404 `KeyNotFoundException`, 409 concurrency or unique conflict). Authorization always precedes validation of the body's data and loading of records, except for the cheap shape checks noted.

## 4.0 The common pipeline (`OrganizationUseCase.Run`, `SetupExecution`, `UnitOfWork`)

1. The request context has a non-empty organization id and actor id (from the access token; else 403 plain).
2. Validation hook: empty for every setup, access, revenue and settings use case.
3. The actor has an **active** membership in the organization (else 403 plain).
4. Required permissions: if the required set is non-empty, resolve the actor permissions (once per request attempt, `OrganizationRepository.cs:17-34`) and require **any one** of the set (else 403 plain). An empty set resolves nothing.
5. Write: `UnitOfWork.Execute` opens a serializable transaction **before** step 1 (the authorization runs inside it), then runs the body, `SaveChanges`, commit. Read: `UnitOfWork.Read` has no transaction and fails with `InvalidOperationException` (500) if the body left tracked changes.
6. `SetupActor` is built inside the body wrapper just before the body (scope rows, business date, permissions, `SettingsVersion`; SU-X2).
7. Retry: when the only conflicting entries are `Organization` rows (the settings version) or SQL error 1205, tracked state and resolved permissions are dropped, the thread waits `Random(5..24) * (attempt + 1)` ms and the whole body runs again from step 1; at most 3 retries (4 attempts), then `DbUpdateConcurrencyException` (409). Any other conflict surfaces at once (OS-19).

## 4.1 Organization settings, logo, appearance, preferences (`OrganizationSettingsUseCases.cs`)

- **Get settings** (`organization.manage`, read): load organization, localization (defaults when missing, 400 if its zone is unknown), branding and security policy (defaults when missing) without tracking; calendar date in the stored zone; the actor effective settings; answer with `effectiveBusinessDate = held ?? calendar date` and `calendarDate`.
- **Save a section** (`organization.manage`, write): 1 typed reason checked, 1..500 or blank (400); 2 load the organization (tracked); 3 find the section by key (404); 4 `Apply`: shape and value checks of the section (400), merge onto the saved row, domain `Validate()`, and for `localization` the held business date versus the calendar date in the new zone (400); a section refusal (`organization` name/slug checks, slug conflict) is returned, not thrown; 5 refusal or `before == after`: `ChangeTracker.Clear()`, nothing written, answer 200 (unchanged) or the plain-JSON 400/409 of the refusal; 6 otherwise the automatic reason (3.11) plus the typed reason, `SettingsChangeLog.Record` (version `+1`, change-log row), audit event `organization.settings.updated`; 7 commit (token conflict on the organization row -> retry, 409).
- **Upload logo** (`organization.manage`): 1 typed reason; 2 `OrganizationLogo.FromDataUrl` (size, MIME, base64, magic bytes: 400); 3 load the existing logo; 4 insert or overwrite; 5 `Record("logo", shape before, shape after)` and audit.
- **Remove logo**: 1 typed reason; 2 load; 3 none -> `{logo: null}`, nothing logged; 4 delete, `Record("logo")`.
- **Appearance** (any active member): organization, localization, effective settings of the caller, logo; no writes.
- **Preferences** (any active member): own row or blank, with the organization allow-flags and defaults; withdrawn overrides are returned as null.
- **Save preferences** (any active member): load or create the own row, replace every field, `Validate()` (400), then `EnsureAllowed` against the organization localization (400 per disallowed override), commit; no change log, no version change.

## 4.2 People and access (`AccessUseCases.cs`)

- **Catalog** (any member), **Me** (any member; own scope with the same company and vehicle filters as the lists), **Roles** (`people.view`, a write because `EnsureRoles` may insert catalog roles), **Scope options** (`people.manage`; companies in the actor scope not archived today, vehicles in scope that are active today with an active company).
- **List** / **Get** (`people.view`): page 1..100000 / 1..100 (400); visibility by `PeopleVisibility` (AC-25; a hidden id is 404); DTOs show only scope items the viewer reaches and count the rest.
- **Save person** (`people.manage`): 1 shape validation (names, e-mail, phone, scope mode, permission list: 400); 2 role by name, ignoring case (400 "Unknown role."); 3 load the target among visible people when updating (404); 4 update needs `Version` (400) equal to the membership version (409 `DbUpdateConcurrencyException`); 5 hidden scope preserved or refused (403); 6 scope validity and reach (400/403); 7 editing oneself (400); 8 only an Owner gives the Owner role (403); 9 only an Owner touches an Owner (403); 10 permissions expanded with dependencies and checked against the catalog (400); 11 anti-escalation: role defaults held, single permissions and approval limit need `access.manage` and held permissions (403); 12 normalise phone (3.7) and lower-case e-mail; 13 changing sign-in details needs an Owner or full-scope rule (403); 14 e-mail or phone already used by another user (400); 15 create: user (active, no PIN), membership, role link, scope rows, overrides, audit `person.created`, change-log "people"; update: if sign-in details changed bump `SecurityVersion` and revoke devices and refresh tokens (PIN kept), replace role, overrides and scope rows, and when something changed bump the membership version, audit `person.updated`, bump `SecurityVersion` only for name, role or single-permission changes, change-log "people".
- **Deactivate / reactivate** (`people.manage`): 1 not oneself (400); 2 load visible (404); 3 Owner rule (403); 4 same state already -> success, nothing written; 5 version required and equal (409); 6 deactivate needs a typed reason 1..500 (400); 7 apply (`Deactivate` + `User.Remove` + revoke sessions, or `Reactivate` + status Active); 8 change log and audit.
- **Sign out everywhere** (`people.manage`): 1 not oneself (400); 2 load (404); 3 Owner rule (403); 4 revoke devices and refresh tokens; 5 audit and change log.

## 4.3 Setup

- **Company save** (`companies.manage`): typed reason (400) -> name (400) -> load for update (404) -> creating needs an organization-wide actor (403) -> an archived company cannot be renamed (400) -> name unique (400) -> unchanged rename returns -> add -> `RecordChange` ("companies").
- **Archive / restore company**: typed reason -> load (404) -> archive: not yet archived and has a vehicle that is not retired -> 400; domain `Archive`/`Restore` -> `RecordChange` only if it changed.
- **Vehicle save** (`vehicles.manage`): typed reason -> registration format -> `Money(target)` -> join date range -> company load (404) -> company active (400) -> creating needs organization-wide or the company in scope (403) -> load vehicle for update (404) -> retired (400) -> registration immutable (400) -> duplicate registration (400) -> join date later than the first recorded day (400) -> `Update` (no-op returns) -> `RecordChange` ("vehicles"). **Retire**: reason -> load (404) -> a record on or after the leave date (400) -> domain `Retire` (400) -> record if changed. **Restore**: reason -> load (404) -> company load (404) -> company active (400) -> `Restore` (400) -> record if changed. **Report**: SU-V15. **List**: `RequireAny(vehicles.manage, invest.view)` (403) -> page (400) -> data -> mask for investment-only viewers. **Company options**: `vehicles.manage`.
- **Scheduled item save** (`commitments.manage`): typed reason -> `Definition` (kind rules, expense item in use: 400) -> load item for update (404) -> `ValidateNew` (400) -> load vehicles and companies, check each share (404/400) -> create, or revise: every existing share in reach (403) -> unchanged returns -> `Revise` (400) -> `RecordChange` ("recurring"). **Stop**: required reason (400) -> confirmed (400) -> load (404) -> every share in reach (403) -> `Stop` (400) -> record if changed. **Cancel stop**: load (404) -> in reach (403) -> `CancelStop` (400) -> record if changed. **List** (`commitments.view`), **vehicle options** (`commitments.manage`).
- **Expense catalog**: list and options use any-of read permissions (SU-E1). Save category: name (400) -> new category (bucket check 400) or load (404) -> name unique (400) -> `Change` (bucket 400; unchanged returns) -> record. Stop or turn on a category or item: load (404) -> `Stop`/`Restore` (400) -> record if changed. Add item: load category (404) -> name (400) -> unique in category (400) -> record. Rename item: name (400) -> load (404) -> unique (400) -> `Rename` -> record if changed.
- **Investment**: get (`invest.view`): vehicle in reach (404), entries, report net, percent; add (`invest.manage`): vehicle (404) -> entry validation (400) -> record; update / remove: entry (404) -> its vehicle in reach (404) -> validation (400) -> record if changed.
- **Change log** (`audit.view`, read): page validation (400) -> `before < 1` (400) -> filter parsing (400) -> query with visibility, filters, seek or offset, count (OS-20 to OS-24).

## 4.4 Revenue

- **Save a day** (`revenue.capture` or `revenue.correct`): 1 reason text and entry validation (400); 2 vehicle in reach (404); 3 existing record for the day; 4 identical replay -> success (RV-3); 5 future date (400); 6 vehicle not active that day (400); 7 reason permission (403); 8 new-record permission (403); 9 past-day-change permission (403); 10 stale or missing version -> 409 with the current cell; 11 (removed by 9276c51: an earlier missing day no longer refuses a new record); 12 create (`Version 1`) or `Replace` (domain 400s, `Version++`, `CorrectedAfterDate`); 13 change-log row + audit (`revenue.recorded`); 14 commit; token or unique race -> 409.
- **Week** (`revenue.view`): 1 paging parameters (400); 2 first day of week; 3 week range (400); 4 grid and records queries; 5 a `vehicleId` not in reach (404); 6 build (3.4).
- **Dashboard** (one of the four `dash.*` card keys): 1 cache key from the actor `SettingsVersion`; 2 compute (400 for a bad period); 3 mask by card permission.

## 4.5 Common outcomes of a write

A write that changes data always ends with: the change-log row (version `+1`, `SettingsChangeLog.Record`), the audit event, then `SaveChanges` and the commit. A write that finds nothing to change returns the entity id (or `{section}`) without a log row.

---

# 5. Permissions and roles

## 5.1 Catalog (`Domain/PermissionKeys.cs:4-53`, groups in `Application/AccessContracts.cs:28-94`)

Forty keys in eight groups, in this wire order. "Enforced by" lists the use cases of this inventory that check the key (grep of `PermissionKeys.<Name>`); a blank means no use case in this scope checks it. Keys of the petty-cash and office-bills features belong to the petty-cash reader.

| Group | Key | Needs (direct) | Enforced by |
|---|---|---|---|
| Dashboard | `dash.capture` | `revenue.capture` | revenue dashboard (RV-17/18) |
| Dashboard | `dash.float` | `pettycash.spend` | **petty-cash feature** |
| Dashboard | `dash.revenue` | `revenue.view` | revenue dashboard |
| Dashboard | `dash.net` | `revenue.view`, `expenses.view`, `commitments.view` | none yet (reserved) |
| Dashboard | `dash.costs` | `expenses.view`, `commitments.view` | none yet (reserved) |
| Dashboard | `dash.gaps` | `revenue.view` | revenue dashboard |
| Dashboard | `dash.pettycash` | `pettycash.view_all` | **petty-cash feature** |
| Dashboard | `dash.commitments` | `commitments.view` | none yet (reserved) |
| Dashboard | `dash.investment` | `invest.view` | none yet (reserved) |
| Dashboard | `dash.edits` | `audit.view` | revenue dashboard |
| Revenue | `revenue.view` | none | week grid |
| Revenue | `revenue.capture` | `revenue.view` | save, cell `canEdit` |
| Revenue | `revenue.no_earnings` | `revenue.capture` | save with a reason |
| Revenue | `revenue.correct` | `revenue.view` | save, cell `canEdit` |
| Expenses | `expenses.view` | none | expense catalog reads |
| Expenses | `expenses.capture` | `expenses.view` | none yet (reserved) |
| Expenses | `expenses.correct` | `expenses.view` | none yet (reserved) |
| Expenses | `expenses.setup` | `expenses.view` | expense catalog reads and writes |
| Petty cash | `pettycash.spend`, `pettycash.view_all`, `pettycash.approve_item`, `pettycash.approve_day`, `pettycash.issue`, `pettycash.issue_negative` | none, none, `view_all`, `approve_item`, `view_all`, `issue` | **petty-cash feature** |
| Office bills | `bills.view`, `bills.capture`, `bills.approve` | none, `bills.view`, `bills.view` | none yet (reserved; **bills feature**) |
| Scheduled expenses and savings | `commitments.view` | none | scheduled list, expense catalog reads |
| Scheduled expenses and savings | `commitments.manage` | `commitments.view` | scheduled save/stop/options, expense options |
| Reports | `reports.view`, `reports.export` | none, `reports.view` | none yet (reserved) |
| Setup | `companies.manage` | none | companies |
| Setup | `vehicles.manage` | none | vehicles, vehicle report, company options |
| Setup | `invest.view` | none | investment get, vehicle list |
| Setup | `invest.manage` | `invest.view` | investment writes |
| Setup | `people.view` | none | people list/get/roles, change-log people section |
| Setup | `people.manage` | `people.view` | people writes, scope options |
| Setup | `access.manage` | `people.manage` | single permissions and approval limit rules |
| Setup | `audit.view` | none | change log endpoint |
| Setup | `organization.manage` | none | organization settings, logo |

The labels are in `AccessContracts.cs:32-92` and in `inventory-http-contract.md` section 3.2 (not repeated here).

## 5.2 Dependency graph (`Domain/Access.cs:52-104`)

Thirty direct edges from 27 keys (the 13 keys with no entry have none): the "Needs" column of 5.1 is the full list. `DirectFor(key)` returns it (empty for unknown keys); `Expand(set)` adds dependencies until nothing is added. Test: `PermissionKeysTests.DependenciesNameOnlyCatalogKeys`.

## 5.3 Role defaults (`AccessContracts.cs:104-125`)

Role names are matched ignoring case; a person has exactly one role. Defaults are expanded with dependencies before use (`DefaultsFor`). Sizes after expansion: Owner 39, Office admin 24, Fleet manager 12 (adds `commitments.view` through `dash.costs`), Revenue clerk 5.

| Role | Listed keys | Not held after expansion |
|---|---|---|
| `Owner` | every key except `dash.capture` (39) | `dash.capture` |
| `Office admin` | `dash.revenue`, `dash.costs`, `dash.gaps`, `dash.commitments`, `dash.edits`, `revenue.view`, `revenue.correct`, `expenses.view`, `expenses.capture`, `expenses.correct`, `expenses.setup`, `bills.view`, `bills.capture`, `commitments.view`, `commitments.manage`, `reports.view`, `reports.export`, `invest.view`, `invest.manage`, `companies.manage`, `vehicles.manage`, `people.view`, `people.manage`, `audit.view` | `access.manage`, `organization.manage`, `revenue.capture`, `revenue.no_earnings`, all `pettycash.*`, `bills.approve`, `dash.capture`, `dash.float`, `dash.net`, `dash.pettycash`, `dash.investment` |
| `Fleet manager` | `dash.float`, `dash.revenue`, `dash.costs`, `dash.gaps`, `revenue.view`, `revenue.capture`, `revenue.no_earnings`, `revenue.correct`, `pettycash.spend`, `expenses.view`, `reports.view` (+ `commitments.view` by dependency) | 28 other keys, among them all setup, people, audit, organization, bills and petty-cash approval keys |
| `Revenue clerk` | `dash.capture`, `dash.gaps`, `revenue.view`, `revenue.capture`, `revenue.no_earnings` | all others |

Roles are rows per organization created on demand (`UserProvisioning.EnsureRoles`, AC-6); the legacy `RolePermission` table is ignored. Tests: `AccessAndSetupTests.RoleDefaultsComeOnlyFromTheCatalog`, `AccessAndSetupTests.RoleDefaultsFollowWebV28`, `PermissionKeysTests.*`.

## 5.4 Resolver, request-time rule, data scope

- Effective permissions: 3.8. Request time: `OrganizationRepository.Permissions` reads the person role names and overrides from the database (never the token), caches per request attempt (`ForgetResolved` on retry), and returns the empty set for an inactive membership.
- A use case needs **any one** of its required keys (`RequiredPermissions`); several (`ReadAny`) are used where two features share an endpoint (SU-X4).
- Data scope (separate from permissions): exactly one of `all` (`SetupDataScope.AllCompanies`), `companies` (rows in `SetupCompanyScope`) or `vehicles` (rows in `SetupVehicleScope`); `scopeMode` on the wire is `all` if the all-companies row exists, else `companies` if any company row exists, else `vehicles` (`AccessUseCases.cs:289`). The actor fields `AllCompanies`, `CompanyIds`, `VehicleIds` drive every visibility query (SU-X3, AC-25).
- Cross-check against `inventory-http-contract.md` section 3.2 (the heading **Permissions, roles and data scope**; the brief named section 3.3, which is "People and access DTOs"): key list, order, direct dependencies and the four role default lists agree with the code read here; that document's `needs` column and role table match 5.1 and 5.3 line for line.

---

# 6. Error vocabulary

## 6.1 Exception to HTTP status

| Exception raised | Status | Body (problem+json unless noted) | Mapped in |
|---|---|---|---|
| `UnauthorizedAccessException` | 403 | title "Not permitted in this organization or data scope."; `detail` = the exception message, omitted when it is the framework default text (a plain refusal has no detail) | `Api/SetupEndpoints.cs:32` |
| `KeyNotFoundException` | 404 | title "Record not found in your scope." | `:33` |
| `ArgumentException` (and subclasses) | 400 | title "Invalid setup change", `detail` = message | `:34` |
| `DbUpdateConcurrencyException` | 409 | title "Settings changed. Reload before saving." | `:35` |
| `DbUpdateException` (unique or FK violation, other) | 409 | title "A conflicting record exists. Reload before saving." | `:36` |
| `RevenueConflictException` | 409 | title "This day already has a different record.", detail "This day was changed after you opened it. Check the current record and save again.", extension `current` (cell) | `Api/RevenueEndpoints.cs:24-28` |
| `DbUpdateConcurrencyException` on `/setup/revenue` | 409 | title "This day was changed by another save.", detail "Reload the current record and try again." | `:29-32` |
| `RevenueEarlierDayMissingException` | 400 | title "Invalid setup change", detail `Record {date} before this date first.`, extension `earliestMissing` **(removed by 9276c51: days are captured in any order; see the drift log entry 24)** | `:33-37` |
| `SectionRefusal` (settings) | 400, or 409 when `Conflict` | plain JSON `{ "detail": "..." }`, not problem details | `Api/OrganizationEndpoints.cs:23-29` |
| anything else (`InvalidOperationException`, `TimeZoneNotFoundException`, `JsonException` ...) | 500 | the global exception handler / problem details (`Program.cs`) | `Program.cs:131-136,163` |

Ordering: the `/setup/revenue` filter is the inner one, so its handlers win for revenue routes; `DbUpdateConcurrencyException` is caught before `DbUpdateException`. The `/setup` filter is installed on the settings, setup, access, revenue and petty-cash route groups. Every 403 from the pipeline (not a member, missing permission, stale context) carries no detail.

## 6.2 Permission refusal wording

`PermissionCatalog.Refusal(action, key)` returns `UnauthorizedAccessException($"{action} needs the permission \"{label}\".")` where `label` is the catalog label of `key`; for a key the catalog does not label the label is the key itself (an unknown key no longer faults, `PermissionKeysTests.ARefusalNamesAKeyTheCatalogDoesNotLabel`). It replaces the former private helper `RevenueUseCases.Needs`. Used by the three revenue refusals (RV-5). The only other hand-written 403 texts are in `AccessUseCases` (AC-9 to AC-18).

## 6.3 Common 400 messages (for the Python validation layer)

Name and registration: SU-C1, SU-V1; money: "Amount must be positive with at most two decimal places."; pagination: "Page must be 1–100000 and page size 1–100."; reasons: "A reason of 1–500 characters is required."; settings: "Send the section's settings as an object.", "A setting has the wrong type of value.", "Invalid settings.", "Invalid format settings", "Invalid security policy.", "PIN sign-in cannot be disabled.", "Invalid accessibility preferences", "Brand colors must meet WCAG AA (4.5:1) against the fixed surfaces"; revenue: RV-2, RV-4, RV-7. The en dash in "1–500" and "0–6" is U+2013.

---

# 7. Time and clock

- `IClock.UtcNow` (`Application/AuthContracts.cs:6`) is the only source of "now"; production `SystemClock` returns `DateTimeOffset.UtcNow` (`Infrastructure/Security.cs:13`). Uses in this scope: revenue `CapturedAt`/`UpdatedAt`, investment `RecordedAt`, change-log `OccurredAt`, audit `OccuredAt`, logo `UpdatedAt`, the calendar date (below), and the session check in `Program.cs`. Every `DateTimeOffset` written must have offset zero (`ValidateWrites`: "Instants must be UTC.").
- **Business date** (`Today` in every setup and revenue rule): `Organization.BusinessDate` when held, else the calendar date of `clock.UtcNow` converted to the **organization** time zone (`OrganizationLocalization.TimeZone`, default `Africa/Nairobi`); never the person zone (OS-1). A held date may move backwards or forwards up to the calendar date (OS-2/OS-3) and a zone change may not leave it in the future (OS-4). The business date is read once per request attempt (SU-X2).
- **Calendar date** in a zone = `date(convert(utc now to zone))`. The settings path turns an unknown or invalid stored zone into a 400 (`SettingsText.CalendarDate`); the setup path (`SetupExecution.Actor`) does not (500). Zone ids are IANA names validated by `TimeZoneInfo` (`TimeZoneId`).
- **Dates without time**: business dates, join/leave/return dates, archive and stop dates, target effective dates, schedule dates and investment dates are `DateOnly` (`yyyy-MM-dd`); no instant is attached.
- **Week** start: organization `FirstDayOfWeek` (0 = Sunday .. 6, default 1) (3.4a); `WeekNumbering` is stored only. Reports `week` and `month` run from the start of the current week or month to the business date (`ReportPeriod.Current`).
- **History date filter**: `from` and `to` are calendar days in the organization zone; the window is `[midnight(from), midnight(to + 1 day))` converted with the zone UTC offset at that local midnight (`SetupRepository.cs:347-365`); an ambiguous or skipped local midnight takes the offset .NET returns for it.
- **Scheduled postings** use the business date and the same calendar; `Stop` and `CancelStop` compare against the business date; a stop dated after it is "pending".
- **Dashboard cache** key includes the business date; entries expire after 60 s (RV-19).
- **Token and lockout times** are UTC instants handled by the authentication reader (`PausedUntil`, `ExpiresAt`).

---

# 8. Naming audit

C# names and wire spellings that the Python and PostgreSQL rewrite should not copy. "Suggested" is a database or code name; the HTTP contract may have to keep the old spelling for released clients (see `inventory-http-contract.md`).

| C# name | Where | Problem | Suggested |
|---|---|---|---|
| `AuditEvent.OccuredAt` | `Domain/Access.cs:38-49` | misspelt | `occurred_at` |
| `CurrentOganizationId` | `Infrastructure/OrganizationModel.cs:15,24` | misspelt | `current_organization_id` |
| `Authroization` (comment) and `OrganizationPort.cs` | `Application/OrganizationPort.cs:32` | typo; the file holds the use-case base, not a port | `use_case_pipeline` module |
| `UseGroupping` / `useGroupping` | `EffectiveFormats.UseGroupping` (legacy output), request alias | legacy misspelling, kept only for released apps | `use_grouping`; accept the alias on PUT and emit it on appearance until old apps are gone |
| `OrganizationSettingsVersion` | `Domain/Setup/OrganizationSettingsVersion.cs` | it is the change log, not a version of settings | `change_log_entry` (table `change_log`) |
| `Organization.SettingsVersion` / `SettingsChanged()` | `Domain/Organization.cs:91` | it versions every change, not only settings; also the cache key and the concurrency token | `change_version`, `record_change()` |
| `SettingsChangeLog` | `Application/Settings/SettingsChangeLog.cs` | same confusion | `ChangeLogWriter` |
| `AuditEvent` vs change log | `Domain/Access.cs:38-49`, `Domain/Setup/OrganizationSettingsVersion.cs` | two stores for one fact | one change log; keep `audit_event` only if a reader exists |
| `SetupActor`, `SetupExecution`, `ISetupExecution`, `SetupPagination`, `SetupValue`, `SetupDataScope` | `Application/ISetupExecution.cs`, `Infrastructure/Setup/*` | "Setup" is a historical module name; the pipeline serves access, revenue and settings too | `RequestActor`, `UseCaseRunner`, `Paging`, `values`, `DataScope` |
| `Recurring*` (item, version, allocation, frequency, kind) vs permission group `commitments.*` vs UI "scheduled expenses and savings" | `Domain/Setup/RecurringItem.cs`, `PermissionKeys.cs:38-39` | three names for one concept | `scheduled_item`, `scheduled_item_version`, `scheduled_item_share`; keep the permission key strings |
| `PsvCompany` | `Domain/Setup/PsvCompany.cs` | acronym in the type name | `company` (UI keeps "PSV company") |
| `FleetVehicle`, `VehicleTarget`, `VehicleAwayPeriod` | `Domain/Setup/FleetVehicle.cs` | fine concepts, long names | `vehicle`, `vehicle_target`, `vehicle_away_period` |
| `LeftOn` / `ReturnedOn` / `JoinedOn` | `FleetVehicle.cs` | pairs do not read as a range; `ReturnedOn` is exclusive | `left_on`, `returned_on` documented as `[left_on, returned_on)`, or `away_from`, `away_until` |
| `Version` on membership, revenue record, user, refresh token | several | the same word is the optimistic token and the change-log number | `row_version` for tokens |
| `Hour12` | `OrganizationLocalization.Hour12` | digit in a boolean name | `uses_12_hour_clock` |
| `WeekNumbering`, `AllowPinSignIn`, `PasswordMinLength`, `PasswordComplexity`, `PasswordHistory`, `IdleUnlockSeconds` | `OrganizationLocalization`, `OrganizationSecurityPolicy` | stored and validated, used by nothing | drop, or keep as documented dead columns |
| `OrganizationSecurityPolicy.AllowPinSignIn` | must always be true | meaningless flag | drop |
| `RolePermission` | `Domain/Access.cs:13-18` | legacy table, nothing reads it | drop |
| `PermissionItem.Needs` | `Application/AccessContracts.cs:8` | wire name `needs` | `requires` internally, `needs` on the wire |
| `EffectiveFrom` of the change-log row | `OrganizationSettingsVersion.cs` | no caller sets it | drop |
| `Costs` and `MoneyOut` in `VehicleReport` | `SetupContracts.cs:75-77` | duplicate field for Phase 1 clients | one `money_out` internally, both on the wire |
| `RevenueNoEarningsReason.NoCrew` label `No Crew` | `Revenue.cs:5-51` | two accepted spellings, label differs from enum and snapshot | store `no_crew`; accept `No Crew` and `NoCrew`; label `No Crew` |
| `CellStatus.Reason` | `RevenueContracts.cs:21-28` | the cell shows a reason, not a "status reason" | keep the five wire strings (none, future, missing, amount, reason) |
| `Page<T>.PageNumber` / `HistoryPage.NextBefore` | `SetupContracts.cs:5,21` | inconsistent with `page` query parameter | keep wire names |
| `dash.*` keys | `PermissionKeys.cs:6-15` | "dash" is a UI place, not a capability | keep strings (clients depend on them) |
| `ContrastValidator`, `HexColour`, `TimeZoneId`, `Locale` | `Domain/Organization.cs:6-69` | value objects named like helpers | `colour_contrast`, `Hex6Colour` |
| `Dto` suffix, `IOrganizationEntity`, `Tenant()` | everywhere | framework vocabulary | `Row`/`Response`, `TenantScoped` |
| Namespace `Auth` | all files | the product is xcode | `xcode` |

---

# 9. Open questions

1. **Brief versus code.** (a) The HTTP contract's permissions section is 3.2, not 3.3 (3.3 is "People and access DTOs"); the contents agree with the code. (b) The brief grouped `commitments.*` and the revenue `dash.*` keys with the petty-cash feature; in the code `commitments.view|manage` gate the scheduled items and the expense item picker (this inventory) and `dash.capture|revenue|gaps|edits` gate the revenue dashboard. Only `pettycash.*`, `dash.float`, `dash.pettycash` belong to petty cash; `bills.*` has no use case yet. (c) `Needs` was replaced by `PermissionCatalog.Refusal`, confirmed. (d) The dashboard still loads the fleet and its targets and computes `expected` in C#; SQL aggregation covers the record sums and counts only.
2. **Banker's rounding.** Display figures use .NET `decimal.Round(x, 2)` (to even). PostgreSQL `round` rounds half away from zero. Decide whether the rewrite reproduces to-even (a custom function) or accepts a one-cent difference on exact midpoints of `target / 7`.
3. **Invalid stored time zone.** The settings path answers 400 and the setup/revenue path answers 500 (`SetupExecution.Actor`). Pick one behaviour; the stored zone is validated on save, so only bad data triggers it.
4. **Organization section with a non-object value.** `OrganizationDetailsSection` deserializes without a try; a JSON string or number likely raises `JsonException` and answers 500, while the merged sections answer 400 "A setting has the wrong type of value." No test found; treat as 400 in the rewrite.
5. **Unknown fields in a merged settings section** are silently ignored (merged then deserialized with the Web defaults), not rejected.
6. **Unenforced permissions.** `dash.net`, `dash.costs`, `dash.commitments`, `dash.investment`, `expenses.capture`, `expenses.correct`, `bills.*`, `reports.*` are in the catalog and role defaults but no use case checks them yet. Decide whether the rewrite keeps them as reserved.
7. **Security policy fields never used:** `PasswordMinLength`, `PasswordComplexity`, `PasswordHistory`, `IdleUnlockSeconds`, `AllowPinSignIn` (and `WeekNumbering` in localization). Keep for wire compatibility or drop.
8. **Two stores for one fact.** `AuditEvent` and the change log both record each change. No read path for `AuditEvent` was found in the files read; confirm before porting it.
9. **Vehicle `Active` flag in the list ignores away periods** (uses the static join/leave form), while every revenue rule uses `ActiveOn` with away. They differ only for a business date that sits inside a past away period.
10. **`missing` in the dashboard is not clamped**; a record on a non-active day cannot exist, so it cannot go negative with consistent data.
11. **Legacy `useGroupping`.** Phase 6 is in flight: the name is accepted on PUT (current name wins) and both names are served by appearance. The removal date is undecided ("remove once they are retired" in the code comment).
12. **`Roles` is a write** (inserts the catalog roles on demand). In PostgreSQL seed the four roles at organization creation and make the list a read.
13. **Petty cash and bills exist** (`Domain/PettyCash.cs`, `Application/PettyCash*.cs`, `Api/PettyCashEndpoints.cs`, `Infrastructure/PettyCash*.cs`, change-log section `pettycash`, approved petty-cash expenses inside the vehicle report postings). They are inventoried by another reader; the report formula in 3.3 includes their postings only as an input.
14. **Authentication** moved to `Application/Authentication/*`; the 1.1 and `ID-` rows cite the deleted `AuthService.cs`. They were not re-pointed here (section 10).
15. **Uncommitted base.** Everything marked in the Snapshot paragraph may still change before commit; the Phase 6 rename in particular.

---

# 10. Corrections after Phases 4 to 6

Applied in place to the finished rows of sections 1 to 2.4. Format: row id, then "was ... now ...". Line numbers are the working tree on 2026-10-07/08. All rows below cite files with uncommitted edits.

**Header and general**
- Scope paragraph: was "organization-settings, logo and preference flows are implemented in `Api/OrganizationEndpoints.cs`" now `Application/Settings/*` (the endpoint file is transport only); petty cash and authentication named as other readers.
- Snapshot paragraph: was "`RevenueDashboardCacheTests` is a measuring stub; no dashboard cache exists in code yet" now `RevenueDashboardCache` exists (RV-19) and the list of uncommitted files was extended.
- Conventions, enums: was "every enum is an integer on the wire except the no-earnings reason" now also `CellStatus` is a string (`none|future|missing|amount|reason`).
- 2.1 header: was `AuthService.cs` as a live file, now deleted; `ID-1` to `ID-29` and the 1.1 entries citing `AuthService.cs:N` (for example the 10-minute code expiry at `AuthService.cs:66`) point at code that now lives in `Application/Authentication/AuthCodes.cs`, `AuthAccounts.cs`, `PinSetupService.cs`, `SessionService.cs`, `SessionTokens.cs`, `SignInService.cs`; their line numbers are stale and were not re-derived (auth reader). The cites into `Api/AuthEndpoints.cs` (`:14-50,103-126`, `:80-86`, `:108-110`, `:127`) are stale for the same reason: the file now has 85 lines.

**Section 1**
- 1.1 identity table: `AuthDb.cs:38-39, 41-43, 45, 46, 48-49, 52, 53, 55-57, 65-72` was shifted by two lines (a petty-cash `DbSet` and `ConfigurePettyCash`) now `+2`; `AccessUseCases.cs:221` now `:222`, `:127` now `:128`.
- 1.2 `RolePermission` row: was `AccessContracts.cs:98-121` now `:104-131`.
- 1.3 `Organization` rows: was `SettingsChanged()` "called by the endpoints" implicit, now only by `SettingsChangeLog.Record`; `EnsureBusinessDateWithin` was public now private; `ChangeTimeZone` was "bumps the version" now leaves `SettingsVersion` alone and is called by the localization section hook; all `Domain/Organization.cs` line cites after line 75 shifted by +5 (and +9 after `EffectiveFormats`) because `IValidatable` and the legacy `UseGroupping` property were added.
- 1.3 `OrganizationLocalization`: was `UseGroupping` (sic) now `UseGrouping` **(uncommitted, phase 6)**, column renamed by migration `20261007181520_RenameUseGrouping`; localization, branding and security policy implement `IValidatable`.
- 1.3 `EffectiveFormats`: was `UseGroupping` now `UseGrouping` plus a computed read-only `UseGroupping` serialized for old apps **(uncommitted, phase 6)**.
- 1.4 reason table: was `RevenueContracts.cs:98-106` now `:154-170`; `RevenueUseCases.cs:112` now `:111`.
- 1.6 `FleetVehicle`: was `FleetVehicle.cs:16-119`, `VehicleTarget :121-137`, `VehicleAwayPeriod :139-157`, `TargetOn :113-118` now `16-124`, `126-142`, `144-162`, `114-123`; `TargetOn` is one pass with a revision tie-break (same result).
- 1.6 change-log entry: was a list of 13 section values now also `pettycash`; `VehicleId` is also set for `pettycash`.

**2.1 identity (cites only)**
- ID-2: `AuthContracts.cs:31` now `:34`. ID-4: `AuthContracts.cs:36-48` now `:39-51`. ID-18: `AuthContracts.cs:13-14` now `:14-15`. ID-21: `Program.cs:96-126` now `:98-128`. ID-22: `AccessUseCases.cs:157,191-192` now `:158,192-193`. ID-25: `AuthDb.cs:65-72` now `:67-74`. ID-26: `Program.cs:88-95` now `:90-98`. ID-29: `Program.cs:209-221` now `:224-236`.

**2.2 access**
- AC-1: was 40 keys cited at `AccessContracts.cs:26-96` now also `Domain/PermissionKeys.cs:4-53` (single source); `AccessUseCases.cs:13` now `:14`.
- AC-2: was "27 direct edges" now 30 direct edges from 27 keys.
- AC-4: was `AccessContracts.cs:98-125` now `:104-131`.
- AC-5: was `OrganizationPort.cs:34-53` now `:34-60`; an empty required set no longer resolves permissions (membership is checked first, then permissions only when the set is non-empty).
- AC-6: `AccessUseCases.cs:16-23,559-564` now `:17-24,560-565`. AC-8: `328-352` now `329-353`. AC-9: `356-357` now `357-358`. AC-10: `359-374` now `360-375`. AC-11: `376-399` now `377-400`. AC-12: `402-432` now `403-433`. AC-13: `97-98,201-202,237-238` now `98-99,202-203,238-239`. AC-14: `100-104,513-517,557` now `101-105,514-518,558`. AC-15: `494-499` now `495-500`. AC-16: `489-510,626-632` now `490-511,623-631`. AC-17: `106-108` now `107-109`. AC-18: `118-121,522-555` now `119-122,523-556`. AC-19: `111-112,122-123` now `112-113,123-124`. AC-20: `90-93` now `91-94`. AC-21: `125-148,261-267,466-481` now `126-149,262-268,467-482`. AC-22: `150-195,596-623` now `151-196,593-621`; the change-log write is now `SettingsChangeLog.Record` (people). AC-23: `198-233` now `199-234`. AC-24: `235-246,567-573` now `236-247,568-574`. AC-26: `65-77,278-326` now `66-78,279-327`. AC-27: `13-80` now `14-81`. AC-28: `125-148` now `126-149`.

**2.3 organization settings and change log**
- Preamble: was "the settings use cases live in `OrganizationEndpoints.cs`, no transaction, one `SaveChanges`" now `Application/Settings/*`, run through `UnitOfWork.Execute` (serializable, change-log retry, 409 after four attempts); reads `AsNoTracking`.
- OS-1: `SetupExecution.cs:32-40` now `:41-49`; `Organization.cs:87` now `:92`.
- OS-2: was `OrganizationEndpoints.cs:69-76,221-227` now `SettingsSections.cs:112-137` (`BusinessDateSection`).
- OS-3: was `OrganizationEndpoints.cs:69-76` now `SettingsSections.cs:116-126`.
- OS-4: was `OrganizationEndpoints.cs:60-66` and the domain method called directly now the `afterMerge` hook of the localization section (`SettingsSections.cs:35-36`); the version moves once for the save.
- OS-5: was `OrganizationEndpoints.cs:205-219` now `SettingsText.cs:13-27`.
- OS-6: was `OrganizationEndpoints.cs:47-59` now `SettingsSections.cs:91-109` returning a `SectionRefusal`; the endpoint maps it to plain `{ detail }` 400 or 409 (`OrganizationEndpoints.cs:23-29`).
- OS-7: was `OrganizationEndpoints.cs:296-325` now `SettingsSections.cs:45-89` (`MergedSection<T>`); legacy field names accepted **(uncommitted, phase 6)**.
- OS-8: was `OrganizationEndpoints.cs:79-81` now `OrganizationSettingsUseCases.cs:39-44`.
- OS-9: was `OrganizationEndpoints.cs:82-83,188-203` now `OrganizationSettingsUseCases.cs:45,133-149` and `SettingsChangeLog.cs:11-19`.
- OS-10: was "unknown section name -> 404 from the endpoint switch" now `KeyNotFoundException` raised in the use case (`OrganizationSettingsUseCases.cs:37`).
- OS-11: `SetupContracts.cs:104-122` now `:106-124`.
- OS-12: was `OrganizationEndpoints.cs:229-277` now `SettingsText.cs:30-75`; the field name for grouping is `useGrouping`.
- OS-13: was `OrganizationEndpoints.cs:92-107,279-281`, `Organization.cs:224-270` now `OrganizationSettingsUseCases.cs:49-61`, `SettingsText.cs:77-79`, `Organization.cs:229-275`.
- OS-14: was `OrganizationEndpoints.cs:109-121` now `OrganizationSettingsUseCases.cs:63-72`.
- OS-15: was `OrganizationEndpoints.cs:146-184` now `OrganizationSettingsUseCases.cs:95-131`; the write now runs in the unit of work.
- OS-16: `OrganizationRepository.cs:38-44` now `:36-45`.
- OS-17: was `OrganizationEndpoints.cs:124-144` now `OrganizationSettingsUseCases.cs:74-93`; formats carry both grouping names **(uncommitted, phase 6)**.
- OS-19: was `OrganizationRepository.cs:47-91` now `:48-92`; every writer goes through `SettingsChangeLog.Record`, the only writer of change-log rows and the only caller of `SettingsChanged()`.
- OS-20: `SetupRepository.cs:281-303`, `SetupEndpoints.cs:131-139` now `:291-313`, `:132-140`; `pettycash` rows follow the vehicle like `revenue`.
- OS-21: `SetupRepository.cs:371-394` now `:380-405`. OS-22: `327-367` now `338-378`. OS-23: `305-325` now `316-335`, `SetupContracts.cs:98-103` now `:102-105`.
- OS-26: was `SetupRepository.cs:464-473`, `RevenueRepository.cs:202-213`, `OrganizationRepository.cs:103-113`, `AccessUseCases.cs:574-585` now `:475-481`, `:241-248`, `:104-114`, `:575-587`; settings audit now written at `OrganizationSettingsUseCases.cs:133-149`.
- OS-27: was "`SettingsSectionRegistry` is registered but unused" now the type is deleted; the section list is `SettingsSections.All()`.

**2.4 setup**
- SU-C1 `CompanyUseCases.cs:17,25-26` now `:18,26-27`; SU-C2 `21-22` now `22-23`; SU-C3 `23-24,29-30` now `24-25,30-31`; SU-C4 `47-57` now `48-58` and `SetupRepository.cs:55-58` now `:56-59`; SU-C5 `SetupRepository.cs:27-41` now `:28-42`; SU-C6 `34,60` now `35,61` (one `using` line added to the use case file).
- SU-V1 `VehicleUseCases.cs:30,42-44` now `:31,43-45`; SU-V2 `31-36` now `32-37`; SU-V3 `37` now `38`; SU-V4 `40-41` now `41-42`; SU-V5 `45-50` now `46-51`; SU-V6 `53` now `54`; SU-V7 `76-86` now `77-87`; SU-V8 `93-109` now `94-110`; SU-V9 `SetupRepository.cs:14-16,133-136` now `:15-17,134-137`.
- Rows with the right content but no change in behaviour: SU-V6 also reads `FleetVehicle.TargetOn` as a single pass.

---

# Appendix A. Decision and contract tags

Tags found in code comments (current tree). Their source documents are not in the repository files read; the meaning is taken from the comment.

| Tag | Meaning (from the comment) | Where |
|---|---|---|
| D4 | Away periods: a vehicle that left and came back is out of the fleet for the stretch; recorded revenue never disappears; those days are neither expected nor missing | `FleetVehicle.cs:45,101`, `VehicleUseCases.cs:46,78`, `RevenueRepository.cs:191`, `SetupRepository.cs:275` |
| D5 | Authorization comes before state disclosure (a revenue conflict carries the saved record) | `RevenueUseCases.cs:61` |
| D11 | Change-log people entries need `people.view` as well as `audit.view` | `SetupRepository.cs:293` |
| D15 | The dashboard can be narrowed to one company like the week grid | `RevenueUseCases.cs:18` |
| D16 | A stop in effect is final; a later-dated stop is cancelled, never re-dated | `RecurringItem.cs:44,55` |
| D10 | not found in the current code (mentioned in earlier plans) | |
| C3 | Expense categories and items contract | `SetupEndpoints.cs:142` |
| C5 | Investment per vehicle contract; never money out | `SetupEndpoints.cs:164` |
| C6 | Vehicle report contract (money in, three buckets, savings) | `SetupContracts.cs:73`, `ISetupRepository.cs:26` |
| C7 | Reasons are optional on most saves; automatic text always, typed text follows | `SetupContracts.cs:42,111`, `RecurringUseCases.cs:81` |
| addendum 1 | New scheduled items follow the stricter rules (no daily, savings weekly or monthly, start no earlier than the first of the month); a non-owner assigns only roles whose complete default set they hold | `RecurringItem.cs:121`, `AccessUseCases.cs:497` |
| C1, C2, C4 | not found in the current code | |

---

# Appendix B. Files read and modification times

Times are local (+03:00), all 2026-10-07 unless the date is given. "unch." marks files the first reading and this one both saw unchanged.

| File | Modified |
|---|---|
| `Domain/Access.cs` | 18:44 |
| `Domain/Entities.cs` | 10-06 12:59 |
| `Domain/Organization.cs` | 20:53 |
| `Domain/PermissionKeys.cs` (untracked) | 18:27 |
| `Domain/PhoneNumber.cs` | 10-06 12:16 |
| `Domain/Revenue.cs`, `Domain/Setup/ExpenseCatalog.cs`, `PsvCompany.cs`, `RecurringItem.cs`, `RecurringSchedule.cs`, `SetupDataScope.cs`, `VehicleInvestment.cs` (unch.) | 10-05 09:20 |
| `Domain/Setup/FleetVehicle.cs` | 23:14 |
| `Domain/Setup/OrganizationSettingsVersion.cs` | 08:15 |
| `Application/AccessContracts.cs` | 18:46 |
| `Application/AccessUseCases.cs` | 18:55 |
| `Application/AuthContracts.cs` | 18:32 |
| `Application/ISetupExecution.cs` | 18:40 |
| `Application/OrganizationPort.cs` | 18:40 |
| `Application/PeopleVisibility.cs` (unch.) | 10-05 09:20 |
| `Application/RevenueContracts.cs` | 18:43 |
| `Application/RevenueUseCases.cs` | 23:00 |
| `Application/Settings/OrganizationSettingsUseCases.cs` (untracked) | 19:14 |
| `Application/Settings/SettingsChangeLog.cs` (untracked) | 18:42 |
| `Application/Settings/SettingsContracts.cs` (untracked) | 20:54 |
| `Application/Settings/SettingsSections.cs` (untracked) | 20:55 |
| `Application/Settings/SettingsText.cs` (untracked) | 20:54 |
| `Application/Setup/CompanyUseCases.cs`, `ExpenseCatalogUseCases.cs`, `InvestmentUseCases.cs`, `RecurringUseCases.cs`, `VehicleUseCases.cs` | 18:45 |
| `Application/Setup/ISetupRepository.cs` | 08:19 |
| `Application/Setup/SetupContracts.cs` | 14:52 |
| `Application/Setup/SetupPermissions.cs` (unch.) | 10-05 09:20 |
| `Infrastructure/OrganizationRepository.cs` | 18:40 |
| `Infrastructure/OrganizationModel.cs` | 10-06 13:01 |
| `Infrastructure/AuthDb.cs` | 14:48 |
| `Infrastructure/RevenueModel.cs` | 10-05 09:20 |
| `Infrastructure/RevenueRepository.cs` | 18:55 |
| `Infrastructure/RevenueDashboardCache.cs` (untracked) | 23:00 |
| `Infrastructure/Setup/HistoryCountCache.cs` (untracked) | 08:20 |
| `Infrastructure/Setup/SetupExecution.cs` | 18:41 |
| `Infrastructure/Setup/SetupModel.cs` | 08:16 |
| `Infrastructure/Setup/SetupRepository.cs` | 18:55 |
| `Api/OrganizationEndpoints.cs` | 18:44 |
| `Api/RevenueEndpoints.cs` | 13:37 |
| `Api/SetupEndpoints.cs` | 18:45 |
| `Program.cs` | 18:44 |
| `Infrastructure/Migrations/20261007181520_RenameUseGrouping.cs` (untracked) | 10-07 |
| Not read (other readers): `Domain/PettyCash.cs`, `Application/PettyCash*.cs`, `Infrastructure/PettyCash*.cs`, `Api/PettyCashEndpoints.cs`, `Application/Authentication/*` | |

---

# Appendix C. Database-enforced invariants

Taken from the EF model (`Infrastructure/OrganizationModel.cs`, `Setup/SetupModel.cs`, `RevenueModel.cs`, `AuthDb.cs`); the exact DDL is in `inventory-persistence.md`. They matter because the rewrite must enforce them in PostgreSQL, not only in application code.

| Invariant | Mechanism | Source |
|---|---|---|
| Every tenant row carries `OrganizationId`, its primary key starts with it, and every FK to a tenant row includes it, so a cross-organization reference is impossible | composite keys `(OrganizationId, Id)` and composite FKs, all `ON DELETE RESTRICT` | `OrganizationModel.cs:12-16`, `SetupModel.cs:14-109` |
| One organization slug | unique index on `Slug` | `OrganizationModel.cs:20` |
| One active membership per user | filtered unique index `IX_Memberships_UserId_Active` on `UserId` where `Active = 1` | `OrganizationModel.cs:31-34` |
| One role per person; role names unique per organization | unique `(OrganizationId, UserId)` on `PersonRole`; unique `(OrganizationId, Name)` on `Role` | `OrganizationModel.cs:58,70` |
| Concurrency tokens | `Organization.SettingsVersion`, `OrganizationMembership.Version`, `RevenueRecord.Version` (plus `User.Version`, `RefreshToken.Version`); changing the value is the caller's job (domain methods or `SettingsChangeLog.Record`) | `OrganizationModel.cs:23,28`, `RevenueModel.cs:16`, `AuthDb.cs:67-74` |
| Security policy bounds | check constraints `CK_SecurityPolicies_<column>` `BETWEEN min AND max` for every bound | `OrganizationModel.cs:40-44` |
| Company, expense category and expense item names unique ignoring case | unique `(OrganizationId, NormalizedName)`; items unique `(OrganizationId, CategoryId, NormalizedName)` | `SetupModel.cs:18,53,59` |
| Vehicle registration unique per organization | unique `(OrganizationId, Registration)` | `SetupModel.cs:23` |
| One target revision, one away period start, one schedule revision per parent | unique `(Org, Vehicle, Revision)`, `(Org, Vehicle, LeftOn)`, `(Org, Item, Revision)`, `(Org, Version, Vehicle)` for allocations | `SetupModel.cs:29,35,45,74` |
| One revenue record per vehicle and day | unique `(OrganizationId, VehicleId, BusinessDate)`; index `(OrganizationId, BusinessDate)` | `RevenueModel.cs:17-18` |
| Change-log version unique per organization; indexes for section/vehicle and time filters | unique `(OrganizationId, Version)`; indexes `(Org, Section, VehicleId)`, `(Org, OccurredAt)`; instants stored as UTC `datetime` | `SetupModel.cs:80-91` |
| Column sizes | `Slug` 100, `Name` 200, company name 160, category/item name 100, registration 8, version name 160, note 200 (recurring), revenue note 80, investment description 160, reason 500, section 160, correlation id 100, logo type 50, logo bytes 262144 | model files |
| Money precision | `decimal(14,2)` for targets, versions, allocations, investments, revenue amounts, approval limit | model files |
| Enumerations are foreign keys to seeded lookup tables | `RecurrenceFrequency`, `RecurringKind`, `ExpenseBucket` lookups seeded from the enums; FK from versions and categories | `SetupModel.cs:111-118` |
| Append-only and no-delete rows | enforced in the application at save time (`ValidateSetupWrites`, `ValidateWrites`), not by the database; a Python rewrite should add triggers or revoke `UPDATE`/`DELETE` | `SetupModel.cs:122-133`, `OrganizationModel.cs:87-114` |
