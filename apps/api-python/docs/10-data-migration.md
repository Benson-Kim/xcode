# Data migration: SQL Server to PostgreSQL, and cutover

Applies only if a SQL Server database holds data that must survive (staging or
production). If the only populated databases are developer machines, skip the copy and
provision users again with `xcode-api provision-user`.

The production data is in neither: it is in the legacy PostgreSQL database of an older
application, and section 7 maps it onto this schema directly. Decided 2026-10-13: nothing is
imported from SQL Server (`docs/13-open-questions.md` question 99); sections 1 to 6 stay as the
strategy that section 7 reuses.

## 1. Approach

A one-off, re-runnable Python tool, `tools/migrate_from_sqlserver/` (separate from the API
package: its own hashed `requirements.lock.txt` with `pyodbc` and `psycopg`, no import of
`xcode_api`; commands and DBA procedure in its `README.md`, the cutover runbook in its
`REHEARSAL.md`). Connection strings come only from `XCODE_MIGRATION_SOURCE_URL` (SQL Server)
and `XCODE_MIGRATION_DATABASE_URL` (PostgreSQL as `xcode_owner`; any other role is refused).

1. `extract`: reads every table of section 3 in one transaction, `SNAPSHOT` isolation when the
   database allows it, else `READ COMMITTED` with `--frozen` stating that the write freeze is
   on. T-SQL casts every value to one text form per type (section 2), so the files do not
   depend on the driver. One CSV per table, ordered by its key, and `manifest.json` with row
   counts, per-table SHA-256 over the file, the extraction instant (the cutover instant of
   section 3.1), the server version, the snapshot mode and the latest EF migration. Tables
   that are not copied are counted only.
2. `transform`: checks every file against the manifest, maps types and names (sections 2 and
   3), runs the documented conversions, and validates every row against the target's own
   constraints by copying everything into the target inside a transaction that is always
   rolled back: a refused batch is halved until each refused row stands alone, so a
   violation is reported with the source key, not as a `COPY` failure, and rows that
   reference a refused row are refused by their foreign key in turn. A deferred rule the
   accepted rows break (a refused vehicle takes its allocations with it) is recorded as
   blocking in `transform.json`, the files are still written so the report names the refused
   rows behind it, and the transform exits 1; the load refuses such a work directory. The
   load files are PostgreSQL's own export of the accepted rows, after a check that the
   database holds exactly the values the transform produced. `transform.json` lists every
   refused row, every row dropped by a documented rule, every changed value with its key and
   reason, and every row the tool made.
3. `load --dry-run | --apply`: as `xcode_owner`, in one transaction under the migration
   runner's advisory lock, `COPY` into the target tables in foreign-key order, then the
   verification queries (section 4). `--dry-run` always rolls back; `--apply` commits only
   when every verification passes, and records an `ops.operator_actions` row
   (`data_migration_load`) named after `XCODE_OPERATOR`. Refused rows must be acknowledged
   with `--accept-rejected N`; a refused person or organization can never be (question 16).
   Both modes load into the real tables rather than a scratch schema: a copy of the schema
   would carry neither the foreign keys to the code tables nor the routines the verification
   calls (`api.auth_resolve_session`), and a transaction that never commits leaves nothing
   behind (identity ids are given explicitly; the audit trail's sequence moves only on the
   committing path). The target must be empty: the load never merges.
4. `report`: prints counts source vs target, checksum matches, refused and dropped rows,
   every changed value, every person's rights before and after, revenue per organization and
   month, and every verification.

No stored procedure is involved in the load; this is a DBA-run bulk operation with a
reviewed script and a printed report.

## 2. Type mapping

| SQL Server (EF Core) | PostgreSQL | Notes |
|---|---|---|
| `uniqueidentifier` | `uuid` | text form is lower-cased on load |
| `nvarchar(n)` / `nvarchar(max)` | `text` with `CHECK (char_length(col) <= n)` where the model had a max length | PostgreSQL `varchar(n)` is allowed where the schema spec prefers it |
| `bit` | `boolean` | |
| `int` / `bigint` | `integer` / `bigint` | concurrency `Version` columns become `bigint` and keep their values |
| `rowversion` (if any) | `bigint` version column | the spec uses explicit `version bigint` everywhere |
| `decimal(18,2)` | `numeric(14,2)` | every stored value fits; the load asserts `abs(value) < 10^12` and reports otherwise |
| `datetime2` | `timestamptz` | EF stored UTC (`DateTime.UtcNow`); load with `AT TIME ZONE 'UTC'` |
| `datetimeoffset` | `timestamptz` | offset preserved by conversion to UTC |
| `date` | `date` | |
| `time` | `time` | |
| `varbinary` | `bytea` | |
| enums stored as `int` | `smallint` referencing a code table (`docs/04-schema.md` section 2) | values copy unchanged; the load asserts that every value exists in the code table |
| enums stored as `nvarchar` | `text` with CHECK | unchanged (the no-earnings reason) |
| JSON in `nvarchar(max)` | `jsonb` | validated on load |
| filtered unique index | partial unique index | same predicate |
| `__EFMigrationsHistory` | not migrated | `ops.schema_migrations` starts at the PostgreSQL baseline |
| sub-microsecond digits | `timestamptz` keeps microseconds | the 100 ns digit of `datetime2(7)` and `datetimeoffset(7)` is rounded half to even; the report counts the rounded values per column instead of listing them (a type mapping, not a value change) |
| `float` (`FontScale`) | `double precision` | extracted with style 3 (round trip), stored exactly |
| text holding U+0000 | refused | PostgreSQL text cannot store it; the row is reported |
| JSON with a repeated key | `jsonb` keeps the last | listed as a changed value |
| columns the source does not have (`created_at`, `updated_at` of most tables) | `timestamptz` | the extraction instant |

Extract text forms: GUIDs `CONVERT(char(36))` (upper case; lower-cased on load), instants
`CONVERT(datetime2(7), SWITCHOFFSET(col, '+00:00'))` style 121 (UTC), dates style 23, bits
`0`/`1`, binaries style 2 (hex), decimals as stored, floats style 3.

