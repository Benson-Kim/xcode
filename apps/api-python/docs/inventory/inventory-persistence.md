# Persistence inventory of the current .NET API (apps/api, EF Core 10 on SQL Server)

Purpose: let a later agent design the PostgreSQL schema, stored procedures and Python data layer without reading the C# code.

Scope and conventions
- Source of truth for the schema: `apps/api/Infrastructure/Migrations/AuthDbModelSnapshot.cs` (working tree, 1640 lines) cross-checked with the Fluent configuration in `AuthDb.cs`, `OrganizationModel.cs`, `RevenueModel.cs`, `Setup/SetupModel.cs` and every non-Designer migration.
- All paths are relative to the repository root. `file:line` references are to the working tree as read on 2026-10-07 (branch `fix/format`).
- "(uncommitted)" marks facts that exist only in files that `git status` shows as modified or untracked at read time (another session is editing them): `Infrastructure/Setup/*`, `Infrastructure/RevenueRepository.cs`, `Infrastructure/Migrations/AuthDbModelSnapshot.cs`, `Infrastructure/Migrations/20261007052529_ChangeLogVehicle*.cs`, `Infrastructure/Setup/HistoryCountCache.cs`, `Domain/Setup/OrganizationSettingsVersion.cs`, `Application/ISetupExecution.cs`, `Application/Setup/ISetupRepository.cs`, `Application/Setup/SetupContracts.cs`, `Api/SetupEndpoints.cs`. The migration `ChangeLogVehicle.cs` was observed growing from 47 to 84 lines while this inventory was written, so treat its exact text as in flux.
- Updated 2026-10-08 after remediation phases 4 to 6 (new files `Application/Authentication/*`, `Application/Settings/*`, `Domain/PermissionKeys.cs`, `Infrastructure/AuthGate.cs`, `AuthUnitOfWork.cs`, `RevenueDashboardCache.cs`, `Setup/HistoryCountCache.cs`; migrations `ChangeLogVehicle`, `RenameUseGrouping`, `PettyCash`, `PettyCashDecimalUnits`; deleted `Application/AuthService.cs` and `Infrastructure/SettingsSectionRegistry.cs`). Statements below that the code no longer supports were corrected in place; every change is also listed in the last section `Drift log (phases 4 to 6)`, which wins over older text. Line citations of `Program.cs`, `Organization.cs`, `AuthDb.cs`, `OrganizationRepository.cs`, `OrganizationPort.cs` and the model snapshot were re-based mechanically; citations into the repositories and use cases edited since reading can still be a few lines off.
- C# namespace root is `Auth` (`Auth.Domain`, `Auth.Domain.Setup`, `Auth.Application`, `Auth.Infrastructure`, `Auth.Api`). The EF context class is `AuthDb`. Migration namespace is `Auth.Api.Infrastructure.Migrations`.
- Type mapping used below: `Guid -> uniqueidentifier`, `string -> nvarchar(n)` or `nvarchar(max)`, `bool -> bit`, `int -> int`, `long -> bigint`, `double -> float`, `decimal(14,2) -> decimal(14,2)`, `DateOnly -> date`, `DateTimeOffset -> datetimeoffset` (precision 7), `byte[] -> varbinary(max)`. Enums are stored as `int` (no string converter anywhere). No `HasDefaultValue`, no computed columns, no sequences, no `rowversion` columns, no owned types, no JSON-mapped (`ToJson`) columns anywhere in the model.
- Constraint and index names are EF defaults unless stated: `PK_<Table>`, `FK_<Table>_<PrincipalTable>_<Columns>`, `IX_<Table>_<Columns>`; explicit names are `IX_Memberships_UserId_Active` and `CK_SecurityPolicies_<Column>`.
- Every foreign key is `ON DELETE NO ACTION` (EF `DeleteBehavior.Restrict`) except the three Users children (`RefreshTokens`, `TrustedDevices`, `VerificationCodes`) which are `ON DELETE CASCADE`.

---

## 1. Schema catalogue

### 1.0 Table index (34 tables, plus EF's `__EFMigrationsHistory`; a 35th, `PettyCashEntries`, was added in phase 6, see the drift log)

Snapshot: `Infrastructure/Migrations/AuthDbModelSnapshot.cs:25-1289` (entity types), `:1291-1757` (relationships); the file is 1763 lines. 35 `ToTable(...)` calls now (grep count 35): the 34 below plus `PettyCashEntries` (phase 6, **uncommitted**, documented in `inventory-petty-cash.md`; its entity block is `:368-465`, so every snapshot citation in this section was shifted by +98 for tables after it). The per-table snapshot citations below were re-based on 2026-10-08.

| # | Table | C# entity (namespace) | Primary key | Tenant filter (see section 2) | Concurrency token | Write rule |
|---|---|---|---|---|---|---|
| 1 | `Users` | `User` (Auth.Domain) | `Id` | none (global) | `Version` bigint (bumped by `AuthDb.BumpVersions`) | updatable, never deleted by code |
| 2 | `VerificationCodes` | `VerificationCode` | `Id` | none | none | updatable (consume, fail counter) |
| 3 | `TrustedDevices` | `TrustedDevice` | `Id` | none | none | updatable (revoke/trust) |
| 4 | `RefreshTokens` | `RefreshToken` | `Id` | none | `Version` bigint (bumped by `AuthDb.BumpVersions`) | updatable (revoke) |
| 5 | `Organizations` | `Organization` | `Id` | `Id == CurrentOganizationId` | `SettingsVersion` bigint (bumped by `Organization.SettingsChanged()`, called only from `SettingsChangeLog.Record`) | updatable; Added/other-org writes rejected unless `Provisioning` |
| 6 | `Memberships` | `OrganizationMembership` | `(OrganizationId, UserId)` | tenant | `Version` bigint (domain methods) | updatable |
| 7 | `Localizations` | `OrganizationLocalization` | `OrganizationId` | tenant | none | updatable, validated on save |
| 8 | `Brandings` | `OrganizationBranding` | `OrganizationId` | tenant | none | updatable, validated on save |
| 9 | `Logos` | `OrganizationLogo` | `OrganizationId` | tenant | none | updatable |
| 10 | `SecurityPolicies` | `OrganizationSecurityPolicy` | `OrganizationId` | tenant | none | updatable, validated on save, 8 CHECKs |
| 11 | `UserPreferences` | `UserPreference` | `(OrganizationId, UserId)` | tenant | none | updatable, validated on save |
| 12 | `Roles` | `Role` | `(OrganizationId, Id)` | tenant | none | updatable |
| 13 | `RolePermissions` | `RolePermission` | `(OrganizationId, RoleId, Permission)` | tenant | none | legacy, nothing reads or writes it |
| 14 | `PersonRoles` | `PersonRole` | `(OrganizationId, UserId, RoleId)` | tenant | none | insert/delete |
| 15 | `PermissionOverrides` | `PersonPermissionOverride` | `(OrganizationId, UserId, Permission)` | tenant | none | insert/update/delete |
| 16 | `AuditEvents` | `AuditEvent` | `(OrganizationId, Id)` | tenant | none | append-only (code rejects Modified/Deleted) |
| 17 | `PsvCompany` | `PsvCompany` (Auth.Domain.Setup) | `(OrganizationId, Id)` | tenant | none | updatable, never deleted |
| 18 | `FleetVehicle` | `FleetVehicle` | `(OrganizationId, Id)` | tenant | none | updatable, never deleted, `Registration` immutable |
| 19 | `VehicleTarget` | `VehicleTarget` | `(OrganizationId, Id)` | tenant | none | append-only |
| 20 | `VehicleAwayPeriod` | `VehicleAwayPeriod` | `(OrganizationId, Id)` | tenant | none | append-only |
| 21 | `VehicleInvestment` | `VehicleInvestment` | `(OrganizationId, Id)` | tenant | none | insert/update/hard delete (the only setup table code deletes from) |
| 22 | `RecurringItem` | `RecurringItem` | `(OrganizationId, Id)` | tenant | none | updatable (`StoppedFrom`), never deleted |
| 23 | `RecurringVersion` | `RecurringVersion` | `(OrganizationId, Id)` | tenant | none | append-only |
| 24 | `RecurringAllocation` | `RecurringAllocation` | `(OrganizationId, Id)` | tenant | none | append-only |
| 25 | `ExpenseCategory` | `ExpenseCategory` | `(OrganizationId, Id)` | tenant | none | updatable, never deleted |
| 26 | `ExpenseItem` | `ExpenseItem` | `(OrganizationId, Id)` | tenant | none | updatable, never deleted |
| 27 | `SetupDataScopes` | `SetupDataScope` | `(OrganizationId, UserId)` | tenant | none | insert/update/delete |
| 28 | `SetupCompanyScopes` | `SetupCompanyScope` | `(OrganizationId, UserId, CompanyId)` | tenant | none | insert/delete |
| 29 | `SetupVehicleScopes` | `SetupVehicleScope` | `(OrganizationId, UserId, VehicleId)` | tenant | none | insert/delete |
| 30 | `OrganizationSettingsVersion` | `OrganizationSettingsVersion` | `(OrganizationId, Id)` | tenant | none (its `Version` is a unique counter, not a token) | append-only |
| 31 | `RevenueRecords` | `RevenueRecord` (Auth.Domain) | `(OrganizationId, Id)` | tenant | `Version` bigint (domain `Replace`) | updatable, never deleted |
| 32 | `RecurrenceFrequencyLookup` | `RecurrenceFrequencyLookup` | `Id` | none | none | seed data |
| 33 | `RecurringKindLookup` | `RecurringKindLookup` | `Id` | none | none | seed data |
| 34 | `ExpenseBucketLookup` | `ExpenseBucketLookup` | `Id` | none | none | seed data |

Filter counts: 27 tables have a global query filter (26 on `OrganizationId`, `Organizations` on `Id`); 7 have none (`Users`, `VerificationCodes`, `TrustedDevices`, `RefreshTokens` and the three lookups).

Table-name inconsistencies are listed in section 10 (singular `PsvCompany`, `FleetVehicle`, `VehicleTarget`, ... vs plural `Users`, `Memberships`, ...).

### 1.A Identity and sign-in tables (not tenant filtered)

#### 1.1 `Users` - `Auth.Domain.User` (`Domain/Entities.cs:6-50`)
- Snapshot `AuthDbModelSnapshot.cs:1169-1218`; config `AuthDb.cs:40-48`.
- PK `PK_Users (Id)`. `Id` is `ValueGeneratedOnAdd` in the snapshot but the class initialises `Id = Guid.NewGuid()` (client-generated GUID, no `NEWID()` or `NEWSEQUENTIALID()` default).
- Concurrency token: `Version` (`AuthDb.cs:48`), bumped by `AuthDb.BumpVersions()` (`AuthDb.cs:67-74`) on every `Modified` User/RefreshToken save.

| Column | CLR -> SQL Server | Null | Max length / precision | Default / converter / notes |
|---|---|---|---|---|
| `Id` | Guid -> uniqueidentifier | no | | client-generated |
| `Email` | string -> nvarchar(320) | no | 320 | unique; provisioning lower-cases (`UserProvisioning.cs:23`), SQL Server default collation is case-insensitive so uniqueness is effectively case-insensitive |
| `FailedAttempts` | int -> int | no | | pause counter, reset by `User.ClearLockout()` |
| `PausedUntil` | DateTimeOffset? -> datetimeoffset | yes | | |
| `PhoneNumber` | string -> nvarchar(13) | no | 13 | normalised E.164 `+254XXXXXXXXX` (`PhoneNumber.Normalize`, `Domain/PhoneNumber.cs:25-49`) or empty string for users created before phone sign-in. Migration `OrganizationsAndFleet` added it with `defaultValue: ""` (DB DEFAULT only on migrated databases) |
| `PinHash` | string? -> nvarchar(256) | yes | 256 | format `base64(salt).base64(PBKDF2-SHA256 hash)`, 210 000 iterations (`Security.cs:55-72`) |
| `SecurityVersion` | int -> int | no | | JWT claim `version`; bumped by `SetPin`, `Remove`, `BumpSecurityVersion` |
| `Status` | UserStatus enum -> int | no | | `Active = 0`, `Removed = 1` (`Entities.cs:3`) |
| `UntrustedFailedAttempts` | int -> int | no | | added by migration `UntrustedFailedAttempts` with `defaultValue: 0` |
| `Version` | long -> bigint | no | | concurrency token; migration default `0L`; CLR initial value 0 |

- Unique indexes: `IX_Users_Email (Email)`; `IX_Users_PhoneNumber (PhoneNumber)` filtered `WHERE [PhoneNumber] <> ''` (`AuthDb.cs:45`, snapshot `:1213-1215`; code comment: users provisioned before phone sign-in have no number yet).
- Non-unique indexes: none.
- Foreign keys: none (it is a principal for Memberships, RefreshTokens, TrustedDevices, VerificationCodes).
- Check constraints: none.

#### 1.2 `VerificationCodes` - `Auth.Domain.VerificationCode` (`Domain/Entities.cs:52-81`)
- Snapshot `:1251-1290`; config `AuthDb.cs:53-55, 61`.
- PK `PK_VerificationCodes (Id)` (client-generated Guid).

| Column | CLR -> SQL Server | Null | Max length | Notes |
|---|---|---|---|---|
| `Id` | Guid -> uniqueidentifier | no | | |
| `CodeHash` | string -> nvarchar(64) | no | 64 | HMAC-SHA256 hex (`TokenIssuer.Hash`, `Security.cs:76`) |
| `Consumed` | bool -> bit | no | | |
| `CreatedAt` | DateTimeOffset -> datetimeoffset | no | | |
| `DeviceId` | string -> nvarchar(128) | no | 128 | |
| `ExpiresAt` | DateTimeOffset -> datetimeoffset | no | | a withdrawn code has `Consumed = 1` and `ExpiresAt = CreatedAt` (`VerificationCode.Withdraw`, `Entities.cs:74-78`) |
| `FailedAttempts` | int -> int | no | | code is consumed at 5 failures (`Entities.cs:64-70`) |
| `Purpose` | CodePurpose enum -> int | no | | `FirstSetup = 0`, `NewDevice = 1`, `PinReset = 2` |
| `UserId` | Guid -> uniqueidentifier | no | | |

- Indexes: `IX_VerificationCodes_UserId_Purpose (UserId, Purpose)` non-unique.
- FK: `FK_VerificationCodes_Users_UserId (UserId) -> Users(Id) ON DELETE CASCADE`.
- No unique constraint: any number of codes per user and purpose can exist; "latest usable" is decided in `AuthCodes` (`Application/Authentication/AuthCodes.cs:43-55`; sections 5 and 6).

#### 1.3 `TrustedDevices` - `Auth.Domain.TrustedDevice` (`Domain/Entities.cs:83-100`)
- Snapshot `:1141-1167`; config `AuthDb.cs:50-51, 60`.
- PK `PK_TrustedDevices (Id)`.

| Column | CLR -> SQL Server | Null | Max length | Notes |
|---|---|---|---|---|
| `Id` | Guid -> uniqueidentifier | no | | |
| `DeviceId` | string -> nvarchar(128) | no | 128 | client-supplied device identifier |
| `Revoked` | bool -> bit | no | | |
| `TrustExpiresAt` | DateTimeOffset? -> datetimeoffset | yes | | null means trust never expires (`AuthOptions.TrustLifetimeDays` null) |
| `UserId` | Guid -> uniqueidentifier | no | | |

- Unique index: `IX_TrustedDevices_UserId_DeviceId (UserId, DeviceId)` (one trust record per user per device).
- FK: `FK_TrustedDevices_Users_UserId (UserId) -> Users(Id) ON DELETE CASCADE`.

#### 1.4 `RefreshTokens` - `Auth.Domain.RefreshToken` (`Domain/Entities.cs:102-113`)
- Snapshot `:466-503`; config `AuthDb.cs:57-60, 62`.
- PK `PK_RefreshTokens (Id)`. Concurrency token `Version` bumped by `AuthDb.BumpVersions()`.

| Column | CLR -> SQL Server | Null | Max length | Notes |
|---|---|---|---|---|
| `Id` | Guid -> uniqueidentifier | no | | |
| `DeviceId` | string -> nvarchar(128) | no | 128 | |
| `ExpiresAt` | DateTimeOffset -> datetimeoffset | no | | |
| `Revoked` | bool -> bit | no | | |
| `TokenHash` | string -> nvarchar(64) | no | 64 | HMAC-SHA256 hex of the opaque token; unique |
| `UserId` | Guid -> uniqueidentifier | no | | |
| `Version` | long -> bigint | no | | concurrency token; migration default `0L` |

- Unique index: `IX_RefreshTokens_TokenHash (TokenHash)`. Non-unique: `IX_RefreshTokens_UserId (UserId)`.
- FK: `FK_RefreshTokens_Users_UserId (UserId) -> Users(Id) ON DELETE CASCADE`.

### 1.B Organization, access and audit tables

#### 1.5 `Organizations` - `Auth.Domain.Organization` (`Domain/Organization.cs:83-116`)
- Snapshot `:69-98`; config `OrganizationModel.cs:20-24`.
- PK `PK_Organizations (Id)`; global query filter `x.Id == CurrentOganizationId` (`OrganizationModel.cs:24`).
- Concurrency token: `SettingsVersion` (`OrganizationModel.cs:23`), bumped by `Organization.SettingsChanged()` (`Organization.cs:91`), which production code calls from exactly one place, `SettingsChangeLog.Record` (`Application/Settings/SettingsChangeLog.cs:15`). It is also the monotonic counter of the change log (section 4).

| Column | CLR -> SQL Server | Null | Max length | Notes |
|---|---|---|---|---|
| `Id` | Guid -> uniqueidentifier | no | | `ValueGeneratedOnAdd` in snapshot; class initialiser `Guid.NewGuid()` |
| `BusinessDate` | DateOnly? -> date | yes | | null means follow the organization time zone; a value is an explicit audited accounting date (`Organization.cs:88`) |
| `Name` | string -> nvarchar(200) | no | 200 | |
| `SettingsVersion` | long -> bigint | no | | concurrency token; CLR initial value 1 (`Organization.cs:90`) |
| `Slug` | string -> nvarchar(100) | no | 100 | |

- Unique index: `IX_Organizations_Slug (Slug)`. No FKs. No CHECKs.
- Provisioning creates `Slug = my-fleet` (`UserProvisioning.cs:92`) or `demo-fleet` (`DemoSeed.cs:36`); `UserProvisioning.EnsureOrganization` refuses a second organization (`:89`), so production data is single-organization today even though every table is tenant keyed.

#### 1.6 `Memberships` - `Auth.Domain.OrganizationMembership` (`Domain/Organization.cs:119-144`)
- Snapshot `:232-268`; config `OrganizationModel.cs:26-34`.
- PK `PK_Memberships (OrganizationId, UserId)`; tenant filter. Concurrency token `Version` (`OrganizationModel.cs:28`), bumped inside domain methods `Deactivate()`, `Reactivate()` (only when the state changes) and `AccessChanged()` (`Organization.cs:128-143`); CLR initial value 1.

| Column | CLR -> SQL Server | Null | Max length / precision | Notes |
|---|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | | |
| `UserId` | Guid -> uniqueidentifier | no | | |
| `Active` | bool -> bit | no | | private setter; default true in the CLR |
| `ApprovalLimit` | decimal? -> decimal(14,2) | yes | precision 14, scale 2 | |
| `FirstName` | string -> nvarchar(max) | no | unbounded | |
| `LastName` | string -> nvarchar(max) | no | unbounded | |
| `Version` | long -> bigint | no | | concurrency token |

- Indexes: `IX_Memberships_UserId (UserId)` (FK support); `IX_Memberships_UserId_Active (UserId)` UNIQUE filtered `WHERE [Active] = 1` (`OrganizationModel.cs:34`, created by migration `AccessIntegrity`): at most one active membership per person across all organizations. The code comment says sign-in and token issue assume one active membership per person.
- FKs: `FK_Memberships_Organizations_OrganizationId (OrganizationId) -> Organizations(Id) NO ACTION`; `FK_Memberships_Users_UserId (UserId) -> Users(Id) NO ACTION`.

#### 1.7 `Localizations` - `Auth.Domain.OrganizationLocalization` (`Domain/Organization.cs:147-184`)
- Snapshot `:155-207`; config `OrganizationModel.cs:36`. PK `PK_Localizations (OrganizationId)` (one row per organization); tenant filter; FK `FK_Localizations_Organizations_OrganizationId -> Organizations(Id) NO ACTION`.
- All string columns are `nvarchar(max)` with no database length. The domain `Validate()` (`Organization.cs:163-169`, run by `AuthDb.ValidateWrites`) holds the rules: `Locale` matches `^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$`, `TimeZone` is a known system time zone id, `DatePattern` is one of short, medium, long; `FirstDayOfWeek` 0..6; `WeekNumbering` is iso8601 or local; `Currency` matches `^[A-Z]{3}$`; `NumberDecimals` 0..2.

| Column | CLR -> SQL Server | Null | CLR default (domain) |
|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | |
| `AllowHour12Override` | bool -> bit | no | true |
| `AllowLocaleOverride` | bool -> bit | no | true |
| `AllowThemeOverride` | bool -> bit | no | true |
| `AllowTimeZoneOverride` | bool -> bit | no | false |
| `Currency` | string -> nvarchar(max) | no | KES |
| `DatePattern` | string -> nvarchar(max) | no | medium |
| `FirstDayOfWeek` | int -> int | no | 1 (0 = Sunday; used with .NET `DayOfWeek` arithmetic in `RevenueRepository.StartOfWeek`) |
| `Hour12` | bool -> bit | no | false |
| `Locale` | string -> nvarchar(max) | no | en-GB |
| `NumberDecimals` | int -> int | no | 2 |
| `TimeZone` | string -> nvarchar(max) | no | Africa/Nairobi (IANA id, resolved with `TimeZoneInfo.FindSystemTimeZoneById`) |
| `UseGrouping` | bool -> bit | no | true. Renamed from `UseGroupping` by migration `20261007181520_RenameUseGrouping` (RenameColumn only, data kept; `Down` renames back; on SQL Server `EXEC sp_rename N'[Localizations].[UseGroupping]', N'UseGrouping', 'COLUMN'`, test `MigrationSnapshotTests.cs:24-41`) **(uncommitted)**; property `Organization.cs:157`, snapshot `:197` |
| `WeekNumbering` | string -> nvarchar(max) | no | iso8601 |

- No indexes beyond the PK, no CHECKs.

#### 1.8 `Brandings` - `Auth.Domain.OrganizationBranding` (`Domain/Organization.cs:188-223`)
- Snapshot `:100-153`; config `OrganizationModel.cs:37`. PK `PK_Brandings (OrganizationId)`; tenant filter; FK `FK_Brandings_Organizations_OrganizationId -> Organizations(Id) NO ACTION`.
- All columns `nvarchar(max)` (no database length). Domain `Validate()` (`Organization.cs:205-222`): `DisplayName` 1..100, `LegalName` 1..200, `LogoAlt` 1..200, three colours `^#[0-9a-fA-F]{6}$` and WCAG AA 4.5:1 against `#FFFFFF` and `#F6F3EC`, URLs (`LogoLight`, `LogoDark`, `Favicon`, `TermsUrl`, `PrivacyUrl`) absolute `https` and at most 2048 chars, `Domain` a DNS host name of at most 253 chars, `SupportEmail` a valid address of at most 320 chars.

| Column | CLR -> SQL Server | Null | CLR default |
|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | |
| `Accent` | string -> nvarchar(max) | no | #1E6B3A |
| `DisplayName` | string -> nvarchar(max) | no | XCODE |
| `Domain` | string? -> nvarchar(max) | yes | null |
| `Favicon` | string? -> nvarchar(max) | yes | null |
| `LegalName` | string -> nvarchar(max) | no | XCODE |
| `LogoAlt` | string -> nvarchar(max) | no | XCODE |
| `LogoDark` | string? -> nvarchar(max) | yes | null |
| `LogoLight` | string? -> nvarchar(max) | yes | null |
| `Primary` | string -> nvarchar(max) | no | #1D5FD6 (column name is the SQL keyword PRIMARY; must be quoted in PostgreSQL) |
| `PrivacyUrl` | string? -> nvarchar(max) | yes | null |
| `Secondary` | string -> nvarchar(max) | no | #14213D |
| `SupportEmail` | string? -> nvarchar(max) | yes | null |
| `TermsUrl` | string? -> nvarchar(max) | yes | null |

#### 1.9 `Logos` - `Auth.Domain.OrganizationLogo` (`Domain/Organization.cs:227-278`)
- Snapshot `:209-230`; config `OrganizationModel.cs:46-49`; created by migration `OrganizationLogo`. PK `PK_Logos (OrganizationId)`; tenant filter; FK `FK_Logos_Organizations_OrganizationId -> Organizations(Id) NO ACTION`.

