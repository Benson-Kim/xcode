# Schema

The PostgreSQL schema that replaces the 34 SQL Server tables of the .NET API. Source of the
current behaviour: `docs/inventory/inventory-persistence.md` (sections 1 to 4 and 9), with
the wire facts in `docs/inventory/inventory-http-contract.md`. Conventions (schemas, roles,
RLS, naming, types) are in `docs/03-database.md`; this document applies them table by table
and is what prompt 02 builds. Where this document and the inventory disagree on current
behaviour, the inventory wins and this document is corrected in the same change.

Reading rules:

- Types: `uuid`, `text` with a `CHECK` on `char_length`, `numeric(14,2)` for money (the
  .NET precision; the domain cap of 999 999 999 999.99 is the column's own cap), `timestamptz`
  (always UTC), `date`, `boolean`, `smallint` for coded enumerations, `bigint` for versions.
- Every table that is updated in place has `created_at timestamptz NOT NULL DEFAULT now()`
  and `updated_at timestamptz NOT NULL DEFAULT now()`, the latter maintained by the trigger
  `ops.touch_updated_at()`. Append-only tables have only their business instant.
- Ids are `uuid` with `DEFAULT gen_random_uuid()`; routines accept a client-supplied id
  only where the contract says so: today only the petty-cash entry create (`P05`, the
  phone's replay key, section 6.2); everywhere else ids are server generated and returned.
- "Tenant table" means: `organization_id uuid NOT NULL` as the first primary-key column,
  a foreign key to `tenancy.organizations(id)`, `ENABLE ROW LEVEL SECURITY`, and the
  `tenant_isolation` policy of `docs/03-database.md` section 2. Composite foreign keys
  between tenant tables always start with `organization_id`, so a row can never point at
  another organization's row.
- "Writes" names the privileges granted to `xcode_api_executor`: `I` insert, `U` update,
  `D` delete; `SELECT` is always granted. Append-only tables get `I` only; rules that the
  .NET code enforced in `ValidateWrites` become privileges here.
- `.NET` names the source table; the source columns are in the inventory, section 1.
- Constraint names: `pk_<table>`, `uq_<table>_<rule>`, `fk_<table>_<target>`,
  `ck_<table>_<rule>`, `ex_<table>_<rule>`, indexes `ix_<table>_<rule>`; `<table>` drops the
  `organization_` prefix (`ck_brandings_contrast`, `ck_security_policies_pin_length`). The
  expected tables, keys, writes and indexes are declared once in
  `src/xcode_api/db/schema_spec.py`, which `db verify` compares with the live database.

## 1. Table index

| # | Table | .NET table | Tenant | Writes | Notes |
|---|---|---|---|---|---|
| 1 | `identity.users` | `Users` | no | I U | never deleted |
| 2 | `identity.verification_codes` | `VerificationCodes` | no | I U | consumed, not deleted |
| 3 | `identity.trusted_devices` | `TrustedDevices` | no | I U | revoked, not deleted |
| 4 | `identity.refresh_tokens` | `RefreshTokens` | no | I U | revoked, not deleted |
| 5 | `identity.sign_in_attempts` | new | no | I | security audit trail |
| 6 | `tenancy.organizations` | `Organizations` | self (policy on `id`) | I U | insert only through `api.ops_*` |
| 7 | `tenancy.memberships` | `Memberships` | yes | I U | |
| 8 | `tenancy.organization_localizations` | `Localizations` | yes | I U | one row per organization |
| 9 | `tenancy.organization_brandings` | `Brandings` | yes | I U | one row per organization |
| 10 | `tenancy.organization_logos` | `Logos` | yes | I U D | hard delete is the contract |
| 11 | `tenancy.organization_security_policies` | `SecurityPolicies` | yes | I U | one row per organization |
| 12 | `tenancy.user_preferences` | `UserPreferences` | yes | I U | |
| 13 | `tenancy.roles` | `Roles` | yes | I | seeded at organization creation |
| 14 | `tenancy.person_roles` | `PersonRoles` | yes | I U | one row per membership |
| 15 | `tenancy.permission_overrides` | `PermissionOverrides` | yes | I U D | |
| 16 | `tenancy.permissions` | in code (`PermissionCatalog`) | no (global) | none | seeded by migration |
| 17 | `tenancy.permission_dependencies` | in code | no | none | seeded by migration |
| 18 | `tenancy.role_defaults` | in code | no | none | seeded by migration |
| 19 | `tenancy.data_scopes` | `SetupDataScopes` | yes | I U D | |
| 20 | `tenancy.data_scope_companies` | `SetupCompanyScopes` | yes | I D | |
| 21 | `tenancy.data_scope_vehicles` | `SetupVehicleScopes` | yes | I D | |
| 22 | `tenancy.change_log` | `OrganizationSettingsVersion` | yes | I | the organization history |
| 23 | `tenancy.audit_events` | `AuditEvents` | yes | I | security trail, never served |
| 24 | `setup.psv_companies` | `PsvCompany` | yes | I U | never deleted |
| 25 | `setup.fleet_vehicles` | `FleetVehicle` | yes | I U | never deleted; registration immutable |
| 26 | `setup.vehicle_targets` | `VehicleTarget` | yes | I | append-only |
| 27 | `setup.vehicle_away_periods` | `VehicleAwayPeriod` | yes | I | append-only, non-overlapping |
| 28 | `setup.vehicle_investments` | `VehicleInvestment` | yes | I U D | the one editable, deletable setup record |
| 29 | `setup.recurring_items` | `RecurringItem` | yes | I U | never deleted |
| 30 | `setup.recurring_versions` | `RecurringVersion` | yes | I | append-only |
| 31 | `setup.recurring_allocations` | `RecurringAllocation` | yes | I | append-only |
| 32 | `setup.expense_categories` | `ExpenseCategory` | yes | I U | never deleted |
| 33 | `setup.expense_items` | `ExpenseItem` | yes | I U | never deleted |
| 34 | `setup.recurring_kinds` | `RecurringKindLookup` | no | none | code table |
| 35 | `setup.recurrence_frequencies` | `RecurrenceFrequencyLookup` | no | none | code table |
| 36 | `setup.expense_buckets` | `ExpenseBucketLookup` | no | none | code table |
| 37 | `revenue.records` | `RevenueRecords` | yes | I U | never deleted |
| 38 | `revenue.no_earnings_reasons` | in code (`RevenueNoEarningsReason`) | no | none | code table |
| 39 | `ops.schema_migrations`, `ops.routine_versions`, `ops.operator_actions`, `ops.rate_limit_windows` | `__EFMigrationsHistory`, new | no | see prompt 01 | created by prompt 01 |
| 40 | `pettycash.entries` | `PettyCashEntries` (uncommitted feature) | yes | I U | soft-removed, never deleted; section 6.2 |

Dropped, not ported: `RolePermissions` (nothing reads or writes it), `CostCategoryLookup`
and `RecurringVersion.Category` (already removed in .NET). The three .NET lookup tables
survive as code tables because the wire sends their integers; the fourth code table
(`revenue.no_earnings_reasons`) replaces an enum that had no table.

## 2. Code tables (enumerations with wire integers)

The wire sends integers for `kind`, `frequency` and `bucket`, and labels for the revenue
reason. The database stores the same integers (`smallint`) with a foreign key to a code
table, so no mapping exists anywhere: stored value = wire value = domain enum value. The
Python `domain` enums repeat the codes and `tests/db/test_enum_parity.py` proves they
match these tables. Labels are the exact strings the clients show or send.

| Table | Rows (`code`, `name`, `label`) |
|---|---|
| `setup.recurring_kinds` | 1 `cost` "Cost"; 2 `savings` "Savings" |
| `setup.recurrence_frequencies` | 1 `daily` "Daily" (legacy, readable, refused on save); 2 `weekly` "Weekly"; 3 `monthly` "Monthly"; 4 `yearly` "Yearly" |
| `setup.expense_buckets` | 1 `repairs_and_maintenance` "repairs and maintenance"; 2 `recurring_charges` "recurring charges"; 3 `loan_repayments` "loan repayments" |
| `revenue.no_earnings_reasons` | 1 `garage` "Garage"; 2 `arrest` "Arrest"; 3 `no_crew` "No Crew"; 4 `other` "Other" |

Each code table: `code smallint PRIMARY KEY`, `name text NOT NULL UNIQUE`, `label text NOT
NULL`; no RLS; `SELECT` for `xcode_api_executor` and `xcode_readonly`; rows inserted by the
migration that creates the table; no routine writes them. `revenue.no_earnings_reasons.name`
is also the enum name the .NET change-log snapshots carry (`NoCrew` becomes `no_crew` in the
column, but the snapshot builder emits the .NET name, section 6 of `docs/05-routines.md`).

Text-coded enumerations that never reach the wire use a `CHECK`, not a table:
`identity.users.status` (`active`, `removed`), `identity.verification_codes.purpose`
(`first_setup`, `new_device`, `pin_reset`), `tenancy.change_log.section` (the wire section
strings, section 4.9), `identity.sign_in_attempts.outcome`.

## 3. Identity schema

Not tenant tables: no `organization_id`, no RLS. They are reachable only through
`identity.*` and `api.auth_*` routines; `xcode_readonly` has no privilege here.

### 3.1 `identity.users`

| Column | Type | Null | Default | Constraint |
|---|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` | PK |
| `email` | text | no | | `char_length <= 320`, `email = lower(email)`, UNIQUE |
| `phone_number` | text | no | | `~ '^\+254[17][0-9]{8}$'`, UNIQUE |
| `pin_hash` | text | yes | | `~ '^[A-Za-z0-9+/]+=*\.[A-Za-z0-9+/]+=*$'` (`base64(salt).base64(hash)`) |
| `status` | text | no | `'active'` | IN (`active`, `removed`) |
| `security_version` | integer | no | 0 | `>= 0` |
| `failed_attempts` | integer | no | 0 | `>= 0` |
| `paused_until` | timestamptz | yes | | |
| `untrusted_failed_attempts` | integer | no | 0 | `>= 0` |
| `version` | bigint | no | 0 | bumped by every routine that updates the row |
| `created_at`, `updated_at` | timestamptz | no | `now()` | |

- .NET allowed `PhoneNumber = ''` for users created before phone sign-in (filtered unique
  index). Here the number is required; the data migration must resolve such rows
  (`docs/13-open-questions.md`).
- Start values of `version` (0 here, 1 on memberships and records) follow .NET so copied
  data and client-held versions stay meaningful.

### 3.2 `identity.verification_codes`

| Column | Type | Null | Default | Constraint |
|---|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` | PK |
| `user_id` | uuid | no | | FK `identity.users(id) ON DELETE CASCADE` |
| `purpose` | text | no | | IN (`first_setup`, `new_device`, `pin_reset`) |
| `device_id` | text | no | | `char_length BETWEEN 1 AND 128` |
| `code_hash` | text | no | | `~ '^[0-9A-F]{64}$'` (HMAC-SHA256, upper-case hex) |
| `created_at` | timestamptz | no | `now()` | |
| `expires_at` | timestamptz | no | | |
| `consumed` | boolean | no | false | |
| `failed_attempts` | integer | no | 0 | `>= 0` |

- Index `(user_id, purpose, created_at DESC)`; no uniqueness (several codes per purpose can
  exist; "newest usable" is decided in `identity.matching_code`). A withdrawn code has
  `consumed` and `expires_at = created_at`.

### 3.3 `identity.trusted_devices`

| Column | Type | Null | Default | Constraint |
|---|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` | PK |
| `user_id` | uuid | no | | FK users ON DELETE CASCADE |
| `device_id` | text | no | | `char_length BETWEEN 1 AND 128` |
| `revoked` | boolean | no | false | |
| `trust_expires_at` | timestamptz | yes | | null = never |
| `created_at`, `updated_at` | timestamptz | no | `now()` | |

- UNIQUE `(user_id, device_id)`.

### 3.4 `identity.refresh_tokens`

| Column | Type | Null | Default | Constraint |
|---|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` | PK |
| `user_id` | uuid | no | | FK users ON DELETE CASCADE |
| `device_id` | text | no | | `char_length BETWEEN 1 AND 128` |
| `token_hash` | text | no | | `~ '^[0-9A-F]{64}$'`, UNIQUE |
| `expires_at` | timestamptz | no | | |
| `revoked` | boolean | no | false | |
| `version` | bigint | no | 0 | |
| `created_at`, `updated_at` | timestamptz | no | `now()` | |

- Index `(user_id, device_id)`.

### 3.5 `identity.sign_in_attempts` (new, append-only)

One row per authentication decision, written by the `api.auth_*` routines in the same
transaction as the decision. It is the "assume breach" trail of `docs/12-security.md`
section 4; nothing serves it over HTTP.

| Column | Type | Null | Default | Constraint |
|---|---|---|---|---|
| `id` | bigint | no | identity | PK |
| `occurred_at` | timestamptz | no | | |
| `operation` | text | no | | IN (`sign_in`, `verify_device`, `request_code`, `verify_code`, `complete_pin`, `refresh`, `sign_out`, `revoke_device`) |
| `outcome` | text | no | | IN (`authenticated`, `verification_required`, `check_email`, `code_verified`, `paused`, `refused`, `signed_out`, `device_revoked`) |
| `refusal` | text | yes | | IN (`unknown_number`, `inactive`, `no_pin`, `wrong_pin`, `paused_untrusted`, `untrusted_cap`, `wrong_code`, `code_expired`, `token_unknown`, `token_replayed`, `token_expired`, `device_untrusted`, `policy_pin_length`) |
| `user_id` | uuid | yes | | FK users, null for unknown numbers |
| `phone_digest` | text | no | | SHA-256 hex of the normalised number or of the raw input when it does not normalise |
| `device_id` | text | no | | `<= 128` |
| `request_id` | text | yes | | `<= 128` |

- Index `(user_id, occurred_at DESC)`, `(phone_digest, occurred_at DESC)`.

## 4. Tenancy schema

### 4.1 `tenancy.organizations`

| Column | Type | Null | Default | Constraint |
|---|---|---|---|---|
| `id` | uuid | no | `gen_random_uuid()` | PK |
| `slug` | text | no | | `~ '^[a-z0-9]+(-[a-z0-9]+)*$'`, `<= 100`, UNIQUE |
| `name` | text | no | | `char_length BETWEEN 1 AND 200` |
| `business_date` | date | yes | | null = follow the calendar in the organization zone |
| `settings_version` | bigint | no | 1 | the change-log counter; concurrency token of settings |
| `created_at`, `updated_at` | timestamptz | no | `now()` | |

- Policy: `USING (id = tenancy.current_organization()) WITH CHECK (id = tenancy.current_organization())`.
  Creation happens in `api.ops_provision_user` and `api.ops_seed_demo`, which call
  `tenancy.enter_organization_as_operator(new id)` before the insert.
- The counter: `tenancy.record_change` runs `UPDATE tenancy.organizations SET
  settings_version = settings_version + 1 WHERE id = $1 RETURNING settings_version` as the
  last statement before inserting the log row. Under `READ COMMITTED` concurrent writers of
  one organization queue on that row lock for the rest of the transaction; nothing fails
  and versions are gap-free and unique, which is what clients page by. The .NET retry loop
  disappears. The row is also the "settings changed" token: `api.organization_settings_set`
  passes the version it read and refuses (`XC409`) when it moved. The settings and logo
  writes lock the row first (`SELECT ... FOR UPDATE`): they read, merge and write
  per-organization rows, and two saves must queue instead of overwriting each other's
  fields.

### 4.2 `tenancy.memberships`

| Column | Type | Null | Default | Constraint |
|---|---|---|---|---|
| `organization_id` | uuid | no | | PK part, FK organizations |
| `user_id` | uuid | no | | PK part, FK `identity.users(id)` |
| `first_name` | text | no | | `char_length BETWEEN 1 AND 100` |
| `last_name` | text | no | | `char_length BETWEEN 1 AND 100` |
| `active` | boolean | no | true | |
| `approval_limit` | numeric(14,2) | yes | | `>= 0` |
| `version` | bigint | no | 1 | bumped on deactivate, reactivate, access change |
| `created_at`, `updated_at` | timestamptz | no | `now()` | |

- UNIQUE partial index `(user_id) WHERE active` (one active membership per person across
  all organizations; sign-in depends on it). Index `(organization_id, last_name, first_name, user_id)`
  for the people list order.

### 4.3 `tenancy.organization_localizations`

PK `organization_id` (FK). Defaults are the .NET domain defaults.

| Column | Type | Default | Constraint |
|---|---|---|---|
| `locale` | text | `'en-GB'` | `~ '^[a-zA-Z]{2,3}(-[a-zA-Z0-9]{2,8})*$'` |
| `time_zone` | text | `'Africa/Nairobi'` | IANA name; validated by `tenancy.check_time_zone` (routine, not CHECK) |
| `date_pattern` | text | `'medium'` | IN (`short`, `medium`, `long`) |
| `hour12` | boolean | false | |
| `first_day_of_week` | smallint | 1 | `BETWEEN 0 AND 6` (0 = Sunday) |
| `week_numbering` | text | `'iso8601'` | IN (`iso8601`, `local`) |
| `currency` | text | `'KES'` | `~ '^[A-Z]{3}$'` |
| `use_grouping` | boolean | true | wire name `useGrouping`; the legacy `useGroupping` is accepted on input and served in the appearance formats (`docs/06-http-contract.md` section 1.2) |
| `number_decimals` | smallint | 2 | `BETWEEN 0 AND 2` |
| `allow_locale_override` | boolean | true | |
| `allow_time_zone_override` | boolean | false | |
| `allow_hour12_override` | boolean | true | |
| `allow_theme_override` | boolean | true | |
| `created_at`, `updated_at` | timestamptz | `now()` | |

### 4.4 `tenancy.organization_brandings`

PK `organization_id` (FK). `primary`, `secondary`, `accent` are renamed because `primary`
is a reserved word; the wire keeps the old names.

| Column | Type | Null | Default | Constraint |
|---|---|---|---|---|
| `display_name` | text | no | `'XCODE'` | `char_length BETWEEN 1 AND 100` |
| `legal_name` | text | no | `'XCODE'` | `1..200` |
| `logo_alt` | text | no | `'XCODE'` | `1..200` |
| `primary_color` | text | no | `'#1D5FD6'` | `~ '^#[0-9a-fA-F]{6}$'` |
| `secondary_color` | text | no | `'#14213D'` | same |
| `accent_color` | text | no | `'#1E6B3A'` | same |
| `logo_light_url`, `logo_dark_url`, `favicon_url`, `terms_url`, `privacy_url` | text | yes | | `~ '^https://'`, `<= 2048` |
| `domain` | text | yes | | `<= 253`, `~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$'` |
| `support_email` | text | yes | | `<= 320`, contains `@` |
| `created_at`, `updated_at` | timestamptz | no | `now()` | |

- The WCAG contrast rule (each colour at least 4.5:1 against `#FFFFFF` and `#F6F3EC`) is
  `tenancy.check_contrast(hex, hex)`, an immutable SQL function used by
  `api.organization_settings_set` and by a `CHECK` on the three colour columns
  (`tenancy.check_contrast(primary_color, '#FFFFFF') >= 4.5 AND ...`). The same function
  exists in Python only as a parity test fixture, never as a second implementation.
- The ratio is computed in `double precision` (as .NET) and truncated, not rounded, to two
  decimals, so `>= 4.5` holds exactly when the unrounded ratio does (`#078A22` on white is
  4.499, served as 4.49 and refused). For an argument that is not `#RRGGBB` it returns
  `NULL`, so the format `CHECK` is the one that reports a malformed colour.

### 4.5 `tenancy.organization_logos`

PK `organization_id` (FK).

| Column | Type | Null | Constraint |
|---|---|---|---|
| `content_type` | text | no | IN (`image/png`, `image/jpeg`, `image/webp`) |
| `data` | bytea | no | `octet_length(data) BETWEEN 1 AND 262144` and the signature `CHECK`: png `substring(data from 1 for 8) = '\x89504e470d0a1a0a'`, jpeg `substring(data from 1 for 3) = '\xffd8ff'`, webp `substring(data from 1 for 4) = 'RIFF' AND substring(data from 9 for 4) = 'WEBP'` |
| `updated_at` | timestamptz | no | |

### 4.6 `tenancy.organization_security_policies`

PK `organization_id` (FK). Every bound is a `CHECK` named `ck_security_policies_<column>`.

| Column | Type | Default | Bounds |
|---|---|---|---|
| `password_min_length` | smallint | 12 | 12..128 |
| `password_complexity` | boolean | true | |
| `password_history` | smallint | 5 | 0..24 |
| `pin_length` | smallint | 4 | 4..8 |
| `lockout_threshold` | smallint | 5 | 3..10 |
| `lockout_minutes` | smallint | 15 | 1..60 |
| `access_token_minutes` | smallint | 10 | 1..15 |
| `refresh_token_days` | smallint | 30 | 1..90 |
| `idle_unlock_seconds` | integer | 300 | 30..3600 |
| `allow_pin_sign_in` | boolean | true | `CHECK (allow_pin_sign_in)` (cannot be disabled) |
| `created_at`, `updated_at` | timestamptz | `now()` | |

### 4.7 `tenancy.user_preferences`

PK `(organization_id, user_id)`, FK memberships.

| Column | Type | Null | Default | Constraint |
|---|---|---|---|---|
| `locale` | text | yes | | locale regex |
| `time_zone` | text | yes | | validated by routine |
| `hour12` | boolean | yes | | |
| `theme_mode` | text | yes | | IN (`light`, `dark`, `system`) |
| `reduced_motion` | boolean | no | false | |
| `font_scale` | double precision | no | 1 | `BETWEEN 1 AND 3` |
| `created_at`, `updated_at` | timestamptz | no | `now()` | |

- The override permissions (`allow_*_override`) are checked by `api.preferences_set`, not by
  the table: a stored value that the organization later disallows is kept and simply not
  offered back (current behaviour).

### 4.8 Access: roles, permissions, scopes

`tenancy.roles`: PK `(organization_id, id)`, `name text NOT NULL CHECK (1..100)`, UNIQUE
`(organization_id, lower(name))`, `created_at`. The four catalog roles are inserted by
`tenancy.seed_roles(organization_id)` when an organization is created and by the data
migration; `api.access_role_list` is read-only (the .NET "GET that writes" is retired).

`tenancy.person_roles`: PK `(organization_id, user_id)` FK memberships; `role_id uuid NOT
NULL`, FK `(organization_id, role_id) -> tenancy.roles`; `updated_at`. One role per person
(the .NET three-column key with a unique two-column index collapses to this).

`tenancy.permission_overrides`: PK `(organization_id, user_id, permission)`; FK
memberships; FK `permission -> tenancy.permissions(key)`; `granted boolean NOT NULL`.
Rows exist only for differences from the role defaults.

Global catalog (no RLS, read-only, seeded by migration `0004_access_catalog`, exact rows
in `docs/inventory/inventory-http-contract.md` section 3.2):

| Table | Columns |
|---|---|
| `tenancy.permissions` | `key text PK CHECK (~ '^[a-z]+\.[a-z_]+$')`, `group_name text`, `label text`, `group_order smallint`, `item_order smallint`; UNIQUE `(group_order, item_order)` |
| `tenancy.permission_dependencies` | `permission text FK`, `needs text FK`, PK both; `CHECK (permission <> needs)` |
| `tenancy.role_defaults` | `role_name text CHECK IN ('Owner','Office admin','Fleet manager','Revenue clerk')`, `permission text FK`, PK both |

`tenancy.effective_permissions(organization_id, user_id) RETURNS text[]` (in
`docs/05-routines.md`) is the only implementation of the resolver; `tenancy.require_permission`
and token issuance call it, and `GET /auth/session` echoes what was issued.

Data scope (one of three modes per person; the editor replaces all of a person's rows):

| Table | Columns |
|---|---|
| `tenancy.data_scopes` | PK `(organization_id, user_id)` FK memberships; `all_companies boolean NOT NULL`; `updated_at` |
| `tenancy.data_scope_companies` | PK `(organization_id, user_id, company_id)`; FK memberships; FK `(organization_id, company_id) -> setup.psv_companies` |
| `tenancy.data_scope_vehicles` | PK `(organization_id, user_id, vehicle_id)`; FK memberships; FK `(organization_id, vehicle_id) -> setup.fleet_vehicles` |

Indexes: `data_scope_companies (organization_id, company_id)`, `data_scope_vehicles
(organization_id, vehicle_id)`.

### 4.9 `tenancy.change_log` (append-only)

The organization-wide history (`GET /setup/history`). Snapshots are stored as `text`
holding JSON, exactly as served, so the web's humaniser sees the same key names; `jsonb`
would reorder keys and is not used.

| Column | Type | Null | Constraint |
|---|---|---|---|
| `organization_id` | uuid | no | PK part, FK organizations |
| `version` | bigint | no | PK part; the counter value after the bump, `>= 2` for rows written here; the `CHECK` is `>= 1` so copied .NET rows load |
| `id` | uuid | no | `DEFAULT gen_random_uuid()`, UNIQUE `(organization_id, id)` |
| `section` | text | no | IN (`companies`, `vehicles`, `investment`, `expenses`, `recurring`, `people`, `revenue`, `organization`, `businessDate`, `localization`, `branding`, `securityPolicy`, `logo`) |
| `entity_id` | uuid | no | polymorphic by section; no FK |
| `vehicle_id` | uuid | yes | set for `vehicles`, `investment`, `revenue` rows; no FK; drives scoped visibility |
| `actor_id` | uuid | no | FK `(organization_id, actor_id) -> memberships` |
| `reason` | text | no | `char_length BETWEEN 1 AND 500` |
| `occurred_at` | timestamptz | no | |
| `effective_from` | timestamptz | yes | never set today; kept for the data migration |
| `before` | text | yes | JSON text; `'null'` for creations (as .NET) |
| `after` | text | yes | JSON text; `NULL` for removals |
| `request_id` | text | no | `<= 128` |

- Indexes: `(organization_id, occurred_at)`, `(organization_id, section, vehicle_id)`,
  `(organization_id, actor_id)`. The primary key gives `ORDER BY version DESC` and the
  seek `version < $before` for free.
- `CHECK ((section IN ('vehicles','investment','revenue')) = (vehicle_id IS NOT NULL))`.

### 4.10 `tenancy.audit_events` (append-only)

The lower-level trail (`revenue.recorded`, `setup.<section>`, `person.*`,
`organization.settings.updated`), written by `tenancy.record_change` and the people
routines, read by DBAs and operators only.

| Column | Type | Null | Constraint |
|---|---|---|---|
| `organization_id` | uuid | no | PK part |
| `id` | bigint | no | identity, PK part |
| `actor_id` | uuid | no | FK memberships |
| `action` | text | no | `<= 100` |
| `entity` | text | no | `<= 200` |
| `before` | jsonb | yes | |
| `after` | jsonb | yes | |
| `occurred_at` | timestamptz | no | |
| `request_id` | text | no | `<= 128` |

- Index `(organization_id, occurred_at)`.

## 5. Setup schema

### 5.1 `setup.psv_companies`

| Column | Type | Null | Default | Constraint |
|---|---|---|---|---|
| `organization_id`, `id` | uuid | no | | PK `(organization_id, id)` |
| `name` | text | no | | `char_length BETWEEN 1 AND 160`, `name = btrim(name)` |
| `normalized_name` | text | no | generated | `GENERATED ALWAYS AS (upper(name COLLATE "C")) STORED` (the `C` collation: question 17's default, the same on every server) |
| `archived_on` | date | yes | | |
| `created_at`, `updated_at` | timestamptz | no | `now()` | |

- UNIQUE `(organization_id, normalized_name)`. .NET normalised with `ToUpperInvariant()`;
  `upper()` under the `C` collation folds ASCII letters only, so every non-ASCII letter keeps
  its case: `école` and `École` are two names here, while .NET refused the second as a
  duplicate (open question 17).

### 5.2 `setup.fleet_vehicles`

| Column | Type | Null | Constraint |
|---|---|---|---|
| `organization_id`, `id` | uuid | no | PK |
| `company_id` | uuid | no | FK `(organization_id, company_id) -> psv_companies` |
| `registration` | text | no | `~ '^K[A-Z]{2} [0-9]{3}[A-Z]$'` (canonical form with the space) |
| `joined_on` | date | no | |
| `left_on` | date | yes | `left_on IS NULL OR left_on >= joined_on` |
| `created_at`, `updated_at` | timestamptz | no | |

- UNIQUE `(organization_id, registration)`; index `(organization_id, company_id)`.
- Trigger `setup.forbid_registration_change` (BEFORE UPDATE, raises `XC422
  registration_immutable`) is the defence in depth behind the routine rule.

### 5.3 `setup.vehicle_targets` (append-only)

| Column | Type | Null | Constraint |
|---|---|---|---|
| `organization_id`, `id` | uuid | no | PK |
| `vehicle_id` | uuid | no | FK `(organization_id, vehicle_id) -> fleet_vehicles` |
| `revision` | integer | no | `>= 1` |
| `effective_from` | date | no | |
| `weekly_amount` | numeric(14,2) | no | `> 0` |
| `created_at` | timestamptz | no | |

- UNIQUE `(organization_id, vehicle_id, revision)`; index `(organization_id, vehicle_id, effective_from DESC, revision DESC)`
  for "target in force on a date".

### 5.4 `setup.vehicle_away_periods` (append-only)

| Column | Type | Null | Constraint |
|---|---|---|---|
| `organization_id`, `id` | uuid | no | PK |
| `vehicle_id` | uuid | no | FK fleet_vehicles |
| `left_on` | date | no | |
| `returned_on` | date | no | `returned_on > left_on` |
| `created_at` | timestamptz | no | |

- UNIQUE `(organization_id, vehicle_id, left_on)`; `EXCLUDE USING gist (organization_id
  WITH =, vehicle_id WITH =, daterange(left_on, returned_on) WITH &&)` (requires the
  trusted extension `btree_gist`, created in migration `0005_setup` by `xcode_owner`
  `WITH SCHEMA ops`, so the `public` schema stays empty; the operator class is found by type,
  whatever its schema).

### 5.5 `setup.vehicle_investments`

| Column | Type | Null | Constraint |
|---|---|---|---|
| `organization_id`, `id` | uuid | no | PK |
| `vehicle_id` | uuid | no | FK fleet_vehicles |
| `invested_on` | date | no | (.NET `Date`) |
| `description` | text | no | `char_length BETWEEN 1 AND 160` |
| `amount` | numeric(14,2) | no | `> 0` |
| `recorded_by` | uuid | no | FK `(organization_id, recorded_by) -> memberships` |
| `recorded_at` | timestamptz | no | |
| `updated_at` | timestamptz | no | |

- Index `(organization_id, vehicle_id, invested_on)`. Edited in place and hard-deleted,
  as today; the change log keeps the removed values.

### 5.6 `setup.recurring_items`

PK `(organization_id, id)`; `stopped_from date NULL`; `created_at`, `updated_at`. Never
deleted; all content is in versions.

### 5.7 `setup.recurring_versions` (append-only)

| Column | Type | Null | Constraint |
|---|---|---|---|
| `organization_id`, `id` | uuid | no | PK |
| `item_id` | uuid | no | FK `(organization_id, item_id) -> recurring_items` |
| `revision` | integer | no | `>= 1`; UNIQUE `(organization_id, item_id, revision)` |
| `effective_from` | date | no | |
| `name` | text | no | `char_length BETWEEN 1 AND 160` |
| `kind` | smallint | no | FK `setup.recurring_kinds` |
| `amount` | numeric(14,2) | no | `> 0` |
| `frequency` | smallint | no | FK `setup.recurrence_frequencies` |
| `day` | smallint | yes | |
| `last_day` | boolean | no | |
| `month` | smallint | yes | |
| `start_on` | date | no | |
| `end_on` | date | yes | `end_on IS NULL OR end_on >= start_on` |
| `expense_item_id` | uuid | yes | FK `(organization_id, expense_item_id) -> expense_items` (MATCH SIMPLE) |
| `bucket` | smallint | yes | FK `setup.expense_buckets` |
| `note` | text | yes | `<= 200` |
| `created_at` | timestamptz | no | |

- `CHECK ck_recurring_versions_schedule`:
  `(frequency = 2 AND day IS NOT NULL AND day BETWEEN 0 AND 6 AND NOT last_day AND month IS NULL)
   OR (frequency IN (3, 4) AND ((day IS NOT NULL AND day BETWEEN 1 AND 28 AND NOT last_day) OR (day IS NULL AND last_day))
       AND ((frequency = 4) = (month IS NOT NULL)) AND (month IS NULL OR month BETWEEN 1 AND 12))
   OR (frequency = 1 AND day IS NULL AND NOT last_day AND month IS NULL)`.
  The `day IS NOT NULL` guards matter: without them a weekly row with no day, or a monthly
  row with neither a day nor `last_day`, makes the expression `NULL`, which a `CHECK` accepts.
- `CHECK ck_recurring_versions_kind`: `(kind = 2 AND expense_item_id IS NULL AND bucket IS NULL) OR kind = 1`
  (legacy cost rows may lack item and bucket; new cost rows get both from the routine).
- Index `(organization_id, expense_item_id)`.

### 5.8 `setup.recurring_allocations` (append-only)

| Column | Type | Null | Constraint |
|---|---|---|---|
| `organization_id`, `id` | uuid | no | PK |
| `version_id` | uuid | no | FK `(organization_id, version_id) -> recurring_versions` |
| `vehicle_id` | uuid | no | FK fleet_vehicles |
| `amount` | numeric(14,2) | no | `> 0` |

- UNIQUE `(organization_id, version_id, vehicle_id)`; index `(organization_id, vehicle_id)`.
- Constraint trigger `setup.check_allocation_sum` (DEFERRABLE INITIALLY DEFERRED, after
  insert into versions and allocations, and after an update of a version's `amount` or of a
  share, which only the owner can make): the shares of a version sum exactly to its
  amount and number 1..500, else `XC422 allocation_sum_mismatch`. Left deferred, it fires at
  commit as the session role `xcode_app`, which has no `USAGE` on `setup`, so the commit fails
  with `42501`: every routine that writes versions or allocations runs
  `SET CONSTRAINTS setup.check_allocation_sum IMMEDIATE` after its last write, as
  `setup.save_recurring` does. Deleting a share, which only the owner can do, is not checked.

### 5.9 `setup.expense_categories` and `setup.expense_items`

| Table | Columns |
|---|---|
| `setup.expense_categories` | PK `(organization_id, id)`; `name text CHECK (1..100, trimmed)`; `normalized_name` generated `upper(name COLLATE "C")`; `bucket smallint NOT NULL FK expense_buckets`; `stopped_on date NULL`; `created_at`, `updated_at`; UNIQUE `(organization_id, normalized_name)` |
| `setup.expense_items` | PK `(organization_id, id)`; `category_id uuid NOT NULL` FK `(organization_id, category_id) -> expense_categories`; `name`, `normalized_name` as above; `stopped_on date NULL`; `created_at`, `updated_at`; UNIQUE `(organization_id, category_id, normalized_name)` |

## 6. Revenue and petty-cash schemas

### 6.1 `revenue.records`

| Column | Type | Null | Default | Constraint |
|---|---|---|---|---|
| `organization_id`, `id` | uuid | no | | PK |
| `vehicle_id` | uuid | no | | FK `(organization_id, vehicle_id) -> setup.fleet_vehicles` |
| `business_date` | date | no | | immutable (routine rule; trigger `revenue.forbid_date_change`) |
| `amount` | numeric(14,2) | yes | | `> 0` |
| `reason` | smallint | yes | | FK `revenue.no_earnings_reasons` |
| `note` | text | yes | | `char_length BETWEEN 1 AND 80` |
| `captured_at` | timestamptz | no | | |
| `captured_by` | uuid | no | | FK `(organization_id, captured_by) -> tenancy.memberships` |
| `updated_at` | timestamptz | no | | |
| `updated_by` | uuid | no | | FK memberships |
| `corrected_after_date` | boolean | no | false | |
| `version` | bigint | no | 1 | |

- `CHECK ck_records_entry`: `(amount IS NOT NULL AND reason IS NULL AND note IS NULL) OR
  (amount IS NULL AND reason IS NOT NULL AND ((reason = 4) = (note IS NOT NULL)))`.
- UNIQUE `(organization_id, vehicle_id, business_date)` (one record per vehicle per day;
  the replay backstop); index `(organization_id, business_date)`.
- No idempotency key and no client id: the contract is `PUT` by natural key with
  payload-equality replay (`docs/05-routines.md`, `api.revenue_capture`).

### 6.2 `pettycash.entries`

Source: `docs/inventory/inventory-petty-cash.md` sections 2 and 3 (re-checked on 2026-10-12)
and the design notes' petty-cash rules, `docs/15-design-v2-3.md` B19 (decisions DEC-21 to
DEC-29), which decide where they differ from .NET. Schema `pettycash` is created by migration
`0012_pettycash.sql` (section 13: 0008 to 0011 are prompt 07b's) with the same ownership and
grants as the others. Code tables follow section 2: `pettycash.kinds` (1 `cash` "Cash given",
2 `expense` "Expense", 3 `credit` "Credit note") and `pettycash.statuses` (1 `waiting`
"Waiting", 2 `approved` "Approved", 4 `rejected` "Rejected"; 3 is the .NET `SentBack` and
stays unused, DEC-21). The wire sends the words `cash`/`expense`/`credit` and
`waiting`/`approved`/`rejected`, plus `sentBack` for a waiting expense with a
`sent_back_note` (the only coded enumerations whose wire form is the name, mapped in
`http/schemas/pettycash.py`). Only expenses have a status; cash given and credit notes have
none (DEC-22).

| Column | Type | Null | Default | Constraint |
|---|---|---|---|---|
| `organization_id`, `id` | uuid | no | `gen_random_uuid()` for `id` | PK `(organization_id, id)`; the client may supply `id` on create (the only client-chosen id in the schema) |
| `holder_id` | uuid | no | | FK `(organization_id, holder_id) -> tenancy.memberships` |
| `kind` | smallint | no | | FK `pettycash.kinds` |
| `entry_date` | date | no | | |
| `vehicle_id` | uuid | yes | | FK `(organization_id, vehicle_id) -> setup.fleet_vehicles` |
| `expense_item_id` | uuid | yes | | FK `(organization_id, expense_item_id) -> setup.expense_items` |
| `units` | numeric(12,3) | no | 1 | `> 0`, `<= 999999999.999` |
| `unit_amount` | numeric(14,2) | no | | `<> 0` (implied by `CHECK (total <> 0)`, so no CHECK of its own: PostgreSQL would always report the total's), `abs <= 999999999999.99` |
| `total` | numeric(14,2) | no | generated | `GENERATED ALWAYS AS (round(units * unit_amount, 2)) STORED` (PostgreSQL `round` on `numeric` is half away from zero, as .NET `MidpointRounding.AwayFromZero`); `CHECK (total <> 0)` |
| `payee` | text | yes | | `char_length BETWEEN 1 AND 80`; credit notes only, optional (DEC-27) |
| `note` | text | yes | | `char_length BETWEEN 1 AND 80` |
| `reimbursable` | boolean | no | false | credit notes only |
| `status` | smallint | yes | | FK `pettycash.statuses`; expenses only |
| `sent_back_note` | text | yes | | `char_length BETWEEN 1 AND 200` |
| `reject_reason` | text | yes | | `char_length BETWEEN 1 AND 200` |
| `reopen_reason` | text | yes | | `char_length BETWEEN 1 AND 200`; the last reopen's reason, kept after the next decision |
| `reviewed_by` | uuid | yes | | FK `(organization_id, reviewed_by) -> tenancy.memberships` |
| `reviewed_at` | timestamptz | yes | | |
| `recorded_by` | uuid | no | | FK memberships |
| `recorded_at` | timestamptz | no | | |
| `updated_by` | uuid | no | | FK memberships |
| `updated_at` | timestamptz | no | | |
| `removed_by` | uuid | yes | | FK memberships |
| `removed_at` | timestamptz | yes | | |
| `removal_reason` | text | yes | | `char_length BETWEEN 1 AND 500`; optional for a waiting expense (DEC-28) |
| `version` | bigint | no | 1 | `>= 1` |

- `CHECK ck_entries_kind_shape`: cash `(kind = 1 AND status IS NULL AND units = 1 AND vehicle_id IS NULL AND expense_item_id IS NULL AND payee IS NULL AND NOT reimbursable)`;
  expense `(kind = 2 AND status IS NOT NULL AND vehicle_id IS NOT NULL AND expense_item_id IS NOT NULL AND payee IS NULL AND NOT reimbursable)`;
  credit `(kind = 3 AND status IS NULL AND units = 1 AND vehicle_id IS NULL AND expense_item_id IS NULL)`.
- `CHECK ck_entries_review`: `(sent_back_note IS NULL OR status = 1)`, `((reject_reason IS NOT NULL) = (status IS NOT DISTINCT FROM 4))`, `(reopen_reason IS NULL OR kind = 2)`, and `((reviewed_by IS NOT NULL) = (reviewed_at IS NOT NULL))` with `(reviewed_by IS NOT NULL) = (status IN (2, 4) OR sent_back_note IS NOT NULL)` (a decision always names who took it; a waiting expense that was never sent back has none).
- `CHECK ck_entries_removal`: `(removed_at IS NULL) = (removed_by IS NULL) AND (removal_reason IS NULL OR removed_at IS NOT NULL)`.
- Indexes: `(organization_id, holder_id, entry_date)` (balance and figures per float), `(organization_id, status, entry_date) WHERE removed_at IS NULL` (waiting lists, the dashboard), `(organization_id, vehicle_id, entry_date) WHERE removed_at IS NULL` (vehicle report, visibility), `(organization_id, expense_item_id)` (the item foreign key).
- Never hard-deleted (`INSERT` and `UPDATE` grants only, no `DELETE`); `version` moves on every change, approval, send-back, rejection, reopen and removal.
- `updated_at` is set by every routine that writes the row (the request instant, as in .NET);
  the `touch_updated_at` trigger `db verify` requires on every table with the column is a
  safety net that fires only when a write leaves it unchanged.
- RLS enabled with the `tenant_isolation` policy, as every tenant table (section 9).
- The .NET `Units` column changed type between the feature's two migrations; only the final
  type exists here (`docs/13-open-questions.md` question 26). Prompt 10 maps a .NET status 3
  (`SentBack`) to 1 with its `SentBackNote`, and drops the status of .NET credit notes
  (DEC-21, DEC-22).
- Shared purchases (a group reference per row) come with prompt 08b's group model as
  nullable columns (DEC-26, question 68).

## 7. Rules and where they are enforced

Every rule the inventory lists as "code only" (section 1.F and 2.5) has a home here. "DB"
means the schema refuses it on any path; "routine" means the `api.*` routine refuses it
with an `XC4xx` error before any write; "domain" means a pure Python check that runs before
the routine is called (and the routine still checks).

| Rule | Mechanism |
|---|---|
| Tenant match on every read and write; tenant immutable | RLS `tenant_isolation` (`USING` and `WITH CHECK`); composite foreign keys |
| Append-only tables; no deletes on core setup tables | privileges (no `UPDATE`/`DELETE` grant) |
| Audit and sign-in trails append-only | privileges |
| Registration immutable; business date of a record immutable | trigger + routine |
| Exactly one of amount or reason; note only with `Other` | `CHECK` + routine message |
| Positive money, two decimals, cap | `numeric(14,2)` + `CHECK (> 0)` |
| Allocation shares sum to the version amount, 1..500 distinct vehicles | constraint trigger + routine message |
| Away periods ordered and non-overlapping; leave date not before join date | `CHECK` + `EXCLUDE` + routine messages |
| Schedule shape (weekday, month day, last day, month) | `CHECK` + routine message |
| Registration, phone, email, slug, locale, currency, colour formats | `CHECK` |
| Time zone known | routine (`tenancy.check_time_zone`) |
| Brand colour contrast | SQL function + `CHECK` |
| Logo type, size, signature | `CHECK` |
| Security policy bounds; PIN sign-in cannot be disabled | `CHECK` |
| Lengths of names, notes, reasons, descriptions | `CHECK` |
| Instants are UTC | `timestamptz` (the API boundary rejects non-UTC input before calling) |
| One active membership per person; one role per person | partial unique index; primary key |
| Uniqueness of names, registrations, emails, phones, slugs, role names | unique indexes (case rules in section 8) |
| Optimistic concurrency (`version`, `settings_version`) | routine: `UPDATE ... WHERE version = p_expected_version`, zero rows = `XC409` |
| Lockout counters exact under concurrency | routine: `SELECT ... FOR UPDATE` on the user row |
| Permission and scope checks | routine: `tenancy.enter_organization`, `tenancy.require_permission`, scope predicates |
| Business-rule refusals with user-facing messages | routine (`XC422` with the message code; the HTTP layer maps codes to the exact .NET strings, `docs/06-http-contract.md` section 1) |

## 8. Case, collation and ordering

SQL Server's default collation made comparisons case-insensitive; PostgreSQL's are not.
The schema makes every case rule explicit:

| Where | Rule |
|---|---|
| `identity.users.email` | stored lower-case (`CHECK`), unique |
| `tenancy.organizations.slug` | lower-case by `CHECK` |
| `tenancy.roles.name` | unique on `lower(name)` |
| company, category, item names | unique on the generated `upper(name)` |
| `setup.fleet_vehicles.registration` | canonical upper-case form by `CHECK` |
| change-log text search | `ILIKE` with `\`-escaped `%`, `_` and `\` in the routine |
| list ordering (`name`, `registration`, `last_name, first_name`) | `ORDER BY ... COLLATE "und-x-icu"` is not required; tests pin only the orders the clients show (`Insurance` before `Office rent`), which the default collation satisfies. Under the `C` collation the clusters use, upper-case letters sort before lower-case ones (`Zebra Ltd` before `apple co`), where SQL Server's default ignored case: question 70. Tie-break by `id` differs from SQL Server GUID order and is not part of the contract |

## 9. Row-level security and grants

- Every tenant table in section 1 has RLS enabled, is owned by `xcode_owner`, and carries
  exactly `tenant_isolation` for `xcode_api_executor`. `tenancy.organizations` carries the
  policy on `id`. Code tables and the global catalog have no RLS.
- Identity tables: `xcode_api_executor` gets the privileges in section 1; no other role
  has any.
- `xcode_readonly`: `SELECT` on the code tables and the three catalogue tables, and
  `USAGE` on the schemas that hold them (`tenancy`, `setup`, `revenue`) so the grant is
  usable (the two `pettycash` code tables carry the grant but stay out of reach); nothing else (deny by default; `0007_readonly.sql` holds the DBA checklist), and
  never `USAGE` on `identity`, `ops`, `api` or `pettycash`. A DBA migration may
  later grant `SELECT` on specific columns of `setup.*`, `revenue.*` and
  `tenancy.change_log`; never on `identity.*`, never on a column ending in `_hash` or
  `_digest`, never on `tenancy.audit_events`.
- `xcode_app` holds `EXECUTE` on `api.*` routines except `api.ops_*`; `xcode_operator`
  (the CLI role, `docs/03-database.md` section 1) holds `EXECUTE` on `api.ops_*` and
  `api.meta_*` only. The runner grants by prefix.
- `db verify` (`db/verify.py`) proves all of this against the live database; the structure
  tests in `tests/db/test_schema_structure.py` run the same checks in CI.

## 10. Triggers and schema-level functions

| Name | Kind | Purpose | File |
|---|---|---|---|
| `ops.touch_updated_at()` | trigger function | on update, sets `updated_at = now()` when the statement left it unchanged; a routine that sets it from `p_now` wins (`docs/03-database.md` section 6); attached to every table with the column | `db/migrations/0002_identity.sql` (first use) |
| `setup.forbid_registration_change()` | trigger | `XC422 registration_immutable` | `0005_setup.sql` |
| `revenue.forbid_date_change()` | trigger | `XC422 business_date_immutable` | `0006_revenue.sql` |
| `setup.check_allocation_sum()` | constraint trigger | shares sum and count | `0005_setup.sql` |
| `tenancy.check_contrast(text, text)` | immutable SQL function | WCAG relative-luminance ratio | `0003_tenancy.sql` |
| `tenancy.current_organization()`, `tenancy.current_actor()`, `tenancy.current_request()` | stable SQL functions | read the transaction-local settings, `NULL` when unset; no `SET search_path` (every name is qualified) so the planner can inline them into the policies; `EXECUTE` granted to `xcode_api_executor` only | `0003_tenancy.sql` |
| `tenancy.enter_organization(...)`, `tenancy.enter_organization_as_operator(uuid)`, `tenancy.require_permission(text)`, `tenancy.effective_permissions(uuid, uuid)`, `tenancy.record_change(...)`, `tenancy.seed_roles(uuid)`, `tenancy.business_date(uuid)`, `tenancy.check_time_zone(text)` | plpgsql helpers (not `api.*`) | specified in `docs/05-routines.md` section 2 | `db/routines/20_tenancy/*.sql` |

Trigger functions and the contrast function are schema (migrations) because constraints
depend on them; the helpers are routines because they change with the rules.

## 11. Migration plan (prompt 02)

| File | Contents |
|---|---|
| `0001_ops.sql` | prompt 01 (bookkeeping, operator actions, rate-limit windows) |
| `0002_identity.sql` | schema `identity`, tables 3.1 to 3.5, `ops.touch_updated_at()`, grants |
| `0003_tenancy.sql` | schema `tenancy`, tables 4.1 to 4.7, 4.9, 4.10, `check_contrast`, `current_organization`, `current_actor`, `current_request`, RLS, grants |
| `0004_access_catalog.sql` | tables 4.8 (roles, person_roles, permission_overrides, the three catalog tables with their rows, data scopes without the vehicle and company foreign keys), grants |
| `0005_setup.sql` | `CREATE EXTENSION IF NOT EXISTS btree_gist WITH SCHEMA ops`, schema `setup`, code tables with rows, tables 5.1 to 5.9, the two scope foreign keys, triggers, RLS, grants |
| `0006_revenue.sql` | schema `revenue`, code table, table 6.1, trigger, RLS, grants |
| `0007_readonly.sql` | empty grant file for `xcode_readonly` with the DBA checklist as comments (so the deny-by-default is explicit and reviewable) |
| `0012_pettycash.sql` (prompt 08; numbers 0008 to 0011 are prompt 07b's, section 13) | schema `pettycash`, code tables with rows, table 6.2, RLS, grants |

Each file: one transaction (the runner's), `SET LOCAL lock_timeout = '10s'`, no data except
code rows and the catalog (`0004` ends with a `DO` block that refuses unless the catalogue has
40 keys, 30 dependencies and 79 role defaults), no `api.*` routine (routines live in
`db/routines/`). Each has a `.down.sql` that reverses it, because `db down` reverses the
latest applied version and the runner's tests require one per file; outside development and
testing `db down` is refused without `--i-know-this-destroys-data` (`docs/03-database.md`
section 7).

Tests that pin this document (`tests/db/`): `test_schema_structure.py` (every table of
section 1 exists with the listed primary key, uniqueness, foreign keys, RLS flag and
policy, privileges per role, `updated_at` triggers), `test_enum_parity.py` (code tables
against the domain enums and the `CHECK` lists), `test_tenancy_isolation.py` (a routine
cannot read or write another organization's rows; without `enter_organization` nothing is
visible), `test_constraints.py` (one failing insert per `CHECK`, `EXCLUDE` and constraint
trigger in section 7, by SQLSTATE and message code), `test_grants.py` (an `UPDATE` or
`DELETE` on an append-only table as `xcode_api_executor` fails with `42501`).

## 12. Decisions and differences from the .NET schema

| Decision | Why |
|---|---|
| Money is `numeric(14,2)` | same precision as .NET, the domain cap becomes the column cap |
| Versions stay `bigint` with .NET start values | clients hold and echo them; the data migration copies them unchanged |
| The change-log counter stays on the organization row, bumped last in the transaction | gap-free, unique, no retry loop, short lock window |
| Snapshots stored as `text` | the web parses whatever JSON is served and hides keys by name; `jsonb` would reorder and reformat |
| `before = 'null'` on creation kept | the clients receive the same strings as today |
| `person_roles` keyed by membership | the unique index already made the wider key meaningless |
| Roles pre-seeded; `GET /setup/access/roles` read-only | removes a write behind a read |
| Code tables for wire integers; no lookup for text-coded identity enums | one representation per value |
| `audit_events` kept beside `change_log` | different readers: users versus operators; `12-security.md` section 4 relies on it |
| `sign_in_attempts` added | assume breach: every refusal and success is a row |
| Phone number required | the sign-in key must exist; legacy empty numbers are a migration decision |
| `RolePermissions` dropped | unread for two releases |
| `primary` renamed `primary_color` (and the other two for symmetry) | reserved word; the wire name is unchanged |
| `Date` renamed `invested_on`, `OccuredAt` spelled `occurred_at`, `UseGroupping` spelled `use_grouping` | the naming rules; the wire serves `useGrouping` and tolerates the old spelling during the transition |
| Scope tables moved to `tenancy` and renamed `data_scope*` | they gate every module, not only setup |
| `xcode_operator` role for `api.ops_*` | the API's credentials cannot seed, clear pauses or revoke sessions outside the business routines |
| Petty cash in its own schema with `total` generated and the kind shape as a `CHECK` | the .NET schema enforced none of it (`inventory-petty-cash.md` section 3.4); the rules now hold on every path |
| Petty-cash create keeps the client-supplied `id` | it is the phone's replay key for an online-only feature; the only client id in the contract |

Open questions raised by this document are in `docs/13-open-questions.md` under "Before
prompt 02".

## 13. Tables and columns of the design notes v2.29 to v2.33 (prompt 07b)

The schema changes of `docs/15-design-v2-3.md` (rule ids `DN-B*`), one migration per build
session of `docs/prompts/07b-design-v2-3.md`. Conventions as in the rest of this document:
tenant tables carry RLS and `tenant_isolation`, writes are the privileges of
`xcode_api_executor`, every query a routine runs has its index listed. Each migration also
migrates the development data it changes (the real data is prompt 10's,
`docs/10-data-migration.md` section 3.1), logs its row counts and ends with a `DO` block that
checks them.

| Migration | Session | Contents |
|---|---|---|
| `0008_sign_in.sql` | D1 | 13.1, the `signIn` change-log section (13.3), the `idle_unlock_seconds` default (built 2026-10-12; the brand host and URL rules of question 58 did not go in: `0008` was applied to the development database before they were written, so they move to `0009_access`, D2) |
| `0009_access.sql` | D2 | 13.2 |
| `0010_setup.sql` | D3 | 13.4 |
| `0011_revenue.sql` | D4 | 13.5, and the drop of `setup.vehicle_targets` once no routine reads it |
| `0012_pettycash.sql` | prompt 08 | section 6.2 (was `0008_pettycash`) |

### 13.1 Identity (`0008_sign_in`)

`identity.users`:

| Change | Column | Type | Null | Default | Constraint |
|---|---|---|---|---|---|
| add | `pin_reset_required` | boolean | no | false | |
| add | `last_signed_in_at` | timestamptz | yes | | |
| change | `failed_attempts` | integer | no | 0 | `BETWEEN 0 AND 5`; wrong PINs in a row on trusted devices; 5 = locked on every device |
| change | `untrusted_failed_attempts` | integer | no | 0 | `BETWEEN 0 AND 5`; wrong PINs in a row on untrusted devices; 5 = locked for new devices |
| drop | `paused_until` | | | | retired with the timed pause |

Data, in this order: an active pause (`paused_until > now()`) becomes the lock
(`failed_attempts = 5`); a lapsed one is cleared (`failed_attempts = 0`); both counters are
clamped to 5; then the column is dropped and the checks added. Status queries read the
counters on the user row the people routines already join; no index.

`identity.trusted_devices`:

| Change | Column | Type | Null | Default | Constraint |
|---|---|---|---|---|---|
| add | `token_hash` | text | yes | | `~ '^[0-9A-F]{64}$'`; UNIQUE where not null (`uq_trusted_devices_token`); null = trusted by `device_id` alone (v2.11) |
| add | `name` | text | yes | | `~ '^[A-Za-z0-9][A-Za-z0-9 .()+-]{0,59}$'` (`docs/07-auth.md` 12.1) |
| add | `trusted_at` | timestamptz | no | | migration: `created_at` |
| add | `last_used_at` | timestamptz | no | | migration: the newest `created_at` of the device's refresh tokens, else `updated_at` |
| add | `remembered` | boolean | no | true | `CHECK (remembered OR token_hash IS NULL)` |
| keep | `trust_expires_at` | timestamptz | yes | | the optional cap from `XCODE_AUTH_TRUST_LIFETIME_DAYS` |

Queries: trust by (user, device) and the own-devices list use `uq (user_id, device_id)`; the
token is compared on the row found, never searched for.

`identity.verification_codes`: no column change; `failed_attempts` now voids at 3. The
per-person caps read `(user_id, created_at)`, served by the existing index `(user_id,
purpose, created_at DESC)` on its first column (a person has a handful of code rows); no new
index.

`identity.sign_in_attempts` (the sign-in history): the `CHECK` lists gain
- `operation`: `start`, `pin`, `code`, `resend_code`, `forgot_pin`, `new_pin`,
  `change_pin`, `remove_device`;
- `outcome`: `pin_required`, `pin_locked`, `blocked`, `code_resent`, `pin_changed`;
- `refusal`: `locked`, `reset_required`, `pin_rule`, `verdict_void`.

New index `ix_sign_in_attempts_unknown (phone_digest, occurred_at DESC) WHERE user_id IS
NULL` for the simulated account of unknown numbers (`docs/07-auth.md` 12.14 a: the wrong
tries recorded for a digest, at most five read).

### 13.2 Access (`0009_access`)

`tenancy.permissions` gains `catalogue boolean NOT NULL DEFAULT true` (false for the hidden
`organization.manage` and the 20 legacy keys) and `section text NULL CHECK (section IN
('View', 'Expenses', 'Approval', 'Cash'))` (the petty-cash card's sections). Rows: the 59 of
`docs/15-design-v2-3.md` section 3.1 in catalogue order (`group_order` 1 to 12) and the 21
non-catalogue keys in `group_order` 99: 80 in all. Labels and group names change as listed
there; the key `CHECK` is unchanged.

New global tables (no RLS, `SELECT` for `xcode_api_executor` and `xcode_readonly`, seeded
here, written by nothing else):

| Table | Columns | Rows |
|---|---|---|
| `tenancy.permission_sources` | `permission text` FK permissions, `source text` FK permissions, PK both, `CHECK (permission <> source)` | 32: a non-catalogue key is held when any source is held (section 3.4 of `docs/15`) |
| `tenancy.permission_translations` | `old_key text` FK permissions, `new_key text` FK permissions, PK both | the table of `docs/15` section 3.5; read by this migration and by the data tool of prompt 10 |

`tenancy.permission_dependencies` is replaced by the 48 rows of `docs/15` section 3.1 and
`tenancy.role_defaults` by its 111 rows (section 3.2). The closing `DO` block refuses unless
there are 80 keys (59 in the catalogue), 48 dependencies, 111 role defaults, 32 sources and
58 translations, every source is a catalogue key, every non-catalogue key but
`organization.manage` and the three `bills.*` keys (office bills were never served, so
nothing derives them) has a source, no dependency names a non-catalogue key, no role
default but the Owner's `organization.manage` does, and every translation leads to a
catalogue key.

Data: each membership's overrides are rewritten as `docs/15` section 3.5 says, using the
old rows (read before they change, by the migration's own query: role defaults plus
granted overrides, dependencies expanded, denied overrides removed, as
`tenancy.assigned_permissions` did; a migration never calls a routine, whose file may
already be the new one) and the translation table. One addition to the rule of `docs/15`
section 3.5: a right of the person's new role defaults that no old key translates to and no
right needs is added too. Only the Owner role has such rights (the petty-cash rights that
start off for everyone else, v2.29 s5); without them an organization's only Owner could
never hold them, because nobody else may change an Owner and nobody may change their own
access. The overrides are then rewritten (granted rows for keys of the new set outside the
new role defaults, denied rows for role defaults outside it) and the number of members and
override rows is logged. Checked before the commit: no override names a non-catalogue key;
the rewritten rows give every person exactly their new set; every old key a person held
reaches the new set through the translation, except `revenue.no_earnings`, `bills.*` and
`organization.manage` (an Owner gets it back from the role), which are dropped on purpose.
`tests/db/test_migrate.py::test_the_grant_translation_keeps_what_each_person_could_do`
migrates people of every role seeded with grants and denials at version 8.

`tenancy.memberships` (the back-dating limit, DN-B12-7):

| Column | Type | Null | Default | Constraint |
|---|---|---|---|---|
| `back_limit_mode` | text | no | `'none'` | `IN ('none', 'days', 'months')` |
| `back_limit_count` | smallint | yes | | `(back_limit_mode = 'none') = (back_limit_count IS NULL)`; days `BETWEEN 0 AND 3650`, months `BETWEEN 0 AND 120` |
| `back_limit_from` | date | yes | | the fixed "never before" date |

Existing memberships keep `none` and no date (`DEC-11`); new people get `days` 7 from the
person save, not from the column default. The limit is read on the actor's own membership
row, which `tenancy.enter_organization` already reads; no index.

`tenancy.organization_security_policies.idle_unlock_seconds`: default 900 (bounds
unchanged); set by `0008_sign_in`.

### 13.3 Change log (`0008_sign_in`)

`tenancy.change_log.section` gains `signIn` (rows of `docs/07-auth.md` 12.11; entity = the
person's user id, `vehicle_id` null). `api.history_list` shows `signIn` rows to exactly the
viewers who see that person's `people` rows (`people.view` and, for a scoped viewer, the
person in `tenancy.people_visible`). No new index: the section filter uses
`(organization_id, section, vehicle_id)`.

### 13.4 Setup (`0010_setup`)

`setup.fleet_vehicles`:

| Change | Column | Type | Null | Constraint |
|---|---|---|---|---|
| add | `fleet_number` | text | yes | `char_length BETWEEN 1 AND 20`, `fleet_number = btrim(fleet_number)`; null only for vehicles saved before this migration (every write requires it, DN-B10-1) |
| add | `normalized_fleet_number` | text | yes | `GENERATED ALWAYS AS (upper(fleet_number COLLATE "C")) STORED` |
| add | `initial_investment` | numeric(14,2) | yes | `> 0`; null = empty (DN-B11-1) |

UNIQUE `uq_fleet_vehicles_fleet_number (organization_id, company_id,
normalized_fleet_number)`: nulls are distinct, so vehicles without a number do not clash;
the same index answers the routine's "taken" check. A move to another company is checked
in the new company. Revenue search (`q` on R01) filters the organization's visible vehicles
by `registration` or `fleet_number` with `ILIKE`; it runs over the grid's id list, which is
already read whole, so no index.

`setup.vehicle_target_sets` (new; tenant table; writes I U D):

| Column | Type | Null | Constraint |
|---|---|---|---|
| `organization_id`, `id` | uuid | no | PK |
| `vehicle_id` | uuid | no | FK `(organization_id, vehicle_id) -> fleet_vehicles` |
| `starts_on` | date | no | |
| `monday` .. `sunday` | numeric(14,2) | no | each `> 0` |
| `created_at` | timestamptz | no | |
| `created_by` | uuid | yes | FK `(organization_id, created_by) -> tenancy.memberships`; null only on the sets `0010` makes from the weekly targets (no author was stored), every routine write sets it |

- UNIQUE `(organization_id, vehicle_id, starts_on)`: one set per start date; the index also
  answers "the set in force on a day" (the greatest `starts_on <= day`), the history of the
  pop-up (`ORDER BY starts_on DESC`) and the next set (the least `starts_on > today`).
- Update and delete are granted because a set that has not started may be replaced or
  removed; that a started set is never changed is a routine rule (`api.setup_target_set_save`
  and `_remove`, `docs/05-routines.md` 10.4) with a test. A trigger cannot hold it: the
  business date depends on `p_now`, which a trigger does not have.
- Data: every row of `setup.vehicle_targets` becomes a set starting on its `effective_from`
  (the highest revision when several share a date), split as `docs/10-data-migration.md`
  3.1 says; a weekly target too small to give seven figures above 0 is left out and counted
  in the migration's notice. `setup.vehicle_targets` stays, read-only (the `INSERT` grant is
  revoked), until `0011_revenue` drops it.

`setup.expense_main_categories` (new; tenant table; writes I U):

| Column | Type | Null | Constraint |
|---|---|---|---|
| `organization_id`, `id` | uuid | no | PK |
| `name` | text | no | `char_length BETWEEN 1 AND 100`, `name = btrim(name)` |
| `normalized_name` | text | no | `GENERATED ALWAYS AS (upper(name COLLATE "C")) STORED`; UNIQUE `(organization_id, normalized_name)` |
| `created_at`, `updated_at` | timestamptz | no | |

`setup.expense_categories`: add `main_category_id uuid NULL`, FK `(organization_id,
main_category_id) -> expense_main_categories` (MATCH SIMPLE, so null means "No main
category"); index `(organization_id, main_category_id)` for the main-category counts and
lists; `bucket` becomes nullable and is written by nothing (the vehicle report still reads
it until prompt 08b replaces the buckets by main categories; a cost whose category has no
bucket counts as a recurring charge, as a scheduled cost without one always has). Data: `DEC-17`, in
`docs/10-data-migration.md` 3.1. No delete for main categories or categories (question 52).

### 13.5 Revenue (`0011_revenue`)

`revenue.records`: `ck_records_entry` becomes `(amount IS NOT NULL OR reason IS NOT NULL)
AND (note IS NULL OR reason IS NOT DISTINCT FROM 4)` (with `reason = 4` a note on a record
without a reason would pass: a CHECK passes on NULL): an amount, an amount with a reason (a low day), or a
reason alone (no revenue); the note only with Other, and optional. That a reason goes with
an amount only below the threshold is a routine rule (the threshold is a setting).

`tenancy.organization_revenue_settings` (new; tenant table, PK `organization_id` FK
organizations; writes I U):

| Column | Type | Null | Default | Constraint |
|---|---|---|---|---|
| `low_day_threshold` | numeric(14,2) | no | 4000 | `>= 0` |
| `gap_amber_percent` | numeric(5,2) | no | 10 | `BETWEEN 0 AND 100` |
| `created_at`, `updated_at` | timestamptz | no | `now()` | |

A missing row reads as the defaults (`tenancy.settings_document('revenue')`, as for the
other sections), so organization creation is unchanged. Read by primary key.

`setup.vehicle_targets` is dropped here, after `revenue.vehicle_days`, the report and the
vehicle routines read `setup.vehicle_target_sets`.

## 14. Expenses, scheduled runs and reports (prompt 08b, migration `0013_expenses`)

Source: `docs/inventory/inventory-expenses-reports.md` (rule ids `CE-*`, `SR-*`, `RP-*`, `RD-*`, `FP-*`), and for the
saving model and the report parts the design notes (`docs/15-design-v2-3.md` B9, B11, B16, B18, decisions `DEC-30` to
`DEC-41` in section 2 of that file). One migration, `0013_expenses.sql` with its reviewed `.down.sql` (the prompt's
`0009_expenses` name is taken: `0009` to `0012` are 07b's and 08's). It runs after `0012`; it re-creates the change-log
checks `0012` re-created, with the two sections it adds, so nothing `0012` added is lost.

### 14.1 Schemas

| Schema | Holds | Grants |
|---|---|---|
| `expenses` (new) | `expenses.entries` (central expenses) and its helpers | as `pettycash`: owned by `xcode_owner`, `USAGE` to `xcode_api_executor` only; `xcode_readonly` gets none (`db verify` `_READONLY_CLOSED_SCHEMAS` adds it) |
| `reports` (new) | no table; the report builders and the table helpers (search, page, totals) of `docs/05-routines.md` 11.4 | `USAGE` to `xcode_api_executor` only |

`docs/11-naming.md` section 1 lists both.

### 14.2 `expenses.entries` (central expenses; tenant table; writes I U)

| Column | Type | Null | Default | Constraint |
|---|---|---|---|---|
| `organization_id`, `id` | uuid | no | | PK `(organization_id, id)`; a one-vehicle purchase takes the client's purchase id as its row id (CE-6) |
| `entry_date` | date | no | | |
| `vehicle_id` | uuid | no | | FK `(organization_id, vehicle_id) -> setup.fleet_vehicles` |
| `expense_item_id` | uuid | no | | FK `(organization_id, expense_item_id) -> setup.expense_items` |
| `units` | numeric(12,3) | no | | `> 0`, `<= 999999999.999` |
| `unit_amount` | numeric(14,2) | no | | `abs <= 999999999999.99` (non-zero through `total`) |
| `total` | numeric(14,2) | no | generated | `GENERATED ALWAYS AS (round(units * unit_amount, 2)) STORED`; `CHECK (total <> 0)`; `round` on `numeric` is half away from zero, as .NET (CE-4) |
| `note` | text | yes | | `char_length BETWEEN 1 AND 80`, `note = btrim(note)` |
| `group_id` | uuid | no | | the purchase; UNIQUE `(organization_id, group_id, vehicle_id)`, removed rows included (CE-10: a row cannot move onto a vehicle the purchase already has, removed or not) |
| `group_size` | integer | no | | `BETWEEN 1 AND 50` (rows when bought; not recounted, CE-11) |
| `group_total` | numeric(14,2) | no | | `<> 0` |
| `group_units` | numeric(12,3) | no | | `> 0` |
| `group_unit_amount` | numeric(14,2) | no | | `<> 0` |
| `recorded_by`, `updated_by` | uuid | no | | FK `(organization_id, ...) -> tenancy.memberships` |
| `recorded_at`, `updated_at` | timestamptz | no | | |
| `removed_by` | uuid | yes | | FK memberships |
| `removed_at` | timestamptz | yes | | |
| `removal_reason` | text | yes | | `char_length BETWEEN 1 AND 500` |
| `version` | bigint | no | 1 | `>= 1` |

- `CHECK ck_entries_removal`: `(removed_at IS NULL) = (removed_by IS NULL) AND (removed_at IS NULL) = (removal_reason IS NULL)`.
- `CHECK ck_entries_group`: `group_size > 1 OR (group_total = total AND group_units = units AND group_unit_amount =
  unit_amount)` (a row alone is its own purchase; a detached row takes its own figures, CE-11).
- Indexes, one per query of `docs/05-routines.md` 11.2: `(organization_id, entry_date) WHERE removed_at IS NULL` (the
  ledger's period, day counts and figures); `(organization_id, vehicle_id, entry_date) WHERE removed_at IS NULL`
  (`setup.fleet_postings` per vehicle); `(organization_id, expense_item_id)` (the foreign key; the catalogue's "in use"
  reads); the unique `(organization_id, group_id, vehicle_id)` answers the retried record's lookup by group (CE-8) and
  "the purchase already has this vehicle"; the PK answers the lookup by row id.
- RLS enabled, policy `tenant_isolation`; `INSERT` and `UPDATE` to `xcode_api_executor`, no `DELETE` (rows are removed
  softly); the `touch_updated_at` trigger like every table with `updated_at`.

### 14.3 Scheduled items: pauses and the saving model

`setup.recurring_pauses` (new; tenant table; writes I U):

| Column | Type | Null | Constraint |
|---|---|---|---|
| `organization_id`, `id` | uuid | no | PK |
| `item_id` | uuid | no | FK `(organization_id, item_id) -> setup.recurring_items` |
| `paused_from` | date | no | |
| `paused_through` | date | yes | null while paused; `paused_through >= paused_from - 1` (a resume on the day of the pause covers no day, SR-1) |
| `created_at`, `updated_at` | timestamptz | no | |

- At most one open pause per item: UNIQUE `(organization_id, item_id) WHERE paused_through IS NULL`.
- No two pauses of an item overlap: `EXCLUDE USING gist (organization_id WITH =, item_id WITH =,
  daterange(paused_from, paused_through + 1, '[)') WITH &&)` (an open pause is `[paused_from, )`; a same-day resume is
  an empty range, which overlaps nothing; `btree_gist` is installed by `0005` for the away periods). The gist index
  answers "is the item paused on day d" and the due-day generator's pause filter.
- RLS, `tenant_isolation`; `INSERT`, `UPDATE` (the resume) to the executor; no `DELETE`.

The saving model of the notes (B18, `DEC-31` to `DEC-35`):

| Change | Table and column | Type | Constraint |
|---|---|---|---|
| add | `setup.recurring_versions.condition_min` | numeric(14,2) NULL | `> 0` |
| add | `setup.recurring_versions.condition_days` | smallint NULL | `IN (1, 7, 30)` |
| check | `ck_recurring_versions_condition` | | `(condition_min IS NULL) = (condition_days IS NULL) AND (condition_min IS NULL OR kind = 2)` (only a saving carries a revenue rule) |
| check | `ck_recurring_versions_schedule` | | unchanged: daily rows were always allowed by the table; the routine decides what a new save may choose |

`setup.saving_openings` (new; tenant table; writes I U D): an item's opening balance, one date per saving.

| Column | Type | Null | Constraint |
|---|---|---|---|
| `organization_id`, `item_id` | uuid | no | PK; FK `-> setup.recurring_items` |
| `opened_on` | date | no | |
| `created_at`, `updated_at` | timestamptz | no | |

`setup.saving_opening_amounts` (new; tenant table; writes I U D):

| Column | Type | Null | Constraint |
|---|---|---|---|
| `organization_id`, `item_id`, `vehicle_id` | uuid | no | PK; FK `(organization_id, item_id) -> setup.saving_openings` ON DELETE CASCADE; FK `(organization_id, vehicle_id) -> setup.fleet_vehicles` |
| `amount` | numeric(14,2) | no | `> 0` (a vehicle without an opening amount has no row) |

Both are replaced as a whole by a saving's save (delete and insert in the routine), so `DELETE` is granted on them alone
among the scheduled-item tables. Index: the PKs answer every read (by item; by item and vehicle).

`setup.saving_runs` (new; tenant table; append-only, writes I): the decided runs of savings that carry a revenue rule.

| Column | Type | Null | Constraint |
|---|---|---|---|
| `organization_id` | uuid | no | PK part |
| `item_id` | uuid | no | PK part; FK `-> setup.recurring_items` |
| `run_on` | date | no | PK part |
| `vehicle_id` | uuid | no | PK part; FK `-> setup.fleet_vehicles` |
| `version_id` | uuid | no | FK `-> setup.recurring_versions` (the version in charge on `run_on`) |
| `amount` | numeric(14,2) | no | `> 0` (the vehicle's share on that version) |
| `state` | smallint | no | FK `setup.saving_run_states` (1 `saved`, 2 `skipped`) |
| `revenue` | numeric(14,2) | no | the revenue of the window when decided (amounts only, B14-8) |
| `decided_at` | timestamptz | no | |

- PK `(organization_id, item_id, run_on, vehicle_id)`: the notes' "unique on schedule, run date and vehicle". A run is
  decided once (`INSERT ... ON CONFLICT DO NOTHING`); two connections deciding the same run leave one row.
- Index `(organization_id, vehicle_id, run_on)` (a vehicle's saved runs in a report window and its balance).
- `INSERT` only to the executor (decided runs are final, "once decided a run is final"); RLS `tenant_isolation`.
- A held run has no row; an unconditional saving's runs have no row either (they are saved on their run date by
  definition, computed like a cost's, `DEC-32`). Code table `setup.saving_run_states` (1 `saved`, 2 `skipped`) with
  the wire word `held` for a conditional run without a row; `tests/db/test_enum_parity.py` adds the
  `SavingRunState` enum.

### 14.4 Petty-cash shared purchases (`DEC-26`, question 68)

`pettycash.entries` adds, all null for an entry that is not part of a shared purchase:

| Column | Type | Constraint |
|---|---|---|
| `group_id` | uuid | the purchase; UNIQUE `(organization_id, group_id, vehicle_id)` |
| `group_total` | numeric(14,2) | `<> 0` |
| `group_units` | numeric(12,3) | `> 0` |
| `group_unit_amount` | numeric(14,2) | `<> 0` |

`CHECK ck_entries_group`: the four are all null or all set, and set only on an expense (`kind = 2`). Index `(organization_id,
group_id) WHERE group_id IS NOT NULL` (the recount: the parts still counted). "Shared by N vehicles" is counted when
read, as the group's rows that are not removed and not rejected, so deleting or editing one part recounts the others by
construction (v2.29 s5).

### 14.5 Change log and code tables

- `tenancy.change_log`: `ck_change_log_section` re-created with `centralexpenses` and `reports` added to `0012`'s list;
  `ck_change_log_vehicle` re-created so that `centralexpenses` requires a vehicle (as `vehicles`, `investment`,
  `revenue`), `reports` has none, `pettycash` stays free.
- `setup.saving_run_states` (1 `saved`, 2 `skipped`): a code table like section 2's, `SELECT` to the executor and to
  `xcode_readonly` like the other code tables of `setup`.

### 14.6 What is deliberately not stored

- Scheduled cost runs and unconditional saving runs: computed on read from the versions, the pauses and the stop, one
  posting per (item, day, vehicle) by construction (one version is in charge on a day; one share per version and
  vehicle). .NET stores none either; the notes' "job safe to run twice" has no job to make safe (`DEC-32`). The decided
  runs of conditional savings are stored because they must not change once decided.
- Reports and exports: no table. Each export writes one change-log row (section `reports`) in the transaction that read
  its rows (`docs/12-security.md` 2.8).
- The posting source: a computed column of `setup.fleet_postings` (1 central, 2 petty cash, 3 scheduled), never stored.

### 14.7 `0013_expenses.down.sql`

Drops, in reverse order: the petty-cash group index, check and columns; `setup.saving_runs`, `setup.saving_run_states`,
`setup.saving_opening_amounts`, `setup.saving_openings`; the two version columns and their check;
`setup.recurring_pauses`; `expenses.entries` and schema `expenses`; schema `reports` (its functions first, by the
routine runner's catalogue); and re-creates `0012`'s change-log checks. A down migration over data refuses when any
`centralexpenses` or `reports` change-log row exists (a `DO` block counts them), because those rows cannot satisfy the
restored check.