Hashes: PIN hashes, code hashes and refresh-token digests copy byte for byte; the Python
implementation uses the same algorithm and parameters (`docs/07-auth.md`), which
`tests/unit/test_pin_hasher.py` proves with vectors produced by the .NET code before
cutover (a PIN hash and an access token captured from the .NET API join the suite then).

## 3. Table map

The map is data: `tools/migrate_from_sqlserver/migrate_from_sqlserver/tablemap.py`, one record
per target table in foreign-key load order (a table may reference an earlier one, never a
later one), naming the source columns and types, the target columns, the enumeration maps,
the documented drop rules and the conversions. The code iterates over it; this table mirrors
it, and `tests/test_load.py::test_the_map_covers_every_column_the_target_requires` fails when
a migration adds a required column the map does not fill or renames a mapped one. Targets and
columns are those of `docs/04-schema.md` as migrations `0001` to `0012` built them; sections
3.1 and 3.2 give the conversions of the design notes and of prompt 08b. A table with a source
row whose target does not exist yet (the `0013` tables) stops the transform; it is never
dropped silently.

| Order | Source (SQL Server) | Target | Renames and conversions | Rows not moved |
|---|---|---|---|---|
| 1 | `Users` | `identity.users` | `Email` lower-cased; `PhoneNumber` normalised as `identity.normalize_phone` does (an empty or unusable number is refused: question 16); `PinHash` byte for byte; `Status` `0` `active`, `1` `removed`; the lock of 3.1; `Version` kept; no source dates, so `created_at`/`updated_at` take the extraction instant | none; a refused person stops the load |
| 2 | `Organizations` | `tenancy.organizations` | `SettingsVersion` kept (change-log versions stay valid) | none; a refused organization stops the load |
| 3 | `Memberships` | `tenancy.memberships` | names, `Active`, `ApprovalLimit`, `Version` kept; back-dating limit `none` (3.1) | none |
| 4 | `Localizations` | `tenancy.organization_localizations` | `TimeZone`: an IANA name the server knows is kept, a Windows id is mapped through the CLDR table (`timezones.py`), anything else is refused (question 18); `UseGrouping` (the model has no `UseGroupping` column); `FirstDayOfWeek`, `NumberDecimals` smallint | none |
| 5 | `Brandings` | `tenancy.organization_brandings` | `Primary`/`Secondary`/`Accent` -> `primary_color`/`secondary_color`/`accent_color`; `LogoLight`/`LogoDark`/`Favicon` -> `logo_light_url`/`logo_dark_url`/`favicon_url`; a blank optional URL, domain or support e-mail becomes null | none |
| 6 | `Logos` | `tenancy.organization_logos` | `Data` -> `bytea`; the signature `CHECK` must pass | none |
| 7 | `SecurityPolicies` | `tenancy.organization_security_policies` | values clamped into the bounds (as the .NET `ClampSql`); `AllowPinSignIn` false is refused, not changed | none |
| 8 | `Roles` | `tenancy.roles` | ids kept; `NormalizedName` not read (unique on `lower(name)`) | none |
| 9 | `PersonRoles` | `tenancy.person_roles` | key `(OrganizationId, UserId)` (.NET has a unique index on it, so a second role cannot exist) | rows without a membership |
| 10 | `PermissionOverrides` | `tenancy.permission_overrides` | every person's overrides rewritten through the grant translation (3.1) | every source row, replaced by the rows the translation makes; keys outside the .NET catalogue and rows without a membership are counted apart |
| 11 | `UserPreferences` | `tenancy.user_preferences` | `TimeZone` as row 4; `FontScale` double | rows without a membership |
| 12 | `PsvCompany` | `setup.psv_companies` | `normalized_name` is generated (`upper` under `C`, question 17); every row whose .NET `NormalizedName` differs is listed | none |
| 13 | `FleetVehicle` | `setup.fleet_vehicles` | the registration `CHECK`; fleet number and initial investment as 3.1 | none |
| 14 | none (made) | `setup.expense_main_categories` | 3.1 | |
| 15 | `ExpenseCategory` | `setup.expense_categories` | `Bucket` kept, `main_category_id` from row 14; names as row 12 | none |
| 16 | `ExpenseItem` | `setup.expense_items` | names as row 12 | none |
| 17 | `VehicleTarget` | `setup.vehicle_target_sets` | 3.1 | lower revisions of a vehicle and date; targets too small to split |
| 18 | `VehicleAwayPeriod` | `setup.vehicle_away_periods` | the `EXCLUDE` constraint and `returned_on > left_on` must pass (a violation is refused) | none |
| 19 | `VehicleInvestment` | `setup.vehicle_investments` | `Date` -> `invested_on`; `RecordedBy` must be a membership | none |
| 20 to 22 | `SetupDataScopes`, `SetupCompanyScopes`, `SetupVehicleScopes` | `tenancy.data_scopes`, `tenancy.data_scope_companies`, `tenancy.data_scope_vehicles` | `AllCompanies` -> `all_companies` | rows without a membership |
| 23 | `RecurringItem` | `setup.recurring_items` | `StoppedFrom` -> `stopped_from` | none |
| 24 | `RecurringVersion` | `setup.recurring_versions` | `Kind`, `Frequency`, `Bucket` the same integers; `Start`/`End` -> `start_on`/`end_on`; the schedule and kind `CHECK`s; a version whose vehicle shares do not add up to its amount, or with no share or more than 500, is refused before the deferred trigger | none |
| 25 | `RecurringAllocation` | `setup.recurring_allocations` | `VersionId` -> `version_id`; the deferred sum trigger runs before the transform ends | none |
| 26 | `RevenueRecords` | `revenue.records` | `Reason` the same integers (`1` garage, `2` arrest, `3` no_crew, `4` other); `Version` kept | none |
| 27 | `PettyCashEntries` | `pettycash.entries` | `Date` -> `entry_date`; `Kind` the same integers; `Status` `1` and `2` kept, `3` (`SentBack`) becomes `1` with its `SentBackNote` and reviewer (DEC-21); cash given and credit notes lose any status, reviewer and sent-back note (DEC-22); `Total` recomputed by the generated column, differences listed; `reject_reason`, `reopen_reason` null | none |
| 28 | `CentralExpenses` | `expenses.entries` (`0013`) | 3.2 | none |
| 29 | `RecurringPause` | `setup.recurring_pauses` (`0013`) | 3.2 | none |
| 30 | `OrganizationSettingsVersion` | `tenancy.change_log` | `Id` and `Version` kept; `OccurredAt`/`EffectiveFrom` UTC; `Before`/`After` text verbatim; `CorrelationId` -> `request_id`; the section and vehicle `CHECK`s must pass (`centralexpenses` and `reports` need `0013`) | none |
| 31 | `AuditEvents` | `tenancy.audit_events` | `Before`/`After` validated into `jsonb`, except that `After` of `person.activated` and `person.deactivated` holds the reason sentence, not JSON (`AccessUseCases.Audit`), and moves as a JSON string (listed as a changed value); any other value that is not JSON is refused; the identity `id` numbered from 1 in (`OccuredAt`, `OrganizationId`, `Id`) order, each source `Id` listed against its number; the identity sequence set to the highest on `--apply` | none |
| 32 | `TrustedDevices` | `identity.trusted_devices` | 3.1 | none (revoked rows move; question 12) |
| 33 | `RefreshTokens` | `identity.refresh_tokens` | `TokenHash` byte for byte (the same signing key keeps it valid: question 84) | revoked rows and rows expired at the extraction instant (question 12) |
| - | `VerificationCodes`, `RolePermissions`, `RecurringKindLookup`, `RecurrenceFrequencyLookup`, `ExpenseBucketLookup`, `__EFMigrationsHistory` | not copied (counted in the manifest) | codes live 10 minutes; `RolePermissions` is dropped (`docs/04-schema.md` section 1); the code tables are seeded with the same integers; `ops.schema_migrations` starts at the PostgreSQL baseline | all |
| - | none | `tenancy.organization_revenue_settings` | no row: `tenancy.settings_document` serves the defaults (threshold 4,000, amber band 10) to an organization without one, as to every organization created before `0011` | |