| Column | CLR -> SQL Server | Null | Max length | Notes |
|---|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | | |
| `ContentType` | string -> nvarchar(50) | no | 50 | one of image/png, image/jpeg, image/webp |
| `Data` | byte[] -> varbinary(max) | no | EF `HasMaxLength(262144)` (= `OrganizationLogo.MaxBytes`, 256 KiB) | the model length is metadata: the column is `varbinary(max)`; the 256 KiB cap and the magic-byte check are enforced only in `OrganizationLogo.FromDataUrl` (`Organization.cs:245-275`) |
| `UpdatedAt` | DateTimeOffset -> datetimeoffset | no | | |

#### 1.10 `SecurityPolicies` - `Auth.Domain.OrganizationSecurityPolicy` (`Domain/Organization.cs:280-300`)
- Snapshot `:270-325`; config `OrganizationModel.cs:38-44`. PK `PK_SecurityPolicies (OrganizationId)`; tenant filter; FK `FK_SecurityPolicies_Organizations_OrganizationId -> Organizations(Id) NO ACTION`.

| Column | CLR -> SQL Server | Null | CLR default | CHECK (name: expression) |
|---|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | | |
| `AccessTokenMinutes` | int -> int | no | 10 | `CK_SecurityPolicies_AccessTokenMinutes`: `[AccessTokenMinutes] BETWEEN 1 AND 15` |
| `AllowPinSignIn` | bool -> bit | no | true | none (domain refuses false: PIN sign-in cannot be disabled) |
| `IdleUnlockSeconds` | int -> int | no | 300 | `CK_SecurityPolicies_IdleUnlockSeconds`: `[IdleUnlockSeconds] BETWEEN 30 AND 3600` |
| `LockoutMinutes` | int -> int | no | 15 | `CK_SecurityPolicies_LockoutMinutes`: `[LockoutMinutes] BETWEEN 1 AND 60` |
| `LockoutThreshold` | int -> int | no | 5 | `CK_SecurityPolicies_LockoutThreshold`: `[LockoutThreshold] BETWEEN 3 AND 10` |
| `PasswordComplexity` | bool -> bit | no | true | none |
| `PasswordHistory` | int -> int | no | 5 | `CK_SecurityPolicies_PasswordHistory`: `[PasswordHistory] BETWEEN 0 AND 24` |
| `PasswordMinLength` | int -> int | no | 12 | `CK_SecurityPolicies_PasswordMinLength`: `[PasswordMinLength] BETWEEN 12 AND 128` |
| `PinLength` | int -> int | no | 4 | `CK_SecurityPolicies_PinLength`: `[PinLength] BETWEEN 4 AND 8` |
| `RefreshTokenDays` | int -> int | no | 30 | `CK_SecurityPolicies_RefreshTokenDays`: `[RefreshTokenDays] BETWEEN 1 AND 90` |

- The 8 CHECK constraints are generated from `SecurityPolicyBounds.All` (`Security.cs:34-35`) at model-build time (`OrganizationModel.cs:40-44`); they were added by migration `NormalizeSecurityPolicy` (section 7) after clamping existing rows. On read the policy is clamped again in code (`SecurityPolicyBounds.Clamp`, used by `OrganizationRepository.Settings`).

#### 1.11 `UserPreferences` - `Auth.Domain.UserPreference` (`Domain/Organization.cs:302-329`)
- Snapshot `:1220-1249`; config `OrganizationModel.cs:51-53`. PK `PK_UserPreferences (OrganizationId, UserId)`; tenant filter.
- FKs: `FK_UserPreferences_Organizations_OrganizationId (OrganizationId) -> Organizations(Id)`; `FK_UserPreferences_Memberships_OrganizationId_UserId (OrganizationId, UserId) -> Memberships(OrganizationId, UserId)`; both NO ACTION.

| Column | CLR -> SQL Server | Null | Notes |
|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | |
| `UserId` | Guid -> uniqueidentifier | no | |
| `FontScale` | double -> float | no | CLR default 1; domain range 1..3 and finite |
| `Hour12` | bool? -> bit | yes | |
| `Locale` | string? -> nvarchar(max) | yes | BCP 47 pattern, validated in code |
| `ReducedMotion` | bool -> bit | no | |
| `ThemeMode` | string? -> nvarchar(max) | yes | null, light, dark or system |
| `TimeZone` | string? -> nvarchar(max) | yes | known time zone id, validated in code |

- Override rules (`OrganizationLocalization.EnsureAllowed`, `Organization.cs:173-183`) are enforced when the preference is written by the use case, not by the database.

#### 1.12 `Roles` - `Auth.Domain.Role` (`Domain/Access.cs:3-8`)
- Snapshot `:559-578`; config `OrganizationModel.cs:55-58`. PK `PK_Roles (OrganizationId, Id)`; tenant filter; FK `FK_Roles_Organizations_OrganizationId -> Organizations(Id)`.

| Column | CLR -> SQL Server | Null | Max length |
|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | |
| `Id` | Guid -> uniqueidentifier | no | |
| `Name` | string -> nvarchar(100) | no | 100 |

- Unique index `IX_Roles_OrganizationId_Name (OrganizationId, Name)`. Rows are created lazily by `UserProvisioning.EnsureRoles` (`UserProvisioning.cs:102-112`) for every key of `PermissionCatalog.RolePermissions` (`Application/AccessContracts.cs:98-119`): `Owner`, `Office admin`, `Fleet manager`, `Revenue clerk` (name comparison is case-insensitive in code; SQL Server default collation is also case-insensitive).

#### 1.13 `RolePermissions` - `Auth.Domain.RolePermission` (`Domain/Access.cs:13-18`) - LEGACY, DO NOT PORT
- Snapshot `:580-595`; config `OrganizationModel.cs:60-63`. PK `PK_RolePermissions (OrganizationId, RoleId, Permission)`; tenant filter.
- Columns: `OrganizationId` uniqueidentifier, `RoleId` uniqueidentifier, `Permission` nvarchar(100) (all not null).
- FKs: `FK_RolePermissions_Organizations_OrganizationId -> Organizations(Id)`; `FK_RolePermissions_Roles_OrganizationId_RoleId (OrganizationId, RoleId) -> Roles(OrganizationId, Id)`; NO ACTION.
- Code comments say nothing reads or writes this table (`Access.cs:11-12`, `OrganizationRepository.cs:23`, `UserProvisioning.cs:100-101`): role defaults come only from the in-code `PermissionCatalog`. Candidate to drop in the PostgreSQL schema; any existing rows are ignored.

#### 1.14 `PersonRoles` - `Auth.Domain.PersonRole` (`Domain/Access.cs:21-26`)
- Snapshot `:347-366`; config `OrganizationModel.cs:65-70`. PK `PK_PersonRoles (OrganizationId, UserId, RoleId)`; tenant filter.

| Column | CLR -> SQL Server | Null |
|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no |
| `UserId` | Guid -> uniqueidentifier | no |
| `RoleId` | Guid -> uniqueidentifier | no |

- Indexes: `IX_PersonRoles_OrganizationId_RoleId (OrganizationId, RoleId)` (FK support); UNIQUE `IX_PersonRoles_OrganizationId_UserId (OrganizationId, UserId)` (migration `AccessIntegrity`): one role per person per organization, so the 3-column PK is wider than the real identity.
- FKs: `FK_PersonRoles_Organizations_OrganizationId -> Organizations(Id)`; `FK_PersonRoles_Roles_OrganizationId_RoleId (OrganizationId, RoleId) -> Roles(OrganizationId, Id)`; `FK_PersonRoles_Memberships_OrganizationId_UserId (OrganizationId, UserId) -> Memberships(OrganizationId, UserId)`; all NO ACTION.

#### 1.15 `PermissionOverrides` - `Auth.Domain.PersonPermissionOverride` (`Domain/Access.cs:29-35`)
- Snapshot `:327-345`; config `OrganizationModel.cs:72-75`. PK `PK_PermissionOverrides (OrganizationId, UserId, Permission)`; tenant filter.

| Column | CLR -> SQL Server | Null | Max length | Notes |
|---|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | | |
| `UserId` | Guid -> uniqueidentifier | no | | |
| `Permission` | string -> nvarchar(100) | no (PK) | 100 | key from `PermissionCatalog` (for example `revenue.capture`) |
| `Granted` | bool -> bit | no | | true grants on top of the role, false denies (a denied permission also removes dependents, `EffectivePermissionResolver`, `Access.cs:107-131`) |

- FKs: `FK_PermissionOverrides_Organizations_OrganizationId -> Organizations(Id)`; `FK_PermissionOverrides_Memberships_OrganizationId_UserId -> Memberships(OrganizationId, UserId)`; NO ACTION. No extra indexes.

#### 1.16 `AuditEvents` - `Auth.Domain.AuditEvent` (`Domain/Access.cs:38-49`)
- Snapshot `:25-67`; config `OrganizationModel.cs:77-83`; created in migration `OrganizationsAndFleet`. PK `PK_AuditEvents (OrganizationId, Id)`; tenant filter. Append-only: `AuthDb.ValidateWrites` throws `Audit events are append-only` for any entry that is not `Added` (`OrganizationModel.cs:92-93`).

| Column | CLR -> SQL Server | Null | Max length | Notes |
|---|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | | |
| `Id` | Guid -> uniqueidentifier | no | | client-generated |
| `Action` | string -> nvarchar(100) | no | 100 | for example `revenue.recorded`, `setup.<section>` (`UnitOfWork.Audit`) |
| `ActorId` | Guid -> uniqueidentifier | no | | |
| `After` | string? -> nvarchar(max) | yes | | JSON text produced by `System.Text.Json` (`UnitOfWork.Audit`, `OrganizationRepository.cs:104-114`); no ISJSON constraint |
| `Before` | string? -> nvarchar(max) | yes | | same |
| `CorrelationId` | string -> nvarchar(100) | no | 100 | `HttpContext.TraceIdentifier` |
| `Entity` | string -> nvarchar(200) | no | 200 | entity id as text for revenue (`entityId.ToString()`), see section 5 |
| `OccuredAt` | DateTimeOffset -> datetimeoffset | no | | column name misspelt (Occured); must be UTC (offset 0) |

- Indexes: `IX_AuditEvents_OrganizationId_ActorId (OrganizationId, ActorId)` (FK support); `IX_AuditEvents_OrganizationId_OccuredAt (OrganizationId, OccuredAt)`.
- FKs: `FK_AuditEvents_Organizations_OrganizationId -> Organizations(Id)`; `FK_AuditEvents_Memberships_OrganizationId_ActorId (OrganizationId, ActorId) -> Memberships(OrganizationId, UserId)`; NO ACTION.

### 1.C Setup and fleet tables (all tenant filtered; config in `Infrastructure/Setup/SetupModel.cs`)

#### 1.17 `PsvCompany` - `Auth.Domain.Setup.PsvCompany` (`Domain/Setup/PsvCompany.cs:3-54`)
- Snapshot `:789-816`; config `SetupModel.cs:14-18`. PK `PK_PsvCompany (OrganizationId, Id)`; tenant filter; FK `FK_PsvCompany_Organizations_OrganizationId -> Organizations(Id)`. Never deleted (`ValidateSetupWrites`, `SetupModel.cs:128-129`).

| Column | CLR -> SQL Server | Null | Max length | Notes |
|---|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | | |
| `Id` | Guid -> uniqueidentifier | no | | |
| `ArchivedOn` | DateOnly? -> date | yes | | company is active on date d when `ArchivedOn is null or ArchivedOn > d` |
| `Name` | string -> nvarchar(160) | no | 160 | trimmed, 1..160 (`SetupValue.Name`, `PsvCompany.cs:58-66`) |
| `NormalizedName` | string -> nvarchar(160) | no | 160 | `Name.ToUpperInvariant()` |

- Unique index `IX_PsvCompany_OrganizationId_NormalizedName (OrganizationId, NormalizedName)`.

#### 1.18 `FleetVehicle` - `Auth.Domain.Setup.FleetVehicle` (`Domain/Setup/FleetVehicle.cs:16-119`)
- Snapshot `:694-724`; config `SetupModel.cs:20-24`. PK `PK_FleetVehicle (OrganizationId, Id)`; tenant filter. Never deleted; `Registration` is immutable (`SetupModel.cs:130-131`, throws `Registration cannot change.`).

| Column | CLR -> SQL Server | Null | Max length | Notes |
|---|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | | |
| `Id` | Guid -> uniqueidentifier | no | | |
| `CompanyId` | Guid -> uniqueidentifier | no | | FK to `PsvCompany` |
| `JoinedOn` | DateOnly -> date | no | | |
| `LeftOn` | DateOnly? -> date | yes | | retired when set; active on d when `d >= JoinedOn and (LeftOn is null or d < LeftOn)` and not inside an away period |
| `Registration` | string -> nvarchar(8) | no | 8 | canonical form `KDA 482M` (regex `^K[A-Z]{2}[0-9]{3}[A-Z]$` after removing spaces, re-spaced after the 3rd character, `VehicleRegistration`, `FleetVehicle.cs:4-14`) |

- Indexes: `IX_FleetVehicle_OrganizationId_CompanyId (OrganizationId, CompanyId)` (FK support); UNIQUE `IX_FleetVehicle_OrganizationId_Registration (OrganizationId, Registration)`.
- FKs: `FK_FleetVehicle_Organizations_OrganizationId -> Organizations(Id)`; `FK_FleetVehicle_PsvCompany_OrganizationId_CompanyId (OrganizationId, CompanyId) -> PsvCompany(OrganizationId, Id)`; NO ACTION.
- Navigations: `Targets` (VehicleTarget) and `AwayPeriods` (VehicleAwayPeriod) are one-to-many navigation collections (ordinary entities with their own tables, not EF owned types), loaded with `Include`.

#### 1.19 `VehicleTarget` - `Auth.Domain.Setup.VehicleTarget` (`FleetVehicle.cs:121-137`)
- Snapshot `:1112-1139`; config `SetupModel.cs:26-30`. PK `PK_VehicleTarget (OrganizationId, Id)`; tenant filter. Append-only (`ValidateSetupWrites` throws `Setup versions and allocations are append-only.` on Modified/Deleted).

| Column | CLR -> SQL Server | Null | Precision | Notes |
|---|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | | |
| `Id` | Guid -> uniqueidentifier | no | | |
| `EffectiveFrom` | DateOnly -> date | no | | |
| `Revision` | int -> int | no | | 1-based per vehicle; first target is revision 1 at the join date |
| `VehicleId` | Guid -> uniqueidentifier | no | | |
| `WeeklyAmount` | decimal -> decimal(14,2) | no | 14,2 | domain: > 0, at most 999 999 999 999.99, two decimals (`SetupValue.Money`) |

- Unique index `IX_VehicleTarget_OrganizationId_VehicleId_Revision (OrganizationId, VehicleId, Revision)` (also serves the FK).
- FKs: `FK_VehicleTarget_Organizations_OrganizationId`; `FK_VehicleTarget_FleetVehicle_OrganizationId_VehicleId (OrganizationId, VehicleId) -> FleetVehicle(OrganizationId, Id)`; NO ACTION.
- Effective target on date d = row with greatest `EffectiveFrom <= d`, ties by greatest `Revision` (`FleetVehicle.TargetOn`, `FleetVehicle.cs:113-118`), and 0 when the vehicle is not active on d.

#### 1.20 `VehicleAwayPeriod` - `Auth.Domain.Setup.VehicleAwayPeriod` (`FleetVehicle.cs:139-157`)
- Snapshot `:1049-1072`; config `SetupModel.cs:32-36`; created by migration `VehicleAwayPeriods`. PK `PK_VehicleAwayPeriod (OrganizationId, Id)`; tenant filter; append-only.

| Column | CLR -> SQL Server | Null | Notes |
|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | |
| `Id` | Guid -> uniqueidentifier | no | |
| `LeftOn` | DateOnly -> date | no | away from this day |
| `ReturnedOn` | DateOnly -> date | no | back in the fleet on this day; the period covers `LeftOn <= d < ReturnedOn` |
| `VehicleId` | Guid -> uniqueidentifier | no | |

- Unique index `IX_VehicleAwayPeriod_OrganizationId_VehicleId_LeftOn (OrganizationId, VehicleId, LeftOn)`. No CHECK that `ReturnedOn > LeftOn` or that periods do not overlap (domain only writes `returnedOn > left`, and `Retire` requires a leave date on or after the last return).
- FKs: `FK_VehicleAwayPeriod_Organizations_OrganizationId`; `FK_VehicleAwayPeriod_FleetVehicle_OrganizationId_VehicleId -> FleetVehicle(OrganizationId, Id)`; NO ACTION.

#### 1.21 `VehicleInvestment` - `Auth.Domain.Setup.VehicleInvestment` (`Domain/Setup/VehicleInvestment.cs`)
- Snapshot `:1074-1110`; config `SetupModel.cs:63-69`; created by migration `ExpenseCatalogAndInvestment`. PK `PK_VehicleInvestment (OrganizationId, Id)`; tenant filter. Mutable (`Change`) and hard-deleted by `ISetupRepository.Remove(VehicleInvestment)` (`SetupRepository.cs:462`); not covered by the append-only or no-delete guards.

| Column | CLR -> SQL Server | Null | Max length / precision | Notes |
|---|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | | |
| `Id` | Guid -> uniqueidentifier | no | | |
| `Amount` | decimal -> decimal(14,2) | no | 14,2 | positive money |
| `Date` | DateOnly -> date | no | | not after the business date |
| `Description` | string -> nvarchar(160) | no | 160 | `VehicleInvestment.DescriptionLength` |
| `RecordedAt` | DateTimeOffset -> datetimeoffset | no | | |
| `RecordedBy` | Guid -> uniqueidentifier | no | | FK to Memberships (not Users) |
| `VehicleId` | Guid -> uniqueidentifier | no | | |

- Indexes: `IX_VehicleInvestment_OrganizationId_RecordedBy (OrganizationId, RecordedBy)` (FK support); `IX_VehicleInvestment_OrganizationId_VehicleId_Date (OrganizationId, VehicleId, Date)`.
- FKs: `FK_VehicleInvestment_Organizations_OrganizationId`; `FK_VehicleInvestment_FleetVehicle_OrganizationId_VehicleId -> FleetVehicle(OrganizationId, Id)`; `FK_VehicleInvestment_Memberships_OrganizationId_RecordedBy (OrganizationId, RecordedBy) -> Memberships(OrganizationId, UserId)`; NO ACTION.

#### 1.22 `RecurringItem` - `Auth.Domain.Setup.RecurringItem` (`Domain/Setup/RecurringItem.cs:5-90`)
- Snapshot `:882-896`; config `SetupModel.cs:38-39`. PK `PK_RecurringItem (OrganizationId, Id)`; tenant filter; FK `FK_RecurringItem_Organizations_OrganizationId -> Organizations(Id)`. Never deleted. The item is only an identity plus a stop date; all content lives in append-only `RecurringVersion` rows.

| Column | CLR -> SQL Server | Null | Notes |
|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | |
| `Id` | Guid -> uniqueidentifier | no | |
| `StoppedFrom` | DateOnly? -> date | yes | no due date on or after this date posts (`DueOn`: `date >= StoppedFrom` gives none); a date after the business date is a pending stop that can be cancelled |

#### 1.23 `RecurringVersion` - `Auth.Domain.Setup.RecurringVersion` (`RecurringItem.cs:140-182`)
- Snapshot `:924-995`; config `SetupModel.cs:41-47, 61, 115-117`. PK `PK_RecurringVersion (OrganizationId, Id)`; tenant filter; append-only. One row per revision of an item; the highest `Revision` is the current version.

| Column | CLR -> SQL Server | Null | Max length / precision | Converter / notes |
|---|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | | |
| `Id` | Guid -> uniqueidentifier | no | | |
| `Amount` | decimal -> decimal(14,2) | no | 14,2 | total of all vehicle shares; must equal the sum of allocations exactly |
| `Bucket` | ExpenseBucket? enum -> int | yes | | FK to `ExpenseBucketLookup`; 1 RepairsAndMaintenance, 2 RecurringCharges, 3 LoanRepayments; cost versions carry a bucket, savings carry none (null) |
| `Day` | int? -> int | yes | | weekly: weekday 0..6 (0 = Sunday); monthly/yearly: day of month 1..28; null with `LastDay` |
| `EffectiveFrom` | DateOnly -> date | no | | the version is in charge from this date until a higher revision takes effect |
| `End` | DateOnly? -> date | yes | | inclusive last due date |
| `ExpenseItemId` | Guid? -> uniqueidentifier | yes | | FK to `ExpenseItem`; required for new costs (`ValidateNew`), null for savings and for legacy cost rows |
| `Frequency` | RecurrenceFrequency enum -> int | no | | FK to `RecurrenceFrequencyLookup`; 1 Daily (legacy), 2 Weekly, 3 Monthly, 4 Yearly |
| `ItemId` | Guid -> uniqueidentifier | no | | FK to `RecurringItem` |
| `Kind` | RecurringKind enum -> int | no | | FK to `RecurringKindLookup`; 1 Cost, 2 Savings |
| `LastDay` | bool -> bit | no | | due on the last day of the month (then `Day` is null) |
| `Month` | int? -> int | yes | | yearly only, 1..12 |
| `Name` | string -> nvarchar(160) | no | 160 | |
| `Note` | string? -> nvarchar(200) | yes | 200 | `RecurringDefinition.NoteLength` |
| `Revision` | int -> int | no | | 1-based per item |
| `Start` | DateOnly -> date | no | | first date a due date may fall on |

- Indexes: `IX_RecurringVersion_Bucket (Bucket)`, `IX_RecurringVersion_Frequency (Frequency)`, `IX_RecurringVersion_Kind (Kind)` (FK support on the lookups); `IX_RecurringVersion_OrganizationId_ExpenseItemId (OrganizationId, ExpenseItemId)`; UNIQUE `IX_RecurringVersion_OrganizationId_ItemId_Revision (OrganizationId, ItemId, Revision)`.
- FKs: `FK_RecurringVersion_Organizations_OrganizationId`; `FK_RecurringVersion_RecurringItem_OrganizationId_ItemId (OrganizationId, ItemId) -> RecurringItem(OrganizationId, Id)`; `FK_RecurringVersion_ExpenseItem_OrganizationId_ExpenseItemId (OrganizationId, ExpenseItemId) -> ExpenseItem(OrganizationId, Id)` (optional); `FK_RecurringVersion_RecurrenceFrequencyLookup_Frequency (Frequency) -> RecurrenceFrequencyLookup(Id)`; `FK_RecurringVersion_RecurringKindLookup_Kind (Kind) -> RecurringKindLookup(Id)`; `FK_RecurringVersion_ExpenseBucketLookup_Bucket (Bucket) -> ExpenseBucketLookup(Id)` (optional); all NO ACTION.
- Note the composite FK to `ExpenseItem` is nullable on one column and not on the other (`OrganizationId` not null, `ExpenseItemId` null): SQL Server and PostgreSQL both skip the check when any column is null (MATCH SIMPLE).
- Removed by migration `RetireOldCostCategories`: column `Category` (int, null), index `IX_RecurringVersion_Category`, FK `FK_RecurringVersion_CostCategoryLookup_Category` and table `CostCategoryLookup` (section 7).

#### 1.24 `RecurringAllocation` - `Auth.Domain.Setup.RecurringAllocation` (`RecurringItem.cs:184-199`)
- Snapshot `:854-880`; config `SetupModel.cs:71-76`. PK `PK_RecurringAllocation (OrganizationId, Id)`; tenant filter; append-only. One row per vehicle share of a version.

| Column | CLR -> SQL Server | Null | Precision |
|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | |
| `Id` | Guid -> uniqueidentifier | no | |
| `Amount` | decimal -> decimal(14,2) | no | 14,2 (positive; the shares sum exactly to the version `Amount`) |
| `VehicleId` | Guid -> uniqueidentifier | no | |
| `VersionId` | Guid -> uniqueidentifier | no | |

- Indexes: `IX_RecurringAllocation_OrganizationId_VehicleId (OrganizationId, VehicleId)` (FK support); UNIQUE `IX_RecurringAllocation_OrganizationId_VersionId_VehicleId (OrganizationId, VersionId, VehicleId)`.
- FKs: `FK_RecurringAllocation_Organizations_OrganizationId`; `FK_RecurringAllocation_FleetVehicle_OrganizationId_VehicleId -> FleetVehicle(OrganizationId, Id)`; `FK_RecurringAllocation_RecurringVersion_OrganizationId_VersionId -> RecurringVersion(OrganizationId, Id)`; NO ACTION. A definition has 1..500 distinct vehicles.

