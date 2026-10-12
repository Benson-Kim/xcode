# Data migration: SQL Server to PostgreSQL, and cutover

Applies only if a SQL Server database holds data that must survive (staging or
production). If the only populated databases are developer machines, skip the copy and
provision users again with `xcode-api provision-user`.

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
   reference a refused row are refused by their foreign key in turn. The load files are
   PostgreSQL's own export of the accepted rows, after a check that the database holds
   exactly the values the transform produced. `transform.json` lists every refused row, every
   row dropped by a documented rule, every changed value with its key and reason, and every
   row the tool made.
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
| 31 | `AuditEvents` | `tenancy.audit_events` | `Before`/`After` validated into `jsonb`; the identity `id` numbered from 1 in (`OccuredAt`, `OrganizationId`, `Id`) order, each source `Id` listed against its number; the identity sequence set to the highest on `--apply` | none |
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