`identity.sign_in_attempts` and `identity.verification_codes` start empty, and `ops` holds only
the load's `ops.operator_actions` row. Enumeration values are copied unchanged wherever the
wire sends integers; the only text conversion is `Users.Status`. Every source row ends in one
of four places the report counts: loaded, dropped by a rule of the last column, refused (with
its key and the constraint), or replaced by rows the tool made (row 10, row 14).

### 3.1 The design notes v2.29 to v2.33 (register row B20)

The target schema has the tables and columns of `docs/04-schema.md` section 13 (prompt 07b).
These conversions apply on top of the table map above. The development database got the same
ones from migrations `0008` to `0011`; the tool runs the same rules on the extract
(`conversions.py`: the lock, the target split, the main categories and the grant translation
are ports of those migrations' SQL), and the load checks the translation again in SQL against
the target's own catalogue, with the query of `0009_access`.

| Data | Conversion | Why |
|---|---|---|
| `Users` lock state | an active pause (`PausedUntil` after the cutover instant) becomes `failed_attempts = 5`; a lapsed one `failed_attempts = 0`; both counters clamped to 5; `pin_reset_required = false`; `last_signed_in_at` null | `docs/07-auth.md` 12.5: a pause becomes the lock, a lapsed pause nothing |
| People without a PIN | copied with `pin_hash` null: status "Not signed in yet"; their first sign-in is number, code, new PIN | DN-B2-1; no default PIN exists anywhere |
| PINs of five to eight digits | copied unchanged; they keep verifying until their holders change them | `DEC-7`: a hash does not reveal its length |
| `TrustedDevices` | `token_hash` null (trusted by device id, as v2.11 phones are), `name` null, `remembered` true. SQL Server stores no date for a device or a refresh token, so the dates come from the tokens: a token's issue instant is its `ExpiresAt` minus the refresh lifetime of the person's organization (30 days without a policy); `trusted_at` is the device's earliest, `last_used_at` its latest, both capped at the extraction instant; a device with no token gets the extraction instant minus 90 days. A device unused for 90 days at cutover needs a code at its next sign-in. Every derived date is listed | DN-B7-2; question 82 |
| `Memberships` back-dating limit | `none`, no date | `DEC-11`; question 65 |
| `PermissionOverrides` | rewritten through `tenancy.permission_translations`: each person's old assigned set (role defaults plus overrides, the .NET resolver, computed by the tool from the .NET catalogue it carries in `legacy_catalogue.py`, which a test checks against `0004_access_catalog`) translated key by key, dependencies added, overrides recomputed against the new role defaults (`docs/15-design-v2-3.md` section 3.5). Dropped on purpose and reported per person: `revenue.no_earnings`, `bills.*`, a non-Owner's `organization.manage`. As built in `0009_access` (D2): an Owner also keeps every right of the Owner role that no old key leads to (the petty-cash rights that start off for others), so an only Owner is not left with denials nobody can lift (`docs/04-schema.md` 13.2); the same query is the tool's (question 71 lists the two grants it widens) | DN-B13-1, DN-B17-2, v2.29 s5 (`pettycash.spend` gives `pettycash.edit_own`); questions 59, 60 |
| `VehicleTarget` | one target set per vehicle and `EffectiveFrom` (the highest `Revision` on that date, whose `Id` the set keeps; `created_at` the extraction instant, `created_by` null), with the weekly amount split as migration `0010_setup` splits the weekly targets already in PostgreSQL (no routine does it: migrations run before routines exist): Monday to Saturday the weekly amount / 7 rounded half to even to the cent, Sunday the rest, so the week total is the old weekly target exactly; the owner adjusts the figures afterwards. A weekly target too small to split into seven positive cents (`weekly - 6 * round_half_even(weekly / 7, 2) <= 0`, e.g. a 0 or unset legacy target) is reported for owner entry and not loaded, so it cannot abort the load on the `monday..sunday > 0` CHECK (`docs/04` 13.4) | v2.31 s1 ("each existing weekly target / 7 into every day, then the owner adjusts"); DN-B9-1 |
| `FleetVehicle` fleet numbers | null, unless the owner hands over a list (`transform --fleet-numbers <csv>` with `registration,fleet_number`; a registration not in the fleet, a registration listed twice or a number given twice in one PSV company stops the transform before any write); until a vehicle has one, drop-downs show the registration alone and its next edit requires one | v2.29 s4 |
| `FleetVehicle` initial investment | null; the dated `VehicleInvestment` rows stay as they are | `DEC-18`; question 61 |
| `ExpenseCategory` buckets | per organization, one main category for each bucket its categories use, named `Repairs and maintenance`, `Recurring charges`, `Loan repayments`, as ordinary records (no source id exists, so the id is a UUIDv5 of the organization and the bucket: a rerun makes the same ids); each category points to its bucket's main category; `bucket` kept (written by nothing; read by the vehicle report until prompt 08b) | `DEC-17`; question 63. Categories imported later from the old system arrive without a main category ("Not set") |
| `RevenueRecords` | unchanged: every stored record fits the new `CHECK`; an old amount below 4,000 without a reason stays as it is and counts in "Below 4,000" by its amount | DN-B14-3 applies to writes |
| `SecurityPolicies` | `idle_unlock_seconds` copied (the new default 900 only applies to organizations created later); `pin_length`, `lockout_threshold` and `lockout_minutes` copied, read by no decision | `docs/07-auth.md` 12.1 |
| change log, sign-in history | `signIn` rows start at cutover; `identity.sign_in_attempts` starts empty, so the simulated tries of unknown numbers start at zero | |

Verification adds: the count of people per new status, of devices that are no longer live,
of target sets per vehicle, of categories per main category, and for every membership the old
and new rights side by side with the keys not carried and the rights gained (`report`); the
load fails when the stored overrides do not reproduce the translated sets or when a person
loses a right the translation keeps.

### 3.2 Expenses, scheduled runs and reports (prompt 08b)

The target schema adds `docs/04-schema.md` section 14 (migration `0013_expenses`). Rows below carry the table map's
load order; each must pass the target's constraints, and a source row that fails one is reported, not loaded. Until
`0013` is applied to the target, a source row of rows 28 and 29 stops the transform ("apply migration 0013 to the
target first"); the map's records for them follow this section and were not yet run against a built `0013`.

| Order | Source (SQL Server) | Target | Renames and conversions | Rows dropped |
|---|---|---|---|---|
| 28 | `CentralExpenses` | `expenses.entries` | `Date` -> `entry_date`; `Total` recomputed by the generated column and compared with the source (differences reported); `Note` trimmed, blank to null; `GroupSize`, `GroupTotal`, `GroupUnits`, `GroupUnitAmount` copied (`ck_entries_group` must pass); `RecordedBy`/`UpdatedBy`/`RemovedBy` must be memberships of the organization (the .NET table has no foreign key: a row naming a person who left is reported); `Version` kept | none |
| 29 | `RecurringPause` | `setup.recurring_pauses` | `From` -> `paused_from`, `Through` -> `paused_through`; the overlap and one-open-pause constraints must pass (.NET has neither: overlaps are reported) | none |
| - | none | `setup.saving_openings`, `setup.saving_opening_amounts` | start empty: .NET has no opening balances; the owner enters them after the cutover (a `--saving-openings <csv>` list is not built: it waits for `0013`) | |
| - | none | `setup.saving_runs` | start empty: no .NET saving has a revenue rule, so every migrated saving runs without one and its runs are computed | |
| 24 | `RecurringVersion` (savings) | `setup.recurring_versions` | as row 24 of section 3 (the map gains the `0013` columns when that migration lands; the coverage test fails if one of them is required and unmapped); `condition_min`, `condition_days` null; a saving's `End` is kept (the notes have no end date, but a migrated end must not post past what the owner set: `DEC-33` refuses new ones only) | none |
| 30 | `OrganizationSettingsVersion` with `Section` `centralexpenses` or `reports` | `tenancy.change_log` | as row 30 of section 3 (refused by the section `CHECK` until `0013`); `centralexpenses` rows carry their `VehicleId` (`ck_change_log_vehicle`) | none |

Verification to add with the `0013` records (not built yet): per organization the count and the sum of `Total` of central rows not removed, before and after;
the ledger's figures for the last full month computed on both sides; the pauses per item; and for three sampled
vehicles the vehicle report of the last full month on both sides (`report`).

## 4. Verification queries (run by `load`, printed by `report`)

Every one must pass for `--apply` to commit (`load.py`):

- Refused rows acknowledged (`--accept-rejected N`), and no refused person or organization.
- The ledger adds up, table by table: source rows + rows made = loaded + dropped by a
  documented rule + refused; each source count equals the manifest's.
- `xcode-api db verify` passes, before the load and again after the commit.
- The deferred constraints hold (`SET CONSTRAINTS ALL IMMEDIATE`).
- Row counts per table equal the load files'.
- Per-table checksum: each table's rows exported in key order equal its load file byte for
  byte (SHA-256).
- Every tenant table's `organization_id` exists in `tenancy.organizations`.
- `api.auth_resolve_session` succeeds for people with an active membership on a device live
  at the extraction instant, with their copied security version (up to 200 sampled).
- Revenue per organization and month equals the source minus the rows that did not move.
- The stored overrides reproduce every person's translated set, and nobody loses a right the
  translation keeps (`0009_access`'s checks).
- Figures for the owner (always pass, printed): people per status, devices live, categories
  per main category, target sets per vehicle.

## 5. Cutover runbook

The numbered, copy-paste procedure (decisions, rehearsal on copies, the night, the watch list
and the rollback) is `tools/migrate_from_sqlserver/REHEARSAL.md`. In short:

1. Rehearse on copies: a restored SQL Server backup into an empty, migrated PostgreSQL
   target; fix in SQL Server what the report refuses; run the clients' end-to-end checks
   (web sign-in, mobile offline replay against the new API).
2. Freeze: put the .NET API in maintenance (503 with `Retry-After`) so no writes occur;
   mobile clients queue offline and replay later, which the idempotent capture supports.
3. Run `extract`, `transform`, `report`, `load --dry-run`, review; then `load --apply`.
4. Start the Python API with the .NET signing key (question 84), smoke-test it, then point the
   web proxy `API_URL` and the public API host name at it (same paths, same JSON, same token
   format and signing key, so sessions survive; question 83).
5. Watch: readiness, error rate, `auth_refusals_total`, replay outcomes, and the
   unassigned-user count log line.
6. Keep SQL Server read-only for the agreed retention period (question 13); the rollback is to
   point `API_URL` and the host name back, with the writes made in between re-entered by hand
   from the change log: no reverse copy is built, and the freeze window is the safety.

## 6. Decisions needed before this phase

In `docs/13-open-questions.md`, ticked at the top of the runbook: whether any SQL Server
database is worth migrating (11); whether refresh tokens and trusted devices move (12;
recommended: trusted devices yes, so phones stay trusted; refresh tokens yes, so sessions
survive; verification codes no); the retention period for the frozen SQL Server copy (13);
people without a phone number (16), name folding (17) and Windows time-zone ids (18); and,
from building the tool, the dates of trusted devices (82), how the clients reach the new API
(83), the signing key (84) and who may leave refused rows behind (85).

## 7. The legacy PostgreSQL database (the data in production)

The data that must survive is not in SQL Server. Production runs an older, single-organization
application on PostgreSQL; its dump of 13 October 2026 is `docs/xcode_20261013T0836Z.dump`
(production data with personal details and password hashes: it is excluded from git and never
copied into a report). This section maps that database straight onto the schema of
`docs/04-schema.md` and the behaviour of the `db/routines`; the .NET code and the SQL Server map
of section 3 play no part in it. The approach of section 1 (extract, transform validated against
the target, load in one transaction, dry run first, every changed or made value listed) applies
unchanged; sections 7.1 to 7.6 are the parts that differ. The tool implements it as a second
source kind (`extract --source legacy`; `legacy_*.py` in `tools/migrate_from_sqlserver`, built
2026-10-14 by `docs/prompts/10b-legacy-migration.md`), and this section follows the code.

### 7.1 The source, as measured

Measured on the dump restored into a scratch PostgreSQL 16 cluster (`pg_restore --no-owner
--no-acl`), 2026-10-13:

| Fact | Value |
|---|---|
| Server | PostgreSQL 16.15 (Ubuntu), database `xcode`, owner `doadmin` (a managed cluster) |
| Schema version | alembic `d8e1a4f9c220`; everything in `public` |
| Organizations | none: one fleet per database; every row belongs to it |
| Rows | `users` 7, `roles` 3, `permissions` 43, `vehicles` 9, `categories` 11, `entries` 295, `records` 6,132, `petty_cash` 2,583, `petty_cash_daily_balances` 378, `budgets` 390, `provisions` 2, `password_reset_codes` 0, `alembic_version` 1 |
| Soft deletes | `deleted_at` exists on every table and is null on every row |
| Money | `double precision` everywhere; every stored amount has at most 2 decimals and every quantity at most 3 |
| Derived columns | kept by triggers: `records.name`, `registration`, `category_id`, `week`, `position`; `petty_cash.name`, `registration`, `category`; `budgets.actual`; `users.permissions`, `role`; `vehicles.provision_cf`; the whole of `petty_cash_daily_balances`. Every derived column agrees with its source on this dump, except the daily balances (7.5) |
| People | 7, all active, signing in by e-mail and bcrypt password (`$2b$12$`); 6 have a 10-digit `07…` number, 1 (an Administrator) has none; names are free text (6 of two words, 1 of one) |
| Roles | `Administrator` (system role, all 43 permissions, 3 people), `Manager 101` (25 permissions, 4 people), `Manager 1` (no permission, nobody) |
| Vehicles | 9 in 2 saccos (`Zuri Genesis` 6, `Metro Trans` 3); 8 registrations lack the space the target requires (`KBT881Z`), 1 has it |
| `entries` | the item catalogue: 3 `plus` (`Earnings`, used by every revenue row, and two unused) and 292 `minus` items in 10 categories, 5 of them without a category; two names repeat inside a category (`Body Works`/`Body Branding`, `Incentives`/`Crew Incentives`), both copies in use |
| `records` | one row per vehicle, day and item: 3,527 `Earnings` rows (revenue, 2024-12-29 to 2026-10-01), 1,407 `minus` rows entered directly (vehicle expenses), and 1,198 `minus` rows the petty-cash trigger copied from committed petty-cash expenses (same id link, amount, day, vehicle and item on every one) |
| `petty_cash` | one global float: 196 cash-in rows (`plus`), 2,381 expenses (item, vehicle, `unit_price` × `quantity` = `minus`), 6 credit notes (`minus` with a payee in `source` and a `description`); 1,198 expenses `committed`, 1,183 not; `manager_id` null on 1,862 rows (all before May 2026), one person marked `is_default_petty_cash_manager` |
| `provisions` | 2 deposits of 1,000 for one vehicle (2026-04-01); its `provision_cf` 2,000 |
| `budgets` | 390 rows per vehicle, category and month (2025-01 to 2026-08); 32 carry a budget, the rest only the trigger's `actual` |

### 7.2 Approach and parameters

- `extract --source legacy` reads a restored copy (never the production cluster) through
  `XCODE_MIGRATION_LEGACY_URL`, in one `REPEATABLE READ READ ONLY` transaction, one query per
  target table (7.3), writing the same CSV-plus-manifest form as section 1. The manifest records
  the source kind, the alembic version, every legacy table's count and the source figures 7.5
  checks (worked out in SQL in the same transaction). It refuses a database that answers a
  write (the copy itself is marked `default_transaction_read_only = on` with `ALTER DATABASE`,
  or is a standby; a URL or `PGOPTIONS` that only makes the tool's own session read-only does
  not pass), any other alembic version
  than the one this section was written against (until the map is checked against it), and
  any soft-deleted row (the map does not cover one). Amounts leave PostgreSQL as the shortest
  decimal that reads back as the same `double precision`; the transform refuses a value that
  would round (more than 2 decimals for an amount, 3 for a quantity). The password hashes are
  never read. The records table is read by three queries that split it (revenue: no petty-cash
  link and a `plus` item; expenses: no link and any other item; copies: a link); the load
  checks that each legacy table's files hold exactly its rows.
- The organization, its settings rows and its four roles are made as `api.ops_provision_user`
  makes them (`tenancy.seed_roles`), with the defaults of `docs/04-schema.md` 4.3 (Africa/Nairobi,
  KES), which match the source. Its name and slug are parameters (`--organization-name`,
  `--organization-slug`).
- `--migrated-by <e-mail>` names the Administrator who becomes the author of every value the
  source never stored: `captured_by`/`updated_by` of revenue, `recorded_by`/`updated_by` of
  central expenses, the reviewer of approved petty-cash expenses, `recorded_by` of cash given.
  Every such value is listed (question 91; the owner named the person, so all cash received
  shows as given by them). The e-mail may be the person's old or new one; they must move as an
  Owner.
- `--people <csv>` (`legacy_email,email,phone,role`, one row per legacy user) gives the e-mail,
  number and role each person moves with; `role` is `Owner` or `Fleet manager`, empty for the
  role 7.3 row 4 derives. A legacy user missing from the file, or left without a number, is
  refused, which stops the load (questions 90 and 98; `docs/13` question 16). The file holds
  personal details: it is written for the night from the owner's letter, kept outside the
  repository, and never echoed into the tool's output (the report names people by role and
  legacy creation date; a problem in the file is reported by line number, never by value).
- `--fleet-numbers <csv>` as in 3.1.
- The target must be empty and migrated to the head (`0014` when this was written); the load is
  the one of section 1 (one transaction, `--dry-run` always rolls back, `--apply` commits only
  when every check of 7.5 passes, `ops.operator_actions` row `data_migration_load`).
- Held-back rows (7.3 rows 12 to 14: the deductions on items without a category and the
  expense without a vehicle, 180 on the dump; also, none on the dump, a day with two different
  revenue amounts, an amount that does not divide by its quantity to the cent, a unit price
  times quantity that does not give the amount, and an amount that would round) are refused
  rows of section 1, acknowledged with `--accept-rejected 180`; the owner resolves them after
  the move (questions 95 and 96).
- `report` also writes the exceptions list the owner asked for (`exceptions.csv` in the work
  directory): one row per held-back, left-out or dropped row, possible double moved and
  petty-cash balance day, with its kind, the legacy day, vehicle, item, amount,
  entry time (Nairobi), a one-line reason, the legacy table and id, and empty Decision and Note
  columns for the owner. No user names, e-mails, numbers or payees; cash labels as typed (they
  can hold a first name: the list stays with the owner's team). A balance day is a stored day
  on which the gap between the old daily balance and the entries' own balance changes (on the
  dump: 17 and 24 September and 9 October 2026, which the letter asks for, and the one-day
  blip of 28 and 29 December 2025, 7.6).

### 7.3 Table map

Ids are kept wherever the source has one (every legacy key is a UUID); made rows take a UUIDv5
of the organization and their natural key, so a rerun makes the same ids. Counts are those of the
2026-10-13 dump.

| Order | Source | Target | Rules | Rows not moved (dump) |
|---|---|---|---|---|
| 1 | `users` | `identity.users` | `email` and `phone` from the person's `--people` row (the owner's letter changes five e-mails and gives the missing number; listed by role, not by value); `email` lower-cased (unique); `phone` normalised as `identity.normalize_phone` (`07…` to `+2547…`); `pin_hash` null (bcrypt passwords cannot become PINs: everyone starts "Not signed in yet" and signs in with number, code and a new PIN, DN-B2-1); `status` `active`; counters 0; `created_at`/`updated_at` kept | none; a user missing from `--people` is refused |
| 2 | made | `tenancy.organizations`, `organization_localizations`, `organization_brandings`, `organization_security_policies`, `tenancy.roles` | as `api.ops_provision_user` with the parameters of 7.2 | |
| 3 | `users` | `tenancy.memberships` | `name` split at its last space into `first_name`/`last_name`; a one-word name fills both (listed); `active` true; `approval_limit` null; back-dating limit `none` (question 98) | none |
| 4 | `users.role_id` | `tenancy.person_roles` | the `role` of `--people` when given (the letter moves one Manager 101 up to Owner); otherwise `Administrator` to Owner and any other role to Fleet manager, with the overrides of 7.4 (an Owner has none) | none |
| 5 | `users.permissions` | `tenancy.permission_overrides` | 7.4: the person's legacy permissions translated to rights, dependencies added, overrides = that set against the role's defaults | the legacy keys with no right (listed per person) |
| 6 | made | `tenancy.data_scopes` | `all_companies` true for every person: the source has no data scopes, everybody saw every vehicle; without a scope a Fleet manager would see none | |
| 7 | `vehicles.sacco` | `setup.psv_companies` | one company per distinct trimmed sacco name, folded as `upper` under `C`, spelled as on its earliest vehicle (a vehicle whose spelling differs is listed) (2) | none |
| 8 | `vehicles` | `setup.fleet_vehicles` | `registration` upper-cased into `K?? 999?` with the space (8 changed, listed); a registration that still fails the CHECK is refused; `joined_on` = the earliest of `created_at` (Nairobi date) and the vehicle's first revenue, expense, petty-cash or provision day (7 vehicles have history from before they were created in the source); `left_on` null; `fleet_number` from `--fleet-numbers` or null; `initial_investment` null | none |
| 9 | `categories` (`factor` `minus`) | `setup.expense_categories` | names kept; `main_category_id` null ("Not set": the design notes, three-level categories) and `bucket` null; ids kept | `Income` (`plus`, holds only `Earnings`) |
| 10 | `entries` (`factor` `minus`) without a category | not moved | an item needs a category, and the owner holds back the deductions on these items until they decide how to treat them (question 96); listed, made once the owner decides | 5 (`Savings`, `Sacco`, `Sacco L`, `Sacco D`; `Balance B/D(-)` is unused) |
| 11 | `entries` (`factor` `minus`) with a category | `setup.expense_items` | ids kept; a second item whose name folds (`upper` under `C`) to one already in the category is merged into the first: its id maps onto the first's everywhere it is used (2 merged, listed); `position`, `primary` not moved | the 3 `plus` items (`Earnings` becomes revenue, 7.3 row 12; the two others are unused) |
| 12 | `records` of `Earnings` | `revenue.records` | one row per vehicle and day; `amount` kept; an amount of 0 becomes reason 4 (Other) with the note `0 in the old system` (2, question 93); a second row for the same vehicle and day with the same amount is dropped as a double entry, keeping the one entered first by `created_at` (5, 38,450 in all, question 92; on the exceptions list); differing amounts on one day hold back every row of that day (refused, on the exceptions list; none on the dump); `captured_at`/`updated_at` from `created_at`/`updated_at`; `captured_by`/`updated_by` the migrated-by person; `corrected_after_date` false; `version` 1; `locked` not moved | 5 double entries |
| 13 | `records` of `minus` items without `petty_cash_id` | `expenses.entries` | `entry_date` = `date`; item through row 11; `units` = `quantity`, `unit_amount` = `minus / quantity` (exact on every row: 1,406 of quantity 1, 1 of quantity 2; a row where it is not exact to the cent is held back), `total` checked against `minus`; a purchase of its own (`group_id` = id, `group_size` 1, group figures = its own); `note` null; authors the migrated-by person; dates from `created_at`/`updated_at`; `version` 1; a row on an item of row 10 is held back (refused with its key and the reason, on the exceptions list; 179 for 1,031,025, question 96); moved: 1,228 for 25,456,717 | 179 held back |
| - | `records` with `petty_cash_id` | not moved | copies of committed petty-cash expenses (row 14 moves the originals; the vehicle report posts approved petty-cash expenses itself, `setup.fleet_postings`); each is matched to its original (amount, day, vehicle, item) and a mismatch, a copy without its original, or a committed expense with a vehicle and an item but no copy stops the transform | 1,198 |
| 14 | `petty_cash` | `pettycash.entries` | `holder_id` = the legacy default petty-cash manager on every row: the owner keeps one float, hers (`manager_id` null on 1,862 rows and another person's on 1, cash of 29 June 2026; both listed); cash in (`plus`): kind 1, `unit_amount` = `plus`, `note` = `name` (the label as typed: "Cash Received" or the user's own, 25 characters at most; `source`, on 57 rows, always repeats it), `recorded_by`/`updated_by` the migrated-by person; expense: kind 2, `units` = `quantity`, `unit_amount` = `unit_price` (`unit_price` × `quantity` must equal `minus` exactly, else held back), `note` = `description` (none on the dump), status 2 approved when `committed` (reviewer and `updated_by` the migrated-by person, `reviewed_at` = `updated_at`), else 1 waiting (`updated_by` the holder), `recorded_by` the holder; credit note: kind 3, `unit_amount` = `minus`, `payee` = `source` unless it is the old application's generic label `Credit Note` (all six on the dump: no payee), `note` = `description` (what the credit was for), status null, `recorded_by`/`updated_by` the holder; a row of amount 0 is dropped (3: it moves no money and the target refuses a zero total); an expense without a vehicle is held back (refused with its key, on the exceptions list; 1, 30,000, waiting, question 95); a row that repeats another of the same day exactly (expense: vehicle, item, amount, quantity; cash: amount and label, `name`) moves as it is and is listed for the owner to confirm (12 expenses, 4 cash, question 100); `recorded_at`/`updated_at` from `created_at`/`updated_at`; `version` 1; moved on the dump: 195 cash in (6,788,630), 1,196 approved (3,895,300), 1,182 waiting (3,362,187), 6 credit notes (120,700) | 3 dropped, 1 held back |
| - | `petty_cash_daily_balances` | not moved | the target computes the float from the entries (PC-4); the stored table is compared in 7.5 | 378 |
| - | `provisions`, `vehicles.provision_bf`/`provision_cf` | not moved | the saving model starts empty; each vehicle's provision balance is listed for the owner to enter as a saving opening after cutover (question 97) | 2 |
| - | `budgets` | not moved | the target has no budgets; the 32 rows with a budget are listed (question 97) | 390 |
| - | `roles`, `permissions` | replaced | by the four roles and the 59-right catalogue (7.4) | 3, 43 |
| - | `password_reset_codes`, `alembic_version` | not moved | | 0, 1 |

Not made: `identity.trusted_devices` and `refresh_tokens` (no device or session exists in the
source), target sets (the source has no targets: every vehicle starts without one and the owner
sets them), away periods, investments, scheduled items and savings, change log and audit events
(history starts at cutover; the load's operator action is its first entry).

### 7.4 Rights

The legacy permission names translate to the rights of `docs/15-design-v2-3.md` 3.1; the
resolver then adds each right's needs. An Administrator becomes an Owner (all 59 and
`organization.manage`) without overrides. Anyone else becomes a Fleet manager with overrides
that grant the rest of their translated set (the translated set always contains the Fleet
manager defaults on this dump; a default not in the set would be denied by an override).

| Legacy permission | Rights |
|---|---|
| `dashboard:read`, `dashboard:overview`, `dashboard:financial` | `dash.net` |
| `dashboard:vehicles` | `dash.gaps` |
| `dashboard:petty_cash` | `dash.pettycash` |
| `records:read` | `revenue.view`, `expenses.view` |
| `records:write` | `revenue.capture`, `expenses.capture` |
| `records:delete`, `records:lock` | `revenue.correct`, `expenses.correct` |
| `categories:read`, `entries:read` | `catalog.view` |
| `categories:write`, `entries:write` | `catalog.add`, `catalog.edit` |
| `categories:delete`, `entries:delete` | `catalog.stop` |
| `vehicles:read` | `vehicles.view`, `companies.view` |
| `vehicles:write` | `vehicles.add`, `vehicles.edit`, `vehicles.target`, `companies.add`, `companies.edit` |
| `petty_cash:read` | `pettycash.view`, `pettycash.view_all` (one float in the source: reading it meant seeing all of it) |
| `petty_cash:write_expense` | `pettycash.spend`, `pettycash.edit_own` |
| `petty_cash:write_cash` | `pettycash.issue`, `pettycash.issue_negative` (the source float went below zero freely) |
| `petty_cash:write_credit_note` | `pettycash.credit` |
| `petty_cash:commit` | `pettycash.approve_item`, `pettycash.approve_day`, `pettycash.send_back`, `pettycash.reject`, `pettycash.reopen` |
| `petty_cash:delete` | `pettycash.delete`, `pettycash.delete_approved`, `pettycash.delete_cash` |
| `petty_cash:reconcile`, `reports:petty_cash` | `pettycash.reports` |
| `provisions:read` / `write` / `delete` | `savings.view` / `savings.add`, `savings.edit` / `savings.pause` |
| `reports:read`, `reports:income`, `reports:expenses`, `reports:print`, `statements:read` | `reports.view` |
| `reports:export` | `reports.export`, `revenue.export`, `expenses.export`, `pettycash.export` |
| `users:read`, `roles:read`, `permissions:read` | `people.view` |
| `users:write`, `roles:write`, `roles:delete` | `people.add`, `people.edit`, `people.block`, `people.sign_in` |
| `budgets:read`, `budgets:write`, `reports:budget` | none (no budgets; listed as not carried) |

A person whose legacy role holds no permission (`Manager 1`: nobody on the dump) becomes a Fleet
manager with every default denied. On this dump the three people who stay `Manager 101` (the
owner's letter moves the fourth up to Owner) get 29 rights: the Fleet manager's 11 plus 18
granted by overrides (`catalog.view`, `catalog.add`, `catalog.edit`, `pettycash.view_all`,
`pettycash.reports`, `expenses.capture`, `expenses.correct`, `reports.export`, `revenue.export`,
`expenses.export`, `pettycash.export`, `vehicles.view`, `vehicles.add`, `vehicles.edit`,
`vehicles.target`, `companies.view`, `companies.add`, `companies.edit`), none denied; as before,
they cannot approve petty cash, issue cash or manage people. The translation is question 98,
decided 2026-10-14 with the roles of the letter.

### 7.5 Verification

On top of the generic checks of section 4 (refused rows acknowledged, the ledger per target
table, `xcode-api db verify` before and after, deferred constraints, counts, checksums, every
tenant row in the organization), the load runs these against the source figures the extract
records less the rows the transform says did not move; each must pass for `--apply`:

- **Every legacy row**: each legacy table's files hold exactly its rows, and each file's rows
  are loaded, dropped by a named rule of 7.3, refused, or replaced by rows the tool made
  (`roles`, `permissions`); the report prints the four counts per file.

- **People**: every legacy user is a person with an active membership, the role `--people`
  gives or 7.3 row 4 derives, an all-companies scope, and no PIN; each person's rights contain
  their translated set (7.4); rights before and after are printed side by side; every
  petty-cash entry's holder is the one float holder.
- **Revenue**: per vehicle and month, the count of days and the sum of `Earnings` minus the
  dropped double entries equal the target's (`revenue.records`, amounts plus reason-only days).
  On the dump: 3,522 days, 27,312,770.
- **Vehicle costs**: per vehicle and month, the legacy `minus` records (the direct ones and the
  petty-cash copies) equal the target's live central expenses plus approved petty-cash expenses,
  less refused rows. On the dump: 30,383,042 less the 1,031,025 held back = 29,352,017 =
  25,456,717 central + 3,895,300 approved petty cash.
- **Petty cash**: per kind and status, count and sum; the float (cash − credit notes − expenses,
  every live entry, any status) equals the legacy `sum(plus) − sum(minus)` over every row, less
  refused rows. On the dump: −619,557 over the source rows, −589,557 with the 30,000 expense held
  back (accepted by the owner). Printed beside it, not checked: the legacy `petty_cash_daily_balances` on the
  extraction day and the first day it differs from its own entries (on the dump: −2,580,518 on
  9 October 2026; first differs on 28 December 2025, 15 days in all, 7.6).
- **Through the routines**: for every vehicle and the last full month, `setup.fleet_postings`
  (what the vehicle report reads) equals the vehicle-cost figure above; and every person, by
  their number, gets the "Not signed in yet" path from `api.auth_start` (a first-setup code;
  inside the load's transaction, rolled back with it in a dry run).

### 7.6 What the owner sees after cutover

- Everyone signs in afresh: number, a code, then a new PIN. Code delivery (SMS or e-mail) must
  work on the night (`docs/08-operability.md`).
- 619 vehicle-days have no record in the source; they show as Missing days. No vehicle has a
  target until the owner sets one.
- The float reads −589,557 (from the entries, without the held-back 30,000 expense; −619,557 once
  it is added) where the old daily-balance page read −2,580,518 on 9 October 2026: the stored
  daily balances agree with the entries on every day with entries until 16 September 2026 and
  differ on 14 days from 17 September (the old trigger's carry-forward); 2 balance rows have no
  entry at all, and one of them (28 December 2025) reads 23,612 above the entries, the next day
  being back in line. The owner chose the entries' balance (point 10 of the letter) and traces
  the 1,960,961 gap from the exceptions list: the gap grows by 577,627 on 17 and 24 September
  and 805,707 on 9 October (and the list also shows the 28/29 December blip).
- 1,182 petty-cash expenses arrive waiting for approval (the source never committed them; the
  oldest is from July 2025) (question 94).
- Held back, on the exceptions list for the owner to resolve: the 30,000 expense without a vehicle
  (question 95) and the 179 deductions entered on items without a category (`Savings` 167 for
  832,100, `Sacco` 6, `Sacco L` 1, `Sacco D` 5; 1,031,025 on four vehicles). Until they move,
  those four vehicles show that much less in expenses than the old system (question 96).
- Also on the list, moved: 12 petty-cash expenses and 4 cash entries that repeat another of the
  same day exactly, for the owner to confirm (question 100).
- Expense categories show "Not set" for their main category until the owner files them; fleet
  numbers are empty unless supplied.