#### 1.25 `ExpenseCategory` - `Auth.Domain.Setup.ExpenseCategory` (`Domain/Setup/ExpenseCatalog.cs:30-82`)
- Snapshot `:628-660`; config `SetupModel.cs:49-53, 118`; created by migration `ExpenseCatalogAndInvestment`. PK `PK_ExpenseCategory (OrganizationId, Id)`; tenant filter. Never deleted.

| Column | CLR -> SQL Server | Null | Max length | Notes |
|---|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | | |
| `Id` | Guid -> uniqueidentifier | no | | |
| `Bucket` | ExpenseBucket enum -> int | no | | FK to `ExpenseBucketLookup(Id)` |
| `Name` | string -> nvarchar(100) | no | 100 | `ExpenseCategory.NameLength` |
| `NormalizedName` | string -> nvarchar(100) | no | 100 | `ToUpperInvariant()` |
| `StoppedOn` | DateOnly? -> date | yes | | active on d when `StoppedOn is null or StoppedOn > d` |

- Indexes: `IX_ExpenseCategory_Bucket (Bucket)` (FK support); UNIQUE `IX_ExpenseCategory_OrganizationId_NormalizedName (OrganizationId, NormalizedName)`.
- FKs: `FK_ExpenseCategory_Organizations_OrganizationId`; `FK_ExpenseCategory_ExpenseBucketLookup_Bucket (Bucket) -> ExpenseBucketLookup(Id)`; NO ACTION.

#### 1.26 `ExpenseItem` - `Auth.Domain.Setup.ExpenseItem` (`ExpenseCatalog.cs:84-132`)
- Snapshot `:662-692`; config `SetupModel.cs:55-60`. PK `PK_ExpenseItem (OrganizationId, Id)`; tenant filter. Never deleted.

| Column | CLR -> SQL Server | Null | Max length | Notes |
|---|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | | |
| `Id` | Guid -> uniqueidentifier | no | | |
| `CategoryId` | Guid -> uniqueidentifier | no | | |
| `Name` | string -> nvarchar(100) | no | 100 | |
| `NormalizedName` | string -> nvarchar(100) | no | 100 | `ToUpperInvariant()` |
| `StoppedOn` | DateOnly? -> date | yes | | |

- Unique index `IX_ExpenseItem_OrganizationId_CategoryId_NormalizedName (OrganizationId, CategoryId, NormalizedName)` (also serves the FK).
- FKs: `FK_ExpenseItem_Organizations_OrganizationId`; `FK_ExpenseItem_ExpenseCategory_OrganizationId_CategoryId -> ExpenseCategory(OrganizationId, Id)`; NO ACTION.

#### 1.27 `SetupDataScopes` - `Auth.Domain.Setup.SetupDataScope` (`Domain/Setup/SetupDataScope.cs:4-9`)
- Snapshot `:1015-1029`; config `SetupModel.cs:97-99`; originally named `SetupDataScope`, renamed to plural by migration `AccessManagement`. PK `PK_SetupDataScopes (OrganizationId, UserId)`; tenant filter.
- Columns: `OrganizationId` uniqueidentifier, `UserId` uniqueidentifier, `AllCompanies` bit (all not null). One row per member saying whether the person reaches every company.
- FKs: `FK_SetupDataScopes_Organizations_OrganizationId -> Organizations(Id)`; `FK_SetupDataScopes_Memberships_OrganizationId_UserId -> Memberships(OrganizationId, UserId)`; NO ACTION. No extra indexes.

#### 1.28 `SetupCompanyScopes` - `Auth.Domain.Setup.SetupCompanyScope` (`SetupDataScope.cs:12-17`)
- Snapshot `:997-1013`; config `SetupModel.cs:101-104`. PK `PK_SetupCompanyScopes (OrganizationId, UserId, CompanyId)`; tenant filter. Columns: `OrganizationId`, `UserId`, `CompanyId` (all uniqueidentifier, not null).
- Index `IX_SetupCompanyScopes_OrganizationId_CompanyId (OrganizationId, CompanyId)` (FK support).
- FKs: `FK_SetupCompanyScopes_Organizations_OrganizationId`; `FK_SetupCompanyScopes_Memberships_OrganizationId_UserId -> Memberships(OrganizationId, UserId)`; `FK_SetupCompanyScopes_PsvCompany_OrganizationId_CompanyId -> PsvCompany(OrganizationId, Id)`; NO ACTION.

#### 1.29 `SetupVehicleScopes` - `Auth.Domain.Setup.SetupVehicleScope` (`SetupDataScope.cs:20-25`)
- Snapshot `:1031-1047`; config `SetupModel.cs:106-109`. PK `PK_SetupVehicleScopes (OrganizationId, UserId, VehicleId)`; tenant filter. Columns: `OrganizationId`, `UserId`, `VehicleId` (all uniqueidentifier, not null).
- Index `IX_SetupVehicleScopes_OrganizationId_VehicleId (OrganizationId, VehicleId)` (FK support).
- FKs: `FK_SetupVehicleScopes_Organizations_OrganizationId`; `FK_SetupVehicleScopes_Memberships_OrganizationId_UserId -> Memberships(OrganizationId, UserId)`; `FK_SetupVehicleScopes_FleetVehicle_OrganizationId_VehicleId -> FleetVehicle(OrganizationId, Id)`; NO ACTION.
- Effective scope of a person (`SetupExecution.Actor`): `AllCompanies` from `SetupDataScopes`, plus the company ids and vehicle ids listed here; a company id grants all vehicles of that company, a vehicle id grants that vehicle only.

#### 1.30 `OrganizationSettingsVersion` - `Auth.Domain.Setup.OrganizationSettingsVersion` (`Domain/Setup/OrganizationSettingsVersion.cs`) - THE CHANGE LOG
- Snapshot `:726-787`; config `SetupModel.cs:78-95`. PK `PK_OrganizationSettingsVersion (OrganizationId, Id)`; tenant filter; append-only (`ValidateSetupWrites`). Entity has private setters and a private parameterless constructor; the public constructor validates (organization, actor and entity non-empty, version >= 1, reason 1..500 chars after trim, UTC instants, `vehicleId` not empty when given).
- The name is misleading: it is the organization-wide change log (people, companies, vehicles, recurring, expenses, investment, revenue), not only settings.

| Column | CLR -> SQL Server | Null | Max length | Converter / notes |
|---|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | | |
| `Id` | Guid -> uniqueidentifier | no | | |
| `ActorId` | Guid -> uniqueidentifier | no | | FK to Memberships |
| `After` | string -> nvarchar(max) | no | | JSON text of the new snapshot (`JsonSerializer.Serialize(after)`); a null object serialises to the text `null` |
| `Before` | string -> nvarchar(max) | no | | JSON text of the old snapshot; the text `null` for creations |
| `CorrelationId` | string -> nvarchar(100) | no | 100 | |
| `EffectiveFrom` | DateTimeOffset? -> datetime2 | yes | precision 7 | ValueConverter DateTimeOffset to DateTime (`value.UtcDateTime`; back via `new DateTimeOffset(stored, TimeSpan.Zero)`), `SetupModel.cs:88-91`; column was `datetimeoffset` until migration `ChangeLogIsFilterable`. Never set by current callers (constructor default null) |
| `EntityId` | Guid -> uniqueidentifier | no | | id of the changed record; polymorphic by `Section`, no FK |
| `OccurredAt` | DateTimeOffset -> datetime2 | no | precision 7 | same converter; stored as UTC |
| `Reason` | string -> nvarchar(500) | no | 500 | trimmed, 1..500 |
| `Section` | string -> nvarchar(160) | no | 160 | values written by code: companies, vehicles, recurring, expenses, investment, people, revenue, pettycash (new, see `inventory-petty-cash.md`), organization, localization, branding, securityPolicy, businessDate, logo (filter logic in `SetupRepository.History`); `SetupValue.Name` trims and caps at 160 |
| `VehicleId` | Guid? -> uniqueidentifier | yes | | (uncommitted) added by migration `ChangeLogVehicle`: the vehicle a vehicles, investment or revenue entry belongs to, so visibility needs no join; no FK |
| `Version` | long -> bigint | no | | the organization `SettingsVersion` value at the time of the write (unique per organization); not a concurrency token |

- Indexes: `IX_OrganizationSettingsVersion_OrganizationId_ActorId (OrganizationId, ActorId)` (FK support); UNIQUE `IX_OrganizationSettingsVersion_OrganizationId_Version (OrganizationId, Version)`; (uncommitted) `IX_OrganizationSettingsVersion_OrganizationId_OccurredAt (OrganizationId, OccurredAt)`; (uncommitted) `IX_OrganizationSettingsVersion_OrganizationId_Section_VehicleId (OrganizationId, Section, VehicleId)`.
- FKs: `FK_OrganizationSettingsVersion_Organizations_OrganizationId -> Organizations(Id)`; `FK_OrganizationSettingsVersion_Memberships_OrganizationId_ActorId (OrganizationId, ActorId) -> Memberships(OrganizationId, UserId)`; NO ACTION.
- The two uncommitted indexes exist in the model (`SetupModel.cs:81-82`) and in the working-tree snapshot (`AuthDbModelSnapshot.cs:779, 784`); the migration creates them with raw SQL (section 7).

### 1.D Revenue

#### 1.31 `RevenueRecords` - `Auth.Domain.RevenueRecord` (`Domain/Revenue.cs:54-119`)
- Snapshot `:505-557`; config `RevenueModel.cs:9-22`; created by migration `RevenueCapture`. PK `PK_RevenueRecords (OrganizationId, Id)`; tenant filter. Never deleted. Concurrency token `Version` (`RevenueModel.cs:16`), CLR initial 1, incremented inside `RevenueRecord.Replace` (`Revenue.cs:118`).

| Column | CLR -> SQL Server | Null | Max length / precision | Converter / notes |
|---|---|---|---|---|
| `OrganizationId` | Guid -> uniqueidentifier | no | | |
| `Id` | Guid -> uniqueidentifier | no | | |
| `Amount` | decimal? -> decimal(14,2) | yes | 14,2 | null when a no-earnings reason is given; otherwise positive money (`SetupValue.Money`: greater than 0, at most 999 999 999 999.99, 2 decimals) |
| `BusinessDate` | DateOnly -> date | no | | immutable after insert (`Replace` throws when it differs) |
| `CapturedAt` | DateTimeOffset -> datetimeoffset | no | | UTC |
| `CapturedBy` | Guid -> uniqueidentifier | no | | no FK |
| `CorrectedAfterDate` | bool -> bit | no | | set to true when `Replace` runs with `BusinessDate < today` |
| `Note` | string? -> nvarchar(80) | yes | 80 | only for reason Other; blank stored as null |
| `Reason` | RevenueNoEarningsReason? enum -> int | yes | | 1 Garage, 2 Arrest, 3 NoCrew, 4 Other; no FK or CHECK in the database |
| `UpdatedAt` | DateTimeOffset -> datetimeoffset | no | | UTC |
| `UpdatedBy` | Guid -> uniqueidentifier | no | | no FK |
| `VehicleId` | Guid -> uniqueidentifier | no | | |
| `Version` | long -> bigint | no | | concurrency token |

- Indexes: `IX_RevenueRecords_OrganizationId_BusinessDate (OrganizationId, BusinessDate)`; UNIQUE `IX_RevenueRecords_OrganizationId_VehicleId_BusinessDate (OrganizationId, VehicleId, BusinessDate)` (one record per vehicle per day; it is also the idempotency backstop, section 6).
- FKs: `FK_RevenueRecords_Organizations_OrganizationId`; `FK_RevenueRecords_FleetVehicle_OrganizationId_VehicleId (OrganizationId, VehicleId) -> FleetVehicle(OrganizationId, Id)`; NO ACTION.
- No CHECK ties Amount to Reason (the rule that exactly one of Amount or Reason is present lives only in `RevenueEntry.Validate`, `Revenue.cs:15-37`).
- There is no idempotency-key column; see section 6.

### 1.E Lookup tables (seed data via `HasData`, no tenant filter)

All three have `Id int` (not identity: the CLR key type is an enum, so EF does not generate values) and `Name nvarchar(max) not null`; PK `PK_<Table> (Id)`. Config `SetupModel.cs:111-113`. They exist so `RecurringVersion` and `ExpenseCategory` can foreign-key the enum ints.

| Table | C# entity | Rows (Id: Name) | Notes |
|---|---|---|---|
| `RecurrenceFrequencyLookup` | `RecurrenceFrequencyLookup` (`SetupDataScope.cs:27-31`) | 1 Daily, 2 Weekly, 3 Monthly, 4 Yearly | rows 1-3 inserted by `OrganizationsAndFleet`; row 4 inserted by raw SQL in `ExpenseCatalogAndInvestment` (section 7) |
| `RecurringKindLookup` | `RecurringKindLookup` (`SetupDataScope.cs:34-38`) | 1 Cost, 2 Savings | inserted by `OrganizationsAndFleet` |
| `ExpenseBucketLookup` | `ExpenseBucketLookup` (`SetupDataScope.cs:42-46`) | 1 RepairsAndMaintenance, 2 RecurringCharges, 3 LoanRepayments | inserted by `ExpenseCatalogAndInvestment` |

- Referenced by: `RecurringVersion.Frequency`, `RecurringVersion.Kind`, `RecurringVersion.Bucket` (optional), `ExpenseCategory.Bucket`. `RevenueRecords.Reason`, `Users.Status` and `VerificationCodes.Purpose` have no lookup table.

### 1.F Cross-table summary of what the schema does NOT enforce (candidates for PostgreSQL CHECKs or procedure rules)

- Amount versus reason on `RevenueRecords` (exactly one present), positive amounts on all `decimal(14,2)` money columns (`WeeklyAmount`, `Amount` on `RecurringVersion`, `RecurringAllocation`, `VehicleInvestment`, `RevenueRecords`), sum of allocation shares equal to the version amount, `VehicleAwayPeriod.ReturnedOn > LeftOn` and non-overlap, `LeftOn >= JoinedOn`, vehicle registration format, locale/time zone/currency formats, brand colour contrast and URL rules, logo size and magic bytes, history instants being UTC.
- Polymorphic references without FK: `OrganizationSettingsVersion.EntityId`, `OrganizationSettingsVersion.VehicleId`, `AuditEvents.Entity` (text), `RevenueRecords.CapturedBy`, `RevenueRecords.UpdatedBy`.
- Rules that live only in `AuthDb.ValidateWrites` / `ValidateSetupWrites` (section 2): append-only tables, no deletes on core setup tables, immutable `FleetVehicle.Registration`, tenant match on every write, UTC offsets.

---

## 2. Global query filters and write guards

### 2.1 How the current organization is resolved

- Interface `IOrganizationContext` (`Application/OrganizationPort.cs:5-10`): `Guid OrganizationId`, `Guid ActorId`, `string CorrelationId`.
- Implementation: class `organizationContext` (lower-case class name, `Infrastructure/OrganizationContext.cs:8-15`), registered scoped (`Program.cs:62`). It reads the validated JWT of the current HTTP request: `OrganizationId` = claim `org`, `ActorId` = claim `sub`, both `Guid.Empty` when the claim is missing or unparsable; `CorrelationId` = `HttpContext.TraceIdentifier` (or a fresh GUID when there is no HttpContext). The claims are put into the access token by `TokenIssuer.Access` (`Security.cs:77-90`): `sub`, `device`, `version` (the user `SecurityVersion`), `org`, `role`, `first_name`, `last_name`, repeated `permission`.
- `AuthDb` constructor: `AuthDb(DbContextOptions<AuthDb> options, IOrganizationContext? organizationContext = null)` (`AuthDb.cs:7`). Property `CurrentOganizationId => organizationContext?.OrganizationId ?? Guid.Empty` (`AuthDb.cs:9`; the name is misspelt). With no context (design time, CLI, hosted services, tests that build `AuthDb` by hand) the id is `Guid.Empty`, so every filtered query returns nothing and every tenant write is refused unless `Provisioning` is on.
- The token is not the only gate: every use case re-checks, per request and against the database, that the actor has an active membership in that organization and holds the required permission (`OrganizationUseCase.Run`, `OrganizationPort.cs:34-61`), and the JWT middleware re-validates the user, `SecurityVersion` and the trusted device on every request (`Program.cs:115-127`).

### 2.2 Global query filters (EF `HasQueryFilter`)

| Applied to | Expression | Where |
|---|---|---|
| `Organization` | `x.Id == CurrentOganizationId` | `OrganizationModel.cs:24` |
| every entity configured through `Tenant<T>()` (26 tables) | `x.OrganizationId == CurrentOganizationId` | `OrganizationModel.cs:12-16` (helper), called for each entity at `OrganizationModel.cs:27,36,37,38,47,52,56,61,66,73,78` (organization and access group), `Setup/SetupModel.cs:15,21,27,34,39,42,50,56,64,72,79,98,102,107` (setup group) and `RevenueModel.cs:13` |
| not filtered | `User`, `VerificationCode`, `TrustedDevice`, `RefreshToken`, the three lookup tables | `AuthDb.cs:40-64` has none |

- `Tenant<T>()` also declares the FK `OrganizationId -> Organizations(Id)` with `OnDelete(DeleteBehavior.Restrict)` for every tenant entity (`OrganizationModel.cs:14`).
- A filter applies to direct queries, to `Include` and `ThenInclude` and to sub-queries written against `db.Set<T>()`; the repositories rely on that (for example `VisibleVehicles(actor)` never mentions `OrganizationId`).
- Tenant-consistent references: every cross-table FK between tenant tables is composite and starts with `OrganizationId` (for example `(OrganizationId, VehicleId) -> FleetVehicle(OrganizationId, Id)`), so a row cannot point at another organization's row even through raw SQL. The only single-column tenant FKs are `OrganizationId -> Organizations(Id)`.

### 2.3 `IgnoreQueryFilters()` usages in production code and why

| Where | What it reads without the filter | Why |
|---|---|---|
| `Application/Authentication/AuthAccounts.cs:59` (`AuthPolicy.For`) | active `Memberships` row of a user | sign-in has no JWT yet, so no organization context; finds the one organization the person belongs to |
| `Application/Authentication/AuthAccounts.cs:64` (`AuthPolicy.ForOrganization`) | `SecurityPolicies` of that organization (AsNoTracking, clamped) | same |
| `Application/Authentication/SessionTokens.cs:14,22,27,34` | membership, `PersonRoles`, `Roles`, `PermissionOverrides` while issuing tokens | same; the explicit `OrganizationId == membership.OrganizationId` predicates replace the filter |
| `Application/Settings/SettingsSections.cs:104` (`OrganizationDetailsSection`) | `Organizations` with another id and the same slug | slug uniqueness is global, not per organization |
| `Infrastructure/DemoSeed.cs:33,56,59,65,78-80` | organization, membership, person role, expense categories, scope rows | seeding runs with no request context |
| `Infrastructure/UserProvisioning.cs:46,58,71,73,77,88,104` | membership, role link, trusted devices, refresh tokens, data scope, all organizations, roles | operator CLI, no request context |
| `Program.cs:237` | `Memberships` (any organization) | startup warning that counts active users without an active membership |
| tests | 59 occurrences in `tests/api/*.cs` | direct seeding and assertions |

### 2.4 `Provisioning` switch

- `public bool Provisioning { get; set; }` on `AuthDb` (`AuthDb.cs:10`). When true, `ValidateWrites` skips the tenant match rule and the Organization rule (below). It is set only by `UserProvisioning.Provision` (`UserProvisioning.cs:25,83`), `DemoSeed.Run` (`DemoSeed.cs:30,74`) and tests; no request path sets it.

### 2.5 Write guards: `AuthDb.ValidateWrites` and `ValidateSetupWrites`

- Hooked into both `SaveChanges(bool)` and `SaveChangesAsync(bool, CancellationToken)` overrides (`OrganizationModel.cs:116-128`), which every public SaveChanges overload funnels into. Order inside each: `ValidateWrites()`, then `BumpVersions()` (`AuthDb.cs:67-74`), then `base.Save...`. So the guards run on every save path, including saves made by seeding, CLI and tests.
- `ValidateWrites` (`OrganizationModel.cs:87-114`) first calls `ValidateSetupWrites()`, then walks every tracked entry whose state is `Added`, `Modified` or `Deleted`:

| # | Rule | Applies to | Failure | HTTP when it escapes |
|---|---|---|---|---|
| 1 | Audit events are append-only: anything but `Added` | `AuditEvent` | `InvalidOperationException` with text Audit events are append-only (`:92-93`) | 500 (not mapped) |
| 2 | Tenant match: `CurrentOganizationId` is not empty, the entity `OrganizationId` equals it, and for non-added entries the original `OrganizationId` equals it too; skipped when `Provisioning` | every `IOrganizationEntity` | `UnauthorizedAccessException` with text Cross-organization write rejected. (`:94-98`) | 403 in `/setup` groups |
| 3 | Organization row: only `Modified` and only the current organization; any `Added` or foreign row is refused; skipped when `Provisioning` | `Organization` | `UnauthorizedAccessException` without message (`:99-100`) | 403 |
| 4 | Domain validation on write | `OrganizationLocalization.Validate()`, `OrganizationBranding.Validate()`, `OrganizationSecurityPolicy.Validate()`, `UserPreference.Validate()` (`:101-108`) | `ArgumentException` | 400 |
| 5 | All instants UTC: any property whose current value is a `DateTimeOffset` with non-zero offset is refused | every entity, every property | `ArgumentException` with text Instants must be UTC. (`:110-112`) | 400 |

- `ValidateSetupWrites` (`Setup/SetupModel.cs:122-133`), only for `Modified` or `Deleted` entries:

| # | Rule | Entities | Failure |
|---|---|---|---|
| 6 | Append-only: no update, no delete | `OrganizationSettingsVersion`, `VehicleTarget`, `VehicleAwayPeriod`, `RecurringVersion`, `RecurringAllocation` | `InvalidOperationException` with text Setup versions and allocations are append-only. |
| 7 | No delete | `PsvCompany`, `FleetVehicle`, `RecurringItem`, `RevenueRecord`, `ExpenseCategory`, `ExpenseItem` | `InvalidOperationException` with text Setup records cannot be deleted. |
| 8 | `FleetVehicle.Registration` immutable (`IsModified`) | `FleetVehicle` | `InvalidOperationException` with text Registration cannot change. |

- Not guarded: `VehicleInvestment` (updatable and hard-deletable), `PersonRoles`, `PermissionOverrides` and the three scope tables (the people editor deletes and re-inserts them), `Logos` (deleted by the logo endpoint), `Users`, `Memberships` and token tables.
- Domain objects add their own guards that are not database rules: private setters, and tenant immutability through the explicit `IOrganizationEntity.OrganizationId` setter that throws `Tenant cannot change.` (`PsvCompany`, `FleetVehicle`, `VehicleTarget`, `VehicleAwayPeriod`, `VehicleInvestment`, `RecurringItem`, `RecurringVersion`, `RecurringAllocation`, `ExpenseCategory`, `ExpenseItem`, `OrganizationSettingsVersion`, `RevenueRecord`).
- Reads that change tracked state fail: `UnitOfWork.Read` throws `InvalidOperationException` (text: A read changed state. Run it as a write.) when `ChangeTracker.HasChanges()` (`OrganizationRepository.cs:96-102`; test `PeopleQueryCostTests.AReadThatChangesStateFailsInsteadOfDroppingTheChange`).

### 2.6 Where the planned PostgreSQL design differs
- `apps/api-python/docs/03-database.md` replaces filters (section 2.2) with RLS policies driven by transaction-local settings; rules 1, 6 and 7 map to privileges (no UPDATE or DELETE grant) or triggers; rules 4 and 5 move into routines and CHECK constraints. This inventory only records the current behaviour.

---

## 3. Concurrency

### 3.1 Tokens and counters

| Table.column | EF mapping | Initial value | Bumped where | Exposed to clients as |
|---|---|---|---|---|
| `Organizations.SettingsVersion` (bigint) | `IsConcurrencyToken()` `OrganizationModel.cs:23` | 1 (`Organization.cs:90`) | `Organization.SettingsChanged()` (`Organization.cs:91`, `SettingsVersion++`), called once per change-log entry and ONLY by `SettingsChangeLog.Record` (`Application/Settings/SettingsChangeLog.cs:11-19`), which is called by `SetupRepository.RecordChange` (`SetupRepository.cs:475-481`), `RevenueRepository.RecordChange` (`RevenueRepository.cs:241-248`), `AccessUseCases.RecordHistory` (`AccessUseCases.cs:588-591`), `OrganizationSettingsUseCases.Record` (`Application/Settings/OrganizationSettingsUseCases.cs:134-149`) and the petty cash repository (`PettyCashRepository.cs:155`); `Organization.ChangeTimeZone` no longer bumps it (`Organization.cs:108-116`) | `AppearanceResponse.SettingsVersion` (`OrganizationSettingsUseCases.cs:83`); it is also the `Version` stored on each change-log row |
| `Memberships.Version` (bigint) | `IsConcurrencyToken()` `OrganizationModel.cs:28` | 1 | domain methods `Deactivate()`, `Reactivate()` (only on a real change) and `AccessChanged()` (`Organization.cs:128-143`); `AccessChanged` is called by `AccessUseCases.Save` when the snapshot differs (`AccessUseCases.cs:185-187`) | `PersonDto.Version`; sent back as `SavePerson.Version` and `PersonLifecycleRequest.Version` |
| `RevenueRecords.Version` (bigint) | `IsConcurrencyToken()` `RevenueModel.cs:16` | 1 (`Revenue.cs:76`) | `RevenueRecord.Replace` (`Revenue.cs:118`, `Version++`) | `RevenueSaved.Version`, `RevenueCellDto.Version`; sent back as `SaveRevenue.Version` |
| `Users.Version` (bigint) | `IsConcurrencyToken()` `AuthDb.cs:48` | 0 | `AuthDb.BumpVersions()` (`AuthDb.cs:67-74`): for every tracked `User` or `RefreshToken` entry in state `Modified`, `Version = OriginalValue + 1` | not exposed |
| `RefreshTokens.Version` (bigint) | `IsConcurrencyToken()` `AuthDb.cs:60` | 0 | `AuthDb.BumpVersions()` | not exposed |

- Not an EF token but a revocation counter: `Users.SecurityVersion` (int). Bumped by `User.SetPin`, `User.Remove`, `User.BumpSecurityVersion` (people editor when name, role or single permissions change, or when sign-in details change; provisioning when identity, status, membership or role changed). It is copied into the JWT claim `version` and compared on every authenticated request by the JWT middleware (`Program.cs:115-127`): a mismatch, a `Removed` user, a revoked device or an expired device trust makes the token invalid at once.
- Not an EF token: `OrganizationSettingsVersion.Version` (the change-log counter) has a unique index `(OrganizationId, Version)` (`SetupModel.cs:80`), so two concurrent writers cannot both log the same version.
- How EF enforces a token: `UPDATE ... WHERE <key> AND <token column> = <original value>`; zero rows affected raises `DbUpdateConcurrencyException` whose `Entries` list the entities that did not update.
- People editor extra check (before EF): `AccessUseCases.Save` and `SetActive` compare `input.Version` with the loaded `Membership.Version` and throw `DbUpdateConcurrencyException` (message: This person's access changed. Reload before saving.) themselves (`AccessUseCases.cs:91-94, 210-211`); `Save` for an existing person without a `Version` throws `ArgumentException` (Reload this person before saving.).
- Revenue extra check (before EF): `RevenueUseCases.Save` throws `RevenueConflictException` when the record exists, the request is not an identical replay and `input.Version != existing.Version` (`RevenueUseCases.cs:73-74`).

### 3.2 Exception to HTTP mapping

| Exception | Raised by | Response | Where mapped |
|---|---|---|---|
| `DbUpdateConcurrencyException` | EF token mismatch (including organization settings, logo and preferences writes after four change-log collisions), or manual throw in `AccessUseCases` | 409, title `Settings changed. Reload before saving.` | `SetupEndpoints.WithSetupErrors` (`SetupEndpoints.cs:35`), applied to groups `/setup`, `/setup/revenue` and the organization endpoints |
| `DbUpdateException` (not concurrency), for example a unique-index violation | EF | 409, title `A conflicting record exists. Reload before saving.` | `SetupEndpoints.cs:36` |
| `DbUpdateConcurrencyException` on revenue routes | EF | 409, title `This day was changed by another save.`, detail `Reload the current record and try again.` (inner filter wins over the setup filter) | `RevenueEndpoints.cs:29-32` |
| `RevenueConflictException` | `RevenueUseCases.Save` | 409, title `This day already has a different record.`, extension `current` = `RevenueCellDto` of the stored record | `RevenueEndpoints.cs:24-28` |
| `RevenueEarlierDayMissingException` (an `ArgumentException`) | `RevenueUseCases.Save` | 400, title `Invalid setup change`, extension `earliestMissing` (yyyy-MM-dd) **(removed by 9276c51: days are captured in any order; see the drift log entry 24)** | `RevenueEndpoints.cs:33-37` |
| `UnauthorizedAccessException` | permission, scope, tenant guard | 403, title `Not permitted in this organization or data scope.`, detail = the message when it is not the default one | `SetupEndpoints.cs:32` |
| `KeyNotFoundException` | record outside the actor's scope or missing | 404, title `Record not found in your scope.` | `SetupEndpoints.cs:33` |
| `ArgumentException` | validation | 400, title `Invalid setup change`, detail = message | `SetupEndpoints.cs:34` |
| slug already used | `SettingsSections.cs:104-105` | 409 `{ detail: This organization slug is already in use. }` (plain JSON, `application/json`), returned as a result, not an exception, by `Api/OrganizationEndpoints.cs:27` | endpoint |
| anything else (`InvalidOperationException`, `DbUpdateConcurrencyException` on `/auth/*`) | | 500 problem details (exception detail removed) | `UseExceptionHandler` + `AddProblemDetails` (`Program.cs:131-136, 151`) |

- `/auth/*` endpoints have no concurrency mapping: they rely on the per-account lock (3.4) and the serializable transaction.

### 3.3 `UnitOfWork` and retry semantics (`Infrastructure/OrganizationRepository.cs:48-115`)

- Port: `IUnitOfWork` (`OrganizationPort.cs:23-30`): `Task<T> Execute<T>(Func<Task<T>> action, CancellationToken ct)`, `Task<T> Read<T>(Func<Task<T>> action, CancellationToken ct)`, `void Audit(string action, string entity, object? before, object? after)`.
- `Execute`:
  1. `db.Database.CreateExecutionStrategy()`. In production this is EF's SQL Server retrying strategy configured at `Program.cs:75`: `EnableRetryOnFailure(3, TimeSpan.FromSeconds(5), null)` (up to 3 retries of transient SQL errors, 5 s maximum delay, default transient error list which includes deadlock 1205). Tests run on SQLite with the non-retrying strategy.
  2. Inside the strategy delegate, a loop `for (attempt = 0; ; attempt++)`: `BeginTransactionAsync(IsolationLevel.Serializable)`; run `action()` (authorization, reads, domain changes, adds); `db.SaveChangesAsync` (which runs `ValidateWrites` and `BumpVersions`); `CommitAsync`; return the result.
  3. The collision rule: `catch (Exception error) when (attempt < ChangeLogRetries && OnlyTheChangeLogCollided(error))` with `ChangeLogRetries = 3`. The handler clears the change tracker, calls `organizations.ForgetResolved()` (drops the per-request permission cache), waits `Random.Shared.Next(5, 25) * (attempt + 1)` milliseconds, and loops with a brand new transaction (the failed one is disposed, so rolled back). So at most 4 attempts (1 + 3 retries). Test: `ChangeLogAndScopeTests.WritesToDifferentRecordsRetryWhenOnlyTheChangeLogCollides` expects 2 transactions for one collision, and with 4 colliding attempts expects HTTP 409 and 4 transactions.
  4. `OnlyTheChangeLogCollided` (`OrganizationRepository.cs:84-92`) is true for: (a) a `DbUpdateConcurrencyException` that has at least one entry and whose entries are all `Organization`; (b) any exception whose `InnerException` chain contains a `SqlException` with `Number == 1205` (deadlock victim).
  5. Never retried by this loop: a concurrency conflict on any other entity (a stale `Membership`, `RevenueRecord`), unique-index violations, authorization failures, validation errors, and the 4th failure of a retried collision. They escape as the exceptions in section 3.2 on the first attempt. Test: `AStaleRecordStillConflictsAtOnce` expects 409 and 1 transaction.
  6. A retry restarts from scratch: nothing resolved earlier survives, so the actor's membership, permissions, scope, settings and organization are read again; revoking a permission or deactivating the membership between attempts makes the retry answer 403 and writes nothing (`ARetryChecksAccessAgain`, two data rows).
  7. The outer execution strategy can additionally re-run the whole delegate (so the whole loop) on transient SQL errors, up to its own 3 retries; the two layers multiply in the worst case. No test pins that interaction.
- `Read`: no explicit transaction, no `SaveChanges`; runs the action then throws `InvalidOperationException` (text: A read changed state. Run it as a write.) when the change tracker holds changes. Default isolation (READ COMMITTED on SQL Server; each statement is its own implicit transaction). Tests: `PeopleQueryCostTests.SetupReadsOpenNoTransaction` expects 0 transactions for `/setup/people`, `/setup/access/catalog`, `/setup/access/scope-options`, `/setup/companies`, `/setup/vehicles`, `/setup/recurring`, `/setup/history`, and exactly 1 for `/setup/access/roles` (listing roles may insert missing catalog roles, so it is a write).
- Pipeline choice: `OrganizationUseCase.Run` uses `Read` when `ReadOnly` is true, else `Execute` (`OrganizationPort.cs:53`). `SetupExecution.Read/ReadAny` are read-only; `Write/WriteAny` are writes.
- Transaction/isolation summary:

| Path | Transaction | Isolation | Retry |
|---|---|---|---|
| `IUnitOfWork.Execute` (all setup, people, access, revenue writes) | explicit | Serializable | change-log collision loop (3 retries) plus the execution strategy |
| `IUnitOfWork.Read` (all setup and revenue reads) | none | default | none |
| `/auth/*` via `AuthUnitOfWork.Run` (`Infrastructure/AuthUnitOfWork.cs:11-33`) | explicit, inside `CreateExecutionStrategy().ExecuteAsync` | Serializable | execution strategy only; every retry starts with `ChangeTracker.Clear()` (`:21-23`) |
| organization settings, logo and preferences writes (`OrganizationSettingsUseCases.cs:33-131` through `ISetupExecution.Write(permission, Func<Task<T>>)`, `SetupExecution.cs:23-27`) | explicit | Serializable | change-log collision loop (3 retries) plus the execution strategy; 409 after four collisions (since phase 5, **uncommitted**; was EF implicit and no retry) |
| JWT `OnTokenValidated` (`Program.cs:115-127`) | none | default | none |
| `VerificationMailer.Withdraw` (`Security.cs:162-177`) | none, own scope | default | none, errors are logged |
| CLI `--provision-user`, `--remove-user`, DemoSeed | EF implicit | default | none |

### 3.4 Per-account serialization of sign-in (`Infrastructure/AuthUnitOfWork.cs:11-47`, `Infrastructure/AuthGate.cs:7-43`, `Api/AuthEndpoints.cs:73-83`)

- `AuthGate` (singleton): `ConcurrentDictionary<string, Entry>` of `SemaphoreSlim(1,1)` keyed by the normalised phone number, or `device:<DeviceId>` when no valid number is sent (refresh, sign-out). Capped at 10 000 entries; above that the least recently used idle semaphores are evicted down to 80 percent. In-process only: it does not coordinate several API replicas.
- `Run` validates sizes first (DeviceId 1..128, PhoneNumber at most 14, Email at most 320 and parseable when non-empty, Pin at most `PinRules.MaximumLength` = 8, Code at most 32, RefreshToken at most 256) and answers 400 `invalid_request` otherwise; then waits on the account's semaphore (`AuthGate.For(lockKey)`, never disposed on eviction); then runs the action in one Serializable transaction with SaveChanges under the execution strategy; then releases the semaphore and, only for the COMMITTED attempt, `AuthUnitOfWork.Deliver` (`AuthUnitOfWork.cs:37-47`) sends the email carried in `AuthResult.Mail` (a `NewDevice` code before answering, 503 `service_unavailable` when that send fails; other codes by `SendLater`). The lock key is the normalised phone, `device:<DeviceId>` when none, and for device revoke the ACCOUNT's phone (`SessionService.AccountKey`, `AuthEndpoints.cs:55`).

### 3.5 Why the Organization row is a hotspot
- Every change-log write updates the single `Organizations` row (token bump) and inserts a log row with the new version, so all concurrent writers of one organization conflict on that row even when they touch different records. The retry loop in 3.3 exists only for that. A PostgreSQL design has to decide whether to keep a per-organization counter row, use a sequence per organization, or serialize writers with `SELECT ... FOR UPDATE`.

---

## 4. Change log and scope

### 4.1 The organization change log (table `OrganizationSettingsVersion`, entity `Auth.Domain.Setup.OrganizationSettingsVersion`)

Append semantics
- Rows are only ever inserted. `ValidateSetupWrites` rejects any Modified or Deleted entry (section 2.5 rule 6). The constructor (`OrganizationSettingsVersion.cs:26-40`) refuses empty organization, actor or entity ids, `version < 1`, an empty or over-500-character trimmed reason, non-UTC `occurredAt` or `effectiveFrom`, and an empty (not null) `vehicleId`. `Section` is trimmed and capped at 160 characters by `SetupValue.Name`.
- Each row takes the organization's counter after the bump: every writer calls `SettingsChangeLog.Record(organizationId, actorId, correlationId, section, entityId, before, after, reason, vehicleId = null, ct)` (`Application/Settings/SettingsChangeLog.cs:11-19`), the ONLY writer of change-log rows: it loads the organization, calls `SettingsChanged()` (version + 1), adds `new OrganizationSettingsVersion(..., version: organization.SettingsVersion, ..., vehicleId: vehicleId)` and returns the new version. `before` and `after` are stored exactly as given (each caller keeps its own JSON shape) and audit events stay with the callers. The first change in a fresh organization therefore gets `Version = 2` (counter starts at 1). Writers of one organization serialize on the `Organizations` row token (section 3), so versions are unique per organization and strictly increasing; production code has no path that bumps the counter without writing a row. A unique index `(OrganizationId, Version)` backs this.
- Writers (all inside the same transaction as the change they describe; each also adds an `AuditEvents` row):

| Section value | Written by | `EntityId` | `VehicleId` | Snapshot shape (Before/After JSON) |
|---|---|---|---|---|
| `companies` | `CompanyUseCases.Save`, `SetArchived` via `SetupRepository.RecordChange` | company id | null | `{Id, Name, ArchivedOn, Active}` (PascalCase, default serializer) |
| `vehicles` | `VehicleUseCases.Save`, `Retire`, `Restore` | vehicle id | vehicle id, passed by `SetupRepository.RecordChange` for sections `vehicles` and `investment` (`SetupRepository.cs:477-479`) (uncommitted) | `{Id, Registration, CompanyId, JoinedOn, LeftOn, Targets:[{EffectiveFrom, WeeklyAmount, Revision}], Away:[{LeftOn, ReturnedOn}]}` |
| `recurring` | `RecurringUseCases.Save`, `Stop`, `CancelStop` | item id | null | `{Id, StoppedFrom, Versions:[{Id, Revision, EffectiveFrom, Name, Kind, Amount, Frequency, Day, LastDay, Month, Start, End, ExpenseItemId, Bucket, Note, Allocations:[{VehicleId, Amount}]}]}`; enums are numbers |
| `expenses` | `ExpenseCatalogUseCases` | category id or item id | null | category `{Id, Name, Bucket, StoppedOn}`, item `{Id, CategoryId, Name, StoppedOn}` |
| `investment` | `InvestmentUseCases.Add`, `Update`, `Remove` | the vehicle id (not the entry id) | vehicle id (uncommitted) | `{Id, VehicleId, Date, Description, Amount}`; Before is null on add and After is null on remove |
| `people` | `AccessUseCases.RecordHistory` | person (user) id | null | `PersonSnapshot {FirstName, LastName, Email, PhoneNumber, Role, Active, ScopeMode, CompanyIds[], VehicleIds[], Permissions[], ApprovalLimit, Name}` with sorted arrays (`Name` is the record's computed get-only property, serialised last) |
| `revenue` | `RevenueRepository.RecordChange` | revenue record id | the record's vehicle id, read from the tracked record (`RevenueRepository.cs:244-246`) (uncommitted) | `{Id, VehicleId, BusinessDate, Amount, Reason (string name), Note, CapturedAt, CapturedBy, UpdatedAt, UpdatedBy, CorrectedAfterDate, Version}` |
| `organization` | `OrganizationSettingsUseCases.Save` (PUT settings) via `Record` | organization id | null | camelCase `{name, slug}` |
| `pettycash` | `PettyCashRepository` (`PettyCashRepository.cs:155`) | the entry id | the entry's vehicle id when it has one | see `inventory-petty-cash.md` |
| `localization`, `branding`, `securityPolicy` | same | organization id | null | the whole section as saved, camelCase (omitted fields saved with defaults) |
| `businessDate` | same | organization id | null | a JSON date string or `null` |
| `logo` | `OrganizationSettingsUseCases.UploadLogo`, `RemoveLogo` | organization id | null | `{ContentType, bytes, UpdatedAt}` (as `SettingsText.DescribeLogo`, camelCase from `SettingsText.Json`) or the text `null` |

- `OccurredAt` is `clock.UtcNow` at write time; `EffectiveFrom` is never set by current code; `CorrelationId` is the request trace id; `Reason` is an automatic sentence (for example `Added company Westlands Movers`, `Recorded revenue for KDA 482M on 28 Sep 2026`, `Changed role for Jane Njeri`) optionally followed by `. Reason: <typed text>.`; the combined text is clipped to 500 characters (`SetupPagination.Automatic`, `SetupContracts.cs:112-122`).
- A repeated identical operation writes nothing: domain methods return false (rename to the same name, archive on the same date, stop on the same day), `RecurringUseCases.Save` returns early when `Same(latest, definition)`, settings saves with `before == after` return early (`OrganizationSettingsUseCases.cs:40-44`), and an identical revenue replay returns the stored id and version (section 6).
- Reading is covered in section 5 (`ISetupRepository.History`).

Filtering (the `ChangeLogIsFilterable` migration)
- `HistoryFilter(Section, From, To, Text)` (`SetupContracts.cs:26-40`). `Section`: exact match on the stored section. `From`/`To`: calendar days in the organization time zone, both included, converted to the UTC window `OccurredAt >= midnight(From)` and `OccurredAt < midnight(To + 1 day)` using the zone offset at that local midnight (`SetupRepository.cs:338-379`); `From > To` is a 400. `Text`: at most 200 characters after trim, matched with `LIKE %text%` against `Reason` or against the full name of an actor (names are looked up first from `Memberships`, then `ActorId IN (...)`), with `[`, `%` and `_` escaped using SQL Server bracket syntax (`SetupRepository.cs:371-375`). The migration exists because those comparisons must run inside the database; it converted `OccurredAt` and `EffectiveFrom` from `datetimeoffset` to `datetime2` (offset was always zero) so SQLite can compare them too.

Ordering and paging (`SetupRepository.History`, `SetupRepository.cs:291-336`, uncommitted)
- Order: `Version DESC` only (the unique counter is the tie-free sort key). Page size 1..100, `page` 1..100000 (`SetupPagination.Validate`). Endpoint: `GET /setup/history?page&pageSize&section&from&to&text&before&includeTotal` (`SetupEndpoints.cs:132-141`, permission `audit.view`); `before` must be at least 1 (else 400 `Before must be a change log version.`), `includeTotal` defaults to true.
- Two paging modes. Offset mode (no `before`): `ORDER BY Version DESC OFFSET (page-1)*pageSize`. Seek mode (`before` given): `WHERE Version < before ORDER BY Version DESC` and `page` is ignored for the skip. Both fetch `pageSize + 1` rows; the extra row only sets `HasMore`. Result `HistoryPage(Items, PageNumber, PageSize, Total?, HasMore, NextBefore?)` where `NextBefore` is the version of the last item shown when `HasMore` (`SetupContracts.cs:21`). Test `ChangeLogPagingTests.PagingByVersionReturnsTheSameRowsAsPagingByNumber` pins that both modes return identical sequences for the whole log, for section and text filters, and that a page ending exactly at the last row has `HasMore = false`.
- Each row is joined to `Memberships` on `ActorId = UserId` (LEFT JOIN, tenant filtered) to build `ActorName = FirstName + ' ' + LastName`, or an empty string when the membership is missing.
- Cost pin: `ChangeLogPagingTests.ReadingTheChangeLogCostsTheSameHoweverLongItGrows` requires identical (commands, rows read) at about 30 and about 630 log rows for owner page 1, owner `before=1000000`, owner text filter and a scoped clerk. `VersionPagesSeekAndUnscopedViewersSkipTheVisibilityChecks` requires: offset mode SQL contains OFFSET; seek mode SQL has no OFFSET and contains `"Version" < @`; for an all-companies viewer the log SQL mentions neither `"FleetVehicle"` nor `"RecurringItem"`; for a scoped viewer it mentions `"FleetVehicle"`, `"RecurringItem"` and `"VehicleId" IS NOT NULL` but not `"RevenueRecords"`.

Visibility (who sees which rows)
- Rows of section `people` need the permission `people.view` for everyone, including all-companies viewers (`SetupRepository.cs:295-297`).
- All-companies viewers (`SetupActor.AllCompanies`) otherwise see every row, including the settings sections (`organization`, `localization`, `branding`, `securityPolicy`, `businessDate`, `logo`).
- Scoped viewers see only: `companies` rows whose `EntityId` is a visible company; `vehicles`, `investment`, `revenue` and `pettycash` rows whose `VehicleId` is not null and is a visible vehicle (visibility follows the vehicle's current company, so moving a vehicle moves its past revenue rows into view, test `ScopedViewersSeeRevenueOnlyForTheVehiclesTheyCanSeeToday`); `recurring` rows whose item is complete, meaning no allocation of any version points at a vehicle outside the viewer's visible set; all `expenses` rows; `people` rows whose `EntityId` is a person the viewer may list (`PeopleVisibility.People`). They never see settings sections.
- Visible vehicle = in the viewer's company scope or vehicle scope; visible company = in the company scope, or holding a visible vehicle (`SetupRepository.cs:15-22`).
- Redaction: for scoped viewers, `people` entries have their `CompanyIds` and `VehicleIds` arrays (in both Before and After JSON) cut down to what the viewer can reach (`WithoutHiddenScope`, `SetupRepository.cs:382-405`; one extra query maps the page's vehicle ids to company ids). Test `PeopleHistoryTests.ScopedAuditorsSeeChangesToVisiblePeopleWithHiddenScopeRedacted`.

Count and cache
- `Total` is the size of the filtered, visible log (not of the page) and is `null` when `includeTotal=false`. When a `HistoryCountCache` is registered the count goes through it (4.4); otherwise a `COUNT` query runs.

### 4.2 Data scope (`SetupDataScopes`, `SetupCompanyScopes`, `SetupVehicleScopes`) and `SetupExecution`

- Principle (`SetupDataScope.cs:1-2`): data scope is separate from permissions, possessing an action never grants all data. A member with no scope rows sees no companies, vehicles, people changes or recurring items.
- A member's scope is one of three modes, stored as rows (the people editor deletes all of a person's scope rows and writes one mode, `AccessUseCases.cs:166-175, 437-464`): `all` = one `SetupDataScopes` row with `AllCompanies = 1`; `companies` = one `SetupCompanyScopes` row per company (1 or more); `vehicles` = one `SetupVehicleScopes` row per vehicle (1 or more). `ScopeModeOf` reads it back as all, else companies when any company row exists, else vehicles (`AccessUseCases.cs:289`). Demo and provisioning give Owner and Office admin (and the demo Fleet manager) an `all` row.
- `SetupActor` (`Application/ISetupExecution.cs:5-7`): `OrganizationId`, `UserId`, `Today` (the business date), `AllCompanies`, `CompanyIds`, `VehicleIds`, `CorrelationId`, `Permissions`, `SettingsVersion` (long?, uncommitted: the organization change-log version read before any data; null means unknown and nothing is cached).
- `SetupExecution` (`Infrastructure/Setup/SetupExecution.cs`) is the adapter that runs every setup read or write through the `OrganizationUseCase` pipeline; it is not a stored lifecycle and has no table. `Domain/Setup/SetupExecution.cs` is an empty 0-byte file. What runs for each call, in order:
  1. `OrganizationUseCase.Run`: refuse (403) when the context organization or actor is `Guid.Empty`; `Validate` (no-op for setup).
  2. `Memberships` lookup for the actor (query 1) and `Permissions` (3 queries, cached for the request); require an active membership and, when the call names permissions, at least one of them (an empty list means any active member).
  3. `Execute` builds the `SetupActor` (`SetupExecution.Actor`, `SetupExecution.cs:32-54`) with these reads: the actor's `SetupDataScopes` row (AsNoTracking, SingleOrDefault); the actor's `SetupCompanyScopes` company ids; the actor's `SetupVehicleScopes` vehicle ids; `Localizations.TimeZone` (default Africa/Nairobi when no row); the `Organizations` row projected to `{BusinessDate, SettingsVersion}` (SingleAsync; the second field is uncommitted); permissions again (served from the request cache). `Today = Organizations.BusinessDate ?? current calendar date in the organization time zone` (`TimeZoneInfo.FindSystemTimeZoneById`, then `ConvertTime(clock.UtcNow)`), never a personal or browser date.
  4. The use case delegate runs with that actor.
  5. Writes: `SaveChanges` and commit inside the serializable transaction (section 3.3). Reads: the tracked-changes check.
- Idempotency of setup commands: there is no idempotency key anywhere in setup. Repeat safety comes from the domain returning no change (same rename, archive on the same date, retire on the same date, stop on the same day, identical recurring definition, same investment values, settings equal to stored), in which case nothing is written and no change-log row is added. Creates are not idempotent: a second Add company with the same normalized name is refused by the unique index and by `CompanyNameExists`, a second vehicle by `RegistrationExists`, but a second recurring item or investment entry simply creates another.

### 4.3 Lifecycle states of setup records (all expressed as dates, no status columns)

| Record | State columns | Active on date d | Transitions (domain method) |
|---|---|---|---|
| `PsvCompany` | `ArchivedOn` | `ArchivedOn is null or ArchivedOn > d` | `Archive(today)` refused while any vehicle of the company has `LeftOn is null or LeftOn > today` (`HasActiveVehicles`); `Restore()` |
| `FleetVehicle` | `JoinedOn`, `LeftOn`, away periods | `JoinedOn <= d and (LeftOn is null or d < LeftOn)` and `d` not inside an away period `[LeftOn, ReturnedOn)` | `Retire(leftOn, today)`: `JoinedOn <= leftOn <= today` and not before the last away return, refused by the use case when revenue exists on or after `leftOn` (`RecordedRevenueDays`); `Restore(returnedOn, today)`: adds an away period when `returnedOn > left`, clears `LeftOn`; `Update` appends a target revision and may move the join date earlier freely, and later only up to the first day that has revenue recorded |
| `VehicleTarget` | `EffectiveFrom`, `Revision` | latest `EffectiveFrom <= d`, ties by highest `Revision` | appended by the `FleetVehicle` constructor and `Update` |
| `RecurringItem` and `RecurringVersion` | `StoppedFrom`; per version `EffectiveFrom`, `Start`, `End`, `Revision` | a version is in charge from its `EffectiveFrom` until a higher revision takes effect; due dates are stepped from `Start` to `End` and stop before `StoppedFrom` | `Revise` appends a version (the start of a running item cannot change); `Stop(today)`; `CancelStop` only while `StoppedFrom > today` |
| `ExpenseCategory`, `ExpenseItem` | `StoppedOn` | `StoppedOn is null or StoppedOn > d` | `Stop(today)`, `Restore()` |
| `Organizations.BusinessDate` | `BusinessDate` | null means the calendar date in the organization zone | `ChangeBusinessDate`: not in the future; `EnsureBusinessDateWithin` when the zone changes |
| `Memberships.Active`, `Users.Status` | bit and int | | `Deactivate` and `Reactivate` (bump `Version`), `User.Remove` (bumps `SecurityVersion`) |

### 4.4 `HistoryCountCache` (`Infrastructure/Setup/HistoryCountCache.cs`, new file, uncommitted)

- What it caches: only the change-log `Total` (an int). Key record `Key(OrganizationId, SettingsVersion, Scope, SeesPeople, Filter)`, where `Scope` is the text `all` for all-companies viewers or the sorted company ids joined with commas, a bar, then the sorted vehicle ids for scoped viewers, `SeesPeople` is the `people.view` permission, and `Filter` is the `HistoryFilter` record (Section, From, To, Text; value equality).
- Why it is safe without invalidation: every change-log row is written with a new organization `SettingsVersion`, and the actor's version is read before any data, so a key names one exact count; the 5-minute absolute expiry only bounds memory (`SizeLimit = 10_000` entries, each of size 1). `Clear()` exists but nothing calls it. It is a singleton (`SetupEndpoints.cs:15`) living in each API process; replicas never talk to each other.
- No caching happens when `actor.SettingsVersion` is null (an actor built by hand).
- Concurrency inside the cache: the value is a `Lazy<Task<int>>`; concurrent requests for the same key share one count. If the shared count fails or is cancelled the entry is removed, a waiter that did not create it counts for itself, and the creator rethrows.
- Test contract (`ChangeLogPagingTests.TheCountIsSkippedOnRequestAndCountedOncePerChange`): the first request counts (a command containing `COUNT(`); the same question at the same version issues one command fewer and returns the same `Total`; a different filter counts again; any change (renaming a company) moves the version so the next request counts again and includes the new row; `includeTotal=false` issues no `COUNT(` and returns `Total = null`.
- Open point: counts depend on current visibility (a vehicle's company, a viewer's scope), which only changes through logged writes, so the version key stays correct; a direct database edit would not be noticed until the entry expires.

### 4.5 The `ChangeLogVehicle` migration (new, uncommitted, `20261007052529`)
- Adds `OrganizationSettingsVersion.VehicleId` (uniqueidentifier, null), backfills it, then creates the indexes `IX_OrganizationSettingsVersion_OrganizationId_OccurredAt` and `IX_OrganizationSettingsVersion_OrganizationId_Section_VehicleId`. Backfill rules: sections `vehicles` and `investment` take `VehicleId = EntityId`; section `revenue` takes the record's vehicle from `RevenueRecords` (records are never deleted). Details and the T-SQL are in section 7.

---

## 5. Repository operations

Conventions: a command is one SQL round trip as counted by `DatabaseProbe` (`tests/api/AuthFactory.cs:42-128`). Counts marked ASSERTED are quoted from a test; counts marked DERIVED come from reading the LINQ (EF Core 10, SQL Server: collection includes and projected collections are a single joined query, `AsSplitQuery` is used only by the revenue week and dashboard vehicle loads (`RevenueRepository.cs:41,111`: one command for the vehicles, one for targets and one for away periods)) and are not pinned by a test. The visibility helpers expand to `IN (...)` lists built from the actor's company and vehicle ids. Every query below also carries the tenant filter `OrganizationId = <current>` (section 2).

### 5.1 Fixed cost around every authenticated request (DERIVED)

| Step | Queries | Source |
|---|---|---|
| JWT `OnTokenValidated`: `Users` by id, `TrustedDevices` by (user, device) | 2 | `Program.cs:122-123` |
| `OrganizationUseCase.Run`: `Memberships` by user (1); `Permissions` (= `Memberships` again (1) + `PersonRoles` joined to `Roles` for role names (1) + `PermissionOverrides` of the user (1)) are resolved ONLY when the call names a permission, so an actor-less read for any active member (appearance, preferences) costs 1 here, every call that names a permission 4, and the other any-member calls resolve permissions later in `SetupExecution.Actor` | 1 or 4 | `OrganizationPort.cs:44-49`, `OrganizationRepository.cs:24-34` |
| `SetupExecution.Actor`: `SetupDataScopes`, `SetupCompanyScopes`, `SetupVehicleScopes`, `Localizations.TimeZone`, `Organizations {BusinessDate, SettingsVersion}`, and `Permissions` (served from the request cache after the pipeline, resolved here for a call that named none); the actor-less overloads `Read/Write(permission, Func<Task<T>>)` used by the settings use cases skip all of these | 5 | `SetupExecution.cs:34-51` |
| Writes only: `BEGIN` Serializable, the use case reads, `RecordChange` loads `Organizations` (1), then one `SaveChanges` batch (INSERTs and UPDATEs, including the `Organizations` token UPDATE, the change-log INSERT and the `AuditEvents` INSERT), `COMMIT` | transaction + own queries | `OrganizationRepository.cs:59-73` |

- ASSERTED (new): the settings reads that every client loads at start cost 10 commands for `GET /setup/appearance` and 5 for `GET /setup/preferences`, both with 0 transactions (`PeopleQueryCostTests.SettingsReadsStayCheap`, `PeopleQueryCostTests.cs:190-205`: two token-check commands, one membership, the rest read the settings; the appearance count is 3 + Organizations + Localizations + the 4 of `Settings()` + Logos), and resolving settings tracks nothing (`SettingsReadsTrackNothing`, `:208-`).
- ASSERTED: the second `Permissions(userId)` call in a request issues 0 commands, and the first issues more than 0 (`PeopleQueryCostTests.PermissionsAreResolvedOncePerRequest`, `PeopleQueryCostTests.cs:132-148`, including a user id that does not exist).
- Per-request cache: `OrganizationRepository` (scoped) keeps `Dictionary<Guid, IReadOnlySet<string>> resolvedPermissions`; `ForgetResolved()` clears it (called before a retry).

### 5.2 `IOrganizationRepository` (`Application/OrganizationPort.cs:12-21`, `Infrastructure/OrganizationRepository.cs:11-46`)

| Method | Inputs | Query shape | Writes | Commands |
|---|---|---|---|---|
| `Task<Organization?> Get(ct)` | none | `Organizations` `SingleOrDefault` (filter `Id = current`), tracked | none (caller bumps the token) | 1 |
| `Task<OrganizationMembership?> Membership(userId, ct)` | user id | `Memberships WHERE UserId = @u` `SingleOrDefault`, tracked, no cache | none | 1 |
| `Task<IReadOnlySet<string>> Permissions(userId, ct)` | user id | cache lookup; else `Membership` + `PersonRoles JOIN Roles ON RoleId = Id WHERE UserId = @u` selecting role names + `PermissionOverrides WHERE UserId = @u` (tracked); role defaults come from the in-code `PermissionCatalog.DefaultsFor(roleName)` (the `RolePermissions` table is not read); resolved by `EffectivePermissionResolver.Resolve(defaults, overrides, active)`; inactive or missing membership gives an empty set | none | 3 first call, 0 after (ASSERTED > 0 then no more) |
| `Task<EffectiveSettings> Settings(userId, ct)` | user id | `Localizations`, `Brandings`, `SecurityPolicies` (then clamped to current bounds, `SecurityPolicyBounds.Clamp`) and `UserPreferences WHERE UserId = @u`, all `SingleOrDefault` and ALL `AsNoTracking` since phase 5, because resolving validates and canonicalizes the copies and a tracked copy would count as a change and trip the read path's guard (`OrganizationRepository.cs:36-45`); `EffectiveSettingsResolver.Resolve` validates each and applies the override rules | none | 4 (DERIVED) |
| `void ForgetResolved()` | none | clears the permission cache | none | 0 |

### 5.3 `IUnitOfWork.Audit` (`OrganizationRepository.cs:104-114`)
- `Audit(string action, string entity, object? before, object? after)` adds an `AuditEvents` row: `OrganizationId` and `ActorId` from the context, `Action`, `Entity`, `Before`/`After` = `JsonSerializer.Serialize(obj)` (default options, PascalCase) or null, `CorrelationId` from the context, `OccuredAt = clock.UtcNow`. The INSERT happens in the caller's `SaveChanges`. Action values written in the codebase: `revenue.recorded` (entity = record id), `setup.<section>` (entity = entity id), `person.created`, `person.updated`, `person.sign_in_details_changed`, `person.activated`, `person.deactivated`, `person.sessions_revoked` (entity = user id, written by `AccessUseCases.Audit`, not through `IUnitOfWork`), `organization.settings.updated` (entity = section name, `After` = `{value, reason}` JSON).

### 5.4 `ISetupExecution` (`Application/ISetupExecution.cs:9-18`, `Infrastructure/Setup/SetupExecution.cs`)
- `Task<T> Read<T>(string permission, Func<SetupActor, Task<T>> query, ct)`; `ReadAny<T>(IReadOnlyCollection<string> permissions, ...)`; `Write<T>(string permission, Func<SetupActor, Task<T>> command, ct)`; `WriteAny<T>(IReadOnlyCollection<string> permissions, ...)`. An empty permission string or list means any active member. Reads go through `unitOfWork.Read` (no transaction), writes through `unitOfWork.Execute` (Serializable plus retry). See 3.3 and 4.2 for the steps and the 5 actor queries. Two overloads without an actor were added in phase 5: `Read<T>(string permission, Func<Task<T>> query, ct)` and `Write<T>(string permission, Func<Task<T>> command, ct)` (`ISetupExecution.cs:15-18`, `SetupExecution.cs:23-27`), the same authorization, transaction and retry for work that needs only the organization context (the organization settings use cases); an empty permission still means any active member (`Required`, `SetupExecution.cs:29-30`).

### 5.5 `ISetupRepository` (`Application/Setup/ISetupRepository.cs`, `Infrastructure/Setup/SetupRepository.cs`; the class is uncommitted-modified)

Helpers: `VisibleVehicles(actor)` = `FleetVehicle WHERE AllCompanies OR CompanyId IN actor.CompanyIds OR Id IN actor.VehicleIds`; `VisibleCompanies(actor)` = `PsvCompany WHERE AllCompanies OR Id IN actor.CompanyIds OR EXISTS visible vehicle of the company`; `VisibleRecurring(actor)` = `RecurringItem WHERE AllCompanies OR ANY version has ANY allocation on a visible vehicle`. Pages are `Page<T>(Items, PageNumber, PageSize, Total)`; page size 1..100, page 1..100000.

| Method (inputs) | Query shape | Writes | Commands |
|---|---|---|---|
| `Companies(actor, page, pageSize)` | `VisibleCompanies` AsNoTracking; `COUNT`; then `ORDER BY Name, Id OFFSET/FETCH`, projecting `VehicleCount` (correlated COUNT of visible vehicles active today) and `Active = ArchivedOn null or > today` | none | 2 DERIVED |
| `Company(actor, id)` | `VisibleCompanies WHERE Id`, tracked | none | 1 |
| `CompanyOptions(actor)` | visible companies not archived at today, `ORDER BY Name, Id`, projected (Id, Name), AsNoTracking | none | 1 |
| `HasActiveVehicles(companyId, today)` | `EXISTS FleetVehicle WHERE CompanyId AND (LeftOn null or LeftOn > today)`; not scope filtered | none | 1 |
| `RecordedRevenueDays(vehicleId)` | `RevenueRecords WHERE VehicleId` `GROUP BY 1` `MIN/MAX(BusinessDate)`, one row | none | 1 |
| `CompanyNameExists(orgId, normalizedName, except)` | `EXISTS PsvCompany WHERE OrganizationId AND NormalizedName AND Id <> except` | none | 1 |
| `Vehicles(actor, page, pageSize)` | `COUNT`; page `ORDER BY Registration OFFSET/FETCH` projecting company name (scalar subquery), `Targets` ordered by Revision and `Away` ordered by LeftOn (collections in the same query); then the latest `RecurringVersion` per item that allocates to any page vehicle, with `StoppedFrom` (scalar subquery) and allocation vehicle ids, filtered in memory by `End >= today` and `StoppedFrom` null or after today to count items still posting per active vehicle; current target computed in memory | none | 3 DERIVED |
| `Vehicle(actor, id)` | `VisibleVehicles WHERE Id` with `Include(Targets)`, `Include(AwayPeriods)`, tracked | none | 1 |
| `VehiclesById(actor, ids)` | `VisibleVehicles WHERE Id IN ids` AsNoTracking to dictionary | none | 1 (batch, count independent of ids; ASSERTED by `RecurringQueryCostTests` equal reads for 2 and 200 shares) |
| `CompaniesById(actor, ids)` | same for `VisibleCompanies` | none | 1 |
| `RegistrationExists(orgId, registration)` | `EXISTS FleetVehicle WHERE OrganizationId AND Registration` | none | 1 |
| `VehicleOptions(actor)` | visible vehicles with `JoinedOn <= today AND (LeftOn null or > today)` and EXISTS company not archived at today, `ORDER BY Registration`, company name by scalar subquery; ignores away periods | none | 1 |
| `FirstDayOfWeek()` | `Localizations.FirstDayOfWeek` AsNoTracking, default 1 when no row | none | 1 |
| `Currency()` | `Localizations.Currency` AsNoTracking, default KES when no row | none | 1 |
| `Recurring(actor, page, pageSize)` | `COUNT` of `VisibleRecurring`; item ids page `ORDER BY (name of the highest-Revision version), Id OFFSET/FETCH`; latest `RecurringVersion` of those ids (`NOT EXISTS` higher revision) projecting `ExpenseItemName` and `StoppedFrom` by scalar subqueries, allocations limited to visible vehicles plus a total allocation count (so `Partial = shown <> total`); then `FleetVehicle (Registration, JoinedOn, LeftOn)` for the allocation vehicles; page order restored in memory | none | 4 DERIVED |
| `RecurringItem(actor, id)` | `VisibleRecurring WHERE Id` with `Include(Versions).ThenInclude(Allocations)`, tracked | none | 1 |
| `Report(actor, vehicle, from, through)` | (a) AsNoTracking `RecurringItem WHERE ANY version allocation on the vehicle` with `Include(Versions).ThenInclude(Allocations WHERE VehicleId = vehicle)`; (b) `RevenueRecords (BusinessDate, Amount) WHERE VehicleId AND BusinessDate BETWEEN first AND last`; (c) **(uncommitted)** approved, not removed petty cash expense entries of the vehicle in the window joined to `ExpenseItem` and `ExpenseCategory`, projected to `PostingDto` with `source = "pettycash"` (`SetupRepository.cs:254-261,269`); postings stepped in memory (`RecurringItem.DueBetween`) and concatenated; `first = max(from, JoinedOn)`, `last = min(through, Today)` then `LeftOn - 1` when the vehicle left | none | 3 DERIVED (2 before petty cash); reads and rows ASSERTED independent of item and share counts: +1 row per extra item version, +41 rows for 41 more items (`VehicleReportTests.cs:196-224`) |

| Method (inputs) | Query shape | Writes | Commands |
|---|---|---|---|
| `History(actor, filter, page, pageSize, before, includeTotal)` (uncommitted signature; HEAD returned `Page<HistoryEntry>` and took no `before` or `includeTotal`) | see 4.1: change-log query with visibility `WHERE`, `Narrow` filters, `ORDER BY Version DESC`, offset or `Version < before`, `TAKE pageSize + 1`, LEFT JOIN `Memberships` for actor names; optional extra reads: time zone (only when `from` or `to` given), matching actor ids (only when `text` given), vehicle-to-company map for people redaction (scoped viewers with people rows on the page), `COUNT` (only when `includeTotal` and not served by `HistoryCountCache`) | none | 1 page query + 0..4 extras; ASSERTED: count skipped on request and reused per version (`ChangeLogPagingTests.cs:100-141`), cost independent of log length (`:177-209`) |
| `ExpenseCategories(today, page, pageSize)` | `ExpenseCategory` AsNoTracking `COUNT`; page `ORDER BY Name, Id OFFSET/FETCH`; all `ExpenseItem WHERE CategoryId IN page ids ORDER BY Name, Id`; grouped in memory | none | 3 DERIVED |
| `ExpenseItemOptions(today)` | `ExpenseItem JOIN ExpenseCategory ON CategoryId = Id WHERE item and category not stopped at today ORDER BY category.Name, item.Name, item.Id` projecting (Id, Name, CategoryId, CategoryName, Bucket), AsNoTracking | none | 1 |
| `ActiveExpenseItem(id, today)` | same query filtered by item id, `SingleOrDefault` | none | 1 |
| `ExpenseCategory(id)`, `ExpenseItem(id)` | `SingleOrDefault` by id, tracked | none | 1 each |
| `ExpenseCategoryNameExists(orgId, normalizedName, except)` | `EXISTS ExpenseCategory WHERE OrganizationId AND NormalizedName AND Id <> except` | none | 1 |
| `ExpenseItemNameExists(orgId, categoryId, normalizedName, except)` | `EXISTS ExpenseItem WHERE OrganizationId AND CategoryId AND NormalizedName AND Id <> except` | none | 1 |
| `Investment(vehicleId)` | `VehicleInvestment WHERE VehicleId` AsNoTracking projecting the recorder name by scalar subquery on `Memberships` (FirstName + space + LastName, empty when missing); sum and ordering (`Date`, then `RecordedAt`) done in memory | none | 1 |
| `InvestmentEntry(id)` | `SingleOrDefault` by id, tracked | none | 1 |
| `Add(PsvCompany / FleetVehicle / RecurringItem / ExpenseCategory / ExpenseItem / VehicleInvestment)` | `db.Set<T>().Add` | INSERT on save (a new `FleetVehicle` also inserts its first `VehicleTarget`; a new `RecurringItem` inserts its first `RecurringVersion` and `RecurringAllocation` rows) | 0 |
| `Remove(VehicleInvestment)` | `db.Set<T>().Remove` | hard DELETE on save | 0 |
| `RecordChange(actor, section, entityId, before, after, reason)` | `SettingsChangeLog.Record(...)` (`organizations.Get` 1 query, `SettingsChanged()`, add `OrganizationSettingsVersion` with `Version = organization.SettingsVersion` and, for sections vehicles and investment, `VehicleId = entityId` (uncommitted)), then `unitOfWork.Audit("setup." + section, entityId.ToString(), before, after)` | UPDATE `Organizations` (token), INSERT change-log row, INSERT `AuditEvents` row | 1 read + 3 writes |

### 5.6 `IRevenueRepository` (`Application/RevenueContracts.cs:173-183`, `Infrastructure/RevenueRepository.cs`, `Infrastructure/RevenueDashboardCache.cs`, uncommitted-modified)

Updated 2026-10-08: the rows below were rewritten against the current files (`RevenueRepository.cs`, `RevenueContracts.cs`, `RevenueUseCases.cs`, `RevenueEndpoints.cs`, `RevenueDashboardCache.cs`, all **(uncommitted)**). Section 6 (replay order) was re-checked: unchanged except that refusal wording now comes from `PermissionCatalog.Refusal` and the 409 `current` cell is built from `RevenueDayRecord` and the target computed once.

| Method (inputs) | Query shape | Writes | Commands |
|---|---|---|---|
| `Week(actor, weekStart?, companyId?, vehicleId?, page?)` (`RevenueRepository.cs:17-83`, `BuildWeek` `:255-325`) | (1) `FirstDayOfWeek`; week start = the date moved back to the organization week start, must lie in the last 3650 days through the current week (else `ArgumentException`); (2) EVERY visible vehicle of the grid (optionally one company; active on some day of the week, `JoinedOn <= through AND (LeftOn null or > start)`; or the one vehicle by id in any week) with `Include(Targets <= through)` and `Include(AwayPeriods)`, `AsSplitQuery` (3 commands), `AsNoTracking`, `ORDER BY Registration, Id`; (2b) when a vehicle id was asked for and nothing came back, `EXISTS` to choose 404 vs empty; the page is then a slice of that list in memory (`Skip((page-1)*size).Take(size)`; no page = page 1 of 500); (3) company options (visible, not archived or having a vehicle active in the week) `ORDER BY Name, Id`; (4) the week's `RevenueRecords` of the LISTED vehicles only, projected to the grid columns (`RevenueDayRecord`: vehicle, date, amount, reason, note, corrected flag, version); (5) the whole grid's records summed in the database over each vehicle's active days (not away) and grouped by (date, and by vehicle only from today on) into `WeekTally` rows, which give `totalAmount`, `dayTotals` and which vehicle-days have a record; (6) company names of the listed vehicles; (7) `EarliestMissing` for every grid vehicle (one aggregate command, +1 when some vehicle has a hole) | none | 9 DERIVED (+1 with holes, +1 for the not-found check); ASSERTED: the same command counts at 2, 100 and 500 vehicles for the unpaged week, a page of 10 and the month dashboard, week rows read <= 10 per vehicle + 10, a page of 10 reads 3 rows fewer per vehicle outside the page (`RevenueComplexityTests.cs:21-59`); equal commands and <= 130 rows for 2 vs 12 vehicles x 150 days (`:87-110`) |
| `Dashboard(actor, period, companyId?)` (`RevenueRepository.cs:88-156`, served through `CachedRevenueRepository`) | period must be today, week or month (`ArgumentException` otherwise, never cached); (1) `FirstDayOfWeek`; (2) visible vehicles (optionally one company) active between `from` and `Today` with targets and the away periods overlapping the window, `AsSplitQuery` (3 commands); (3) ONE grouped query over the records on those vehicles' active days (not away), one row per vehicle: `SUM(Amount)`, `COUNT` recorded before today, `COUNT` recorded today, `COUNT` corrected after the date; revenue, expected, missing, captured and edited figures are combined per vehicle in memory from those rows and each vehicle's calendar (no record is loaded; was: all records loaded and summed in memory) | none | 5 DERIVED on a cache miss; ASSERTED: a cache hit issues fewer commands than a miss with identical JSON (`RevenueDashboardCacheTests.cs:24-39`); the remediation notes record 16 commands for a miss and 11 for a hit including session, membership, scope and version reads (`.claude/remediation/README.md:69`, not asserted by a test); commands flat from 2 to 500 vehicles (`RevenueComplexityTests.cs:21-59`) |
| `Vehicle(actor, id)` | `VisibleVehicles WHERE Id` with targets and away periods, tracked | none | 1 |
| `Record(actor, vehicleId, date)` | `VisibleVehicles WHERE Id = vehicleId` `SelectMany` `RevenueRecords WHERE VehicleId AND BusinessDate = date`, `SingleOrDefault`, tracked | none | 1 |
| `EarliestMissing(actor, vehicle, before)` (left the interface in 9276c51; the private set form still serves `Week`) | grouped aggregate over `RevenueRecords JOIN FleetVehicle` restricted to each vehicle's active days before the date (`MIN`, `MAX`, `COUNT` per vehicle); a contiguous history answers from that one row; a vehicle with a hole or an overlapping away period reads its own `(VehicleId, BusinessDate)` rows | none | ASSERTED 1 command and at most 2 rows for a contiguous 120-day history; ASSERTED 2 commands for a history with a hole (`RevenueComplexityTests.cs:44-64`) |
| `Add(record)` | `db.Set<RevenueRecord>().Add` | INSERT on save | 0 |
| `RecordChange(actor, entityId, before, after, reason)` (`RevenueRepository.cs:241-248`) | reads the record's `VehicleId` from the tracked set (`db.Set<RevenueRecord>().Local.Single`, so the record must already be tracked), then `SettingsChangeLog.Record(..., "revenue", entityId, before, after, reason, vehicleId)` (`organizations.Get`, `SettingsChanged()`, change-log row with `section = revenue` and `vehicleId` set) and `Audit("revenue.recorded", entityId.ToString(), before, after)` | UPDATE `Organizations`, INSERT change-log row, INSERT `AuditEvents` row | 1 read + 3 writes |

`CachedRevenueRepository` (`Infrastructure/RevenueDashboardCache.cs:89-109`, registered as `IRevenueRepository` with `RevenueRepository` and the singleton `RevenueDashboardCache` behind it, `Api/RevenueEndpoints.cs:11-14`) caches `Dashboard` only; every other method passes straight through. `RevenueDashboardCache` (`RevenueDashboardCache.cs:16-86`, **uncommitted**): in-process `MemoryCache`, `SizeLimit = 10_000` (each entry size 1), absolute expiry **60 seconds**, key `(OrganizationId, SettingsVersion, Today = business date, Period, CompanyId?, Scope)` where `Scope` is `all` for an all-companies viewer, else the SHA-256 hex of the sorted company ids, a bar, then the sorted vehicle ids; the value is the in-flight or finished `Task<RevenueDashboardDto>` holding UNMASKED figures (`RevenueUseCases.Visible` masks per request after it, `RevenueUseCases.cs:25-41`). Nothing is cached when `actor.SettingsVersion` is null. A failed or cancelled computation removes its entry; waiting callers whose creator failed compute for themselves; a cancelled waiter does not cancel the others. There is no explicit invalidation: every write that changes a figure's inputs (revenue, a vehicle's dates, targets, company or time away, the business date, the first day of the week) writes a change-log row through `SettingsChangeLog.Record`, which moves `SettingsVersion`, part of the key, so a stale entry is simply never read again; a direct database edit is not noticed for up to 60 s, and each replica keeps its own copy. A write that skipped `SettingsChangeLog.Record` would serve stale figures for up to 60 s.

### 5.7 Persistence access that does not go through a repository interface (the Python service must reproduce all of it)

| Component (file:line) | Reads | Writes and rules |
|---|---|---|
| JWT `OnTokenValidated` (`Program.cs:115-127`) | `Users` by id; `TrustedDevices` by (UserId, DeviceId) | none; token valid only if user `Status = Active`, claim `version` equals `SecurityVersion`, device exists, not `Revoked`, and `TrustExpiresAt` is null or in the future |
| `AuthAccounts.Find` (`Application/Authentication/AuthAccounts.cs:9-11`) | `Users WHERE PhoneNumber = normalized` (no query when the number does not normalise) | none |
| `SignInService.SignIn` and unlock (`Application/Authentication/SignInService.cs:11-56`) | user by phone, `TrustedDevices`, membership then `SecurityPolicies` for the lockout policy | wrong PIN on a trusted device: `FailedAttempts++`, pause for `LockoutMinutes` at `LockoutThreshold`; wrong PIN on an untrusted device: `UntrustedFailedAttempts++` up to `SignInService.UntrustedAttemptLimit = 10` (`SignInService.cs:9`), after which the answer equals an unknown number; correct PIN on an untrusted device issues a `NewDevice` code (HTTP 202); correct PIN on a trusted device clears the pause and issues tokens. A PIN hash is always verified (`DummyHash` for unknown users) |
| `AuthCodes.Issue` (`Application/Authentication/AuthCodes.cs:17-41`) | `VerificationCodes` of the user and purpose; all codes of the user | marks older codes of that purpose consumed; inserts a code: 6 digits (HMAC-SHA256 hex stored), `ExpiresAt = now + 10 min`; refuses when a non-withdrawn code of that purpose is under 1 minute old (not in development mode), or when 5 in the last hour or 10 in the last 24 hours exist; it returns the code and the mail message, which is sent only after the attempt commits (`AuthResult.Mail`, `AuthUnitOfWork.cs:37-47`) |
| `AuthCodes.Matching` and `Consume` (`AuthCodes.cs:43-63`) | codes of (user, device, purpose) not consumed, newest first | a wrong code does `FailedAttempts++` and consumes the code at 5; success sets `Consumed` |
| `SessionTokens.Issue` (`Application/Authentication/SessionTokens.cs:11-63`; leaves lockout alone, callers clear it) | active `Memberships` (any organization), `SecurityPolicies`, `PersonRoles`, `Roles`, `PermissionOverrides` (all with filters ignored) | inserts a `RefreshTokens` row: random 48 bytes base64, stored as HMAC-SHA256 hex, `ExpiresAt = now + policy.RefreshTokenDays`; returns a JWT valid `AccessTokenMinutes` |
| `SignInService.VerifyDevice` (`SignInService.cs:58-72`), `PinSetupService.Request` and `CompletePin` (`PinSetupService.cs:10-15,25-48`) | user, codes | `VerifyDevice`: consume `NewDevice` code, clear lockout and untrusted counter, trust device, issue tokens. `CompletePin`: consume code, `SetPin` (hash, untrusted counter 0, `SecurityVersion++`), clear lockout, revoke all the user's refresh tokens, consume all outstanding codes, trust device, issue tokens |
| `SessionService.Refresh`, `SignOut`, `RevokeDevice` (`Application/Authentication/SessionService.cs:10-59`) | `RefreshTokens` by hash, user, device | rotation: old token revoked, new one issued; a revoked token presented again revokes all tokens of that device; an inactive user revokes all tokens of the user; `RevokeDevice` revokes the trusted device, its tokens and its unconsumed codes |
| `VerificationMailer.Withdraw` (`Security.cs:162-177`) | `VerificationCodes` by id (own scope, no transaction) | `Withdraw()`: `Consumed = 1`, `ExpiresAt = CreatedAt` when mail delivery failed |
| `AccessUseCases` (`Application/AccessUseCases.cs`) | people list: visible memberships (`PeopleVisibility.People`), then per page one query each for `Users`, `PersonRoles JOIN Roles`, `PermissionOverrides`, `SetupDataScopes`, `SetupCompanyScopes`, `SetupVehicleScopes` (+1 vehicle-to-company map for scoped viewers); `ScopeOptions` 2 queries; `Me` 2 queries; uniqueness check `Users WHERE (PhoneNumber OR Email) AND Id <> self`; owner check `PersonRoles JOIN Roles WHERE Name = Owner` | create person: INSERT `Users`, `Memberships`, `PersonRoles`, scope rows, `PermissionOverrides` (only deviations from role defaults), `AuditEvents`, change-log row. Update: DELETE all of the person's `PersonRoles`, `PermissionOverrides` and three scope tables, then re-INSERT; bump `Membership.Version` when something changed; bump `SecurityVersion` for name, role or single-permission changes or sign-in detail changes (the latter also revokes all trusted devices and refresh tokens). `SetActive`: `Reactivate` plus `User.Status = Active`, or `Deactivate` plus `User.Remove()` plus revoke sessions. `SignOut`: revoke sessions. `Roles`: `EnsureRoles` inserts missing catalog roles (a write behind a GET) |
| `OrganizationSettingsUseCases` (`Application/Settings/OrganizationSettingsUseCases.cs`, behind the transport-only `Api/OrganizationEndpoints.cs`) | settings GET: `Organizations`, `Localizations`, `Brandings`, `SecurityPolicies` plus `Settings()` (4 queries); appearance GET: `Organizations`, `Localizations`, `Settings()`, `Logos`; preferences GET: `UserPreferences`, `Localizations` | PUT settings section: merge posted fields onto the stored section (or a new default entity, legacy field names mapped), validate, then `SettingsChangeLog.Record` (version bump plus change-log row) and an `AuditEvents` row, all inside the serializable `UnitOfWork.Execute` with the change-log retry (since phase 5, **uncommitted**; was no explicit transaction); a refused or unchanged save clears the change tracker and writes nothing; PUT logo upserts `Logos`, DELETE logo removes the row, both logged; PUT preferences upserts `UserPreferences` after `EnsureAllowed` (no change-log row) |
| `Program.cs` startup and CLI (`:181-240`) | `__EFMigrationsHistory` existence check; unassigned users count | `--migrate`, development auto-migrate, `--provision-user`, `--remove-user` (sets `Removed`, bumps `SecurityVersion`, revokes refresh tokens) |
| `DatabaseHealthCheck` (`Infrastructure/DatabaseHealthCheck.cs:6-22`) | `db.Database.CanConnectAsync` (opens a connection; no table is read) | none; used by `/health/ready` (tag ready, 10 s timeout); `/health/live` skips the database |

### 5.8 Every count or cost assertion in the tests, with its scenario

| Test (file:line) | Scenario | Assertion |
|---|---|---|
| `ChangeLogAndScopeTests.WritesToDifferentRecordsRetryWhenOnlyTheChangeLogCollides` (`:113-140`) | company rename while another writer bumps `Organizations.SettingsVersion` between read and write | 1 collision: HTTP 200 and 2 transactions; 4 collisions: HTTP 409 and 4 transactions |
| `ChangeLogAndScopeTests.ARetryChecksAccessAgain` (`:143-160`) | permission denied or membership deactivated between attempts | 2 transactions, HTTP 403, data unchanged |
| `ChangeLogAndScopeTests.AStaleRecordStillConflictsAtOnce` (`:162-176`) | `Memberships.Version` bumped between read and write | HTTP 409, 1 transaction |
| `PeopleQueryCostTests.APageOfPeopleLoadsOnlyThatPage` (`:49-72`) | 204 people, page 2 of 25 | rows read < 250 (commands printed only); one person: rows read < 40 |
| `PeopleQueryCostTests.SavingAPersonCountsItsQueries` (`:150-163`) | update a person among 204 | exactly 1 transaction (commands printed only) |
| `PeopleQueryCostTests.SetupReadsOpenNoTransaction` (`:165-182`) | seven read routes; `/setup/access/roles` | 0 transactions; roles listing: 1 transaction |
| `PeopleQueryCostTests.PermissionsAreResolvedOncePerRequest` (`:132-148`) | `Permissions` twice for an unknown user | first call > 0 commands, second call 0 |
| `RecurringQueryCostTests.SavingAndStoppingReadTheSameNumberOfTimesForTwoOrTwoHundredVehicles` (`:32-57`) | create, revise, stop an item with 2 vs 200 shares | equal SELECT counts for create, revise and stop, and equal command count for stop |
| `RevenueComplexityTests.TheWeekFindsTheEarliestMissingDayFromOneAggregateRowWhateverTheHistoryLength` (`:63-82`, renamed and rewritten in 9276c51) | one vehicle's week, 120-day history, contiguous vs one hole | contiguous: `EarliestMissing` null and <= 30 rows read; hole: the missing date, one command more than the contiguous week |
| `RevenueComplexityTests.WeekAndDashboardIssueTheSameCommandsWhateverTheFleetSizeAndHistory` (`:66-84`) | 2 vehicles x 10 days vs 12 vehicles x 150 days; month dashboard before and after another 12-vehicle fleet | equal command counts; week reads <= 130 rows for 12 vehicles; `EarliestMissing` null |
| `RevenueComplexityTests.WeekAndDashboardCommandsStayFlatFromTwoToFiveHundredVehicles` (`:21-59`) | 2, 100, 500 vehicles; unpaged week, a page of 10, month dashboard | one distinct (week, page, month) command triple across all three fleets; week rows <= 10 per vehicle + 10; a page of 10 reads 3 rows fewer per vehicle outside the page and <= 3 per vehicle + 80; month rows <= 3 per vehicle + 10 |
| `VehicleReportTests.TheReportReadsTheSameNumberOfTimesHoweverManyItemsAndOtherSharesThereAre` (`:195-224`) | repeat call; item shared with 100 other vehicles; 40 more daily items | same SELECT count every time; rows read +1, then +41 |
| `ChangeLogPagingTests` (uncommitted, new) (`:99-245`) | paging, counting, scoped revenue, constant cost, SQL shape | see 4.1 and 4.4 |
| `RevenueDashboardCacheTests` (uncommitted, new, `tests/api/RevenueDashboardCacheTests.cs:24-260`) | repeated dashboards, fresh figures after a revenue save, a retire, a business-date move, a first-day-of-week change and a company move; owner vs scoped clerk and owner vs office admin in both orders; two organizations; 16 concurrent callers; a failed and a cancelled computation; no settings version | a hit issues fewer commands than a miss with identical JSON; every listed change gives fresh figures; one computation per key; entries never shared across organizations or scopes; masking per viewer; nothing kept without a version |
| `RevenueWeekPagingTests` (uncommitted, new, `tests/api/RevenueWeekPagingTests.cs:53-230`) | seven vehicles in two companies, pages of 2, company filter, a scoped clerk, `vehicleId`, invalid paging, unpaged shape | pages concatenate to the unpaged list; whole-grid figures identical on every page; `vehicleId` never paged; 400 for `pageSize=101`, `pageSize=0`, `page=0`, `page=100001`; key order and types of the response |
| `PeopleQueryCostTests.SettingsReadsStayCheap` (`:190-205`) | clerk reads `/setup/appearance` and `/setup/preferences` | exactly 10 and 5 commands, 0 transactions |
| `ChangeLogAndScopeTests.SettingsWritesRetryWhenOnlyTheChangeLogCollides` (`:142-185`, new) | branding, business date and logo saves with one interleaved change-log bump; then four | 1 collision: 200, 2 transactions, version +2 and the entry carries it; 4 collisions: 409 and 4 transactions |
| `RevenueCaptureTests.AConcurrentUpdateRaceReturns409NotAServerError` (`:250-267`; the file now writes a vehicle's early retirement directly and moves the settings version by hand, `:375-390`) | `RevenueRecords.Version` bumped between read and write | HTTP 409, title This day was changed by another save., 1 transaction |
| `ProductionStartupTests.ProductionStartupDoesNotCreateOrMigrateTheSchema` (`:58-73`) | non-Testing start against an empty database | startup SQL reads `Users`, never runs `CREATE TABLE` nor touches `__EFMigrationsHistory` |

---

## 6. Idempotency and replay (revenue capture)

### 6.1 What is stored
| Aspect | Current behaviour | Source |
|---|---|---|
| Idempotency key column | none. There is no request id, client id or key in `RevenueRecords`, the request body or a header | `Domain/Revenue.cs:54-76`, `RevenueContracts.cs:154` |
| Record id | generated by the server (`Guid.NewGuid()` in `RevenueRecord`), returned as `RevenueSaved.Id`; never accepted from the client | `Revenue.cs:64`, `RevenueContracts.cs:137` |
| Natural key | `(OrganizationId, VehicleId, BusinessDate)` UNIQUE index `IX_RevenueRecords_OrganizationId_VehicleId_BusinessDate` | `RevenueModel.cs:17` |
| Route and body | `PUT /setup/revenue/{vehicleId}/{date}` with `{amount, reason, note, version}`; response 200 `{id, version}` | `RevenueEndpoints.cs:51-53`, `RevenueContracts.cs:154` |
| Replay test | `RevenueRecord.Matches(entry)`: `Amount == entry.Amount` (decimal equality) and `Reason == entry.Reason` and `Note` equal (ordinal) to the trimmed note, where a blank note is null | `Revenue.cs:98-101` |

### 6.2 Decision order in `RevenueUseCases.Save` (`Application/RevenueUseCases.cs:44-102`)
| # | Check | Outcome |
|---|---|---|
| 1 | pipeline: active membership holding `revenue.capture` or `revenue.correct`; serializable transaction | 403 otherwise |
| 2 | `SaveRevenue.Entry()` and `RevenueEntry.Validate()`: reason text maps Garage=1, Arrest=2, No Crew or NoCrew=3, Other=4, blank=none; amount xor reason; money greater than 0, at most 999 999 999 999.99, 2 decimals; note at most 80 characters, required for Other, forbidden for others | 400 |
| 3 | vehicle visible in the actor's scope | 404 |
| 4 | existing record for (vehicle, date) in scope | continues |
| 5 | existing and `Matches(entry)`: return `(existing.Id, existing.Version)` and write nothing. Happens before every later check, so it works after the day closed, whatever `version` the client sent, and creates no change-log or audit row | 200, idempotent replay |
| 6 | `date == default` or `date > Today` | 400 (future date) |
| 7 | vehicle not active on that date (not joined, left, or away) | 400 (message differs for away) |
| 8 | reason present without `revenue.no_earnings`; no record yet without `revenue.capture`; existing record on a past day without `revenue.correct` | 403 naming the missing permission; these come before any state disclosure |
| 9 | existing and `input.Version != existing.Version` (a missing version counts as different) | 409 `RevenueConflictException`, body carries `current` (the stored cell: date, status, expected, amount, reason, note, canEdit, editedAfterCapture, version) |
| 10 | (removed by 9276c51: a new record no longer waits for earlier missing days) | was 400 with `earliestMissing` |
| 11 | write: new `RevenueRecord` (`Version = 1`) or `Replace` (`Version++`; `CorrectedAfterDate = true` when `BusinessDate < Today`; `BusinessDate` cannot change); change-log row (section `revenue`, entity = record id, vehicle set) with reason Recorded revenue for REG on d MMM yyyy, Recorded no revenue ... : reason, Updated revenue ... or Corrected revenue ...; audit `revenue.recorded` | 200 `{id, version}` |

### 6.3 Concurrency outcomes that involve the constraints
| Situation | Mechanism | Result |
|---|---|---|
| two writers insert the same (vehicle, date) | the loser's INSERT violates the unique index (`DbUpdateException`) | 409 `A conflicting record exists. Reload before saving.` without `current` (`RevenueCaptureTests.TwoClerksCapturingTheSameDayAtOnceGetAConflictNotAServerError`, `:223-248`); the failed transaction rolls back everything, so an immediate retry succeeds |
| two writers update the same record | `RevenueRecords.Version` token mismatch (`DbUpdateConcurrencyException`) | 409 `This day was changed by another save.`, 1 transaction, no retry (`:250-267`) |
| writers of different records collide on `Organizations.SettingsVersion` | `UnitOfWork` retry loop (3.3): the retry re-reads, so a duplicate of an identical entry ends as a replay and a different one as a version conflict | 200 or 409 |
| offline replay of an identical entry after the day closed | step 5 | 200 with the stored id and version (`:189-221`); after another person corrected the day, the clerk's identical entry is no longer a replay and gets 403 (clerk lacks `revenue.correct`) with no stored data disclosed |
| client repeats with the same version after its own success | version is now higher | 409 with `current` |

### 6.4 Other idempotency-like behaviours elsewhere
- Verification codes are not idempotent: a request issues a new code and consumes older ones of the same purpose (cooldown, hourly and daily caps).
- Refresh tokens rotate; presenting a revoked token revokes all tokens of that device.
- People lifecycle: repeating an already completed activate or deactivate returns the id without a version check or change-log row (`AccessUseCases.cs:208-210`).
- Setup creates have no key: uniqueness comes from `IX_PsvCompany_OrganizationId_NormalizedName`, `IX_FleetVehicle_OrganizationId_Registration`, `IX_ExpenseCategory_OrganizationId_NormalizedName`, `IX_ExpenseItem_OrganizationId_CategoryId_NormalizedName`, `IX_Roles_OrganizationId_Name`, `IX_Users_Email`, `IX_Users_PhoneNumber` (filtered), `IX_Organizations_Slug`.
- Planned design note: `apps/api-python/docs/03-database.md` mentions revenue idempotency keys and client-supplied ids; the .NET contract has neither (open question in section 11).

---

## 7. Raw SQL inventory

Application code contains no raw SQL except the two `__EFMigrationsHistory` statements in `Program.cs` (7.7). Everything else is in migrations. All of it is T-SQL (square-bracket quoting) unless stated.

### 7.1 `NormalizeSecurityPolicy` (`Migrations/20260929200500_NormalizeSecurityPolicy.cs`)
- `public const string ClampSql` (`:13-23`), executed by `migrationBuilder.Sql(ClampSql)` (`:28`) before the CHECKs are added. Plain `CASE`, so it also runs on SQLite. Frozen: later bounds need a new migration.
```
UPDATE [SecurityPolicies] SET
    [PasswordMinLength] = CASE WHEN [PasswordMinLength] < 12 THEN 12 WHEN [PasswordMinLength] > 128 THEN 128 ELSE [PasswordMinLength] END,
    [PasswordHistory] = CASE WHEN [PasswordHistory] < 0 THEN 0 WHEN [PasswordHistory] > 24 THEN 24 ELSE [PasswordHistory] END,
    [PinLength] = CASE WHEN [PinLength] < 4 THEN 4 WHEN [PinLength] > 8 THEN 8 ELSE [PinLength] END,
    [LockoutThreshold] = CASE WHEN [LockoutThreshold] < 3 THEN 3 WHEN [LockoutThreshold] > 10 THEN 10 ELSE [LockoutThreshold] END,
    [LockoutMinutes] = CASE WHEN [LockoutMinutes] < 1 THEN 1 WHEN [LockoutMinutes] > 60 THEN 60 ELSE [LockoutMinutes] END,
    [AccessTokenMinutes] = CASE WHEN [AccessTokenMinutes] < 1 THEN 1 WHEN [AccessTokenMinutes] > 15 THEN 15 ELSE [AccessTokenMinutes] END,
    [RefreshTokenDays] = CASE WHEN [RefreshTokenDays] < 1 THEN 1 WHEN [RefreshTokenDays] > 90 THEN 90 ELSE [RefreshTokenDays] END,
    [IdleUnlockSeconds] = CASE WHEN [IdleUnlockSeconds] < 30 THEN 30 WHEN [IdleUnlockSeconds] > 3600 THEN 3600 ELSE [IdleUnlockSeconds] END
```
- Then 8 `AddCheckConstraint` calls (`:30-68`), names and expressions as listed in 1.10. Down only drops the checks; the clamped values stay.
- Tests: `MigrationSnapshotTests.NormalizingBringsAnOlderPolicyIntoTheCurrentBounds` (`MigrationSnapshotTests.cs:36-55`) inserts out-of-range values with `PRAGMA ignore_check_constraints = 1`, runs `ClampSql` through `ExecuteSqlRawAsync` and expects `(12, 24, 4, 3, 60, 1, 90, 30)` for (PasswordMinLength, PasswordHistory, PinLength, LockoutThreshold, LockoutMinutes, AccessTokenMinutes, RefreshTokenDays, IdleUnlockSeconds); `TheDatabaseRefusesAnOutOfRangePolicy` (`:58-65`) expects an exception for `UPDATE "SecurityPolicies" SET "LockoutMinutes" = 1440`; `AccessMigrationsRunInOrder` (`:22-32`) pins the order AccessIntegrity then NormalizeSecurityPolicy before ExpenseCatalogAndInvestment.

### 7.2 `ExpenseCatalogAndInvestment` (`Migrations/20260929210000_ExpenseCatalogAndInvestment.cs`)
| Lines | Statement | Purpose | Test |
|---|---|---|---|
| `:158-160` (Up) | `UPDATE [RecurringVersion] SET [Bucket] = CASE WHEN [Category] = 2 THEN 1 ELSE 2 END WHERE [Kind] = 1 AND [Category] IS NOT NULL AND [Bucket] IS NULL;` | backfill: legacy cost category RepairsAndUpkeep (2) becomes bucket RepairsAndMaintenance (1); RunningCosts, CrewCosts, FixedCommitments become RecurringCharges (2); only the new column is filled | none |
| `:164-166` (Up) | `IF NOT EXISTS (SELECT 1 FROM [RecurrenceFrequencyLookup] WHERE [Id] = 4) INSERT INTO [RecurrenceFrequencyLookup] ([Id], [Name]) VALUES (4, N'Yearly');` | adds lookup row 4, tolerant of a rolled-back database that kept it | none (model-built test databases get the row from `HasData`) |
| `:255-257` (Down) | `DELETE FROM [RecurrenceFrequencyLookup] WHERE [Id] = 4 AND NOT EXISTS (SELECT 1 FROM [RecurringVersion] WHERE [Frequency] = 4);` | rollback keeps row 4 when yearly schedules exist | none |

### 7.3 `RetireOldCostCategories` (`Migrations/20261004110000_RetireOldCostCategories.cs`)
- No raw SQL: `DropForeignKey FK_RecurringVersion_CostCategoryLookup_Category`, `DropTable CostCategoryLookup`, `DropIndex IX_RecurringVersion_Category`, `DropColumn Category` on `RecurringVersion`. The category values are lost; reporting relies on the `Bucket` column that 7.2 backfilled. Down recreates the nullable `Category` int, the table (Id int, Name nvarchar(max)) with rows 1 RunningCosts, 2 RepairsAndUpkeep, 3 CrewCosts, 4 FixedCommitments, the index and the FK, but cannot restore the lost values. No test.

### 7.4 `ChangeLogIsFilterable` (`Migrations/20261004151525_ChangeLogIsFilterable.cs`)
- EF-generated `ALTER COLUMN`: `OrganizationSettingsVersion.OccurredAt` datetimeoffset to datetime2 NOT NULL, `EffectiveFrom` datetimeoffset to datetime2 NULL. The dropped offset was always zero (the entity refuses others); Down restores datetimeoffset. No test of the conversion itself; the model converter is exercised by every history test.

### 7.5 `UntrustedFailedAttempts` (`Migrations/20261006084351_UntrustedFailedAttempts.cs`)
- `AddColumn Users.UntrustedFailedAttempts int NOT NULL default 0`, `Users.Version bigint NOT NULL default 0`, `RefreshTokens.Version bigint NOT NULL default 0`. These create SQL Server default constraints on migrated databases only.

### 7.6 `ChangeLogVehicle` (`Migrations/20261007052529_ChangeLogVehicle.cs`, UNCOMMITTED; verified on 2026-10-08 against the final 84-line file, which matches the text below)
- `Up`: `AddColumn VehicleId uniqueidentifier NULL` on `OrganizationSettingsVersion`; then `Sql(Batched(BackfillVehiclesSql), suppressTransaction: true)`; `Sql(Batched(BackfillRevenueSql), suppressTransaction: true)`; then two `Sql(CreateIndex(...), suppressTransaction: true)` calls. `Down`: `DropIndex` both, `DropColumn VehicleId`.
```
BackfillVehiclesSql (public const):
UPDATE [OrganizationSettingsVersion] SET [VehicleId] = [EntityId]
WHERE [VehicleId] IS NULL AND [Section] IN ('vehicles', 'investment')

BackfillRevenueSql (public const):
UPDATE [OrganizationSettingsVersion] SET [VehicleId] = (
    SELECT [r].[VehicleId] FROM [RevenueRecords] AS [r]
    WHERE [r].[OrganizationId] = [OrganizationSettingsVersion].[OrganizationId] AND [r].[Id] = [OrganizationSettingsVersion].[EntityId])
WHERE [VehicleId] IS NULL AND [Section] = 'revenue' AND EXISTS (
    SELECT 1 FROM [RevenueRecords] AS [r]
    WHERE [r].[OrganizationId] = [OrganizationSettingsVersion].[OrganizationId] AND [r].[Id] = [OrganizationSettingsVersion].[EntityId])

Batched(update) (public static, T-SQL only):
WHILE 1 = 1
BEGIN
    <update with "UPDATE [OrganizationSettingsVersion]" replaced by "UPDATE TOP (5000) [OrganizationSettingsVersion]">;
    IF @@ROWCOUNT = 0 BREAK;
END

CreateIndex(name, columns) (private static, T-SQL only; ONLINE only on EngineEdition 3, 5 or 8):
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE [name] = N'<name>' AND [object_id] = OBJECT_ID(N'[OrganizationSettingsVersion]'))
BEGIN
    IF CAST(SERVERPROPERTY('EngineEdition') AS int) IN (3, 5, 8)
        EXEC(N'CREATE INDEX [<name>] ON [OrganizationSettingsVersion] (<columns>) WITH (ONLINE = ON)');
    ELSE
        CREATE INDEX [<name>] ON [OrganizationSettingsVersion] (<columns>);
END
```
- Index calls: `IX_OrganizationSettingsVersion_OrganizationId_OccurredAt` on `[OrganizationId], [OccurredAt]`; `IX_OrganizationSettingsVersion_OrganizationId_Section_VehicleId` on `[OrganizationId], [Section], [VehicleId]`.
- Rationale in the file: EF cannot do the backfill because change-log rows are write-once; the statements are frozen, plain SQL, and each only touches rows still unset so the loop ends and can be rerun.
- Tests: `ChangeLogPagingTests.TheBackfillGivesEarlierRowsTheirVehicle` (`ChangeLogPagingTests.cs:247-280`, new) writes rows through the API, nulls `VehicleId`, runs both consts on SQLite, expects the original vehicle ids back, expects the second run to affect 0 rows, and asserts the `Batched` text contains `UPDATE TOP (5000) [OrganizationSettingsVersion] SET [VehicleId] = (` and `[VehicleId] IS NULL AND [Section] = 'revenue' AND EXISTS`. The T-SQL wrappers (`WHILE`, `TOP`, `@@ROWCOUNT`, `sys.indexes`, `SERVERPROPERTY`, `EXEC`) run only in `SqlServerTests.SqlServerMigrationsApplyWhenCiProvidesServer`, which needs `SQLSERVER_TEST_CONNECTION` and is excluded locally.

### 7.7 `Program.cs` (the only application raw SQL)
| Lines | Statement | When | Test |
|---|---|---|---|
| `:191-195` | `IF OBJECT_ID(N'[__EFMigrationsHistory]') IS NOT NULL UPDATE [__EFMigrationsHistory] SET [MigrationId] = N'20260924172309_OrganizationsAndFleet' WHERE [MigrationId] = N'20260924172309_Phase1Setup'` | `--migrate`, only if the database exists | none |
| `:205-209` | same statement | development auto-migrate on a local database, only if the database exists | none |
- Purpose: an earlier migration id (`Phase1Setup`, a plan identifier) was renamed to `OrganizationsAndFleet`; the shim keeps already-migrated databases consistent. Pre-dates the first PostgreSQL cutover and is not needed in a new database; a data migration from SQL Server must not carry the `Phase1Setup` history row.

### 7.8 Other SQL-dialect text in code
| Where | Text | Note |
|---|---|---|
| `SetupRepository.cs:371-375` | `EF.Functions.Like(..., pattern)` where the pattern is the search text with `[` replaced by `[[]`, `%` by `[%]`, `_` by `[_]` | SQL Server bracket escaping of LIKE wildcards; case-insensitive only because of the database collation |
| `AuthDb.cs:45` | `HasFilter("[PhoneNumber] <> ''")` | filtered unique index |
| `OrganizationModel.cs:34` | `HasFilter("[Active] = 1")` | filtered unique index |
| `OrganizationModel.cs:43` | `HasCheckConstraint($"CK_SecurityPolicies_{Column}", $"[{Column}] BETWEEN {Min} AND {Max}")` | generated from `SecurityPolicyBounds.All` |
| tests only | `PRAGMA ignore_check_constraints`, `CREATE TRIGGER other_clerk BEFORE INSERT ON RevenueRecords ...`, `DatabaseProbe.Interleave` update strings such as `UPDATE "Organizations" SET "SettingsVersion" = "SettingsVersion" + 1` | SQLite test harness; the trigger simulates a competing insert |

---

## 8. Seed and provisioning

### 8.1 `DemoSeed.Run(AuthDb)` (`Infrastructure/DemoSeed.cs`, development only)
| Aspect | Behaviour |
|---|---|
| When it runs | `Program.cs:202-213`: not in the Testing environment; only when `options.DevelopmentMode` (Development environment and a local database: connection string containing localhost, (localdb), 127.0.0.1, :memory:, mode=memory or `.db`) after `MigrateAsync`, and only when environment variable `ALLOW_DEMO_SEED` equals `true` (case-insensitive). Tests call it through `AuthFactory.SeedDemo` (`tests/api/AuthFactory.cs:195-200`) after `AddOrganization` |
| Guards | `db.Provisioning = true` for the run (bypasses tenant write rules, reset in `finally`); idempotent: adds only what is missing, so a PIN changed or reset during development survives restarts, an expense catalog edited during development survives, and a scope chosen during development survives. `SingleOrDefault` on organizations throws if more than one exists |
| Organization | if none exists: `Organizations` row Slug `demo-fleet`, Name `Demo Fleet` (SettingsVersion 1) plus default `Localizations` (en-GB, Africa/Nairobi, KES, first day 1), `Brandings` (XCODE defaults), `SecurityPolicies` (defaults). Tests pre-create the same slug with TimeZone UTC |
| Roles | `UserProvisioning.EnsureRoles`: `Owner`, `Office admin`, `Fleet manager`, `Revenue clerk` |
| Users (only added when the email is missing; `Status` is set to Active on every run, which also revives a removed demo user) | `+254733520614 antony.maina@shamayah.co.ke` PIN 4826, role Owner; `+254722410355 peter.otieno@zurigenesis.co.ke` PIN 1379, Office admin; `+254700111222 brian.mwangi@metrotrans.co.ke` no PIN (sets one with an email code), Fleet manager; `+254712345678 wanjiru.kamau@zurigenesis.co.ke` PIN 2580, Revenue clerk. PINs are hashed with `PinHasher.Hash` (PBKDF2-SHA256, 210 000 iterations) |
| Memberships and role links | one `Memberships` row per user if missing: FirstName and LastName from the two dot-separated parts of the email local part, capitalised (Antony Maina, Peter Otieno, Brian Mwangi, Wanjiru Kamau); one `PersonRoles` row if the user has none |
| Scope | Owner, Office admin and Fleet manager get one `SetupDataScopes` row `AllCompanies = 1` when they have no scope row of any kind; the Revenue clerk gets none (sees nothing until scoped) |
| Expense catalog | only when the organization has no `ExpenseCategory`: Garage and repairs (RepairsAndMaintenance): Garage labour, Spares, Tyres, Service and maintenance, Body work, Towing; Charges (RecurringCharges): Parking, City council, SACCO fee, Insurance, Licence, Inspection; Loans (LoanRepayments): Loan repayment. 3 categories, 13 items (asserted: `DemoSeedTests.cs:45` expects 13 options) |
| Not seeded | companies, vehicles, revenue, recurring items, investments, change-log rows, audit events |
| Tests | `DemoSeedTests.DesignLoginsSignInWithTheirPins_AndReseedingKeepsChangedPins` (`:16-37`, 4 users after reseed, changed PIN survives, Brian has no PIN); `TheDesignsExpenseCatalogIsSeededOnceAndLocalChangesSurviveReseeding` (`:39-57`, a renamed category survives); `TheFleetManagerHasAScopeThatCanBeSavedAndKeepsOneChosenLater` (`:59-79`) |

### 8.2 `UserProvisioning` (`Infrastructure/UserProvisioning.cs`, operator CLI `--provision-user <email> --phone <mobile> [--role] [--first-name] [--last-name] [--organization-name]`, `Program.cs:215-223`)
| Step | Behaviour |
|---|---|
| Validation | email must parse (`MailAddress`); phone must normalise (`PhoneNumber.Normalize`, E.164 `+254` plus 9 digits starting 1 or 7); role must be a `PermissionCatalog.RolePermissions` key; email trimmed and lower-cased |
| Organization | `EnsureOrganization`: 0 organizations: creates Name from `--organization-name` or `My fleet`, Slug `my-fleet`, plus default localization, branding, security policy; exactly 1: reuses it; more than 1: `InvalidOperationException` (single-organization limitation) |
| Roles | `EnsureRoles` adds missing catalog roles; no `RolePermissions` rows are written |
| User | refuses when another user (different email) has the phone number; finds by email or creates; sets `PhoneNumber` and `Status = Active`; no PIN is set (the person sets one with an email code) |
| Membership | creates with names from the request or from the email (`NameFrom`: first two dot parts, capitalised, defaults New and Member); an existing inactive membership is reactivated; names updated only when given |
| Role | default `Owner` for a new link; an existing link is kept unless `--role` names another, in which case the old `PersonRoles` row is removed and a new one added |
| Invalidation | for an existing user whose phone, status, membership active flag or role changed: `SecurityVersion++` and every `TrustedDevices` and `RefreshTokens` row of the user is revoked, so the change takes effect on all devices |
| Scope | Owner and Office admin get one `SetupDataScopes` row `AllCompanies = 1` if none exists |
| Save | one `SaveChanges` with `Provisioning = true`; no change-log row and no audit event |

### 8.3 First owner creation and invitation acceptance
- First owner: `--provision-user` is the only bootstrap (`Provision` with no role creates an Owner in a new `my-fleet` organization). There is no sign-up endpoint.
- There is no invitation table, token or acceptance step in the .NET model. A person created by the people editor (`AccessUseCases.Save`) exists with `PinHash = null`; they become able to sign in by `POST /auth/setup-pin/request` (code purpose `FirstSetup`, allowed only while `HasPin` is false), `/auth/setup-pin/verify`, `/auth/setup-pin/complete`, which writes the PIN hash, trusts the device and issues tokens. The email code (6 digits, 10 minutes, HMAC hash stored) is the acceptance step. `apps/api-python/docs/03-database.md` mentions invitations for `tenancy`; that is new design, not current behaviour.
- `--remove-user <email>` (`Program.cs:224-236`): `User.Remove()` (`Status = Removed`, `SecurityVersion++`) and revokes all refresh tokens; the membership stays.
- Startup warning (`Program.cs:237-239`): counts active users with no active membership.

### 8.4 Health and readiness
| Endpoint | Check |
|---|---|
| `/health/live` | no checks (`Predicate = _ => false`), never touches the database |
| `/health/ready` | `DatabaseHealthCheck` (tag ready, timeout 10 s): new scope, `AuthDb.Database.CanConnectAsync`; unhealthy message `The database cannot be reached.` on false or on a non-cancellation exception. EF's SQL Server `CanConnect` opens a connection and runs no table query. Test: `OperabilityTests` expects 503 with a failing database |
| `/health` | static `{status: ok}` |

---

## 9. SQL Server specific features in use, and the natural PostgreSQL equivalent

| # | Feature in use | Where | PostgreSQL equivalent and caveat |
|---|---|---|---|
| 1 | `uniqueidentifier` keys generated by the client, no `NEWID()` default | every table | `uuid`; sorting differs (SQL Server orders GUIDs by the last 6 bytes first, PostgreSQL bytewise), which only changes tie-break order in `ORDER BY ... Id` (Companies, ExpenseCategories, Recurring, People) |
| 2 | `datetimeoffset` for instants (always offset 0) | `CapturedAt`, `UpdatedAt`, `RecordedAt`, `OccuredAt`, `CreatedAt`, `ExpiresAt`, `PausedUntil`, `TrustExpiresAt`, `Logos.UpdatedAt` | `timestamptz`; the code-level rule that a non-zero offset is refused (`Instants must be UTC.`) cannot live in the column and moves to the API boundary |
| 3 | `datetime2` via value converter | `OrganizationSettingsVersion.OccurredAt`, `EffectiveFrom` | `timestamptz` (or `timestamp` holding UTC); date-window filter then compares instants directly |
| 4 | `date` for `DateOnly` (business dates, joins, stops) | many | `date` |
| 5 | `bit` | flags | `boolean` |
| 6 | `nvarchar(n)` (UTF-16 code unit lengths) and `nvarchar(max)` | see section 1 | `varchar(n)` or `text` with CHECK length; PostgreSQL counts characters, SQL Server counts UTF-16 units, so astral characters count differently; `nvarchar(max)` columns without a database length (Localizations, Brandings, Memberships names, UserPreferences, change-log JSON) get their limits only from domain validation |
| 7 | `varbinary(max)` with EF length 262144 as metadata only | `Logos.Data` | `bytea` plus an explicit `CHECK (octet_length(data) <= 262144)` if the cap should be a database rule |
| 8 | `decimal(14,2)` | money columns | `numeric(14,2)`; the planned doc says `numeric(18,2)`, so the domain cap 999 999 999 999.99 must then be enforced separately |
| 9 | `float` | `UserPreferences.FontScale` | `double precision` |
| 10 | enums stored as `int`, FK to three lookup tables for three of them | `Status`, `Purpose`, `Reason`, `Kind`, `Frequency`, `Bucket` | `smallint` or text with CHECK; the three lookup tables only exist to give FKs; client wire values mix numbers (kind, frequency, bucket) and names (revenue reason) |
| 11 | filtered unique indexes | `IX_Memberships_UserId_Active WHERE [Active] = 1`, `IX_Users_PhoneNumber WHERE [PhoneNumber] <> ''` | partial unique indexes `WHERE active` and `WHERE phone_number <> ''` |
| 12 | check constraints with bracket quoting | `CK_SecurityPolicies_*` | `CHECK (col BETWEEN a AND b)` |
| 13 | composite primary and foreign keys led by `OrganizationId`, all `NO ACTION` except three cascades from `Users` | whole schema | same; consider RLS on `organization_id` |
| 14 | default case-insensitive collation relied on for uniqueness and search | `Users.Email`, `Organizations.Slug`, `Roles.Name`, `FleetVehicle.Registration`, change-log `LIKE`, name ordering | `citext`, ICU nondeterministic collation, or `lower()` unique indexes; `ILIKE` for search. Normalised names (`NormalizedName`) are computed with .NET `ToUpperInvariant()`; PostgreSQL `upper()` differs for some non-ASCII letters |
| 15 | trailing-space-insensitive string equality | all string comparisons | PostgreSQL `varchar` compares trailing spaces; inputs are trimmed by the domain, so low risk |
| 16 | `LIKE` with bracket-escaped wildcards | `SetupRepository.cs:371-375` | `ILIKE ... ESCAPE '\'` with backslash escaping |
| 17 | no `rowversion`; version columns are application-bumped `bigint` | `Version`, `SettingsVersion` | `bigint` or `integer` bumped in the routine (`UPDATE ... WHERE version = $n`); `xmin` not needed |
| 18 | no identity columns, sequences or computed columns | none (`UseIdentityColumns` is only the default annotation) | the change-log counter could become a sequence or stay a counter row |
| 19 | SERIALIZABLE transactions with lock-based deadlocks (error 1205) and EF retry strategy (3 retries, 5 s) | `UnitOfWork.Execute`, `AuthEndpoints.Run` | `SERIALIZABLE` gives SSI serialization failures (SQLSTATE 40001) and `40P01` deadlocks; retry on both; or READ COMMITTED with `SELECT ... FOR UPDATE` on the organization row |
| 20 | T-SQL in migrations: `WHILE`, `UPDATE TOP (5000)`, `@@ROWCOUNT`, `IF NOT EXISTS ... INSERT`, `sys.indexes`, `SERVERPROPERTY('EngineEdition')`, `EXEC(N'...')`, `WITH (ONLINE = ON)`, `OBJECT_ID` | sections 7.2, 7.6, 7.7 | set-based `UPDATE ... FROM` (the table is small), `INSERT ... ON CONFLICT DO NOTHING`, `CREATE INDEX CONCURRENTLY` outside a transaction |
| 21 | `MERGE`, `OUTPUT`, `NEWSEQUENTIALID`, temporal tables, JSON functions, full-text | none used | not applicable |
| 22 | `Include` joins and projected nested collections as single queries | repositories | lateral subqueries, `json_agg`, or separate queries; the tests only require the command count to stay flat as data grows |
| 23 | JSON stored as plain `nvarchar(max)` text, no `ISJSON` check, mixed key casing (PascalCase for setup, people and revenue snapshots, camelCase for organization settings) | `Before`, `After` in the change log and audit | `text` or `json` keeps the exact bytes sent to clients; `jsonb` reorders keys and drops whitespace; the history endpoint returns the raw strings and rewrites `CompanyIds` and `VehicleIds` for scoped viewers |
| 24 | in-process `MemoryCache` and `SemaphoreSlim` (count cache, auth gate) | `HistoryCountCache`, `AuthGate` | row locks (`FOR UPDATE` on the user row), or no cache |
| 25 | Windows or ICU time zone ids resolved by `TimeZoneInfo.FindSystemTimeZoneById` | `SetupExecution.Actor`, `SetupRepository.Narrow`, `SettingsText.CalendarDate` (`Application/Settings/SettingsText.cs:13-27`) | IANA names with `AT TIME ZONE`; the organization zone default is `Africa/Nairobi` |

---

## 10. Naming audit

### 10.1 Names that carry the old Auth project name (product is xcode)
| Name | Where | Note |
|---|---|---|
| `Auth.Api.csproj`, root namespace `Auth` (`Auth.Domain`, `Auth.Domain.Setup`, `Auth.Application`, `Auth.Application.Setup`, `Auth.Application.Revenue`, `Auth.Infrastructure`, `Auth.Infrastructure.Setup`, `Auth.Api`) | `apps/api/*.cs` | the service is the whole product API, not just authentication |
| `AuthDb` (the single DbContext for all 34 tables) | `Infrastructure/AuthDb.cs:7`, `[DbContext(typeof(AuthDb))]` in the snapshot `:13` | holds fleet, revenue, organization and access data |
| `AuthDbDesignFactory`, `AuthDbModelSnapshot` | `Infrastructure/AuthDbDesignFactory.cs:7`, `Migrations/AuthDbModelSnapshot.cs:14` | |
| migration namespace `Auth.Api.Infrastructure.Migrations` | all migrations | differs from the context namespace `Auth.Infrastructure` |
| migration `20260923104350_InitialAuth` | `Migrations/` | first migration only created the sign-in tables |
| connection string key `ConnectionStrings:Auth` | `appsettings.json`, `Program.cs:37`, `AuthDbDesignFactory.cs:17`, `ProductionStartupTests.cs:20` | |
| configuration section `Auth` (`Auth:SigningKey`, `Auth:Issuer`, `Auth:Audience`, `Auth:TrustLifetimeDays`) and class `AuthOptions` | `Program.cs:22`, `Application/AuthContracts.cs:10` | environment form `Auth__SigningKey` |
| `AuthGate`, `AuthUnitOfWork`, `AuthEndpoints`, `AuthSessionResponse` and the services `SignInService`, `PinSetupService`, `SessionService`, `AuthCodes`, `SessionTokens`, `AuthAccounts` (the old `AuthService` was split in phase 4 to 6) | Application and Api | correct only as the authentication feature |
| test project `Auth.Tests`, `AuthFactory`, folder `tests/api` | `tests/api` | |
| database name `XCode` | `appsettings.json` connection string | the code and branding write the product as XCODE (`OrganizationBranding` defaults `DisplayName`, `LegalName`, `LogoAlt` = `XCODE`, `Organization.cs:191-195`), the planned database is `xcode` |

### 10.2 Misspellings and casing
| Name | Where | Correct form |
|---|---|---|
| `CurrentOganizationId` | `AuthDb.cs:9`, used in every query filter | `CurrentOrganizationId` |
| `OccuredAt` (column, property and index `IX_AuditEvents_OrganizationId_OccuredAt`) | `AuditEvents`, `Access.cs:48` | `OccurredAt`; the change log table spells it correctly (`OccurredAt`) |
| `UseGroupping` (fixed in phase 6, **uncommitted**: column and property are now `UseGrouping`, migration `RenameUseGrouping`; the wire accepts both names, see the HTTP inventory) | `Localizations` column, `Organization.cs:157` | `UseGrouping` |
| class `organizationContext` (lower case) in file `OrganizationContext.cs` | `OrganizationContext.cs:8` | `OrganizationContext` |
| comment `authroization` | `OrganizationPort.cs:32` | authorization |

### 10.3 Table and column names that disagree with each other or with the domain language
| Name | Where | Issue |
|---|---|---|
| plural vs singular table names | plural: `Users`, `VerificationCodes`, `TrustedDevices`, `RefreshTokens`, `Organizations`, `Memberships`, `Localizations`, `Brandings`, `Logos`, `SecurityPolicies`, `UserPreferences`, `Roles`, `RolePermissions`, `PersonRoles`, `PermissionOverrides`, `AuditEvents`, `RevenueRecords`, `SetupDataScopes`, `SetupCompanyScopes`, `SetupVehicleScopes`; singular: `PsvCompany`, `FleetVehicle`, `VehicleTarget`, `VehicleAwayPeriod`, `VehicleInvestment`, `RecurringItem`, `RecurringVersion`, `RecurringAllocation`, `ExpenseCategory`, `ExpenseItem`, `OrganizationSettingsVersion`, and the three `*Lookup` tables | singular ones have no `DbSet` property and take the class name; the scope tables were renamed to plural in migration `AccessManagement` while their neighbours were not |
| `OrganizationSettingsVersion` | change-log table, entity, `Organizations.SettingsVersion` | it is the organization-wide change log (people, companies, vehicles, recurring, expenses, investment, revenue, settings), called change log in the UI and `audit.view`, `History` in code (`ISetupRepository.History`, `/setup/history`, `HistoryEntry`, `HistoryPage`, `HistoryCountCache`) and `ChangeLog*` in migrations and tests; its `Version` is the organization counter |
| `AuditEvents.Entity` | `Access.cs:44` | holds an entity id (as text) for `revenue.recorded`, `setup.*` and `person.*`, but a section name for `organization.settings.updated` |
| `OrganizationSettingsVersion.Section` values | written by use cases | mix plural nouns (companies, vehicles, people, expenses), singular (investment, revenue, recurring, logo, organization) and camelCase (securityPolicy, businessDate) |
| `Localizations`, `Brandings`, `Logos`, `SecurityPolicies`, `UserPreferences` | tables | their classes are `OrganizationLocalization`, `OrganizationBranding`, `OrganizationLogo`, `OrganizationSecurityPolicy`, `UserPreference` |
| `PermissionOverrides` table vs class `PersonPermissionOverride`; `PersonRoles` | `Access.cs` | person vs membership vs user wording |
| `RolePermissions` | table | legacy, unread (1.13) |
| `Setup*` prefix on `SetupDataScopes`, `SetupCompanyScopes`, `SetupVehicleScopes` and namespace `Auth.Domain.Setup` | scope tables | they gate data access for every module, not only setup; `/setup/*` routes also serve people, revenue, organization settings, appearance and preferences |
| `PsvCompany` vs company; `FleetVehicle` vs vehicle | table and class vs routes (`/setup/companies`, `/setup/vehicles`), columns `CompanyId`, `VehicleId`, permissions `companies.manage`, `vehicles.manage` | PSV is a domain word, `Fleet` prefix appears only in the table name |
| `Recurring*` vs commitments | tables `RecurringItem`, `RecurringVersion`, `RecurringAllocation`, route `/setup/recurring` vs permissions `commitments.view`, `commitments.manage`, `dash.commitments` and the UI label Scheduled expenses and savings | three names for one concept |
| `VehicleInvestment` vs `invest.view`, `invest.manage`, `dash.investment` | | |
| `Memberships` / class `OrganizationMembership` vs People (`/setup/people`, `PersonDto`, `people.*`) | | |
| `Organizations.BusinessDate` vs `RevenueRecords.BusinessDate` | | same name, different meaning (accounting-date override vs the day a record is for) |
| `VehicleTarget.WeeklyAmount` vs DTO `WeeklyTarget` | | |
| `Users.Status` (`Removed`) vs `Memberships.Active` and endpoint `/deactivate` | | three words for ending access |
| `VerificationCodes.Purpose` values `FirstSetup`, `NewDevice`, `PinReset` vs routes `setup-pin`, `pin-reset`, `verify-device` | | |
| `RevenueRecords.Reason` | | the no-earnings reason (`RevenueNoEarningsReason`), column name is generic |
| (removed in phase 5) `SettingsSectionRegistry` was deleted; the real settings section list is `SettingsSections.All()` (`Application/Settings/SettingsSections.cs:29-43`: `OrganizationDetailsSection`, two `MergedSection<T>` with legacy names, `BusinessDateSection`), registered by `AddOrganizationSettings` (`Api/OrganizationEndpoints.cs:8-15`) | `ISettingsSection`, `MergedSection<TEntity>` | the old `switch` in `OrganizationEndpoints.cs` is gone |
| empty file `Domain/Setup/SetupExecution.cs` (0 bytes) next to the real `Infrastructure/Setup/SetupExecution.cs` | | the planned doc names a persisted `setup_execution`, which does not exist in .NET |
| plan and phase identifiers in comments and history | migration id `20260924172309_Phase1Setup` (renamed, shim in `Program.cs:191-209`); comments such as `Contract C6` (`ISetupRepository.cs:26`), `D4`, `D5`, `D11`, `D16`, `Phase 1 template-method pipeline` (`SetupExecution.cs:7`) | must not be carried into the new project |
| hand-made migration ids | `20260929120000`, `20260929190000`, `20260929200000`, `20260929200500`, `20260929210000`, `20261004100000`, `20261004110000` | round times instead of generated stamps |

---

## 11. Open questions (with pointers)

| # | Question | Pointer |
|---|---|---|
| 1 | Version columns start differently (`Users.Version` 0; `Memberships.Version`, `RevenueRecords.Version`, `Organizations.SettingsVersion` 1) and travel to clients as 64-bit numbers (`PersonDto.Version`, `RevenueSaved.Version`, `RevenueCellDto.Version`, `AppearanceResponse.SettingsVersion`); the planned doc says `version integer DEFAULT 1`. Keep bigint and the same start values for client compatibility? | `Domain/Entities.cs:17`, `Organization.cs:90,127`, `Revenue.cs:76`, `RevenueContracts.cs:38,137`, `AccessContracts.cs:17` |
| 2 | The change-log counter is a single hot row per organization with a bounded retry loop. Keep a counter row, use a per-organization sequence, or serialize with `FOR UPDATE`? Versions are gap-free and unique today and clients page by them (`before`) | `OrganizationRepository.cs:50-92`, `Organization.cs:90-91`, `SetupModel.cs:80`, `ChangeLogPagingTests.cs:59-97` |
| 3 | Revenue has no idempotency key or client-supplied id; replay is natural key plus payload equality, evaluated before date, permission and version checks. The planned doc assumes idempotency keys and client ids. Which contract is the target? | `RevenueUseCases.cs:49-52`, `Revenue.cs:98-101`, `03-database.md` section 4 and 6 |
| 4 | `RolePermissions` is unread; `CostCategoryLookup` and `RecurringVersion.Category` were dropped. Confirm neither is migrated. Cost versions with no bucket report as RecurringCharges (`ExpenseBuckets.Of`), so legacy NULL buckets must keep that meaning or be backfilled | `Access.cs:11-18`, `ExpenseCatalog.cs:16-17`, `20261004110000_RetireOldCostCategories.cs`, `20260929210000_ExpenseCatalogAndInvestment.cs:155-160` |
| 5 | Change-log and audit JSON is stored as text with mixed key casing and enum-as-number inside setup snapshots; the endpoint returns the raw string and rewrites arrays for scoped viewers. Keep text/json or move to jsonb (key order and whitespace change)? | `Application/Settings/SettingsText.cs:11,77-79`, `OrganizationSettingsUseCases.cs:134-149`, `SetupRepository.cs:382-405`, `RecurringUseCases.cs:140-163` |
| 6 | The schema is multi-tenant but provisioning and the seed assume one organization; a user may hold memberships in many organizations but only one active. Is multi-organization a goal? | `UserProvisioning.cs:86-90`, `DemoSeed.cs:33`, `OrganizationModel.cs:31-34` |
| 7 | Scoped viewers never see settings sections in the change log, and `people` rows need `people.view` even for all-companies viewers. Confirm both rules are intended before porting the visibility predicate | `SetupRepository.cs:295-313` |
| 8 | Case-insensitivity: uniqueness and search depend on the SQL Server collation (`Users.Email`, `Organizations.Slug`, `Roles.Name`, `FleetVehicle.Registration`, change-log `LIKE`); `NormalizedName` uses `ToUpperInvariant()`. Which PostgreSQL mechanism and which normalisation for non-ASCII? | `AuthDb.cs:41`, `OrganizationModel.cs:20,58`, `SetupModel.cs:18,23,53,59`, `PsvCompany.cs:32`, `SetupRepository.cs:368-376` |
| 9 | Rules held only in code, not in the database: revenue amount xor reason, positive money, away-period order and non-overlap, `LeftOn >= JoinedOn`, allocation sum equals version amount, logo size and magic bytes, locale/time zone/currency/colour formats. Which become CHECK or exclusion constraints and which stay in routines? | `Revenue.cs:15-37`, `PsvCompany.cs:66-72`, `FleetVehicle.cs:57-111`, `RecurringItem.cs:102-119`, `Organization.cs:163-222` |
| 10 | Ordering depends on the collation (company, expense category and recurring names, people by last then first name) and on GUID order for ties. Tests expect name order such as Insurance before Office rent | `SetupRepository.cs:32,48,176,406`, `AccessUseCases.cs:71-76`, `ChangeLogAndScopeTests.cs:103-107` |
| 11 | People update deletes and re-inserts all of a person's role, override and scope rows, with a 3-column `PersonRoles` key plus a unique `(OrganizationId, UserId)`. Simplify to one role row per membership? | `AccessUseCases.cs:166-183`, `OrganizationModel.cs:65-70` |
| 12 | Two parallel trails per change: `AuditEvents` and the change log (`organization.settings.updated` embeds `{value, reason}` in `After`). Keep both? `AuditEvents.Entity` has two meanings | `OrganizationRepository.cs:104-114`, `OrganizationSettingsUseCases.cs:134-149`, `AccessUseCases.cs:588-591` |
| 13 | Auth endpoints rely on an in-process per-account lock and map no concurrency exception (500). The target uses `FOR UPDATE`; confirm the lockout counters must remain exact under concurrency | `AuthEndpoints.cs:73-83`, `Infrastructure/AuthUnitOfWork.cs:11-33`, `SignInService.cs:11-56` |
| 14 | RESOLVED in phase 5 (**uncommitted**): organization settings, logo and preferences writes now run inside `UnitOfWork.Execute` (serializable transaction, change-log collision retry, 409 after four collisions), through `OrganizationSettingsUseCases`. Nothing left to decide except keeping that in the port | `Application/Settings/OrganizationSettingsUseCases.cs:33-131`, `ChangeLogAndScopeTests.cs:142-185` |
| 15 | Reads run without an explicit transaction, so the actor/scope reads and the data reads can see different states. Use a repeatable-read read-only transaction in PostgreSQL? | `OrganizationRepository.cs:94-102`, `SetupExecution.cs:32-54` |
| 16 | `GET /setup/access/roles` writes (creates missing catalog roles). Seed roles at organization creation instead? | `AccessUseCases.cs:16-24`, `UserProvisioning.cs:102-112` |
| 17 | No retention for `VerificationCodes`, `RefreshTokens`, `TrustedDevices` (rows accumulate), `AuditEvents` and the change log (append-only forever) | `Application/Authentication/AuthCodes.cs:17-41`, `SessionTokens.cs:11-63`, `Entities.cs` |
| 18 | Legacy `Users.PhoneNumber = ''` rows exist on migrated databases and are excluded from the unique index; target column should probably be NOT NULL and unique. How are such rows migrated? | `AuthDb.cs:43-45`, `OrganizationsAndFleet.cs:675-690` |
| 19 | The `Program.cs` migration-history shim for `Phase1Setup` has no meaning in a new database; drop it and do not copy the `__EFMigrationsHistory` row | `Program.cs:191-209` |
| 20 | RESOLVED by this update: the in-flight work named at read time (`ChangeLogVehicle.cs`, `HistoryCountCache.cs`, the `History` signature, `RevenueRepository.RecordChange` reading `Local`, the dashboard cache, `ChangeLogPagingTests.cs`) has settled and is described in 4.1, 4.4, 4.5, 5.6 and 7.6; all of it is still uncommitted | `git status` on 2026-10-08 |
| 21 | Business date and history date windows use the organization time zone via `TimeZoneInfo`; the History window takes the zone offset at local midnight. Confirm the PostgreSQL equivalent (`AT TIME ZONE`) gives the same day boundaries for Africa/Nairobi and for any zone an organization may choose | `SetupExecution.cs:42-49`, `SetupRepository.cs:338-379`, `SettingsText.cs:13-27` |
| 22 | `VehicleInvestment` is the only setup record that is edited in place and hard-deleted; the change log keeps the removed values. Keep, or make it append-only like targets? | `SetupRepository.cs:443-462`, `InvestmentUseCases.cs:46-53` |
| 23 | Revenue `Reason` is an int column but appears as a name in snapshots and requests, while recurring kind, frequency and bucket are numbers on the wire. Which wire values must the new database layer emit? | `RevenueContracts.cs:155-168`, `RevenueUseCases.cs:111`, `RecurringQueryCostTests.cs:25`, `DemoSeedTests.cs:51` |
| 24 | RESOLVED by this update: the revenue repository, contracts, use case, endpoints, `Program.cs` and `RevenueCaptureTests.cs` were re-read; the dashboard cache exists (`RevenueDashboardCache`, 5.6). Further drift is listed in the last section | `git diff` on the same files |

---

## Drift log (phases 4 to 6)

Written 2026-10-08 against the working tree on branch `fix/format` (HEAD `3253914`). The .NET code is the source of truth; where this list and an older paragraph above disagree, this list wins. **(uncommitted)** = the fact exists only in modified or untracked files (remediation phase 6 is still in flight); unmarked facts are committed. Petty cash (`PettyCash*.cs`, `PettyCashEndpoints.cs`, `PettyCashModel.cs`, the table `PettyCashEntries` and its two migrations) is inventoried in `inventory-petty-cash.md` and only named here.

Migration list, in apply order (`apps/api/Infrastructure/Migrations/`, namespace `Auth.Api.Infrastructure.Migrations`; only `SqlServerTests` proves a migration applies, the other tests use `EnsureCreated`):

| # | Id | State | Note |
|---|---|---|---|
| 1 | `20260923104350_InitialAuth` | committed | sign-in tables |
| 2 | `20260924172309_OrganizationsAndFleet` | committed | renamed from `Phase1Setup`; shim at `Program.cs:191-195,205-209` |
| 3 | `20260925054855_AccessManagement` | committed | |
| 4 | `20260927043715_OrganizationLogo` | committed | |
| 5 | `20260929120000_BusinessDateAndSetupLifecycle` | committed | |
| 6 | `20260929190000_RevenueCapture` | committed | |
| 7 | `20260929200000_AccessIntegrity` | committed | |
| 8 | `20260929200500_NormalizeSecurityPolicy` | committed | clamp SQL, 7.1 |
| 9 | `20260929210000_ExpenseCatalogAndInvestment` | committed | 7.2 |
| 10 | `20261004100000_VehicleAwayPeriods` | committed | |
| 11 | `20261004110000_RetireOldCostCategories` | committed | 7.3 |
| 12 | `20261004151525_ChangeLogIsFilterable` | committed | 7.4 |
| 13 | `20261006084351_UntrustedFailedAttempts` | committed | 7.5 |
| 14 | `20261007052529_ChangeLogVehicle` | **(uncommitted)** | adds `OrganizationSettingsVersion.VehicleId` (uniqueidentifier NULL), two batched backfills as `public const` SQL (`BackfillVehiclesSql`, `BackfillRevenueSql`; `Batched` wraps them in `WHILE 1 = 1 ... UPDATE TOP (5000) ... IF @@ROWCOUNT = 0 BREAK`, run with `suppressTransaction: true`), then two indexes created by raw SQL that is `WITH (ONLINE = ON)` only on SQL Server engine editions 3, 5 and 8 (Enterprise, Azure SQL Database, Managed Instance) and a plain `CREATE INDEX` elsewhere; `Down` drops both indexes and the column. `ChangeLogVehicle.cs:14-84`, 7.6 |
| 15 | `20261007115030_PettyCash` | **(uncommitted)** | see `inventory-petty-cash.md` |
| 16 | `20261007124851_PettyCashDecimalUnits` | **(uncommitted)** | see `inventory-petty-cash.md` |
| 17 | `20261007181520_RenameUseGrouping` | **(uncommitted)** | `RenameColumn Localizations.UseGroupping -> UseGrouping`, `Down` renames back; no drop, no add (SQL Server `EXEC sp_rename`); `RenameUseGrouping.cs:11-26`, `tests/api/MigrationSnapshotTests.cs:24-41` |

1. The snapshot has 35 tables, not 34: `PettyCashEntries` was added (entity block `AuthDbModelSnapshot.cs:368-465`, relationships `:1394-1417`), so the snapshot is 1763 lines and every per-table snapshot citation in section 1 was shifted by +98 for tables after it. `Infrastructure/AuthDb.cs:31,38` (`DbSet<PettyCashEntry>`, `ConfigurePettyCash`). **(uncommitted)**
2. `Localizations` column `UseGroupping` (bit, default true, "sic") is now `UseGrouping`: snapshot `AuthDbModelSnapshot.cs:197`, property `Domain/Organization.cs:157`, migration 17 above. **(uncommitted)**
3. The change log table gained `VehicleId` (uniqueidentifier NULL, no FK) and two indexes, `IX_OrganizationSettingsVersion_OrganizationId_OccurredAt` and `IX_OrganizationSettingsVersion_OrganizationId_Section_VehicleId`: snapshot `AuthDbModelSnapshot.cs:769,779,784`, model `Infrastructure/Setup/SetupModel.cs:81-82`, entity `Domain/Setup/OrganizationSettingsVersion.cs:18-19,26-38`; section 7.6 was checked against the final 84-line migration. **(uncommitted)**
4. `SettingsChangeLog.Record(Guid organizationId, Guid actorId, string correlationId, string section, Guid entityId, string before, string after, string reason, Guid? vehicleId = null, CancellationToken ct = default)` returns the new `long` version; it is the ONLY writer of change-log rows and the ONLY caller of `Organization.SettingsChanged()`; `before` and `after` are stored as given; audit events stay with the callers. `Application/Settings/SettingsChangeLog.cs:9-19`, `Domain/Organization.cs:91`. **(uncommitted)**
5. Callers of `Record` and the vehicle id they pass: `SetupRepository.RecordChange` (vehicle id = the entity id for sections `vehicles` and `investment`, else null; `Infrastructure/Setup/SetupRepository.cs:475-481`), `RevenueRepository.RecordChange` (the tracked record's `VehicleId`; `RevenueRepository.cs:241-248`), `AccessUseCases.RecordHistory` (section `people`, null; `Application/AccessUseCases.cs:588-591`), `OrganizationSettingsUseCases.Record` (sections `organization`, `localization`, `branding`, `securityPolicy`, `businessDate`, `logo`; null; `OrganizationSettingsUseCases.cs:134-149`), `PettyCashRepository.RecordChange` (section `pettycash`, the entry's vehicle id; `PettyCashRepository.cs:153-159`). **(uncommitted)**
6. `OrganizationRepository.Settings()` read some entities tracked: it now reads all four `AsNoTracking` (resolving validates and canonicalizes the copies); pinned by `PeopleQueryCostTests.SettingsReadsStayCheap` (10 commands for `GET /setup/appearance`, 5 for `GET /setup/preferences`, 0 transactions) and `SettingsReadsTrackNothing`. `Infrastructure/OrganizationRepository.cs:36-45`, `tests/api/PeopleQueryCostTests.cs:187-230`. **(uncommitted)**
7. The fixed cost per call changed: `OrganizationUseCase.Run` resolves permissions only when the call names one (a call for any active member costs 1 membership query there instead of 4); the 3 queries moved out of the any-member path. `Application/OrganizationPort.cs:41-49`. **(uncommitted)**
8. `UnitOfWork.Execute` is unchanged (3 change-log retries, 4 attempts, `ChangeTracker.Clear()` and `ForgetResolved()` per retry, `OnlyTheChangeLogCollided` = concurrency exception whose entries are all `Organization`, or SQL Server error 1205), but now also wraps organization settings, logo and preferences writes (they were EF-implicit before): 1 collision = 200 with 2 transactions, 4 collisions = 409 with 4 transactions. `Infrastructure/OrganizationRepository.cs:50-92`, `tests/api/ChangeLogAndScopeTests.cs:142-185`. **(uncommitted)** for the settings part.
9. `RevenueDashboardCache` and `CachedRevenueRepository` exist: in-process `MemoryCache`, 60 s absolute expiry, `SizeLimit` 10 000, key (organization id, `SettingsVersion`, business date, period, company id, scope = `all` or SHA-256 of the sorted company and vehicle ids), unmasked values, no explicit invalidation (the key includes the version that every logged write moves), nothing cached without an actor `SettingsVersion`. `Infrastructure/RevenueDashboardCache.cs:16-109`, `Api/RevenueEndpoints.cs:11-14`. **(uncommitted)**
10. `HistoryCountCache` was re-verified unchanged: key (organization id, settings version, viewer scope string, sees-people flag, filter record), 5 minutes absolute expiry, 10 000 entries, singleton, `Lazy<Task<int>>` per key. `Infrastructure/Setup/HistoryCountCache.cs:10-58`, `Api/SetupEndpoints.cs:15`. **(uncommitted)**
11. The revenue week and dashboard descriptions (5.6) were wrong after phase 5: the week lists vehicles with `AsSplitQuery` (3 commands) and computes whole-grid totals in the database, the dashboard sums records in the database (one row per vehicle, 5 commands on a miss), and the 5.5 convention "no `AsSplitQuery` anywhere" is false for those two loads. `Infrastructure/RevenueRepository.cs:17-156`. **(uncommitted)**
12. `AuthUnitOfWork` replaced the inline lock-and-transaction in `AuthEndpoints.Run`: per-account `AuthGate` semaphore, serializable transaction under the execution strategy, `ChangeTracker.Clear()` on every retry after the first attempt, then release and `Deliver` for the committed attempt only; `AuthGate` caps at 10 000 entries, evicts idle semaphores down to 80 percent and never disposes them. `Infrastructure/AuthUnitOfWork.cs:11-47`, `Infrastructure/AuthGate.cs:7-43`. **(uncommitted)**
13. The 6 citations of `Application/AuthService.cs` (deleted) in 2.3, 3.4, 5.7 and 11 now point at `Application/Authentication/AuthAccounts.cs:9-65`, `AuthCodes.cs:17-63`, `SessionTokens.cs:11-72`, `SignInService.cs:11-72`, `PinSetupService.cs:10-48`, `SessionService.cs:10-64`; device revoke now takes the account's phone as lock key (`SessionService.cs:61-63`). **(uncommitted)**
14. `Infrastructure/SettingsSectionRegistry.cs` (unused) is deleted; the live section list is `SettingsSections.All()` and `MergedSection<TEntity>` carries legacy field names (`useGroupping` -> `useGrouping`). `Application/Settings/SettingsSections.cs:29-67`. **(uncommitted)**
15. Open questions 14 (settings writes outside `UnitOfWork`), 20 (in-flight work) and 24 (revenue drift) are resolved (marked in section 11); question 13 now points at the new auth files.
16. `Program.cs` citations were renumbered by +1 to +15 (compression block `:138-146,164-165`, startup `:181-240`, `--migrate` `:188-199`, development auto-migrate `:202-213`); `Organization.cs`, `AuthDb.cs`, `OrganizationRepository.cs`, `OrganizationPort.cs` and snapshot citations were renumbered too. Citations into `SetupRepository.cs`, `AccessUseCases.cs` and the revenue files were re-pointed where the statement changed and otherwise can be a few lines off.
17. Startup, container and restore files: `Program.cs` never migrates outside a local Development database (`--migrate` only); `apps/api/Dockerfile` (SDK build with `dotnet restore --locked-mode`, `aspnet:10.0` runtime image because SqlClient needs ICU and the IANA time zones need tzdata, `ASPNETCORE_ENVIRONMENT=Production`, `EXPOSE 8080`, entrypoint `dotnet Auth.Api.dll`, comment: run the image once with `--migrate` per release), `apps/api/.dockerignore`, `tests/api/packages.lock.json` (`RestorePackagesWithLockFile` in `Auth.Tests.csproj`); `apps/api/packages.lock.json` is committed. There is no operational-notes section in this document, so this entry is the note. **(uncommitted)**
18. Test tables (5.8) updated: `RevenueComplexityTests` now asserts flat commands from 2 to 500 vehicles, `RevenueDashboardCacheTests` pins the cache, `RevenueWeekPagingTests` pins paging, `ChangeLogAndScopeTests.SettingsWritesRetryWhenOnlyTheChangeLogCollides` pins the settings retry; the "miss 16 commands, hit 11" figures are from `.claude/remediation/README.md:69` and are NOT asserted by any test (the test asserts hit < miss). **(uncommitted)**
