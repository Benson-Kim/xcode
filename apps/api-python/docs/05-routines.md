# Routines

The callable surface of the database: every `api.*` routine the Python service or the CLI
may call, the helpers in the data schemas they are built from, and the rules each one
enforces. This is the document a DBA reviews before a routine file is merged. Sources:
`docs/06-http-contract.md` (one routine per endpoint row, the message codes), `docs/04-schema.md`
(tables, constraints, helpers it names), `docs/inventory/inventory-domain.md` (rule ids such
as `SU-V5`, `OS-11`, `RV-3`), `docs/inventory/inventory-http-contract.md` (check orders,
cited as `inv 2.x`). Where this document and the .NET code disagree, the code and its tests
win, the inventory is corrected, and this document follows.

Nothing here is code. Signatures are specifications; the SQL lives in `db/routines/` and is
written by prompts 03 to 09.

## 1. Conventions and the entry format

### 1.1 Files and headers

- One routine per file, `db/routines/<nn>_<area>/<routine_name>.sql`, folder per
  `db/routines/README.md`; helpers live in the data schema they serve
  (`db/routines/10_common/`, `20_identity/`, ...). Applied in lexical path order by
  `xcode-api db routines` (`docs/03-database.md` section 7), all in one transaction.
- Every file begins with a comment header carrying, one line each: the routine name and
  signature; `Purpose:` one sentence; `Callers:` the gateway method and use case that call
  it (or `CLI <command>` / `startup`); `Reads:` and `Writes:` the tables touched;
  `Raises:` every SQLSTATE and code it can raise, in the order the checks run; `Tests:`
  the test module that covers it. `tests/db/test_routine_headers.py` parses every file and
  fails when a line is missing or when `Raises:` differs from the `refuse(` calls in the body.
- `CREATE OR REPLACE FUNCTION` / `PROCEDURE` only; a signature change (parameters or return
  type) is a versioned migration that drops the old signature first, plus a bump of
  `api.meta_contract_version()` and of the Python constant (`docs/prompts/01-bootstrap-db.md`).
- Every `api.*` routine: `LANGUAGE plpgsql` (or `sql` for trivial reads), `SECURITY
  DEFINER`, `SET search_path = pg_catalog, pg_temp`, every object name schema-qualified,
  owned by `xcode_api_executor`, no `EXECUTE`/`format()` with parameters. `db verify`
  checks all of it.

### 1.2 Parameters

| Rule | Detail |
|---|---|
| Prefix | every parameter is `p_<name>`; names are the schema's column names where one exists |
| Tenant routines | `(p_actor_id uuid, p_organization_id uuid, p_request_id text, ...command fields..., [p_expected_version bigint,] p_now timestamptz)`; the first statement in the body is `PERFORM tenancy.enter_organization(p_actor_id, p_organization_id, p_request_id, '<permission or NULL>')` |
| Identity routines (`api.auth_*`) | `(p_request_id text, ...fields..., p_now timestamptz)`; no actor, no organization (the account is found by phone number or by user id) |
| Operator routines (`api.ops_*`) | `(p_operator text, p_request_id text, ...fields..., p_now timestamptz)`; the first statement records `ops.operator_actions` |
| Time | `p_now timestamptz` is always the last parameter and the only source of "now" (never `now()` inside a routine body, except `DEFAULT now()` column defaults for `created_at`); the business date is derived from it with `tenancy.business_date` |
| Money | `numeric`; the routine checks `> 0`, `scale(p) <= 2`, `< 10^12` and raises `money_invalid`; nothing is rounded silently |
| Text | the routine trims where .NET trimmed (`btrim`); length checks run on the trimmed value; `NULL` and `''` are the same for optional text |
| Ids | `uuid`; a routine never generates an id that the caller supplies; new ids come from column defaults and are returned |
| Pages | `p_page integer, p_page_size integer`, validated by `tenancy.check_page` (`page_out_of_range`) |
| Versions | `p_expected_version bigint` (nullable where the contract makes it optional); the update statement carries `WHERE version = p_expected_version` and a zero row count raises `version_conflict` (`XC409`) |

### 1.3 Results

| Shape | Used by | Form |
|---|---|---|
| Write result | every command | composite `api.write_result (id uuid, version bigint, outcome text)`; `outcome` is `created`, `updated`, `unchanged` (no change, no log) or `replayed` (revenue identical replay) |
| Document | every read that the contract renders as a nested object | `jsonb` whose keys are the snake_case names of the pydantic schema fields; the HTTP layer's alias generator turns them into the camelCase wire names, so the rename rule exists once (`http/schemas/common.py`). A legacy duplicate such as `use_groupping` is an explicit second alias in the schema, never a second key here |
| Paged list | list routines | `jsonb` `{"total": bigint, "items": [...]}`; `page_number` and `page_size` are echoed by the HTTP layer |
| Account state | `api.auth_account_lookup` | `SETOF api.account_state` (section 3.1): one row, or none for an unknown number |
| Scalar | helpers, `api.meta_contract_version()` | native types |

Nulls are written as JSON `null` (never omitted); dates as `YYYY-MM-DD` text; instants as
`timestamptz` rendered by `to_jsonb`, which the HTTP layer re-serialises to the six-digit
`+00:00` form of `docs/06-http-contract.md` section 1.2; money as JSON numbers.

### 1.4 Errors

Routines refuse with `RAISE EXCEPTION USING ERRCODE = '<sqlstate>', MESSAGE = '<code>',
DETAIL = '<json object>'` through `tenancy.refuse(p_code, p_sqlstate, p_detail)`. The code
is the stable snake_case identifier of `docs/06-http-contract.md` section 3; `DETAIL`
carries the parameters that sentence needs (`{"registration": "KDA 482M", "date":
"2026-10-01"}`) or the extension members the contract adds (`current`).
`db/errors.py` turns SQLSTATE and code into the domain refusal; `http/messages.py` turns the
code into the sentence.

| SQLSTATE | Meaning | Default HTTP |
|---|---|---|
| `XC401` | session invalid (user inactive, version moved, device untrusted or expired) | 401, empty body |
| `XC403` | not a member, permission missing, outside own scope for a grant, tenant guard | 403 |
| `XC404` | record missing or outside the caller's scope | 404 |
| `XC409` | stale version, conflicting record, concurrent save | 409 |
| `XC422` | rule violation with a user-facing sentence | 400 (the contract decides per code) |

Auth routines never raise for a business refusal: they return an outcome (section 3) so
that counters and consumed codes commit, as in .NET.

Check order inside a routine is always: membership and permission (`XC403`), then input
shape (`XC422`), then record existence and scope (`XC404`), then state rules (`XC422`),
then version (`XC409`), then the write. Deviations required by the .NET contract are listed
per routine (for example revenue replay before permission, `inv 2.10` step 4).

### 1.5 Transactions, locks, statements

- One routine call is one transaction (`db/session.py`); a routine never commits, never
  opens a sub-transaction except the `BEGIN ... EXCEPTION WHEN unique_violation` blocks
  listed per routine, which translate a constraint violation into the contract's `XC409`;
  the block of `api.revenue_capture` also turns `lock_not_available` into
  `XC409 revenue_concurrent_save`.
- Writers that log a change end with `tenancy.record_change`, whose `UPDATE
  tenancy.organizations ... RETURNING settings_version` is the serialisation point for an
  organization (`docs/04-schema.md` section 4.1). The organization settings and logo writes
  lock that row first, because they read, merge and write per-organization rows; nothing
  else locks it.
- Row locks: `SELECT ... FOR UPDATE` on the user row in every `api.auth_*` routine that
  counts attempts or issues tokens (`AuthGate` parity, `inv 3.4`), on the record row in
  `api.revenue_capture` (`NOWAIT`: a save of a day another open save holds is refused at
  once as `revenue_concurrent_save`, never queued behind it), on the membership row in
  people writes, on the row every setup write changes (company, vehicle, category, item,
  scheduled item, investment). A routine that checks another row it does not change locks
  that row too, because routines run in READ COMMITTED where .NET ran setup writes
  serializable: a vehicle create, update or restore reads its PSV company `FOR SHARE`, so an
  archive of that company either commits before the check or waits for the write. The
  `api.auth_*` routines
  that find no account take `pg_advisory_xact_lock(hashtext('device:' || p_device_id))`
  instead (`docs/07-auth.md` section 2). No other advisory locks except
  the migration runner's.
- Statement budget (`docs/06-http-contract.md` section 2): the gateway counts statements per
  request; a routine is one statement however many queries it runs inside. Per-routine
  cost notes are in section 7.

### 1.6 Tests every routine has

`tests/db/test_<area>_routines.py`, as `xcode_app` (or `xcode_operator` for `api.ops_*`),
one database per test from the template: happy path; every `Raises:` code with its
SQLSTATE and `DETAIL` keys; tenant isolation (an actor of organization B calling with
organization A's ids gets `XC403 not_member`, and sees no rows through any read); version
bump and `XC409`; `unchanged` on a no-op write with no change-log row; the change-log row
and audit row of every logged write (section, entity, vehicle id, reason text, `before` and
`after` text, version = organization `settings_version`); and the fake parity case in
`tests/db/test_fakes_match_routines.py` (`docs/09-testing.md`).

## 2. Helper catalogue (data schemas; never granted to `xcode_app` or `xcode_operator`)

### 2.1 `tenancy` (session, scope, change log)

| Helper | Signature | Behaviour |
|---|---|---|
| `tenancy.refuse` | `(p_code text, p_sqlstate text DEFAULT 'XC422', p_detail jsonb DEFAULT '{}') RETURNS void` | raises as in section 1.4; the only `RAISE` site for business refusals |
| `tenancy.current_organization` / `tenancy.current_actor` / `tenancy.current_request` | `() RETURNS uuid` / `uuid` / `text` | read `current_setting('xcode.organization_id', true)` and the actor and request settings; `NULL` when unset (RLS then matches nothing) |
| `tenancy.enter_organization` | `(p_actor_id uuid, p_organization_id uuid, p_request_id text, p_permission text DEFAULT NULL) RETURNS void` | `set_config('xcode.organization_id', ..., true)` and the actor and request settings (transaction-local); requires an active membership of the actor in the organization (`XC403 not_member`); when `p_permission` is given, requires it in `tenancy.effective_permissions` (`XC403 permission_missing`) |
| `tenancy.enter_organization_as_operator` | `(p_organization_id uuid) RETURNS void` | sets the organization setting only; callable from `api.ops_*` routines that create or seed an organization; records nothing itself |
| `tenancy.require_permission` / `tenancy.require_any_permission` | `(p_permission text)` / `(p_permissions text[]) RETURNS void` | `XC403 permission_missing` unless held by the current actor; used by routines whose permission depends on the request (`api.revenue_capture`, `api.setup_vehicle_list`) |
| `tenancy.has_permission` | `(p_permission text) RETURNS boolean` | the predicate form, for shaping results (`can_edit`, hidden targets) |
| `tenancy.effective_permissions` | `(p_organization_id uuid, p_user_id uuid) RETURNS text[]` | what a member holds now: `{}` for an inactive membership, else `tenancy.assigned_permissions`. Token issuance (`api.auth_*`) and `tenancy.enter_organization` call it |
| `tenancy.assigned_permissions` | `(p_organization_id uuid, p_user_id uuid) RETURNS text[]` | the only resolver: role defaults plus granted overrides, dependencies expanded transitively, denied overrides removed, then every permission whose direct dependencies are not all present removed until stable (`inv 3.2`), whether or not the membership is active (an inactive person's document and snapshot keep their permissions, `AC-26`) |
| `tenancy.actor_scope` | `() RETURNS tenancy.scope` (composite `all_companies boolean, company_ids uuid[], vehicle_ids uuid[]`) | the current actor's data scope rows; empty arrays when none |
| `tenancy.scope_mode` | `(p_organization_id uuid, p_user_id uuid) RETURNS text` | `all` / `companies` / `vehicles` as `inv 3.2` defines |
| `tenancy.business_date` | `(p_organization_id uuid, p_now timestamptz) RETURNS date` | the held `business_date`, else `(p_now AT TIME ZONE <organization time zone>)::date` |
| `tenancy.calendar_date` | `(p_organization_id uuid, p_now timestamptz) RETURNS date` | always the calendar date in the organization zone (`O01 calendar_date`) |
| `tenancy.check_time_zone` | `(p_name text) RETURNS text` | `XC422 time_zone_invalid` with `{"value": p_name}` unless `p_name` is an IANA zone name that PostgreSQL resolves to exactly itself: the name is set transaction-locally as `TimeZone`, which opens the one zone file it names and reports that file's own name (so a wrong case comes back different and an abbreviation such as `EAT` is refused), then the setting is restored; POSIX rules (`UTC+3`, `<+03>-3`) are refused by a name pattern. `pg_timezone_names` is not read: it loads every zone file, which takes seconds on some hosts, over the 5 s statement timeout. Returns the name |
| `tenancy.check_contrast` | `(p_hex text, p_against text) RETURNS numeric` (schema function, migration) | WCAG relative-luminance contrast ratio to 2 decimals |
| `tenancy.check_page` | `(p_page integer, p_page_size integer) RETURNS void` | `page_out_of_range` unless `1 <= p_page <= 100000` and `1 <= p_page_size <= 100` |
| `tenancy.check_money` | `(p_amount numeric, p_code text DEFAULT 'money_invalid') RETURNS numeric` | `> 0`, `round(p, 2) = p` (so `1.500` passes, as .NET's `Round(v, 2) == v`; `scale(p) <= 2` would refuse it), `<= 999999999999.99`; returns the value |
| `tenancy.trim_text` | `(p_value text) RETURNS text` | trims Unicode white space at both ends as .NET `Trim()`; `NULL` for `NULL` or blank |
| `tenancy.organization_ids` | `() RETURNS uuid[]` | every organization id, oldest first, for provisioning's one-organization rule; `SECURITY DEFINER` owned by `xcode_owner` so it reads past row-level security (ids only, executor only) |
| `tenancy.check_typed_reason` | `(p_reason text) RETURNS text` | trims; `NULL` or `''` gives `NULL`; else 1..500 or `reason_length` |
| `tenancy.compose_reason` | `(p_automatic text, p_typed text) RETURNS text` | the `OS-11` rule: `p_automatic` when no typed text (clipped to 497 characters plus `...` when longer than 500, as .NET's `Automatic(reason)`); else `<automatic>. Reason: <typed>` with no second full stop when the typed text ends in `.`, `!` or `?`; when the sum exceeds 500 the automatic part is cut first to `greatest(500 - length(suffix), 100)` characters ending in `...`, and the result is clipped to 497 characters plus `...` |
| `tenancy.join_words` | `(p_parts text[]) RETURNS text` | `a`, `a and b`, `a, b and c` |
| `tenancy.record_change` | `(p_section text, p_entity_id uuid, p_vehicle_id uuid, p_before json, p_after json, p_reason text, p_audit_action text, p_audit_entity text, p_audit_before jsonb, p_audit_after jsonb, p_now timestamptz) RETURNS bigint` | bumps `tenancy.organizations.settings_version` (`UPDATE ... RETURNING`), inserts the `tenancy.change_log` row (snapshots stored as the `json::text`, `'null'` for creations, `NULL` for removals) and the `tenancy.audit_events` row, both with the current actor and request id; returns the new version. Every logged write calls it exactly once and last |
| `tenancy.seed_roles` | `(p_organization_id uuid) RETURNS void` | inserts the four catalog roles (`Owner`, `Office admin`, `Fleet manager`, `Revenue clerk`) when missing |
| `tenancy.person_snapshot`, `tenancy.settings_snapshot`, `tenancy.logo_snapshot` | `(p_user_id uuid)`, `(p_section text)`, `() RETURNS json` | section 6.2 |
| `tenancy.fmt_money`, `tenancy.fmt_day`, `tenancy.fmt_iso`, `tenancy.setting_word`, `tenancy.setting_value` | section 6.1 | formatting for reasons |
| `tenancy.people_visible` | `(p_viewer uuid) RETURNS SETOF uuid` | the people the viewer may see (`inv 2.3` S05): themselves; everyone when the viewer has all companies; people whose company scope meets the viewer's companies or the companies of the viewer's vehicles; people whose vehicle scope holds a vehicle the viewer can see |
| `tenancy.person_scope` / `tenancy.person_reach` | `(p_user_id uuid) RETURNS tenancy.scope` | a person's data scope rows; their reach (the same, plus every vehicle of their companies), used for what a viewer is shown and what an editor may hand on; `tenancy.actor_scope` is `person_scope` of the current actor |
| `tenancy.person_in_view` | `(p_user_id uuid) RETURNS boolean` | the person has a role in the current organization and is in `tenancy.people_visible` of the current actor (`AC-25`) |
| `tenancy.role_of` | `(p_user_id uuid) RETURNS text` | the person's role name, for the Owner rules |
| `tenancy.expand_permissions` / `tenancy.role_permissions` | `(p_keys text[])` / `(p_role_name text) RETURNS text[]` | catalogue keys with their dependencies, in catalogue order; a role's defaults expanded (name matched ignoring case) |
| `tenancy.check_person_grant` | `(p_user_id, p_role, p_scope_mode, p_company_ids, p_vehicle_ids, p_permissions, p_approval_limit, p_email, p_phone) RETURNS tenancy.scope` | steps 10 to 15 of a person save (scope rules with hidden holdings kept, self edit, Owner rules, known permissions, holdings and `access.manage`, sign-in details); returns the scope to store |
| `tenancy.save_person` | `(p_user_id uuid, ...the person fields..., p_expected_version bigint, p_now timestamptz) RETURNS api.write_result` | the sixteen steps and the writes of `api.people_create` (`p_user_id` `NULL`) and `api.people_update`, once |
| `tenancy.person_document` | `(p_user_id uuid, p_viewer tenancy.scope) RETURNS jsonb` | the person document with the scope ids inside the viewer's reach and counts of the rest |
| `tenancy.redact_person_snapshot` | `(p_snapshot text, p_company_ids uuid[], p_vehicle_ids uuid[]) RETURNS text` | a people snapshot with `CompanyIds`/`VehicleIds` kept to a viewer's reach, every other key and the key order untouched (`OS-21`) |
| `tenancy.settings_defaults` / `tenancy.settings_document` | `(p_section text) RETURNS jsonb` | the defaults of `localization`, `branding`, `securityPolicy` (pinned equal to the column defaults by a test); the stored section under the document keys (`primary`, `logo_light` for the renamed branding columns), defaults when the row is missing |
| `tenancy.check_localization` / `tenancy.check_branding` / `tenancy.check_security_policy` | `(p_document jsonb) RETURNS void` | the validation of a merged or stored section (`docs/06-http-contract.md` section 3, organization block), shared by the save and the read-time validation |
| `tenancy.effective_settings` | `(p_user_id uuid) RETURNS jsonb` | the effective formats, branding, clamped policy, theme, motion and font scale of `OS-16`, validating the stored sections on every read |
| `tenancy.settings_reason` | `(p_section text, p_before json, p_after json) RETURNS text` | the automatic reason of a settings save (section 6.1) |
| `tenancy.compact_json` / `tenancy.fmt_instant` | `(json) RETURNS json` / `(timestamptz) RETURNS text` | the compact form snapshots are stored in; an instant as `2026-10-07T05:25:29.123456+00:00` |

### 2.2 `identity` (accounts, codes, devices, tokens)

| Helper | Signature | Behaviour |
|---|---|---|
| `identity.normalize_phone` | `(p_input text) RETURNS text` | `+254XXXXXXXXX` from `+254...`, `254...`, `07...`, `7...` with subscriber `[17][0-9]{8}`; `NULL` when it does not normalise (the caller decides the refusal) |
| `identity.normalize_email` | `(p_input text) RETURNS text` | the address trimmed (`tenancy.trim_text`) and lower-cased when it is `local@domain` with no white space and at most 320 characters; `NULL` otherwise (the caller decides the refusal). Callers: `api.ops_provision_user`, `tenancy.save_person` |
| `identity.lock_user` | `(p_user_id uuid) RETURNS identity.users` | `SELECT ... FOR UPDATE`; the per-account serialisation point |
| `identity.active_organization` | `(p_user_id uuid) RETURNS uuid` | the organization of the user's single active membership; `SECURITY DEFINER` owned by `xcode_owner` (the table owner) so it reads past row-level security before any organization is known; returns the id only and is executable by `xcode_api_executor` alone (`tests/db/test_routine_headers.py` pins the allow-list) |
| `identity.policy_for` | `(p_user_id uuid) RETURNS identity.policy` (composite `organization_id, pin_length, lockout_threshold, lockout_minutes, access_token_minutes, refresh_token_days, role_name, first_name, last_name, permissions text[]`) | the single active membership's organization policy, clamped into the bounds of `docs/04-schema.md` section 4.6 (defaults when no row); `NULL` row when the user has no active membership or no role (then no tokens are ever issued, `inv 3.1`); sets the transaction-local organization setting to that organization to read its tenant rows. Callers needing lockout values without a policy use the defaults (5, 15) |
| `identity.matching_code` | `(p_user_id uuid, p_purpose text, p_device_id text, p_code_hash text, p_now timestamptz) RETURNS identity.code_check` (composite `code_id uuid, refusal text`) | the newest unconsumed code of that purpose and device: `code_id` on a match (not consumed); `refusal = code_expired` when there is none, it expired (`p_now > expires_at`) or it already failed five times; `refusal = wrong_code` after `failed_attempts + 1` (the fifth consumes it), so the sign-in trail can tell the two apart |
| `identity.supersede_codes` | `(p_user_id uuid, p_purpose text) RETURNS integer` | marks every unconsumed code of the user and purpose consumed (all devices) before a new one is issued; superseded codes keep `expires_at`, so they still count toward the cooldown and caps (only a withdrawn code does not; `inv-auth 1.2`) |
| `identity.code_caps` | `(p_user_id uuid, p_purpose text, p_skip_cooldown boolean, p_now timestamptz) RETURNS boolean` | false when a non-withdrawn code of the same user and purpose (any device) is younger than 60 s (unless `p_skip_cooldown`, development codes), or when the user has 5 non-withdrawn codes in the last hour or 10 in the last day across purposes and devices; the caller then issues nothing and answers as if it had (`docs/07-auth.md` section 1) |
| `identity.mask_email` | `(p_email text) RETURNS text` | section 3.2 |
| `identity.touch_version` | `(p_user_id uuid) RETURNS bigint` | `version = version + 1` on the user row, once per routine that changed the row or issued tokens; the concurrency-token parity of `AuthDb.BumpVersions` |
| `identity.lock_account` | `(p_phone text, p_device_id text) RETURNS identity.users` | normalises the number and locks the account row, or takes the `device:` advisory lock and returns a `NULL` row for an unknown or non-normalising number |
| `identity.device_trusted` | `(p_user_id uuid, p_device_id text, p_now timestamptz) RETURNS boolean` | the device row exists, is not revoked and `trust_expires_at` is `NULL` or later than `p_now` |
| `identity.trust_device` | `(p_user_id uuid, p_device_id text, p_trust_days integer, p_now timestamptz) RETURNS void` | upsert with `revoked = false`, `trust_expires_at = p_now + p_trust_days` days or `NULL` |
| `identity.issue_session` | `(p_user_id uuid, p_device_id text, p_refresh_token_hash text, p_policy identity.policy, p_now timestamptz) RETURNS jsonb` | stores the refresh digest (`expires_at = p_now + refresh_token_days`) and returns the `authenticated` outcome with the claim material |
| `identity.outcome` | `(p_outcome text, p_fields jsonb DEFAULT '{}') RETURNS jsonb` | the outcome document with every key present (section 3.1) |
| `identity.phone_digest` | `(p_value text) RETURNS text` | SHA-256 hex of the normalised number, or of the raw input when it does not normalise (`docs/04-schema.md` section 3.5); flows without a number (refresh, sign-out, device revoke) record the digest of the account's stored number, or of the empty string when no account is found |
| `identity.revoke_devices` / `identity.revoke_tokens` | `(p_user_id uuid[, p_device_id text]) RETURNS integer` | set `revoked` on trusted devices / refresh tokens (all, or one device); return the count |
| `identity.record_attempt` | `(p_operation text, p_outcome text, p_refusal text, p_user_id uuid, p_phone_digest text, p_device_id text, p_now timestamptz) RETURNS void` | one `identity.sign_in_attempts` row with the current request id |

### 2.3 `setup` (companies, vehicles, catalog, schedules)

| Helper | Signature | Behaviour |
|---|---|---|
| `setup.company_visible` | `(p_company_id uuid) RETURNS boolean` | all companies, or id in the actor's companies, or the company owns a vehicle in the actor's vehicle scope |
| `setup.vehicle_visible` | `(p_vehicle_id uuid) RETURNS boolean` | all companies, or the vehicle's company in the actor's companies, or the id in the actor's vehicles |
| `setup.visible_vehicles` / `setup.visible_companies` | `() RETURNS SETOF uuid` | the sets behind every list |
| `setup.company_active_on` | `(p_company_id uuid, p_day date) RETURNS boolean` | `archived_on IS NULL OR archived_on > p_day` |
| `setup.vehicle_active_on` | `(p_vehicle_id uuid, p_day date) RETURNS boolean` | `joined_on <= day AND (left_on IS NULL OR day < left_on)` and not inside an away period `[left_on, returned_on)` |
| `setup.vehicle_away_on` | `(p_vehicle_id uuid, p_day date) RETURNS boolean` | inside an away period (distinguishes the two revenue messages) |
| `setup.target_on` | `(p_vehicle_id uuid, p_day date) RETURNS numeric` | 0 when not active; else the `weekly_amount` of the target with the greatest `effective_from <= day`, ties by greatest `revision` (one indexed lookup) |
| `setup.registration_normalize` | `(p_input text) RETURNS text` | trim, upper-case, strip spaces, must match `^K[A-Z]{2}[0-9]{3}[A-Z]$` else `vehicle_registration_format`; returns `KDA 482M` form |
| `setup.recurring_current_version` | `(p_item_id uuid) RETURNS setup.recurring_versions` | the highest revision |
| `setup.recurring_version_on` | `(p_item_id uuid, p_day date) RETURNS setup.recurring_versions` | the version in force on a day (`effective_from <= day`, highest revision) |
| `setup.recurring_due_days` | `(p_version setup.recurring_versions, p_from date, p_through date) RETURNS SETOF date` | due dates by the frequency rules of `inv 3.5` (weekly weekday, monthly day or last day, yearly month and day; missing days skipped), within `start_on..end_on`, before `stopped_from`, and only while that version rules (until a higher revision's `effective_from`) |
| `setup.schedule_valid` | `(p_frequency integer, p_day integer, p_last_day boolean, p_month integer) RETURNS boolean` | the `ck_recurring_versions_schedule` rule as a predicate for the `recurring_schedule_shape` message; integer parameters because the routines take the wire integers (a `smallint` signature would need a cast at every call); `false`, never null |
| `setup.company_snapshot` | `(p_id uuid) RETURNS json` | section 6.2; `Active` is `archived_on IS NULL` whatever the business date, as .NET's `CompanyUseCases.Snapshot` |
| `setup.vehicle_snapshot`, `setup.recurring_snapshot`, `setup.expense_category_snapshot`, `setup.expense_item_snapshot`, `setup.investment_snapshot` | `(p_id uuid) RETURNS json` | section 6.2; the string `null` for an unknown id |
| `setup.unchanged_result` | `(p_id uuid) RETURNS api.write_result` | `(p_id, the current settings_version, 'unchanged')`: what every no-op write answers |
| `setup.record_setup_change` | `(p_section text, p_entity_id uuid, p_vehicle_id uuid, p_before json, p_after json, p_reason text, p_now timestamptz) RETURNS bigint` | `tenancy.record_change` with the section `setup.{section}` audit action; the new settings version |
| `setup.recurring_visible` | `(p_item_id uuid) RETURNS boolean` | all companies, or any version of the item allocates to a visible vehicle (the 404 rule of the scheduled item routes) |
| `setup.save_recurring` | `(p_item_id uuid, p_name text, p_kind integer, p_amount numeric, p_frequency integer, p_day integer, p_last_day boolean, p_start date, p_end date, p_allocations jsonb, p_expense_item_id uuid, p_note text, p_month integer, p_reason text, p_now timestamptz) RETURNS api.write_result` | the nine steps of `inv 2.6` and the writes, shared by create (`p_item_id` null) and revise; `p_allocations` is a `jsonb` array of `{vehicle_id, amount}` with the amounts as text, read exactly; it fires the deferred share-sum constraint trigger with `SET CONSTRAINTS ... IMMEDIATE` so the check runs with the routine owner's rights (at commit it would run as `xcode_app`, which has no `USAGE` on `setup`) |
| `setup.report_window` | `(p_vehicle_id uuid, p_from date, p_through date, p_today date) RETURNS daterange` | the report window of `inv 3.5` (`max(from, joined_on)` to `min(through, today)`, ending the day before `left_on`); `empty` when nothing remains |
| `setup.vehicle_money_in` | `(p_vehicle_id uuid, p_window daterange) RETURNS numeric` | the revenue amounts recorded in the window |
| `setup.vehicle_postings` | `(p_vehicle_id uuid, p_window daterange) RETURNS TABLE (item_id uuid, version_id uuid, day date, name text, kind smallint, amount numeric, bucket smallint)` | every due day of every version with a share on the vehicle, through `setup.recurring_due_days`; `bucket` is the reported bucket of a cost (2 when none was stored), null for a saving |
| `setup.vehicle_net` | `(p_vehicle_id uuid, p_from date, p_through date, p_today date) RETURNS numeric` | money in less the cost postings over the report window: the report's `net` and the investment's `returned`, one definition for both |

### 2.4 `revenue`

Since `0011_revenue` (07b D4) section 10.5 changes these rows, and where the two differ
section 10.5 holds. `target` is the day target. `revenue.cell` and `revenue.vehicle_week`
take the viewer's earliest writable date, and the week also takes the threshold and the
amber band. `revenue.percent` divides by the sum of the day targets, and `revenue.gap_band`
is new.

| Helper | Signature | Behaviour |
|---|---|---|
| `revenue.vehicle_day` (type) | composite `vehicle_id uuid, day date, active boolean, away boolean, target numeric, counted boolean, record_id uuid, amount numeric, reason smallint, reason_label text, note text, corrected_after_date boolean, version bigint` | one day of one vehicle: `active` = in the fleet and not away, `target` = the weekly target that day (0 when not active), `counted` = active and before the business date or recorded, and the day's record if any |
| `revenue.vehicle_days` | `(p_vehicle_ids uuid[], p_from date, p_through date, p_today date) RETURNS SETOF revenue.vehicle_day` | every day of `[p_from, p_through]` of each vehicle by vehicle and day, set-based (targets as date ranges, away periods, the period's records and reason labels joined once: a function body is planned without its arguments, and an unbounded records join hashed the organization's whole history even for one vehicle's week); agrees with `setup.vehicle_active_on`, `setup.vehicle_away_on` and `setup.target_on` day by day |
| `revenue.earliest_missing` | `(p_vehicle_ids uuid[], p_today date) RETURNS TABLE (vehicle_id uuid, earliest_missing date)` | per vehicle the first day `>= joined_on` and `< least(left_on, p_today)` on which it is not away and has no record; `NULL` when complete. The day before it is before the join date, recorded or away, so it is the first of the candidates (the join date, the day after a record whose next day has none, each return from time away) that is neither away nor recorded. An open join date answers at once; otherwise the vehicle's records are walked in date order (index only) and the walk stops at the first open day, so only a history without a gap is read to its end; time away is gathered once per vehicle into a multirange |
| `revenue.cell` | `(p_day revenue.vehicle_day, p_today date, p_can_capture boolean, p_can_correct boolean) RETURNS jsonb` | one `RevenueCellDto` (`day`, `status`, `expected` = `round_half_even(target / 7, 2)`, `amount`, `reason` label, `note`, `can_edit`, `edited_after_capture`, `version`): `none` when not active, `future` after the business date, then `missing`, `amount` or `reason`; `can_edit` = capture for a missing day, capture or correct for a record of the business date, correct for an earlier record, false otherwise (days are captured in any order since 9276c51) |
| `revenue.vehicle_week` | `(p_days revenue.vehicle_day[], p_today date, p_can_capture boolean, p_can_correct boolean) RETURNS jsonb` | the cells of the days given (in day order), `total_amount` and `total_expected` (the counted days' amounts, and their unrounded targets / 7, each rounded once), `percent`; `plpgsql`, which keeps the plans of the helpers it calls across a grid's rows (a SQL body is run afresh per row and plans them again) |
| `revenue.percent` | `(p_amount numeric, p_target_sum numeric) RETURNS integer` | `round(amount * 700 / target_sum)` half away from zero, held to the 32-bit range; `NULL` when the target sum is 0. Exact, where .NET divided each day's target by 7 to 28 digits and summed: when the exact figure is a half, .NET can land one point lower or higher (a full week at a weekly target of 10 000 with 5 050 recorded: .NET 50, here 51; one day of it: both 179). An accepted deviation, pinned by `test_percent_rounds_half_away_from_zero_and_holds_to_32_bits`; the expected sums themselves never tie and agree |
| `revenue.week_start` | `(p_day date) RETURNS date` | the first day of the organization week holding `p_day` (localization `first_day_of_week`) |
| `revenue.reason_label` / `revenue.reason_code` | `(smallint) RETURNS text` / `(text) RETURNS smallint` | `Garage`, `Arrest`, `No Crew`, `Other` and the accepted input spellings (`No Crew` and `NoCrew`), case-sensitive; unknown text gives `NULL` |
| `revenue.round_half_even` | `(p_value numeric, p_scale integer) RETURNS numeric` | banker's rounding (.NET `decimal.Round` default) for the revenue money figures (cell `expected`, totals, day totals, dashboard `revenue` and `expected`); PostgreSQL `round` is half away from zero and is used everywhere else, including petty-cash totals and percentages; `plpgsql`, whose expressions are kept across the calls of one query (a SQL body with `FROM` cannot be inlined and ran five times slower over a week grid) |
| `revenue.record_snapshot` | `(p_id uuid) RETURNS json` | section 6.2 (`Reason` as the .NET enum name, `NoCrew`) |

## 3. Authentication routines (`api.auth_*`; `docs/07-auth.md` holds the check orders)

Secrets never enter the database: the service hashes PINs (PBKDF2, worker thread) and
computes HMAC digests of codes and refresh tokens with the signing key, then passes digests.
A PIN check therefore needs two statements: a lookup that returns the stored hash material
and the account state, then the decision routine that records the outcome. Every other auth
operation is one statement. The service always runs the PBKDF2 derivation, against a fixed
dummy hash when the lookup found no usable account, so timing does not reveal existence
(`domain/policies.py`). Every decision routine here locks the account row (`identity.lock_user`) or,
without an account, takes `pg_advisory_xact_lock(hashtext('device:' || p_device_id))`, and
writes one `identity.sign_in_attempts` row (`docs/07-auth.md` section 2). The lookup writes
a row only for an unknown or non-normalising number; `api.auth_withdraw_code` and
`api.auth_resolve_session` are not decisions and write none (the `operation` constraint of
`docs/04-schema.md` section 3.5 has no value for them). `silent` is recorded as the wire
answer `check_email`, `invalid_pin` as `refused` with `policy_pin_length`; a refusal the
constraint has no word for (an account that already has a PIN asking for `first_setup`, a
cooldown or cap, a refresh while paused) is recorded with `refusal` `NULL`.

### 3.1 Shared result types

`api.account_state`: `user_id uuid, status text, pin_hash text, security_version integer,
failed_attempts integer, paused_until timestamptz, untrusted_failed_attempts integer,
device_trusted boolean, policy jsonb` (no row when the number is unknown or does not
normalise; the lookup still records the attempt with `refusal = unknown_number`). `policy` is
`to_jsonb(identity.policy_for(user))`, `NULL` without an active membership or role: a nested
composite of schema `identity` would reach the gateway as unparsed text, because its roles
cannot look up a type in a schema they have no `USAGE` on; `db/types.py` maps the document
to `AccountPolicy`.

`api.auth_outcome` (`jsonb`): `{outcome, refusal, retry_after_seconds, masked_email,
code_issued, code_id, email, minimum_pin_length, user_id, organization_id, role, first_name,
last_name, permissions, security_version, access_token_minutes, refresh_expires_at}` (every
key present, built by `identity.outcome`); `outcome` is one
of `authenticated`, `verification_required`, `check_email`, `silent`, `code_verified`,
`invalid_pin` (with `minimum_pin_length`), `paused`, `refused`, `signed_out`,
`device_revoked`. Only the keys the outcome needs are non-null.

### 3.2 Catalogue

| Routine | Parameters (after `p_request_id`) | Returns | Decision (`docs/07-auth.md` section) | Writes |
|---|---|---|---|---|
| `api.auth_account_lookup` | `p_phone text, p_device_id text, p_now` | `SETOF api.account_state` | 3.1 (statement one) | attempt row for an unknown or non-normalising number only |
| `api.auth_sign_in` | `p_user_id uuid, p_device_id text, p_pin_ok boolean, p_checked_pin_hash text, p_code_hash text, p_refresh_token_hash text, p_skip_cooldown boolean, p_now` | `api.auth_outcome` | 3.1 steps 1 to 9; `p_pin_ok` counts only when `p_checked_pin_hash` equals the locked row's `pin_hash` | user counters and pause; `verification_codes` (supersede older `new_device`, insert); `refresh_tokens` insert; `touch_version`; attempt row |
| `api.auth_verify_device` | `p_phone text, p_device_id text, p_code_hash text, p_refresh_token_hash text, p_trust_days integer, p_now` | `api.auth_outcome` | 3.2 | code failed tries or consume; counters; trusted device upsert; refresh token; `touch_version`; attempt row |
| `api.auth_request_code` | `p_phone text, p_device_id text, p_purpose text, p_code_hash text, p_skip_cooldown boolean, p_now` | `api.auth_outcome` (`check_email` with `email` and `code_id`, or `silent`) | 3.3 | supersede older codes of the user and purpose; insert; attempt row |
| `api.auth_verify_code` | `p_phone text, p_device_id text, p_purpose text, p_code_hash text, p_now` | `api.auth_outcome` (`code_verified` / `refused`) | 3.4 | failed tries on a wrong code; attempt row |
| `api.auth_complete_pin` | `p_phone text, p_device_id text, p_purpose text, p_code_hash text, p_pin_length integer, p_pin_hash text, p_refresh_token_hash text, p_trust_days integer, p_now` | `api.auth_outcome` (`authenticated` / `invalid_pin` / `refused`) | 3.5 | consume codes; `pin_hash`; counters; `security_version + 1`; revoke every refresh token; trust the device; insert the refresh token; `touch_version`; attempt row |
| `api.auth_refresh` | `p_token_hash text, p_device_id text, p_new_token_hash text, p_now` | `api.auth_outcome` | 3.6 | revoke (old, or all on replay or inactive user), insert new; `touch_version`; attempt row |
| `api.auth_sign_out` | `p_token_hash text, p_device_id text, p_now` | `api.auth_outcome` (`signed_out`) | 3.7 | revoke the device's tokens when matched; attempt row |
| `api.auth_revoke_device` | `p_user_id uuid, p_device_id text, p_now` | `api.auth_outcome` (`device_revoked`) | 3.8 | device revoked; device's tokens revoked; device's codes consumed; attempt row |
| `api.auth_withdraw_code` | `p_code_id uuid, p_now` | `void` | 7 (mail failure) | `consumed = true`, `expires_at = created_at` for a code still unconsumed; no attempt row |
| `api.auth_resolve_session` | `p_user_id uuid, p_device_id text, p_security_version integer, p_now` (no `p_request_id`) | `jsonb` `{organization_id, role}` for the log context | 3.10; raises `XC401 session_invalid` | none |

`p_skip_cooldown` carries `XCODE_DEVELOPMENT_CODES` (the cooldown is skipped, the caps are
not) and `p_trust_days` carries `XCODE_AUTH_TRUST_LIFETIME_DAYS` (`NULL` = trust without
expiry): both are settings of the service that the routines need to decide.

`identity.mask_email(text)`: the first character, `***`, then everything from the first `@`;
`***` alone when there is no `@` or it is the first character.

## 4. Tenant routines

Every routine below begins with `tenancy.enter_organization(p_actor_id, p_organization_id,
p_request_id, <permission>)`; the `Permission` column is that argument (`member` means
`NULL`). "Logs" names the change-log section, the automatic reason (section 6.1) and the
audit action. `W` in the Returns column is `api.write_result`.

### 4.1 Access and people (S01 to S11; rules `AC-*`)

| Routine | Permission | Parameters (after the three standard ones) | Returns | Raises (in order) | Logs |
|---|---|---|---|---|---|
| `api.access_catalog_list` | member | `p_now` | `jsonb` groups and items in catalog order (`tenancy.permissions` ordered by `group_order, item_order`, `needs` from `permission_dependencies`) | | |
| `api.access_role_list` | `people.view` | `p_now` | `jsonb` `[{id, name, permissions}]` by name, permissions = role defaults with dependencies expanded | | none (roles are pre-seeded; the .NET write-on-read is retired) |
| `api.access_scope_options` | `people.manage` | `p_now` | `jsonb` `{companies: [{id, name}], vehicles: [{id, registration, company_id}]}` limited to what the actor may hand on (`inv 2.3` S03) | | |
| `api.access_my_scope` | member | `p_now` | `jsonb` `{all_companies, companies, vehicles}` (retired vehicles included) | | |
| `api.people_list` | `people.view` | `p_page, p_page_size, p_role text, p_status text, p_now` | paged `person` documents (`inv 3.3`), order `last_name, first_name, user_id`, kept to one role by name (case ignored) and one sign-in state (`active`, `waiting`, `none`; blank or `all` keeps everyone); `company_ids`/`vehicle_ids` filtered to the actor's reach, `other_companies`/`other_vehicles` counts | `page_out_of_range`, then `people_filter_status_invalid` | |
| `api.people_get` | `people.view` | `p_user_id, p_now` | one `person` document | `XC404` when not in `tenancy.people_visible` | |
| `api.people_create` | `people.manage` | `p_first_name, p_last_name, p_email, p_phone, p_role, p_scope_mode, p_company_ids uuid[], p_vehicle_ids uuid[], p_permissions text[], p_approval_limit numeric, p_now` | `W` (`id` = the new user id) | the sixteen steps of `inv 2.3` in order, codes `people_*` of `docs/06-http-contract.md` section 3; `people_contact_taken` is raised by the routine's own check and, as a backstop, by the `unique_violation` handler on `identity.users` | `people`: `Added {First Last} as {Role}`; audit `person.created` |
| `api.people_update` | `people.manage` | `p_user_id, ...the same fields..., p_expected_version, p_now` | `W` (`unchanged` when nothing differs; `membership.version + 1` otherwise) | the sixteen steps; `people_version_required` when `p_expected_version IS NULL`; `version_conflict` on mismatch; `people_self_edit` for the actor's own row | `people`: `Changed {name, sign-in details, role, single permissions, data scope, approval limit} for {First Last}`; a name, role or permission change bumps the person's `security_version`; an email or phone change also revokes their devices and tokens; audit `person.updated`, and `person.sign_in_details_changed` (email and phone before and after) when they change |
| `api.people_set_active` | `people.manage` | `p_user_id, p_active boolean, p_expected_version bigint, p_reason text, p_now` | `W` | `people_self_deactivate` (both directions, same text); `XC404`; `people_owner_edit`; already in the state -> `unchanged` with no version check; else `version_conflict` when `p_expected_version` is `NULL` or differs; deactivate needs a typed reason (`reason_length`) | deactivate: membership inactive, user `removed`, `security_version + 1`, devices and tokens revoked, `Removed access for {First Last}` plus the typed reason, audit `person.deactivated`; activate: `Restored access for {First Last}`, audit `person.activated` |
| `api.people_sign_out` | `people.manage` | `p_user_id, p_now` | `W` | `people_self_sign_out`; `XC404`; `people_owner_edit` | revokes devices and tokens; `Signed {First Last} out of every device` (before = after); audit `person.sessions_revoked` (`AC-24`) |

Owner rules, role and permission holdings, hidden-scope preservation and the sign-in
details rules are implemented once, in `tenancy.check_person_grant(...)`, called by
`tenancy.save_person`, which holds the sixteen steps and the writes once for create and
update (the two `api.*` routines enter the organization and call it); `tenancy.person_snapshot` builds the PascalCase snapshot (section 6.2).

### 4.2 Companies and vehicles (S12 to S23; rules `SU-C*`, `SU-V*`, `SU-A*`)

| Routine | Permission | Parameters | Returns | Raises (in order) | Logs |
|---|---|---|---|---|---|
| `api.setup_company_list` | `companies.manage` | `p_page, p_page_size, p_now` | paged `{id, name, vehicle_count, active, archived_on}` by `name, id`; `vehicle_count` = visible vehicles joined by today and not left | `page_out_of_range` | |
| `api.setup_company_create` | `companies.manage` | `p_name, p_reason, p_now` | `W` | `reason_length`; `company_name_length`; `XC403 permission_missing` (no detail) unless the actor has all companies; `company_name_taken` (own check on `normalized_name`, backstop `unique_violation`) | `companies`: `Added company {name}`; audit `setup.companies` |
| `api.setup_company_rename` | `companies.manage` | `p_company_id, p_name, p_reason, p_now` | `W` | `reason_length`; `company_name_length`; `XC404`; `company_archived_rename` (archived as of today); `company_name_taken` (excluding itself); same name -> `unchanged` | `Renamed company {old} to {new}` |
| `api.setup_company_archive` | `companies.manage` | `p_company_id, p_reason, p_now` | `W` | `reason_length`; `XC404`; `company_has_vehicles` (any vehicle with `left_on IS NULL OR left_on > today`, vehicles not yet joined included); archived today -> `unchanged`; archived on another date -> `company_already_archived` | `archived_on = today`; `Archived company {name}` |
| `api.setup_company_restore` | `companies.manage` | `p_company_id, p_reason, p_now` | `W` | `reason_length`; `XC404`; not archived -> `unchanged` | clears `archived_on` (also a future one); `Restored company {name}` |
| `api.setup_vehicle_list` | member, then `require_any_permission('{vehicles.manage, invest.view}')` before `check_page` | `p_page, p_page_size, p_company_id uuid, p_now` | paged `vehicle` documents (`inv 3.4`) by `registration`, of one company when `p_company_id` is given (total and pages count the matches only); without `vehicles.manage`: `weekly_target` and `recurring_items` `NULL`, `targets` `[]`; `weekly_target` = `setup.target_on(today)` for an active vehicle else 0; `recurring_items` = distinct items whose current version allocates to it, `end_on` not before today, not stopped on or before today | `XC403`; `page_out_of_range` | |
| `api.setup_vehicle_create` | `vehicles.manage` | `p_company_id, p_registration, p_joined_on, p_weekly_target, p_reason, p_now` | `W` | `reason_length`; `vehicle_registration_format`; `money_invalid`; `vehicle_joined_future` (`p_joined_on` after today); `XC404` company not visible; `vehicle_company_inactive`; `XC403 permission_missing` (no detail) unless all companies or the company is in the actor's companies; `vehicle_registration_taken` | inserts the vehicle and target revision 1 at `joined_on`; `vehicles`: `Added vehicle {reg} to {company} with a weekly target of {CUR} {amount} from {joined_on}` |
| `api.setup_vehicle_update` | `vehicles.manage` | `p_vehicle_id, p_company_id, p_registration, p_joined_on, p_weekly_target, p_reason, p_now` | `W` | `reason_length`; `vehicle_registration_format`; `money_invalid`; `vehicle_joined_future`; `XC404` company; `vehicle_company_inactive`; `XC404` vehicle; `vehicle_retired_edit`; `vehicle_registration_change`; `vehicle_join_after_revenue` with `{registration, date}` (first recorded day earlier than the new `joined_on`) | company and `joined_on` updated; a differing target appends a revision effective `greatest(today, joined_on)`; an earlier `joined_on` backfills a revision at the old join date's amount (`SU-V6`); nothing changed -> `unchanged`; reason `Moved {reg} to {company}; changed when {reg} joined the fleet to {date}; changed the weekly target of {reg} to {CUR} {amount} from {date}` joined with `; `, first letter upper-cased, fallback `Changed vehicle {reg}` |
| `api.setup_company_options` | `vehicles.manage` | `p_now` | `jsonb` `[{id, name}]` visible, not archived, by `name, id` | | |
| `api.setup_vehicle_retire` | `vehicles.manage` | `p_vehicle_id, p_left_on, p_reason, p_now` | `W` | `reason_length`; `XC404`; `vehicle_leave_before_revenue` with `{registration, date}` (last record on or after `p_left_on`); `vehicle_leave_date_range`; `vehicle_leave_before_return`; same date -> `unchanged`; `vehicle_already_retired` | `left_on = p_left_on`; `Vehicle {reg} left the fleet on {date}` |
| `api.setup_vehicle_restore` | `vehicles.manage` | `p_vehicle_id, p_returned_on date (NULL = today), p_reason, p_now` | `W` | `reason_length`; `XC404` vehicle or its company not visible; `vehicle_company_archived_restore`; not retired -> `unchanged`; `vehicle_return_date_range` | clears `left_on`; when `returned_on > left_on` inserts the away period `[left_on, returned_on)`; `Vehicle {reg} returned to the fleet on {date}` plus `; it was away from {left_on} to {returned_on - 1}` when recorded |
| `api.setup_vehicle_report` | `vehicles.manage` | `p_vehicle_id, p_period text, p_from date, p_through date, p_now` | `jsonb` `VehicleReport` (`inv 3.5`: window, money in, target, postings by `setup.recurring_due_days`, buckets, totals): `{vehicle_id, from_date, through, money_in, target, repairs, charges, loans, money_out, net, savings, after_savings, costs, postings: [{item_id, version_id, day, name, kind, amount, bucket, source}]}`; `net` is `setup.vehicle_net`; `source` is null until petty-cash spending joins the report | `report_period_invalid` (the trimmed period is neither `week` nor `month`; a blank period counts as absent); `report_range_required`; `report_range_invalid`; `XC404` | |

Check orders follow the use-case flows of `docs/inventory/inventory-domain.md` section 4.3:
the typed reason and the name come before the record is loaded, and the all-companies 403 of
a company create comes after the name. Every write answers `api.write_result`: `created` and
`updated` carry the new settings version, `unchanged` the current one
(`setup.unchanged_result`). A scope refusal without detail is `XC403 permission_missing`.
Document keys are snake_case; the wire renames four of them (`http/schemas/setup.py`):
`from_date` is `from`, a posting's `day` and an investment entry's `invested_on` are `date`,
a scheduled item's `start_on` and `end_on` are `start` and `end`.

### 4.3 Scheduled expenses and savings (S24 to S29; rules `SU-R*`)

| Routine | Permission | Parameters | Returns | Raises (in order) | Logs |
|---|---|---|---|---|---|
| `api.setup_recurring_list` | `commitments.view`, after the filter checks | `p_page, p_page_size, p_kind text, p_company_id uuid, p_status text, p_now` | paged `recurring` documents (`inv 3.5`): the latest version per item; allocations limited to visible vehicles, `partial` when others exist, `amount` = sum of listed allocations, `active_amount` = the part on vehicles in the fleet; `bucket` 2 for a cost without one; filters on the current version: `p_kind` `cost`/`savings`, `p_company_id` a visible vehicle of that company among its shares, `p_status` `running`/`stopped` (running: not stopped and not ended on the business date, with a share on a visible vehicle in the fleet that day); null, empty or `all` keeps every item; order `running DESC, name, id` | `recurring_filter_kind_invalid`, `recurring_filter_status_invalid` (both before `enter_organization`, as .NET reads the filter before the request runs); `page_out_of_range` | |
| `api.setup_vehicle_options` | `commitments.manage` | `p_now` | `jsonb` `[{id, company_id, company_name, registration, active: true}]` visible, active today, company not archived, by registration | | |
| `api.setup_recurring_create` | `commitments.manage` | `p_name, p_kind, p_amount, p_frequency, p_day, p_last_day, p_start, p_end, p_allocations jsonb [{vehicle_id, amount}], p_expense_item_id, p_note, p_month, p_reason, p_now` | `W` (item id) | the nine steps of `inv 2.6` in order with the `recurring_*` codes: `reason_length`; `recurring_savings_item` / `recurring_item_not_in_use`; `recurring_schedule_shape`; definition checks (`recurring_name_length`, `money_invalid`, `recurring_kind_invalid`, `recurring_note_length`, `recurring_end_before_start`, `recurring_allocations_count`, `recurring_allocation_sum`); new-save rules (`recurring_daily_retired`, `recurring_savings_frequency`, `recurring_cost_needs_item`, `recurring_start_required`, `recurring_start_too_early`); `XC404` per allocation vehicle or its company; `recurring_share_inactive` | item + version 1 (`effective_from` = `start`, so a back-dated start posts from that day, as `RecurringItem.Create` does and the yearly-item report test expects) + allocations; `recurring`: `Added scheduled saving {name}` / `Added scheduled expense {name}` |
| `api.setup_recurring_revise` | `commitments.manage` | `p_item_id, ...the same fields..., p_now` | `W` (`unchanged` when nothing differs from the current version) | as create plus: `XC404` item; `XC403` (no detail) when a vehicle on the current version is not visible; `recurring_stopped_edit`; `recurring_running_start_change`; a vehicle already on the current version is exempt from `recurring_share_inactive`; `recurring_start_too_early` is waived when `p_start` equals the current version's start | appends the next revision; `Changed the {type, expense item or name, bucket, amount, schedule, start date, end date, vehicles, note} of {name}` (`tenancy.join_words`; fallback `Changed {name}`) |
| `api.setup_recurring_stop` | `commitments.manage` | `p_item_id, p_confirmed boolean, p_reason, p_now` | `W` | `reason_length` (required here); `recurring_stop_confirm`; `XC404`; `XC403` hidden allocation; stopped today -> `unchanged`; `recurring_stop_later_pending`; `recurring_already_stopped` | `stopped_from = today`; `Stopped {name} from {date}` plus the typed reason |
| `api.setup_recurring_cancel_stop` | `commitments.manage` | `p_item_id, p_now` | `W` | `XC404`; `XC403` hidden allocation; not stopped -> `unchanged`; `recurring_stop_in_effect` | clears `stopped_from`; `Cancelled the stop of {name}` |

Both saves call `setup.save_recurring`, which holds the nine steps and the writes once.
`p_kind`, `p_frequency`, `p_day` and `p_month` are `integer` (the wire integers);
`p_allocations` is a `jsonb` array of `{vehicle_id, amount}` whose amounts are text, so the
routine reads every digit sent. The allocations of a version carry no order, so the snapshot
lists them by vehicle id.

### 4.4 Change log (S30; rules `OS-20` to `OS-24`)

| Routine | Permission | Parameters | Returns | Raises |
|---|---|---|---|---|
| `api.history_list` | `audit.view` | `p_page, p_page_size, p_section, p_from date, p_to date, p_text, p_before bigint, p_include_total boolean, p_now` | `jsonb` `{items: [{version, section, entity_id, reason, occurred_at, actor_id, actor_name, before, after}], total (NULL when not asked), has_more, next_before}`; newest first by `version`; `p_before` seeks `version < p_before` and ignores the offset; `has_more` from fetching one extra row; `next_before` = the last returned version when `has_more` | `history_dates_order`; `history_text_length` (trimmed > 200); `history_before_invalid` (`p_before < 1`); `page_out_of_range` |

Filters: `section` exact; `from`/`to` as day bounds in the organization zone (`occurred_at
>= from at midnight`, `< to + 1 day at midnight`); `text` as `ILIKE '%' || escaped || '%'` on
the reason or on the actor's `first_name || ' ' || last_name`. Visibility is one predicate in
the `WHERE` clause of `api.history_list`, the only reader of the change log, over the
viewer's visible vehicles, companies and people computed once per call: `people` rows need `people.view` and, for a scoped viewer, a
person in `tenancy.people_visible`; an all-companies viewer sees every other section; a
scoped viewer sees `companies` rows for visible companies, `vehicles`/`investment`/`revenue`
rows whose `vehicle_id` is visible, `recurring` rows whose every allocation on the current
version is visible, every `expenses` row, and no settings section. `people` snapshots are
redacted for scoped viewers (`CompanyIds`, `VehicleIds` kept to the viewer's reach). The
total is a count over the same predicate in the same statement; no cache (section 7).

### 4.5 Expense catalog (S31 to S40; rules `SU-E*`)

| Routine | Permission | Parameters | Returns | Raises (in order) | Logs |
|---|---|---|---|---|---|
| `api.setup_expense_category_list` | any of `expenses.view`, `expenses.setup`, `commitments.view` | `p_page, p_page_size, p_now` | paged categories by `name, id`, each with `items` by `name, id`; `active` = not stopped as of today | `XC403`; `page_out_of_range` | |
| `api.setup_expense_item_options` | any of the three plus `commitments.manage` | `p_now` | `jsonb` items in use today in categories in use today, by category name, item name, item id | `XC403` | |
| `api.setup_expense_category_create` | `expenses.setup` | `p_name, p_bucket, p_now` | `W` | `expense_name_length`; `expense_bucket_invalid`; `expense_category_taken` (`normalized_name`, backstop `unique_violation`) | `expenses`: `Added expense category {name}` |
| `api.setup_expense_category_update` | `expenses.setup` | `p_category_id, p_name, p_bucket, p_now` | `W` (`unchanged`) | `expense_name_length`; `XC404`; `expense_category_taken`; `expense_bucket_invalid`; same name and bucket -> `unchanged` | `Renamed expense category {old} to {new}` / `Changed {name} to count as {label}` / `Renamed expense category {old} to {new}, counted as {label}` |
| `api.setup_expense_category_set_stopped` | `expenses.setup` | `p_category_id, p_stopped boolean, p_now` | `W` | `XC404`; stop: stopped today -> `unchanged`, stopped another day -> `expense_already_stopped`; restore: not stopped -> `unchanged` | `Turned off expense category {name}` / `Turned on expense category {name}` |
| `api.setup_expense_item_create` | `expenses.setup` | `p_category_id, p_name, p_now` | `W` (item id) | `XC404` category; `expense_name_length`; `expense_item_taken` | `Added expense item {name} under {category}` (a stopped category still accepts items) |
| `api.setup_expense_item_rename` | `expenses.setup` | `p_item_id, p_name, p_now` | `W` | `expense_name_length`; `XC404`; `expense_item_taken`; same name -> `unchanged` | `Renamed expense item {old} to {new}` |
| `api.setup_expense_item_set_stopped` | `expenses.setup` | `p_item_id, p_stopped boolean, p_now` | `W` | as for categories | `Turned off expense item {name}` / `Turned on expense item {name}` |

No typed reasons in this area; the snapshot is the category or item (section 6.2).

### 4.6 Investment (S41 to S44; rules `SU-I*`)

| Routine | Permission | Parameters | Returns | Raises (in order) | Logs |
|---|---|---|---|---|---|
| `api.setup_investment_get` | `invest.view` | `p_vehicle_id, p_now` | `jsonb` `{vehicle_id, total_invested, returned, percent_paid_off, entries: [{id, invested_on, description, amount, recorded_by (name or ""), recorded_at}]}`; `returned` = the vehicle report's `net` from `joined_on` through today; `percent_paid_off` = `round(returned / total_invested * 100)` half away from zero, `NULL` when nothing invested | `XC404` | |
| `api.setup_investment_create` | `invest.manage` | `p_vehicle_id, p_invested_on, p_description, p_amount, p_now` | `W` (entry id) | `XC404`; `investment_date_invalid`; `investment_description_length`; `money_invalid` | `investment` (entity = the vehicle, `vehicle_id` set): `Recorded investment {description} on {reg}` |
| `api.setup_investment_update` | `invest.manage` | `p_entry_id, p_invested_on, p_description, p_amount, p_now` | `W` (`unchanged`) | `XC404` (entry unknown or vehicle not visible); the three checks | `Changed investment {description} on {reg}` |
| `api.setup_investment_delete` | `invest.manage` | `p_entry_id, p_now` | `W` (`updated`) | `XC404` | hard delete; `Removed investment {description} on {reg}`; `after` is the string `null` (`SU-I4`) |

### 4.7 Revenue (R01 to R03; rules `RV-*`)

Since `0011_revenue` (07b D4) section 10.5 changes these rows, and where the two differ
section 10.5 holds. R01 takes `p_q`, and R02 is gated by `dash.net` and `dash.gaps`. R03
takes `p_captured_at` and checks the low-day threshold after the identical replay. It asks
`revenue.correct` for every saved record, today's included, and runs
`tenancy.check_writable` after the permission check. `revenue_no_earnings_permission` and
`revenue_other_needs_note` are retired.

| Routine | Permission | Parameters | Returns | Raises (in order) |
|---|---|---|---|---|
| `api.revenue_week_get` | `revenue.view` | `p_week_start date, p_company_id uuid, p_vehicle_id uuid, p_page integer, p_page_size integer, p_now` | `jsonb` `RevenueWeekDto` (`inv 3.6`) plus `page_number`, `page_size`, `total_vehicles`, `truncated`, `day_totals` (seven sums over the whole grid) and `first_gap` (the earliest day still needing capture over the whole grid: a vehicle's earliest missing day, or the business date while it has no record; the first vehicle in grid order on a tie; not permission-gated): the week containing `p_week_start` (or today); vehicles = visible, optionally by company, in the fleet on some day of the week, by registration; with `p_vehicle_id` exactly that vehicle for any week and never paged; without `p_page`/`p_page_size` the first 500 vehicles with `truncated`; `day_totals` and `first_gap` over the whole filtered grid; `companies` = visible companies not archived today or with a visible vehicle running that week | `XC403` (membership, `revenue.view`); `page_out_of_range` (only when paged); `revenue_week_range` (after the current week or earlier than it minus 3650 days); `XC404` for an invisible or unknown `p_vehicle_id` (a visible vehicle of another company than `p_company_id` gives an empty grid) |
| `api.revenue_dashboard_get` | any of `dash.capture`, `dash.revenue`, `dash.gaps`, `dash.edits` | `p_period text (today/week/month; NULL = week), p_company_id uuid, p_now` | `jsonb` `{period, from, through, business_date, revenue, expected, percent, captured_today, vehicles_today, missing_days, missing_vehicles, edited_records}` with each card `NULL` unless the actor holds its permission; one aggregating query over visible vehicles and their active days in `[from, today]` (`inv 2.10` R02 maths) | `XC403`; `dashboard_period_invalid` |
| `api.revenue_capture` | member, then `require_any_permission('{revenue.capture, revenue.correct}')` | `p_vehicle_id, p_day date, p_amount numeric, p_reason text, p_note text, p_expected_version bigint, p_now` | `W` (`created`, `updated`, `replayed`) | the steps of `inv 2.10` R03 in order, after membership and one of the two permissions: 1 entry shape (`revenue_reason_invalid`, `money_invalid`, `revenue_amount_with_reason`, `revenue_entry_required`, `revenue_other_needs_note`, `revenue_note_length`, `revenue_note_without_other`); 2 `XC404`, the vehicle row read `FOR SHARE` (a retirement or join-date change in flight locks it `FOR UPDATE` and then looks for revenue it would strand: it commits first and this capture reads its result, or it waits for this capture and sees the record); 3 lock the day's record (`FOR UPDATE NOWAIT`; held by another open save -> `revenue_concurrent_save`); 4 identical replay -> `replayed` with the stored id and version, no write, whatever the version, the date and the permissions; 5 `revenue_future_date` (also `0001-01-01`); 6 `revenue_vehicle_away` / `revenue_vehicle_inactive`; 7 `revenue_no_earnings_permission`, `revenue_capture_permission`, `revenue_correct_permission` (403 before any disclosure, never `current`); 8 `revenue_version_conflict` with `DETAIL.current` = `revenue.cell(...)` when a record exists and `p_expected_version` is `NULL` or differs; 9 removed by 9276c51 (days are captured in any order); 10 insert (`version 1`) or update (`version + 1`, `corrected_after_date` when the day is before today; the lock of step 3 keeps the version read until here), `unique_violation` on the natural key (a first capture racing another) -> `unique_conflict`; 11 `tenancy.record_change` (`revenue`, entity = record, `vehicle_id`, `Recorded revenue for {reg} on {d MMM yyyy}` / `Recorded no revenue for {reg} on {day}: {label}` / `Corrected revenue for ...` / `Updated revenue for ...`; audit `revenue.recorded`) |

### 4.8 Organization settings, logo, appearance, preferences (O01 to O07; rules `OS-*`)

| Routine | Permission | Parameters | Returns | Raises (in order) | Logs |
|---|---|---|---|---|---|
| `api.organization_settings_get` | `organization.manage` | `p_now` | `jsonb` `{organization: {id, slug, name, business_date, settings_version}, localization, branding, security_policy, effective_business_date, calendar_date, effective: {formats, branding, security_policy, theme_mode, reduced_motion, font_scale}}`; sections are the stored rows with `organization_id`; the policy in `effective` is clamped | | |
| `api.organization_settings_set` | `organization.manage` | `p_section text, p_value jsonb, p_reason text, p_expected_version bigint, p_now` | `W` (`unchanged` when the merged section equals the stored one) | `reason_length` (first, as `OS-10`); `XC404` for an unknown section; `organization`: `organization_name_slug`, `organization_slug_taken` (`XC409`, from the `unique_violation` of the slug index: other organizations' rows are invisible under row-level security, so there is no own check); `localization`/`branding`/`security_policy`: `settings_not_object`, `settings_wrong_type` (a value of the wrong JSON type), then the validation codes of `docs/06-http-contract.md` section 3 (`locale_invalid`, `time_zone_invalid`, `format_settings_invalid`, `brand_*`, `security_policy_pin_sign_in`, `security_policy_invalid`), then for localization `settings_business_date_future_zone`; `business_date`: `business_date_invalid`, `business_date_future`; `version_conflict` when `p_expected_version` is not `NULL` and differs from `settings_version` | the section's snapshot before and after (camelCase keys, `tenancy.settings_snapshot`); reason `Changed the {setting} to {value}` joined by `tenancy.join_words`, or `Set the business date to {date}` / `Returned the business date to the calendar` (section 6.1); audit `organization.settings.updated` |
| `api.organization_logo_set` | `organization.manage` | `p_content_type text, p_data bytea, p_reason, p_now` | `W` | `reason_length`; `logo_type`, `logo_too_large`, `logo_signature` (the service decodes the data URL first, `LogoUpload.parse`: longer than 349 592 characters `logo_too_large`, not the data-URL shape `logo_type`, undecodable base64 `logo_unreadable`; the routine checks type, size and signature again) | upsert; `logo`: `Uploaded a new logo`; snapshot `{content_type, bytes, updated_at}` |
| `api.organization_logo_delete` | `organization.manage` | `p_reason, p_now` | `W` (`unchanged` when no logo, nothing logged) | `reason_length` | delete; `Removed the logo`; `after` is `"null"` |
| `api.organization_appearance_get` | member | `p_now` | `jsonb` `{organization_name, settings_version, business_date, branding: {display_name, logo_alt, primary, secondary, accent, logo (data URL text or NULL)}, formats (effective, incl. direction), theme_mode, reduced_motion, font_scale, lockout_threshold, lockout_minutes}` with the effective-value rules of `inv 3.7` | the stored rows are validated on read: a stored value that no longer passes raises its `XC422` code (parity: the .NET read answered 400) | |
| `api.preferences_get` | member | `p_now` | `jsonb` `PreferencesResponse` (`inv 2.11` O06: disallowed overrides served as `NULL`, plus the four allow flags and `organization: {locale, time_zone, hour12}`) | | |
| `api.preferences_set` | member | `p_locale, p_time_zone, p_hour12 boolean, p_theme_mode, p_reduced_motion boolean, p_font_scale double precision, p_now` | `jsonb` the saved row (`organization_id, user_id, locale, time_zone, hour12, theme_mode, reduced_motion, font_scale`) | `locale_invalid`; `time_zone_invalid`; `preferences_accessibility` (theme mode outside `light`/`dark`/`system`/`NULL`, or `font_scale` not finite or outside 1..3); then `preferences_locale_not_allowed`, `preferences_time_zone_not_allowed`, `preferences_hour12_not_allowed`, `preferences_theme_not_allowed` for non-null values the organization disallows | none (no change log, no version bump) |

Section merge (`O02`): the routine reads the stored row as `jsonb`, overlays `p_value`
(top-level keys only; `organization_id` ignored; unknown keys ignored; the legacy key
`use_groupping` accepted for `use_grouping`, current key winning), casts to the row type
(a cast failure is `settings_wrong_type`), validates, and compares the `json::text`
snapshots before and after: equal means `unchanged`. A localization change also runs
`tenancy.check_time_zone` and, when a business date is held, the future-in-zone check.

### 4.9 Petty cash (P01 to P13; rules `PC-1` to `PC-33` of `docs/inventory/inventory-petty-cash.md` as changed by `docs/15-design-v2-3.md` B19)

The .NET rules hold except where B19 and its decisions (DEC-21 to DEC-29) change them; the
rule ids below name the inventory rule and the B19 rule that changed it. Words used here:
an **expense** has a status (waiting, approved, rejected); a waiting expense with a
`sent_back_note` is **sent back**; **cash** and **credit notes** have no status (DEC-22);
the **effect** of an entry on its float is `+total` for cash, `-total` for a credit note,
`-total` for an expense that is not rejected, 0 for a rejected one.

Helpers in schema `pettycash` (`db/routines/55_pettycash/`):

| Helper | Signature | Behaviour |
|---|---|---|
| `pettycash.kind_code` | `(p_word text) RETURNS smallint` | the code of a kind's wire word (`cash` 1, `expense` 2, `credit` 3), compared exactly after trimming; null for anything else |
| `pettycash.status_word` | `(p_status smallint, p_sent_back_note text) RETURNS text` | `waiting`, `sentBack` (a waiting expense with a `sent_back_note`), `approved`, `rejected`; null for cash and credit notes |
| `pettycash.member_name` | `(p_user_id uuid) RETURNS text` | the member's first and last name, trimmed; null when the organization has no such member |
| `pettycash.is_holder` | `(p_user_id uuid) RETURNS boolean` | an active membership of the current organization whose `tenancy.effective_permissions` hold `pettycash.spend` (`PC-9`) |
| `pettycash.holders` | `() RETURNS TABLE (user_id uuid, name text, active boolean)` | active holders plus anyone with a non-removed entry (`active = false`), ordered by `upper(name)` under `COLLATE "C"` (ordinal ignoring case, as .NET's `OrdinalIgnoreCase`), then id (`PC-9`) |
| `pettycash.visible_holders` | `(p_view_all boolean) RETURNS TABLE (user_id uuid, name text, active boolean)` | `pettycash.holders` with `pettycash.view_all`; else the actor's own row when the actor has one; else none (`PC-18`) |
| `pettycash.entry_visible` | `(p_entry pettycash.entries, p_view_all boolean, p_vehicles uuid[]) RETURNS boolean` | `PC-17`: not removed and (holder is the actor, or `p_view_all` and (no vehicle, or the vehicle among `p_vehicles`, the actor's `setup.visible_vehicles`)) |
| `pettycash.visible_entry` | `(p_entry_id uuid, p_view_all boolean, p_vehicles uuid[], p_lock boolean) RETURNS pettycash.entries` | the entry when `entry_visible`, else `XC404 not_found` (missing, removed or out of view); with `p_lock` the float is locked first (`lock_float`) and the row then read `FOR UPDATE NOWAIT`, a row another save holds being `XC409 pettycash_concurrent_save` |
| `pettycash.effect` | `(p_kind smallint, p_status smallint, p_total numeric) RETURNS numeric` | the effect above (DN-B19-11) |
| `pettycash.balance` | `(p_holder_id uuid) RETURNS numeric` | sum of the effects of the holder's non-removed entries, visible or not (`PC-4`, DN-B19-11) |
| `pettycash.lock_float` | `(p_holder_id uuid) RETURNS void` | `SELECT ... FROM tenancy.memberships ... FOR NO KEY UPDATE` on the holder's membership: every write takes it before it reads a balance, so two writes on one float run one after the other (the .NET retry on the change-log version, `PC-24`). `NO KEY UPDATE` does not block the change log's foreign-key `KEY SHARE` (`docs/14` D3) |
| `pettycash.authorize_change` | `(p_entry pettycash.entries, p_permissions text[]) RETURNS void` | approved or rejected `pettycash_change_decided`; own float without `edit_own` or `edit` `pettycash_change_own_permission`; another float without `edit` `pettycash_change_other_permission` |
| `pettycash.authorize_remove` | `(p_entry pettycash.entries, p_permissions text[], p_reason text) RETURNS void` | the remove step below: the permission refusals, then a missing reason for cash, a credit note or an approved expense `reason_length` |
| `pettycash.authorize_review` | `(p_entry pettycash.entries, p_limit numeric) RETURNS void` | cash `pettycash_cash_not_reviewed`, credit `pettycash_credit_not_reviewed`, own float `pettycash_own_float_review`, own entry `pettycash_own_entry_review`, over the limit (null is none) `pettycash_above_limit` |
| `pettycash.flags` | `(p_entry pettycash.entries, p_permissions text[], p_limit numeric, p_earliest date) RETURNS jsonb` | `{can_edit, can_remove, can_review, above_limit, can_send_back, can_reject, can_reopen}`: the actor's actions on the row as the three `authorize_*` helpers decide them (DN-B19-3 to DN-B19-9), edit, remove and reopen also false on a row dated before `p_earliest` (DN-B19-12); `can_review` = may approve it now |
| `pettycash.check_line` | `(p_kind smallint, p_date date, p_unit_amount numeric, p_units numeric, p_vehicle_id uuid, p_expense_item_id uuid, p_payee text, p_note text, p_reimbursable boolean) RETURNS void` | the fifteen line checks of `inventory-petty-cash.md` section 2.3 (checks 14 and 16 are gone: DN-B19-10), in that order, codes `pettycash_kind_invalid` and `pettycash_line_*`; the caller trims the texts first, blank is null |
| `pettycash.check_date` | `(p_date date, p_today date) RETURNS void` | `pettycash_future_date`, `pettycash_too_old` (`PC-10`) |
| `pettycash.check_period` | `(p_from date, p_to date, p_today date) RETURNS void` | `PC-21` periods: `pettycash_range_both`, `history_dates_order`, `pettycash_range_length` (367 days), `pettycash_range_start`, `pettycash_too_old`; a week is `revenue.week_start` (the organization's first day of week) to six days later |
| `pettycash.check_expense` | `(p_vehicle_id uuid, p_expense_item_id uuid, p_date date, p_check_vehicle boolean, p_check_item boolean) RETURNS void` | `PC-11`: vehicle in the actor's scope (`pettycash_vehicle_scope`), in the fleet on the date (`pettycash_vehicle_inactive`), item in use on the date (`pettycash_item_inactive`); on a change only what changed is checked, the date counting as a change of both; the vehicle, the item and its category are read `FOR SHARE` (section 1.5: a retirement, away period or stop in flight holds them `FOR UPDATE`, so it commits before the check or waits for the save) |
| `pettycash.check_version` | `(p_entry pettycash.entries, p_expected bigint, p_permissions text[], p_limit numeric, p_earliest date) RETURNS void` | a null or different `p_expected` is `XC409 pettycash_entry_changed` with `DETAIL.current` = the entry's `entry_document` |
| `pettycash.guard_float` | `(p_holder_id uuid, p_kind smallint, p_delta numeric) RETURNS void` | `PC-12`: cash only, `p_delta < 0`, balance after below zero, no `pettycash.issue_negative` -> `XC422 pettycash_below_zero` with `DETAIL {"balance_after": ...}`; called after `lock_float` |
| `pettycash.tallies` | `(p_holder_ids uuid[], p_from date, p_to date, p_view_all boolean, p_vehicles uuid[]) RETURNS TABLE (holder_id uuid, kind smallint, status smallint, sent_back boolean, window_position smallint, total numeric, entries integer, latest date)` | `PC-19`, `PC-20` over the entries the actor may see (`entry_visible`); `window_position` 0 before the days, 1 within, 2 after |
| `pettycash.entry_snapshot` | `(p_entry pettycash.entries) RETURNS json` | the PascalCase keys of `PC-25` with `RejectReason` and `ReopenReason` after `SentBackNote`; `Kind` and `Status` as names (`Cash`, `Expense`, `Credit`; `Waiting`, `Approved`, `Rejected`, null) |
| `pettycash.describe` | `(p_entry pettycash.entries) RETURNS text` | the subjects of `PC-26`; a credit note reads `{holder}'s petty cash credit note paying {payee}`, else `{holder}'s petty cash credit note, {note}`, else `{holder}'s petty cash credit note` |
| `pettycash.entry_document` | `(p_entry pettycash.entries, p_permissions text[], p_limit numeric, p_earliest date) RETURNS jsonb` | one `PettyCashEntryDto` (`docs/06` 2.11) with names, `bucket`, and `pettycash.flags` |
| `pettycash.log` | `(p_entry_id uuid, p_before json, p_verb text, p_typed text, p_action text, p_now timestamptz) RETURNS void` | read after the write: `tenancy.record_change(section 'pettycash', entity = entry id, vehicle_id = the entry's, before, after = the snapshot now, reason = tenancy.compose_reason('{p_verb} {subject}', p_typed))` and one audit row `pettycash.<p_action>` (question 25) |
| `pettycash.saved` | `(p_entry_id uuid, p_outcome text) RETURNS jsonb` | the answer of an entry write: `{id, version, status (word), balance (the float to date), outcome}` (`created`, `saved`, `replayed`) |
| `pettycash.vehicle_postings` | `(p_vehicle_id uuid, p_window daterange) RETURNS TABLE (item_id uuid, version_id uuid, day date, name text, kind smallint, amount numeric, bucket smallint)` | `PC-31`: one cost per approved, non-removed expense on the vehicle dated in the window, the entry id as item and version, the item's name, the bucket of its category (2, charges, when it has none, as `setup.vehicle_postings` serves a scheduled cost); the shape of `setup.vehicle_postings` |

Routines: each begins with `tenancy.enter_organization(..., NULL)` and then
`tenancy.require_any_permission` with its gate. Writes lock in this order: the float(s)
(`lock_float`, several in id order), then the entry rows `FOR UPDATE` (several in id order),
then the `FOR SHARE` reads of `check_expense` (the vehicle, the item and its category; on a
create too, so no write holds a vehicle or item share while it waits for a float), then
whatever `tenancy.record_change` takes. `p_now` is the request instant; the business
date `today` comes from it. `earliest` is `tenancy.earliest_writable(organization, actor, today)`
(section 10.2), read once per request.

| Routine | Gate (any of) | Parameters | Returns | Steps, in order (the first refusal answers) | Logs |
|---|---|---|---|---|---|
| `api.pettycash_overview_get` | `pettycash.view` | `p_date date, p_period text, p_holder_id uuid, p_from date, p_to date, p_now` | `jsonb` `PettyCashOverviewDto` | with `p_from` or `p_to`: `check_period`, else `check_date(p_date or today)` and `pettycash_period_invalid`; holder not visible `XC404` | |
| `api.pettycash_entry_list` | `pettycash.view` | `p_from date, p_to date, p_holder_id uuid, p_kinds text[], p_statuses text[], p_q text, p_page, p_page_size, p_now` | paged `PettyCashEntryDto` documents, order `entry_date, kind, id` | `page_out_of_range`; `history_dates_order`; `history_text_length` (200); `pettycash_kind_invalid`; `pettycash_status_invalid` (`waiting`, `approved`, `sentBack`, `rejected`); `XC404` holder | |
| `api.pettycash_options_get` | `spend`, `spend_other`, `edit_own`, `edit`, `issue`, `credit` | `p_date date, p_now` | `jsonb` `{vehicles, items, holders}` | `check_date`; vehicles visible and in the fleet on the date and items in use on it, for the four expense rights; holders (active only) for `spend_other`, `issue`, `credit` (`PC-30`) | |
| `api.pettycash_dashboard_get` | `dash.pettycash` | `p_now` | `jsonb` `{float, approvals}` | the float card when the actor holds `pettycash.spend`, the approvals card when they hold `pettycash.approve_item`, each null otherwise (DEC-25; `PC-22` with "waiting" meaning not sent back) | |
| `api.pettycash_entry_create` | `spend`, `spend_other`, `issue`, `credit` | `p_id uuid (nullable), p_kind text, p_date, p_unit_amount, p_holder_id, p_vehicle_id, p_expense_item_id, p_units, p_payee, p_note, p_reimbursable, p_now` | `jsonb` `{id, version, status, balance, outcome}` | 1 `check_line`; 2 `p_id` known: another actor's entry `pettycash_already_saved` (`XC409`, `DETAIL.current = null`), the actor's own `outcome = replayed` (body not read, `PC-15`); 3 holder (below); 4 `check_date`; 5 `tenancy.check_writable(date)`; 6 `lock_float`; 7 `check_expense`; 8 `guard_float(effect)`; 9 insert (expense `waiting`) | `Recorded {subject}`; `vehicle_id` for expenses; audit `pettycash.created` |
| `api.pettycash_entry_update` | `edit_own`, `edit` | `p_entry_id, ...the create fields without p_id..., p_expected_version, p_now` | as create | 1 `check_line`; 2 not visible `XC404`; 3 `pettycash_kind_change`; 4 `pettycash_holder_change`; 5 cash or credit `pettycash_change_cash` (DEC-23); 6 replay: the line matches and not sent back -> `replayed` (`PC-16`); 7 `authorize_change`: approved or rejected `pettycash_change_decided`, own float without `edit_own` or `edit` `pettycash_change_own_permission`, another float without `edit` `pettycash_change_other_permission`; 8 `check_date` when the date changed; 9 `check_writable` on the stored date and on the new one; 10 version `pettycash_entry_changed` (`XC409`, `DETAIL.current` = the document; also when `p_expected_version` is null); 11 `check_expense` for what changed; 12 apply: still waiting, `sent_back_note` and review cleared, `version + 1` | `Changed {subject}` (read after); audit `pettycash.changed` |
| `api.pettycash_entry_approve` | `approve_item` | `p_entry_id, p_expected_version, p_now` | as create | 1 `XC404`; 2 replay: approved by the actor -> `replayed`; 3 `authorize_review`: cash `pettycash_cash_not_reviewed`, credit `pettycash_credit_not_reviewed`, own float `pettycash_own_float_review`, own entry `pettycash_own_entry_review`, over the limit `pettycash_above_limit`; 4 version; 5 not waiting `pettycash_not_waiting`; sent back `pettycash_sent_back` | `Approved {subject}`; audit `pettycash.approved` |
| `api.pettycash_entries_approve` | `approve_item` | `p_entries jsonb` (`[{id, version}]`), `p_now` | `jsonb` `{approved, total, skipped}` | `pettycash_approve_none`; `pettycash_approve_many` (over 100); duplicates by id dropped (the first kept); then per entry in the order sent: `XC404`; approved -> skipped; `authorize_review`; version (`pettycash_entry_changed` with that entry's `current`); not waiting, sent back; only then any is approved (`PC-33`) | one change-log and one audit row per approved entry |
| `api.pettycash_entry_send_back` | `send_back` | `p_entry_id, p_expected_version, p_comment, p_now` | as create | 1 `XC404`; 2 replay: sent back by the actor with the same trimmed comment -> `replayed`; 3 `authorize_review`; 4 version; 5 not waiting `pettycash_not_waiting`; already sent back `pettycash_already_sent_back`; 6 `pettycash_comment_required`; `pettycash_comment_length` (200) | `Sent back {subject}. Reason: {comment}.`; audit `pettycash.sent_back` |
| `api.pettycash_entry_reject` | `reject` | `p_entry_id, p_expected_version, p_reason, p_now` | as create | 1 `XC404`; 2 replay: rejected by the actor with the same trimmed reason -> `replayed`; 3 `authorize_review`; 4 version; 5 not waiting `pettycash_not_waiting`; 6 `pettycash_reject_reason_required`; `pettycash_decision_reason_length` (200); then status rejected, `reject_reason`, review set, `sent_back_note` cleared | `Rejected {subject}. Reason: {reason}.`; audit `pettycash.rejected` |
| `api.pettycash_entry_reopen` | `reopen` | `p_entry_id, p_expected_version, p_reason, p_now` | as create | 1 `XC404`; 2 `check_writable` on the entry's date; 3 version; 4 not approved or rejected (cash and credit notes included) `pettycash_not_decided`; 5 `pettycash_reopen_reason_required`; `pettycash_decision_reason_length`; then waiting, review, `reject_reason` and `sent_back_note` cleared, `reopen_reason` set | `Reopened {subject}. Reason: {reason}.`; audit `pettycash.reopened` |
| `api.pettycash_entry_remove` | `delete_own`, `delete`, `delete_approved`, `delete_cash` | `p_entry_id, p_expected_version, p_reason, p_now` | as create (the last status, the balance after) | 1 reason over 500 `reason_length` (before the entry is read); 2 `XC404` (`visible_entry` with the float locked); 3 `authorize_remove`: cash or credit without `delete_cash` `pettycash_delete_cash_permission`, rejected `pettycash_delete_rejected`, approved without `delete_approved` `pettycash_delete_approved_permission`, waiting on one's own float without `delete_own` or `delete` `pettycash_delete_own_permission`, on another float without `delete` `pettycash_delete_other_permission`; then a missing reason for cash, a credit note or an approved expense `reason_length`; 4 `check_writable` on the entry's date; 5 version; 6 `guard_float(-effect)`; 7 soft removal | `Removed {subject}. Reason: {reason}.`, or `Removed {subject}` without one (DEC-28); audit `pettycash.removed` |
| `api.pettycash_day_approve` | `approve_day` | `p_date date, p_to date, p_holder_id uuid, p_now` | `jsonb` `{approved, total, skipped}` | without `p_to` `check_date(p_date)`, with it `check_period(p_date, p_to)`; holder not visible `XC404`; the waiting, not sent back, visible expenses of the chosen floats in the days are locked; those the actor may approve (`authorize_review` passes) are approved; `skipped` = the rest (`PC-23`) | one change-log and one audit row per approved entry |

The holder step of create (DN-B19-2, DN-B19-10, `PC-8`): an expense with no `holderId` or
the actor's own needs `pettycash.spend` (`pettycash_spend_permission`); with another
`holderId` it needs `pettycash.spend_other` and an active holder
(`pettycash_holder_not_holder`), and without `spend_other` the answer is
`pettycash_own_float_only` when the actor holds `spend`, else `pettycash_spend_permission`.
A credit note needs `pettycash.credit` (`pettycash_credit_permission`) and goes to
`holderId`, or to the actor when it is absent, which must be an active holder
(`pettycash_holder_not_holder`). Cash needs `pettycash.issue` (`pettycash_cash_permission`),
a `holderId` (`pettycash_holder_required`) and an active holder.

The `XC409` with `current` and the `XC422 pettycash_below_zero` with `balance_after` carry
their extension members in `DETAIL`; `http/errors.py` renders them as `current` and
`balanceAfter`. A save that finds the entry row held by another (`visible_entry` reads it
`FOR UPDATE NOWAIT` after the float lock) answers `pettycash_concurrent_save`; the float
locks make it a backstop. Approved expenses post into the
vehicle report through `setup.vehicle_net` and `api.setup_vehicle_report` (`PC-31`: one
posting per approved, non-removed expense in the window and inside the vehicle's own days,
`source = pettycash`, bucket from the item's category; rejected and reopened ones do not).
The visibility predicate of `api.history_list` (section 4.4) lets `pettycash` rows through
for a scoped viewer only when their `vehicle_id` is in scope (`PC-32`). The only routine that
takes a client-chosen id is `api.pettycash_entry_create` (`docs/04` 6.2).

## 5. Operator and meta routines

| Routine | Caller | Parameters | Returns | Raises | Writes |
|---|---|---|---|---|---|
| `api.meta_contract_version` | startup check, readiness, CLI | none | `integer` | | none |
| `api.rate_limit_hit` | service (`PostgresRateLimiter`) | `p_key text, p_limit integer, p_window_seconds integer, p_now` | `(allowed boolean, remaining integer, retry_after_seconds integer)` | `XC422` on bad bounds | `ops.rate_limit_windows` upsert, old windows deleted (`docs/prompts/01-bootstrap-db.md` D3) |
| `api.ops_record_operator_action` | CLI commands without another routine | `p_operator, p_action, p_target, p_detail jsonb, p_now` | `void` | | `ops.operator_actions` (through the `ops.record_operator_action` helper) |
| `api.ops_provision_user` | `xcode-api provision-user` | `p_operator, p_request_id, p_email, p_phone, p_role, p_first_name, p_last_name, p_organization_name, p_now` | `jsonb` `{user_id, organization_id, created_user, created_organization, reactivated}` | `XC422 people_email_invalid` (`local@domain`, 320 at most), `people_phone_invalid`, `people_role_unknown` (a catalog name in any case, stored as the catalog spells it, as .NET's `OrdinalIgnoreCase` lookup), `people_names_required` (a name over 100), `organization_name_slug` (a name over 200); `XC409 organization_not_single` when more than one organization exists; `XC409 people_contact_taken` when the phone belongs to another user | finds or creates the organization (`organization_ids`, `enter_organization_as_operator`, `seed_roles`, default localization, branding and policy rows; name `My fleet` and slug `my-fleet` unless named), the user (no PIN) and an active membership (names from the options, else the email's `first.last` local part title-cased, defaults `New` / `Member`) with the role (option, else the existing link, else `Owner`) and an all-companies scope for `Owner` and `Office admin` when they have none; reactivates a removed user; an existing user whose phone, status, membership or role changed gets `security_version + 1` and every device and token revoked; `operator_actions` row. No `tenancy.audit_events` row: that table's actor must be a member, and the operator's trail is `ops.operator_actions` |
| `api.ops_remove_user` | `xcode-api remove-user` | `p_operator, p_request_id, p_email, p_now` | `jsonb` `{user_id, removed, tokens}` | `XC404 not_found` | user `removed` and `security_version + 1` (only when it was active), every refresh token revoked; devices and membership untouched (`docs/07-auth.md` sections 6 and 9, parity); `operator_actions` row |
| `api.ops_clear_pause` | `xcode-api clear-pause` | `p_operator, p_request_id, p_email, p_now` | `jsonb` `{user_id, was_paused}` | `XC404 not_found` | clears `paused_until` and `failed_attempts`; never `untrusted_failed_attempts` (`ClearLockout` parity); `operator_actions` row |
| `api.ops_revoke_sessions` | `xcode-api revoke-sessions` | `p_operator, p_request_id, p_email, p_now` | `jsonb` `{user_id, devices, tokens}` | `XC404 not_found` | `security_version + 1`, revoke every device and token; `operator_actions` row |
| `api.meta_unassigned_user_count` | startup summary (as `xcode_app`) | none | `integer` (active users without an active membership, through `identity.active_organization`) | | none |
| `api.ops_account_state` | `xcode-api account-state` | `p_operator, p_request_id, p_email, p_now` | `jsonb` `{user_id, status, has_pin, paused_until, failed_attempts, untrusted_failed_attempts, trusted_devices, live_refresh_tokens, active_membership}` (never a hash or digest) | `XC404 not_found` | `operator_actions` row |
| `api.ops_seed_demo` | `xcode-api seed-demo` and, in development, `XCODE_DEMO_SEED` at startup (the CLI and the settings refuse elsewhere first) | `p_operator, p_request_id, p_environment, p_pins jsonb, p_now` (`p_pins`: email to PIN hash, made in Python like every PIN hash) | `jsonb` `{organization_id, created}` | `XC403 seed_development_only` (`p_environment` is not `development`), `XC409 organization_not_single`, `XC409 seed_exists` (the one organization is not `demo-fleet`: a database holding other data is never seeded) | the demo organization `Demo Fleet` (`demo-fleet`) with default rows and roles, the four .NET logins (`db/seeds/README.md`; a PIN hash only on an account this run creates, a removed login revived), the 13-item catalogue when there is none, and, when there is no vehicle, six weeks of history written day by day through the `api.*` business routines as the demo people at instants counted back from `p_now` (companies, vehicles with dated targets and an away period, scheduled items of every frequency a new item can have, investments, revenue with gaps, no-earnings and low-day reasons and corrections, petty cash in every entry state), so `tenancy.record_change` writes a realistic change log; idempotent (a second run answers `created: false` and adds nothing); `operator_actions` row. One call takes seconds, past `xcode_operator`'s 5 s `statement_timeout`, so the gateway runs it with `SET LOCAL statement_timeout = '120s'` (`OpsRoutines.seed_demo`) |

The CLI connects as `xcode_operator` for the `api.ops_*` calls (`XCODE_DATABASE_OPERATOR_URL`)
and prints only ids and counts; no personal data is echoed.

Helper (schema `ops`, never granted to `xcode_app` or `xcode_operator`; `EXECUTE` granted to
`xcode_api_executor` only):

| Helper | Signature | Behaviour |
|---|---|---|
| `ops.record_operator_action` | `(p_operator text, p_action text, p_target text, p_detail jsonb, p_now timestamptz) RETURNS void`, `SECURITY INVOKER` | appends one `ops.operator_actions` row; called by every `api.ops_*` routine so the audit write is in one place; the runner records `migrate`/`routines`/`down` with a direct insert |
| `ops.seed_demo_user` | `(p_organization_id uuid, p_owner_id uuid, p_request_id text, p_email text, p_phone text, p_role text, p_company_id uuid, p_pin_hash text, p_at timestamptz) RETURNS uuid` | one demo login, added only when missing: the Owner by plain rows (no actor exists yet), everyone else through `api.people_create` as the Owner; the PIN hash only on an account this call created; a removed account is revived with its sessions ended |
| `ops.seed_catalogue` | `(p_organization_id uuid, p_owner_id uuid, p_request_id text, p_at timestamptz) RETURNS void` | the three main categories (found by name when one exists), a category under each and 13 items, through the setup routines |
| `ops.seed_companies` | `(p_organization_id uuid, p_owner_id uuid, p_request_id text, p_at timestamptz) RETURNS uuid[]` | the two demo companies, found by name or added through `api.setup_company_create` |
| `ops.seed_vehicle_plan` | `() RETURNS TABLE (idx integer, registration text, fleet_number text, company_index integer, joined_days_back integer, day_targets numeric[], initial_investment numeric)` | the six demo vehicles |
| `ops.seed_fleet` | `(p_organization_id uuid, p_owner_id uuid, p_request_id text, p_company_ids uuid[], p_now timestamptz) RETURNS void` | the day loop from 42 days back to yesterday: each day's setup events, revenue and petty cash at that day's instant |
| `ops.seed_fleet_setup` | `(p_organization_id uuid, p_owner_id uuid, p_request_id text, p_company_ids uuid[], p_days_back integer, p_day date, p_at timestamptz) RETURNS void` | one day's setup events through the setup routines; resets the deferred allocation check after each scheduled item (`api.setup_recurring_create` leaves it `IMMEDIATE` for the transaction) |
| `ops.seed_revenue_day` | `(p_organization_id uuid, p_owner_id uuid, p_request_id text, p_days_back integer, p_day date, p_at timestamptz) RETURNS void` | one day's captures through `api.revenue_capture` by the demo clerk and fleet manager, with gaps, reasons and the Owner's corrections |
| `ops.seed_pettycash_day` | `(p_organization_id uuid, p_owner_id uuid, p_request_id text, p_days_back integer, p_day date, p_at timestamptz) RETURNS void` | one day's petty-cash events through the petty-cash routines, so every entry state exists |

## 6. Reasons, snapshots and formatting

### 6.1 Automatic reasons

| Helper | Rule |
|---|---|
| `tenancy.fmt_money(numeric)` | `to_char(amount, 'FM999,999,999,999,990')` when `amount = trunc(amount)`, else `to_char(amount, 'FM999,999,999,999,990.00')` (.NET `#,##0` / `#,##0.00`, invariant culture); used with the organization currency code as `{CUR} {amount}` |
| `tenancy.fmt_day(date)` | `to_char(day, 'FMDD Mon YYYY')` (.NET `d MMM yyyy`, invariant month abbreviations, no zero padding): `8 Oct 2026`; used by revenue reasons |
| `tenancy.fmt_iso(date)` | `to_char(day, 'YYYY-MM-DD')`; used by every other reason that names a date |
| `tenancy.setting_word(key)` | the fixed map of `inv 3.9` (`name` -> `the organization name`, `hour12` -> `the 12-hour clock`, `use_grouping` -> `digit grouping`, ...); any other key becomes `the ` plus the camelCase wire key split before capitals and lower-cased (`timeZone` -> `the time zone`); `organization_id` never mentioned |
| `tenancy.setting_value(key, jsonb)` | `on`/`off` for booleans, `none` for null, the weekday name for `first_day_of_week` (0 Sunday .. 6 Saturday), strings as is, numbers as text |
| Settings reason | `Changed ` + `join_words` of `{setting word} to {value}` per changed top-level key (ignoring `organization_id`), or `Changed the {section} settings` when no key differs (`OS-12`); business date `Set the business date to {iso}` / `Returned the business date to the calendar` |
| People, companies, vehicles, scheduled items, catalog, investment, revenue | the sentences listed per routine in section 4, which are the exact strings of `inv 2.3` to `inv 2.11` |
| Typed reason | `tenancy.compose_reason(automatic, typed)` (section 2.1) |

### 6.2 Snapshots (`json`, not `jsonb`, so key order is preserved; stored as `text`)

| Builder | Keys (exact casing) |
|---|---|
| `setup.company_snapshot` | `Id`, `Name`, `ArchivedOn`, `Active` |
| `setup.vehicle_snapshot` | `Id`, `Registration`, `CompanyId`, `JoinedOn`, `LeftOn`, `Targets` `[{EffectiveFrom, WeeklyAmount, Revision}]`, `Away` `[{LeftOn, ReturnedOn}]` |
| `setup.recurring_snapshot` | `Id`, `StoppedFrom`, `Versions` `[{Id, Revision, EffectiveFrom, Name, Kind, Amount, Frequency, Day, LastDay, Month, Start, End, ExpenseItemId, Bucket, Note, Allocations: [{VehicleId, Amount}]}]` (enums as numbers) |
| `setup.expense_category_snapshot` / `setup.expense_item_snapshot` | `Id`, `Name`, `Bucket`, `StoppedOn` / `Id`, `CategoryId`, `Name`, `StoppedOn` |
| `setup.investment_snapshot` | `Id`, `VehicleId`, `Date`, `Description`, `Amount` |
| `revenue.record_snapshot` | `Id`, `VehicleId`, `BusinessDate`, `Amount`, `Reason` (the .NET enum name: `Garage`, `Arrest`, `NoCrew`, `Other`, or null), `Note`, `CapturedAt`, `CapturedBy`, `UpdatedAt`, `UpdatedBy`, `CorrectedAfterDate`, `Version` |
| `tenancy.person_snapshot` | `FirstName`, `LastName`, `Email`, `PhoneNumber`, `Role`, `Active`, `ScopeMode`, `CompanyIds`, `VehicleIds`, `Permissions` (sorted ordinal), `ApprovalLimit`, then since `0009_access` `BackLimitMode`, `BackLimitCount`, `BackLimitFrom` (`yyyy-MM-dd` or null; section 10.3), and `Name` (`{First} {Last}`, last: the .NET record serialised this computed property too, `docs/13-open-questions.md` question 37) |
| `tenancy.settings_snapshot(section)` | `organization`: camelCase `name`, `slug`; `localization`, `branding`, `securityPolicy`: the camelCase entity keys including `organizationId` (localization carries `useGrouping`; the legacy spelling is not written); `businessDate`: a JSON string `"yyyy-MM-dd"` or `null` |
| `tenancy.logo_snapshot` | `contentType`, `bytes`, `updatedAt`, or the string `null` |
| `pettycash.entry_snapshot` | `Id`, `HolderId`, `Kind` (`Cash`, `Expense`, `Credit`), `Date`, `VehicleId`, `ExpenseItemId`, `Units`, `UnitAmount`, `Total`, `Payee`, `Note`, `Reimbursable`, `Status` (`Waiting`, `Approved`, `Rejected`, or null for cash and credit notes), `SentBackNote`, `RejectReason`, `ReopenReason`, `ReviewedBy`, `ReviewedAt`, `RecordedBy`, `RecordedAt`, `UpdatedBy`, `UpdatedAt`, `RemovedBy`, `RemovedAt`, `RemovalReason`, `Version` (`PC-25`; the two reasons are B19's) |

Dates inside snapshots are `yyyy-MM-dd`; instants are the `+00:00` form with six digits;
money is a number with trailing zeros trimmed (`5000.00` is `5000`); creations store
`before = 'null'`; removals store `after = 'null'` (the investment removal, `SU-I4`, and the logo
removal, `OS-14`). The text is compact, no white space between tokens (`tenancy.compact_json`), as
System.Text.Json wrote it; non-ASCII characters are written as UTF-8 where System.Text.Json
escaped them (`\u00E9`), which is the same JSON. Whether the .NET people snapshot also
carried a computed `Name` key is open (`docs/13-open-questions.md` question 37).

### 6.3 Other formatting

| Rule | Where |
|---|---|
| Masked email (`verification_required`) | `identity.mask_email(text)`: the first character of the stored address, `***`, then everything from the first `@` (`b***@example.com`); `***` alone without an `@` or with a leading one |
| Registration | `setup.registration_normalize` (section 2.3) |
| Phone | `identity.normalize_phone` (section 2.2) |
| Percent | `round(x * 100)` half away from zero (`numeric` rounding in PostgreSQL is half away from zero; `expected` per day uses banker's rounding, implemented as `round(x, 2)` on a value checked for the half case, with a test pinning both) |

## 7. Statement budgets and cost notes

| Routine group | Statements per request | Cost notes and indexes |
|---|---|---|
| `api.auth_account_lookup` + `api.auth_sign_in` | 2 (A01, A02; 3 when a new-device mail fails and the code is withdrawn); 1 for every other anonymous auth route; A12 is 2 (session resolution plus the routine) | user by `phone_number` (unique), device by `(user_id, device_id)`, codes by `(user_id, purpose, created_at DESC)` |
| session resolution + tenant routine | 2 | `enter_organization` reads one membership row and resolves permissions (one query over `person_roles`, `role_defaults`, `permission_overrides`, `permission_dependencies`); the .NET tests pin 10 commands for appearance and 5 for preferences, so the budget is a reduction, not a regression |
| lists | 2 | index rows per `docs/04-schema.md`; `history_list` uses the `(organization_id, version)` primary key for both the seek and the offset form |
| `api.revenue_week_get` | 2 | the grid's ids in registration order, then one statement: `revenue.vehicle_days` over the whole grid (seven rows a vehicle, records by `(organization_id, vehicle_id, business_date)`) and `revenue.earliest_missing`, each materialised once, feed the page's rows, the totals, `day_totals` and `first_gap`; cells are built for the page only; `EXPLAIN (ANALYZE, BUFFERS)` at 10x seed in `docs/perf/revenue.md` (quiet machine: a page of 100 in 120 ms, the legacy 500 in 233 ms, one vehicle in 17 ms; about three times that at full CPU load; the records are read for the week only, `earliest_missing` stops at each vehicle's first gap) |
| `api.revenue_dashboard_get` | 2 | one aggregate over `[from, today]` (the .NET version aggregated record sums in SQL but still loaded vehicles and targets to compute `expected` in C#; here the target arithmetic is in the same query); the .NET 60-second cache is not reproduced: figures are always fresh. If the measured cost at 10x seed exceeds 50 ms the operability prompt adds a `revenue.dashboard_cache` table keyed like the .NET cache (organization, settings version, business date, period, company, scope) rather than a process cache. Measured on 2026-10-11 (`docs/perf/revenue.md`), quiet machine: today 25 ms, week 28 ms, month 41 ms median (63 ms at worst), a month of one company 12 ms; at full CPU load the month took 90 ms. The operability prompt measures again on the host before deciding |
| `api.history_list` total | 2 | counted in the routine; the .NET five-minute count cache is not reproduced (`include_total = false` remains the client's way to skip it) |

## 8. Test matrix (`tests/db/`)

| Module | Covers |
|---|---|
| `test_tenancy_helpers.py` | `enter_organization` (`not_member`, `permission_missing`, GUCs transaction-local), `effective_permissions` table cases from `inv 3.2` (role defaults, grants, denies, dependency pruning), `actor_scope`, `business_date` in several zones and with a held date, `check_time_zone`, `check_page`, `check_money`, `check_typed_reason`, `compose_reason` (every branch of `OS-11` with the examples of `AutomaticReasonTests`), `join_words`, `record_change` (version, log row, audit row, request id) |
| `test_identity_helpers.py` | `normalize_phone` table, `matching_code` (newest, expired, consumed, five wrong tries), `code_caps` (cooldown, hourly, daily), `revoke_*`, `touch_version`, `record_attempt` |
| `test_auth_routines.py` | every branch of section 3.2 with the attempt row asserted, lockout and cap state machine, rotation and reuse detection, the revocation matrix of `docs/07-auth.md` |
| `test_access_routines.py` | the sixteen-step order (one case per step), owner rules, hidden scope preservation, snapshots, side effects on `security_version`, devices and tokens |
| `test_setup_company_routines.py`, `test_setup_vehicle_routines.py`, `test_setup_recurring_routines.py`, `test_setup_expense_routines.py`, `test_setup_investment_routines.py` | one case per `Raises:` code, `unchanged` no-ops, reasons and snapshots byte for byte, target backfill (`SU-V6`), away periods, due-day generation (the cases of `DueDateGeneratorTests`), report maths |
| `test_history_routines.py` | filters, both paging forms, visibility per viewer kind, people redaction, `total` on and off |
| `test_revenue_helpers.py` | the cell status table, `can_edit` per status and permission, `earliest_missing` with away days and a leave date, `vehicle_days` against the setup helpers, rounding (a weekly 1000 is 142.86 a day and 1000.00 a week), `percent`, `reason_code` spellings, `week_start` |
| `test_revenue_routines.py` | the steps in order (one case per step), replay after the day closed with any version, a stale save after another's correction refused for permission without `current`, two first captures racing (`unique_conflict`), two updates racing (`revenue_concurrent_save`), week maths, the range at both bounds, paging and `truncated` with the whole-grid figures unchanged, a company- or vehicle-scoped viewer's week figures and dashboard cards counting only what they see, dashboard cards by permission and period |
| `test_organization_routines.py` | every section with merge semantics, `unchanged`, version once per save, legacy `use_groupping` key, logo signatures, appearance effective values and the read-time validation, preferences allow flags |
| `test_ops_routines.py` | as `xcode_operator`: provisioning (create, reactivate, conflicts), remove, clear pause (cap untouched), revoke sessions, seed idempotence; as `xcode_app`: `42501` on any `api.ops_*` |
| `test_routine_headers.py`, `test_message_codes.py` | header lines present; every code raised has a sentence in `http/messages.py` and vice versa |

## 9. Open points

- Petty cash (section 4.9): prompt 08 re-read `docs/inventory/inventory-petty-cash.md` against
  9276c51 plus the working tree on 2026-10-12 and designed the notes' rules beside it
  (`docs/15-design-v2-3.md` B19).
- `api.revenue_week_get` returns the fifteen-field `RevenueWeekDto` of the drift log
  (`docs/inventory/inventory-http-contract.md`, entries 1 and 2).
- A stored time zone that PostgreSQL does not know raises `XC422 time_zone_invalid` from
  `tenancy.business_date` on every path (the .NET API answered 400 on the settings path
  and 500 elsewhere, `inventory-domain.md` section 9); the data migration maps zones first
  (`docs/13-open-questions.md` question 18).
- Permissions the catalogue lists but no routine enforces today (`dash.net`, `dash.costs`,
  `dash.commitments`, `dash.investment`, `expenses.capture`, `expenses.correct`,
  `bills.*`, `reports.*`) stay in the catalogue and in the token; no routine requires them
  until a feature does.

## 10. Routines of the design notes v2.29 to v2.33 (prompt 07b)

Helpers and `api.*` routines for the rules of `docs/15-design-v2-3.md`, by build session.
The conventions of section 1 hold: one routine per file with its header, `p_now` the only
clock, refusals through `tenancy.refuse` with the codes of `docs/06-http-contract.md`
section 2.12.5 (planned codes; section 3 once built), check order membership and permission, shape, existence, state,
version, write. A signature change drops the old signature in the session's migration and
bumps `api.meta_contract_version()` (the stale-overload gap of `db routines` is open). Every
routine below has the tests of section 1.6 and the rule tests of `docs/09-testing.md`
section 4.1.

### 10.1 Identity (D1; `docs/07-auth.md` section 12)

Helpers (schema `identity`, executor only):

| Helper | Signature | Behaviour |
|---|---|---|
| `identity.pin_tries` / `identity.device_idle_days` | `() RETURNS integer` | 5 and 90; `IMMUTABLE`; parity tests with `PIN_TRIES` and `TRUSTED_DEVICE_IDLE_DAYS` |
| `identity.device_live` | `(p_device identity.trusted_devices, p_now timestamptz) RETURNS boolean` | not revoked, `last_used_at > p_now - 90 days`, `trust_expires_at` null or later |
| `identity.device_trusted` (changed) | `(p_user_id uuid, p_device_id text, p_token_hash text, p_now timestamptz) RETURNS boolean` | the row for (user, device) is live and remembered, and: `p_token_hash` null (old routes **only**) and the row has no token, or `p_token_hash` equals the row's token. The new routines pass `coalesce(p_device_token_hash, '')` (never equal to a stored `^[0-9A-F]{64}$` digest), so a new-route request that omits `deviceToken` is **not** trusted by `deviceId` alone on a legacy row (`docs/07-auth.md` 12.8, `DEC-5`); only the old routes send null |
| `identity.trust_device` (changed) | `(p_user_id uuid, p_device_id text, p_name text, p_token_hash text, p_remembered boolean, p_trust_days integer, p_now timestamptz) RETURNS void` | upsert of `docs/07-auth.md` 12.8: `revoked = false`, `trusted_at = last_used_at = p_now`, `name`, `token_hash` (null when not remembered or on an old route), `remembered`, `trust_expires_at` |
| `identity.locked_for` | `(p_user identity.users, p_trusted boolean) RETURNS boolean` | `failed_attempts >= 5`, or not trusted and `untrusted_failed_attempts >= 5` |
| `identity.count_wrong_pin` | `(p_user identity.users, p_trusted boolean, p_now timestamptz) RETURNS integer` (built without the unused device name) | adds one to the scope's counter; at five writes the change-log row "PIN locked after 5 wrong tries" through `identity.log_sign_in`; returns the new count |
| `identity.unknown_pin_tries` | `(p_phone_digest text) RETURNS integer` | the number (at most 5) of history rows for the digest with `user_id` null, `operation` `sign_in` and refusal `unknown_number` — the lookup's one attempt row per A01/A02/N02 try; the decision routine's `pin` row is the trail, **not** counted (counting both would make N02 double-count, stepping `triesLeft` 3, 1 while a real untrusted account steps 4, 3, 2, 1 — a distinguisher, the opposite of `DEC-2`); index `ix_sign_in_attempts_unknown` |
| `identity.unknown_code_tries` | `(p_phone_digest text, p_device_id text, p_now timestamptz) RETURNS integer` | built: NULL when no simulated reset code is live on this device (no `forgot_pin` row, A07 or N05, and no `code_resent` row of the digest and device in the last 10 minutes), else the device's wrong `code` rows after the newest of them (per device, as a real code is); the third try answers `code_resent` (`docs/07-auth.md` 12.16) |
| `identity.code_caps` (changed) | `(p_user_id uuid, p_skip_cooldown boolean, p_replacement boolean, p_now timestamptz) RETURNS boolean` | `docs/07-auth.md` 12.6: per person across purposes; the one-a-minute rule skipped for a replacement or with development codes |
| `identity.issue_code` | `(p_user_id uuid, p_purpose text, p_device_id text, p_code_hash text, p_skip_cooldown boolean, p_replacement boolean, p_now timestamptz) RETURNS uuid` | caps, `identity.supersede_codes`, insert; the code id, or null when a cap stopped it (silent). Every issue path calls it (one place for the caps) |
| `identity.matching_code` (changed) | `(p_user_id uuid, p_purpose text, p_device_id text, p_code_hash text, p_now timestamptz) RETURNS identity.code_check` (built: the type also carries `tries_left`) | as today, but the third wrong try consumes the code; `refusal` is `wrong_code` with the new field `voided` (true on the third) |
| `identity.remove_devices` | `(p_user_id uuid, p_now timestamptz, p_row_id uuid DEFAULT NULL) RETURNS text[]` (built with `p_now` for liveness) | revokes one row (or all), their refresh tokens and unconsumed codes; returns the names of the live remembered rows it removed (null for unnamed) |
| `identity.sign_in_status` | `(p_user identity.users, p_member_active boolean) RETURNS text` | `blocked` (user removed or membership inactive), `not_signed_in` (no PIN), `pin_reset_due`, `locked` (either counter at 5), else `active`; the one definition behind S05, S06 and the snapshot |
| `identity.log_sign_in` | `(p_user_id uuid, p_actor_id uuid, p_phrases text[], p_before json, p_now timestamptz) RETURNS bigint` | the change-log row of `docs/07-auth.md` 12.11: enters the person's organization (as `identity.policy_for` does) with the actor and request settings, builds the reason (phrases joined with `; `, then `, {First Last}` when the actor is someone else) and calls `tenancy.record_change('signIn', ...)` with `p_before` and the snapshot now; nothing when the person has no active membership |
| `tenancy.sign_in_snapshot` | `(p_user_id uuid, p_now timestamptz) RETURNS json` (built with `p_now` for liveness) | `{"Status": <word of identity.sign_in_status: Active, Not signed in yet, PIN reset due, Locked, Blocked>, "Devices": [names of live remembered rows by trusted_at]}`, compact |
| `identity.issue_session` (changed) | `(..., p_signing_in boolean)` | as today, plus `last_used_at = p_now` on the device row, and `last_signed_in_at = p_now` when `p_signing_in` (every caller but refresh) |

Routines (new or changed; every one locks the account row with `identity.lock_user`, or the
`device:` advisory lock when there is no account, and writes one history row):

| Routine | Parameters (after `p_request_id`) | Returns | Decision | Budget |
|---|---|---|---|---|
| `api.auth_start` (new, N01) | `p_phone text, p_device_id text, p_device_token_hash text, p_code_hash text, p_skip_cooldown boolean, p_now` | `api.auth_outcome` (`pin_required`, `pin_locked`, `blocked`, `verification_required` with `purpose`, `masked_email`, `code_id`, `email`) | `docs/07-auth.md` 12.2 | 1 |
| `api.auth_account_lookup` (changed) | `p_phone text, p_device_id text, p_device_token_hash text, p_pin_try boolean, p_now` (built: `p_pin_try` records an unknown number as a PIN try; a reset completion passes false) | `api.account_state` plus `pin_reset_required` and `untrusted_failed_attempts`; `device_trusted` per the changed helper; `paused_until` leaves the type | statement one of A01, A02, N02; for N07 the variant `api.auth_account_lookup_user (p_user_id, p_device_id, p_now)` returns the same row and the stored number | 1 |
| `api.auth_sign_in` (changed, A01 and A02) | as today without `p_skip_cooldown` change; the verdict guard of `p_checked_pin_hash` kept | `api.auth_outcome` | `docs/07-auth.md` 12.13 and 12.5: legacy trust only; counters and lock; `reset_required`; `last_used_at`, `last_signed_in_at` | 2 with the lookup |
| `api.auth_pin` (new, N02) | `p_phone text, p_device_id text, p_device_token_hash text, p_pin_ok boolean, p_checked_pin_hash text, p_code_hash text, p_refresh_token_hash text, p_skip_cooldown boolean, p_now` | `api.auth_outcome` (`authenticated`, `verification_required`, `refused` with `tries_left`, `pin_locked`, `blocked`) | 12.3 | 2 with the lookup |
| `api.auth_check_code` (new, N03) | `p_phone text, p_device_id text, p_purpose text, p_code_hash text, p_replacement_code_hash text, p_device_name text, p_trust boolean, p_device_token_hash text, p_refresh_token_hash text, p_trust_days integer, p_now` | `api.auth_outcome` (`authenticated` with `device_token_issued`, `code_verified`, `refused` with `tries_left`, `code_resent` with `code_id` and `email`) | 12.6; `new_device` success: both counters 0, trust per `p_trust`, session; `first_setup`/`pin_reset` success: `code_verified`, code kept for N06 | 1 |
| `api.auth_resend_code` (new, N04) | `p_phone text, p_device_id text, p_purpose text, p_code_hash text, p_skip_cooldown boolean, p_now` | `api.auth_outcome` (`verification_required`, issued or not) | 12.6 resend row | 1 |
| `api.auth_request_code` (changed; A04, A07, N05) | as today | as today | caps through `identity.issue_code`; N05 calls it with `pin_reset` and answers in the new envelope | 1 |
| `api.auth_verify_device` (changed, A03) and `api.auth_verify_code` (changed, A05, A08) | add `p_replacement_code_hash text` | as today; a voiding try answers `refused` and issues the replacement | 12.6; A03 success resets both counters, trusts by `deviceId`, logs "Device trusted" | 1 |
| `api.auth_complete_pin` (changed; A06, A09, N06) | `p_phone, p_device_id, p_purpose, p_code_hash, p_new_pin_is_current boolean, p_checked_pin_hash text, p_pin_hash, p_device_name text, p_trust boolean, p_device_token_hash text, p_refresh_token_hash, p_trust_days, p_now` (`p_pin_length` removed) | `api.auth_outcome` (`invalid_pin` with `pin_problem` `unchanged`, `authenticated`, `refused`) | section 3.5 order, then: `unchanged` when `p_new_pin_is_current` holds for the stored hash (code kept); for `pin_reset` every device removed before the completing one is trusted; both counters 0; `pin_reset_required = false`; logs | 1 (2 on a reset: the lookup that returns the hash to compare) |
| `api.auth_change_pin` (new, N07) | `p_user_id uuid, p_device_id text, p_current_ok boolean, p_checked_pin_hash text, p_pin_hash text, p_now` | `api.auth_outcome` (`pin_changed`, `refused` with `tries_left`, `pin_locked`) | 12.12 | 3 with session and lookup |
| `api.auth_device_list` (new, N08) | `p_user_id uuid, p_device_id text, p_now` (no history row) | `jsonb` `[{id, name, trusted_at, last_used_at, this_device}]` | live remembered rows of the user, `last_used_at` descending | 2 with session |
| `api.auth_device_remove` (new, N09) | `p_user_id uuid, p_row_id uuid, p_now` | `api.auth_outcome` (`device_revoked`); `XC404 not_found` for another user's row or a row not live | `identity.remove_devices`, log | 2 with session |
| `api.auth_refresh` (changed) | as today | as today | refused while `failed_attempts >= 5` (replaces "paused") and when the device row is not live; `last_used_at` | 1 |
| `api.auth_sign_out` (changed) | as today | as today | also revokes the device row when it is not remembered | 1 |
| `api.auth_revoke_device` (changed, A12) | as today | as today | logs "Trusted device removed" when a live remembered row was revoked | 2 with session |
| `api.auth_resolve_session` (changed) | as today | as today | the device row must be live (`identity.device_live`), remembered or not | 1 |
| `api.ops_clear_pause` (changed) | as today | `{user_id, was_locked}` | `failed_attempts = 0` and `untrusted_failed_attempts = 0` (both scopes, so the no-email recovery lever of question 53 also clears a new-devices lock) | |
| `api.ops_account_state` (changed) | as today | adds `pin_reset_required`, `last_signed_in_at`, `status` (`identity.sign_in_status`); `paused_until` leaves it | | |

The service generates, before each call, every secret a routine may keep: the code (and the
replacement code for the code routes), the refresh token, the device token. A routine that
does not use one leaves it unused; nothing secret is generated inside SQL.

Lock order (deadlock-free). A sign-in routine holds `identity.lock_user` (the user row) and
then writes its `signIn` change-log row, whose `change_log` insert takes `FOR KEY SHARE` on
the actor's membership through `fk_change_log_actor` (the actor is the person for their own
events). A people routine that also touches the user (`tenancy.save_person`,
`api.people_set_active`, and D2's S45/S46) therefore locks the person's membership with
`FOR NO KEY UPDATE` — not `FOR UPDATE` — before `identity.lock_user`: it never changes the
membership key, `FOR NO KEY UPDATE` still serialises membership writers and still blocks a
concurrent `FOR UPDATE`, and it does **not** conflict with the `FOR KEY SHARE` the sign-in
path takes, so the opposite acquisition orders cannot deadlock. A two-connection test
(an admin block racing a person's logged sign-in event) pins it.

### 10.2 The earliest writable date (D2; prompts 08 and 08b call it too)

| Helper | Signature | Behaviour |
|---|---|---|
| `tenancy.earliest_writable` | `(p_organization_id uuid, p_user_id uuid, p_today date) RETURNS date` | from the membership's limit: `days` -> `p_today - count`; `months` -> `(p_today - make_interval(months => count))::date`, which PostgreSQL already moves to the last day of the month when the day does not exist (`2026-03-31` minus one month is `2026-02-28`, `2024-03-31` minus one month `2024-02-29`); `none` -> no rolling date; then the later of the rolling date and `back_limit_from`; `NULL` when neither is set (any date). One `SELECT` by primary key; `STABLE` |
| `tenancy.back_limit_earliest` | `(p_mode text, p_count integer, p_from date, p_today date) RETURNS date` | the rule of `tenancy.earliest_writable` for a limit that is not stored yet; `IMMUTABLE`; `tenancy.earliest_writable` is this over the membership row, and the person save compares the new person's date with the editor's |
| `tenancy.check_writable` | `(p_day date, p_as_of timestamptz) RETURNS void` | for the current actor and organization: `today = tenancy.business_date(organization, p_as_of)` (the held business date or the calendar date in the organization's time zone); `XC422 record_too_old` with `{"earliest": "yyyy-MM-dd"}` when `p_day < tenancy.earliest_writable(organization, actor, today)` |
| `tenancy.back_limit_words` | `(p_mode text, p_count integer, p_from date) RETURNS text` | the "Can change" words of DN-B12-8: `Any date`; `Today only` (days 0); `{n} day back` / `{n} days back`; `{n} month back` / `{n} months back`; then `, not before {d MMMM yyyy}` (or `Not before {d MMMM yyyy}` alone), the date as `to_char(date, 'FMDD FMMonth YYYY')` (`14 September 2026`) |

Callers and their place in the check order: after membership and permission, after the
record is found and its date known, before the version check, so a 403 never discloses the
limit and a stale writer with an old date gets the limit first. The writes that call it are
exactly those of DN-B12-5: `api.revenue_capture` (section 10.5); prompt 08 the petty-cash
expense add, edit, delete and reopen, cash issue, credit note and cash delete (on the
record's date, and for an edit that moves the date, on both dates); prompt 08b the central
expense add and edit, and the revenue day capture (`PUT /setup/revenue/day/{date}`). Each
row of the day capture runs the steps of `api.revenue_capture` as section 10.5 states them:
the low-day threshold, `revenue.capture` or `revenue.correct`, and this check on the day.
.NET's day save (`RevenueUseCases.SaveDay`) is the specification of the batch only, not of
these per-row rules. Approve, reject, send back, schedules, savings, setup, reads and
exports never call it.

### 10.3 People and access (D2)

| Routine or helper | Change |
|---|---|
| `tenancy.assigned_permissions` | unchanged algorithm over the new tables; hidden role defaults (`organization.manage` for Owner) are assigned; legacy keys are not |
| `tenancy.effective_permissions` | `assigned_permissions` plus every legacy key with a held source (`tenancy.permission_sources`) that no override denies (no writer stores such a denial since the catalogue change; tests and stray rows keep their meaning), in catalogue order (catalogue, then the legacy keys, then `organization.manage`); token issue, session resolution and every permission gate read it |
| `tenancy.expand_permissions` / `tenancy.role_permissions` | catalogue keys only: a role's offered rights (`GET /setup/access/roles`) and the role set an override is measured against never hold `organization.manage`, so no person save names it or stores a denied override for it |
| `api.access_catalog_list` | catalogue rows only, each item with `section` |
| `tenancy.check_person_grant` | "unknown permission" means not a catalogue key (a legacy or the hidden key is `people_permission_unknown`, for an Owner too); the `access.manage` rules read `people.edit`; Owner, self and holdings rules unchanged, except that the sign-in-details rule no longer asks for `people.edit` when the person has an approval limit (an update already needs `people.edit`, so that clause could not refuse) |
| `tenancy.save_person` | new parameters `p_back_limit_mode text, p_back_limit_count integer, p_back_limit_from date` before `p_expected_version` (on update all three null = unchanged; on create null = `days` 7; no mode with a count or a date is `people_back_limit_invalid`); checked after the role (step 8) and before the person and version (step 9): `people_back_limit_invalid` (mode not `none`/`days`/`months`, a count with `none` or none with `days`/`months`, days outside 0-3650, months outside 0-120), `people_back_limit_date_future` (a fixed date after `tenancy.business_date`); a change bumps the membership `version` (not the security version: `tenancy.check_writable` reads the membership live), joins the reason as `how far back they can change records` (last, after `approval limit`) and appears in the snapshot. A person provisioned by the operator, and every member the migration found, starts at `none` (the column default). After the grant rules (step 15) and before the contact check (step 16): a non-Owner may not give a limit looser than their own, on create (the default 7 days included) and whenever the limit changes: `XC403 people_back_limit_not_held` when the new person's earliest date on today's business date is before the editor's (no limit is the loosest; an editor without a limit gives any). Otherwise a limited editor could add a second account of their own without a limit |
| `tenancy.person_snapshot` | keys `BackLimitMode`, `BackLimitCount`, `BackLimitFrom` after `ApprovalLimit`, before `Name` |
| `tenancy.person_document` | adds `status` (`identity.sign_in_status`), `last_signed_in_at`, `back_limit` `{mode, count, from_date}` (`from` on the wire), `can_change` (`tenancy.back_limit_words`), `modules` `[{name, held, total}]` over the catalogue groups in order, only those with `held > 0` (the access chips: all, "n of m"), `everything` (all 59 held), and `sign_in` null; `permissions` stays the assigned catalogue rights |
| `tenancy.person_sign_in` (new) | `(p_user_id uuid, p_now timestamptz) RETURNS jsonb`: the S06 "Sign in" pane `{status, lock (null, every_device at five wrong PINs on trusted devices, new_devices at five on others), last_signed_in_at, email, devices: [{id, name, trusted_at, last_used_at}]}`, the live remembered devices most recently used first; `api.people_get` sets it as `sign_in` |
| `api.people_list` | gate `people.view`; filters `p_role`, `p_status` (`active`, `not_signed_in`, `pin_reset_due`, `locked`, `blocked`, and the legacy `waiting` = `not_signed_in`, `none` = `blocked`; empty or `all` no filter; else `people_filter_status_invalid`, after the permission and page checks as in .NET); the status predicate is `identity.sign_in_status` |
| `api.people_create` / `api.people_update` / `api.people_set_active` | gates `people.add` / `people.edit` / `people.block` |
| `api.access_scope_options` | gate any of `people.add`, `people.edit` |
| `api.access_my_scope` | adds `can_change` (the actor's own limit in words) and `earliest` (`tenancy.earliest_writable` on today's business date, null for any date), so a form can grey out the dates a write would refuse |
| `api.people_sign_out` (S11, "Remove all") | gate `people.sign_in`; `people_self_sign_out`, `XC404`, `people_owner_edit` as today; `unchanged` when no live device or token remains; else `identity.remove_devices` and the change-log row (section `signIn`, reason "Trusted device removed, {First Last}"), replacing "Signed {First Last} out of every device" in section `people`; audit `person.sessions_revoked` kept |
| `api.people_pin_reset` (new, S45) | gate `people.sign_in`; `p_user_id, p_now`; `people_self_sign_in`; `XC404` (not in view); `people_owner_edit`; no PIN or a reset already pending -> `unchanged`; else `docs/07-auth.md` 12.7 and "PIN reset required, {First Last}"; audit `person.pin_reset_required` |

The three sign-in actions take the membership `FOR NO KEY UPDATE`, then `identity.lock_user`,
the order of every people routine (a sign-in event holds the user row and takes `KEY SHARE`
on a membership for its change-log row), so two actions on one person run one after the
other and the second sees the first's result (`unchanged`, or `XC404` for a device already
removed).
| `api.people_device_remove` (new, S46) | gate `people.sign_in`; `p_user_id, p_device_row_id, p_now`; `people_self_sign_in`; `XC404` (person not in view); `people_owner_edit`; then, under the membership and user locks, `XC404` when the row is not their live remembered device (so a non-Owner learns nothing about an Owner's devices); `identity.remove_devices(user, row)` and "Trusted device removed, {First Last}"; audit `person.device_removed` |
| `api.organization_settings_get` / `_set`, `api.organization_logo_set` / `_delete` | gate `organization.manage` (now an Owner-only key); new section `revenue` (section 10.5) |
| `api.organization_appearance_get` | adds `idle_unlock_seconds`; `lockout_threshold` served as 5 |

### 10.4 Setup (D3)

Helpers:

| Helper | Signature | Behaviour |
|---|---|---|
| `setup.target_set_on` | `(p_vehicle_id uuid, p_day date) RETURNS setup.vehicle_target_sets` | the set with the greatest `starts_on <= p_day` (one index probe); null row when none |
| `setup.day_target` | `(p_vehicle_id uuid, p_day date) RETURNS numeric` | 0 when the vehicle is not active that day or has no set in force; else the set's figure for the ISO weekday of `p_day` (1 Monday .. 7 Sunday). The report target is the sum of the day targets of the window (DN-B9-2). `setup.target_on` stays, as the week total of the set in force (0 when inactive), for the vehicle list's `weekly_target` and for the revenue routines until D4 moves them to `setup.day_target`; until then `revenue.vehicle_days` reads the sets as week totals |
| `setup.week_total` | `(p_set setup.vehicle_target_sets) RETURNS numeric` | the sum of the seven |
| the migration split (no routine) | inline in `0010_setup` | `docs/10-data-migration.md` 3.1: Monday to Saturday `p_weekly / 7` rounded to the cent (half-even; a seventh never ends in exactly half a cent, so `round` agrees), Sunday the remainder, so the seven sum to the weekly target exactly; the highest revision per date wins; a target too small to give seven figures above 0 is left out and counted in the migration's notice. Not a helper because migrations run before routines exist |
| `setup.fleet_number` | `(p_value text) RETURNS text` | trims (`tenancy.trim_text`); `vehicle_fleet_required` when empty, `vehicle_fleet_length` above 20 |
| `setup.check_day_targets` | `(p_days numeric[]) RETURNS numeric[]` | exactly seven values, each through `tenancy.check_money`, else `target_days_required` |
| `setup.recurring_kind_right` | `(p_kind integer, p_verb text) RETURNS text` | `savings.{verb}` for a saving (kind 2), else `scheduled.{verb}` |
| `setup.recurring_change_reason` | `(p_kind integer, p_name text) RETURNS text` | `Saving, {name}` for a saving, else `Scheduled expense, {name}` |
| `setup.recurring_visible` (changed) | | also false unless the actor holds the view right of the current version's kind, so writes on a hidden kind answer `XC404` |
| `setup.vehicle_snapshot` (changed) | | keys `Id`, `Registration`, `FleetNumber`, `CompanyId`, `JoinedOn`, `LeftOn`, `InitialInvestment`, `TargetSets` `[{StartsOn, Monday, ..., Sunday}]` by `StartsOn`, `Away` |
| `setup.expense_category_snapshot` (changed) | | `Id`, `Name`, `MainCategoryId`, `StoppedOn` (`Bucket` leaves it); `setup.expense_main_category_snapshot`: `Id`, `Name` |

Routines (all logged in the section shown; `W` is `api.write_result`):

| Routine | Gate | Parameters (after the three standard ones) | Raises (in order) | Logs |
|---|---|---|---|---|
| `api.setup_vehicle_list` (changed) | member, then any of `vehicles.view`, `reports.investment` | as today, `p_q` not here (revenue only) | as today | document adds `fleet_number`, `initial_investment`, `day_targets` (the set in force today, also while away or after leaving; `null` when none has started or without `vehicles.view`), `weekly_target` (its total; 0 when none or inactive), `next_target` `{starts_on, day_targets, weekly_target}` or null; `targets` keeps today's shape for released clients, one entry per set that has started (by start, `revision` its ordinal; a future set only in `next_target`, since the released web reads every entry but the newest as past) |
| `api.setup_vehicle_create` (changed) | `vehicles.add` | `p_company_id, p_registration, p_fleet_number, p_joined_on, p_day_targets numeric[], p_initial_investment numeric, p_reason, p_now` (`p_weekly_target` removed) | `reason_length`; `vehicle_registration_format`; `vehicle_fleet_required`/`_length`; `target_days_required`; `money_invalid` (investment: negative; 0 is stored as null); `vehicle_joined_future`; `XC404` company; `vehicle_company_inactive`; `XC403` scope; `vehicle_registration_taken`; `vehicle_fleet_taken` (own check on the normalised number in the company, backstop `unique_violation`) | `vehicles`: `Added vehicle {reg}, fleet number {fleet}, to {company} with a weekly target of {CUR} {amount} from {joined_on}`; the first set starts on `joined_on` (`DEC-13`) |
| `api.setup_vehicle_update` (changed) | `vehicles.edit` | `p_vehicle_id, p_company_id, p_registration, p_fleet_number, p_joined_on, p_initial_investment numeric, p_reason, p_now` (`p_weekly_target` removed: targets change only through `api.setup_target_set_save`) | as today with the fleet and investment checks | parts joined as today, plus `changed the fleet number of {reg} to {fleet}`, `changed the initial investment of {reg} to {CUR} {amount}` / `cleared the initial investment of {reg}`; an earlier `joined_on` before the first set copies the first set to the new join date (the `SU-V6` backfill, the only set that may start before today) |
| `api.setup_target_set_list` (new) | `vehicles.view` | `p_vehicle_id, p_now` | `XC404` | none; `[{id, starts_on, days, week_total, in_force, can_remove}]` newest first (`in_force` for the set in force today, `can_remove` for `starts_on > today` with `vehicles.target`) |
| `api.setup_target_set_save` (new) | `vehicles.target` | `p_vehicle_id, p_starts_on date, p_days numeric[], p_now` | `target_start_required`; `target_days_required`; lock the vehicle row (`FOR UPDATE`); `XC404`; `vehicle_retired_edit`; `target_start_past` (`p_starts_on` before today); `target_set_unchanged` with `{date}` (equal to the set in force on `p_starts_on`) | inserts, or replaces the set on that date (today or later, `DEC-14`); `vehicles` with `vehicle_id`: `Target set, {registration}`, snapshots before and after |
| `api.setup_target_set_remove` (new) | `vehicles.target` | `p_set_id, p_now` | `XC404` (unknown set or vehicle not visible); lock the vehicle row; `target_set_started` (`starts_on` today or earlier) | deletes; `Target removed before it started, {registration}` (the prototype's wording; the notes say only that it is logged) |
| `api.setup_vehicle_options`, `api.access_scope_options`, the revenue week and the petty-cash options (08) | | | | every vehicle option carries `fleet_number` |
| `api.setup_expense_main_category_list` (new) | any of `catalog.view`, `expenses.view`, `scheduled.view` | `p_page, p_page_size, p_now` | `page_out_of_range` | paged `{id, name, category_count, item_count}` by `name, id`, plus `categories_without_main` |
| `api.setup_expense_main_category_create` (new) | `catalog.add` | `p_name, p_now` | `expense_name_length`; `expense_main_taken` | `expenses`: `Added main category {name}` |
| `api.setup_expense_main_category_rename` (new) | `catalog.edit` | `p_id, p_name, p_now` | `expense_name_length`; `XC404`; `expense_main_taken`; same name -> `unchanged` | `Renamed main category {old} to {new}` |
| `api.setup_expense_category_list` (changed) | any of `catalog.view`, `expenses.view`, `scheduled.view` | as today | as today | rows add `main_category_id`, `main_category_name`; `bucket` served as stored (legacy, null for new categories) |
| `api.setup_expense_item_options` (changed) | any of `catalog.view`, `expenses.view`, `expenses.capture`, `scheduled.view`, `scheduled.add`, `scheduled.edit`, `pettycash.spend` | as today | | options add the main category |
| `api.setup_expense_category_create` (changed) | `catalog.add` | `p_name, p_main_category_id, p_now` (`p_bucket` removed) | `expense_name_length`; `XC404` main category; `expense_category_taken` | `Added expense category {name}` plus ` under {main}` |
| `api.setup_expense_category_update` (changed) | `catalog.edit` | `p_category_id, p_name, p_main_category_id, p_main_category_given boolean, p_now` | `expense_name_length`; `XC404`; `XC404` main; `expense_category_taken`; nothing differs -> `unchanged` | `Renamed expense category {old} to {new}` / `Moved expense category {name} to main category {main}` (or `to no main category`); both: `Renamed expense category {old} to {new}, moved to main category {main}` (as the .NET rename-and-bucket sentence) |
| item and stop routines (S35 to S40) | `catalog.add` (item create), `catalog.edit` (rename), `catalog.stop` (stop, restore) | unchanged | unchanged | unchanged |
| `api.setup_recurring_list` (changed) | any of `scheduled.view`, `savings.view`, after the filter checks | as today | as today | items of a kind the actor cannot view are left out (cost needs `scheduled.view`, savings `savings.view`), also from the total |
| `api.setup_recurring_create` / `_revise` / `_stop` / `_cancel_stop` (changed) | member, then by kind: create `scheduled.add` or `savings.add`; revise the edit right of the current kind and of the new kind; stop and cancel stop the edit right of the kind | as today | `XC404` for an item of a kind the actor cannot view (it is not visible to them), then as today | every scheduled-item write's automatic reason is `Scheduled expense, {name}` or `Saving, {name}` (the current kind; the typed reason is appended by `tenancy.compose_reason`); snapshots and audit actions unchanged |
| `api.setup_vehicle_options` (recurring) | any of `scheduled.add`, `scheduled.edit`, `savings.add`, `savings.edit` | | | |
| `api.setup_company_*` | list `companies.view`; create `companies.add`; rename, archive, restore `companies.edit` | | | |
| `api.setup_vehicle_retire` / `_restore` / `_report` | `vehicles.edit` / `vehicles.edit` / `vehicles.view` | | | the report's `target` is the sum of `setup.day_target` over the window |
| `api.setup_investment_get` / `_create` / `_update` / `_delete` | `reports.investment` / `vehicles.edit` (three) | | | unchanged (question 61) |

Prompt 08b adds pause, resume, runs and summary with `scheduled.pause`/`savings.pause` and
the view rights by kind, on the same pattern.

### 10.5 Revenue (D4)

| Routine or helper | Change |
|---|---|
| `revenue.vehicle_day` (type) | `target` is now the day target (`setup.day_target`), not the weekly one |
| `revenue.vehicle_days` | sets as date ranges `[starts_on, next starts_on)` joined once, the weekday's column picked per day; agrees with `setup.day_target` day by day (test) |
| `revenue.cell` | `expected` = the day target (no division by 7); `amount` and `reason` may both be set (status `amount`); `can_edit`: a missing day with `revenue.capture`, a recorded day with `revenue.correct` (any day, today's included), and in both cases the day not before `tenancy.earliest_writable` for the actor (else false) |
| `revenue.vehicle_week` | adds `gap` = `total_amount - total_expected` (the counted days' targets, the "target to date"), `gap_band` (`revenue.gap_band`), `below_threshold_days` (counted days whose record has no amount or an amount below the threshold, so records saved before the rule and a later change of the threshold count by the figure itself); `percent` kept |
| `revenue.percent` | `round(amount * 100 / target_sum)` half away from zero (the day targets are no longer weekly) |
| `revenue.gap_band` (new) | `(p_gap numeric, p_target numeric, p_amber_percent numeric) RETURNS text`: null when `p_target = 0`; `green` when `p_gap >= 0`; `amber` when `-p_gap <= p_target * p_amber_percent / 100`; else `red` |
| `api.revenue_week_get` | new `p_q text` (trimmed, at most 40 characters, else `revenue_search_length`; matches `registration` or `fleet_number` with `ILIKE` and `%`, `_`, `\` escaped; applied with the company filter before paging, so totals cover the matches); the document adds `low_day_threshold`, `gap_amber_percent`, the week's `gap`, `gap_band`, `below_threshold_days`, `missing_days`, and per vehicle `fleet_number`, `gap`, `gap_band`, `below_threshold_days` |
| `api.revenue_dashboard_get` | gate any of `dash.net`, `dash.gaps`; `captured_today`, `vehicles_today`, `missing_*` with `dash.gaps`; `revenue`, `expected`, `percent`, `edited_records` with `dash.net`; `expected` from the day targets |
| `api.revenue_capture` | new `p_captured_at timestamptz` (nullable). Step 1, entry shape, after membership: a reason label that is not one of the four -> `revenue_reason_invalid`; `money_invalid` for an amount of 0 or less or more than two decimals, except that an amount of 0 with a reason is the reason alone; neither an amount nor a reason -> `revenue_entry_required`; note length; a note without Other -> `revenue_note_without_other` (Other no longer needs a note). Steps 2 to 4 unchanged. Step 4b, the threshold, after the replay (it is a setting, and an entry the server already holds is answered the same whatever the setting says now): an amount below the threshold without a reason -> `revenue_low_needs_reason` with `{threshold}`; an amount at or above it with a reason -> `revenue_amount_with_reason` with `{threshold}` (`DEC-16`). Steps 5 and 6 unchanged. Step 7: no record -> `revenue.capture` (`revenue_capture_permission`), a record -> `revenue.correct` (`revenue_correct_permission`, any day); `revenue_no_earnings_permission` is retired. Step 7b: `tenancy.check_writable(p_day, greatest(least(coalesce(p_captured_at, p_now), p_now), p_now - interval '72 hours'))` (`DEC-12`). Steps 8 to 11 unchanged; the reason sentences are today's, and a new record with an amount and a reason adds its label (below) |
| `revenue.record_snapshot` | unchanged keys; `Amount` and `Reason` may both be set |
| `tenancy.settings_document('revenue')`, `tenancy.check_revenue_settings`, `api.organization_settings_set` | section `revenue` `{lowDayThreshold, gapAmberPercent}` merged like the others; `revenue_settings_invalid`; the setting words `the low-day threshold` and `the amber band`; the reason shows the threshold as `{CUR} {amount}` ("Changed the low-day threshold to KES 3,500.50"), the logged snapshots keep the numbers |

The identical-replay step (4) precedes every check after the lock, the threshold's
included, so an offline replay of a record already stored answers `replayed` whatever its
date, the threshold, the limit or the rights, also for a record saved before the low-day
rule (an amount below the threshold without a reason).

Built 2026-10-12 (D4), with these signatures and choices the table above leaves open:

- `revenue.cell(p_day, p_today, p_can_capture, p_can_correct, p_earliest date)` and
  `revenue.vehicle_week(p_days, p_today, p_can_capture, p_can_correct, p_earliest date,
  p_threshold numeric, p_amber_percent numeric)`; `p_earliest` is the viewer's
  `tenancy.earliest_writable` for the business date (NULL: any date). The week's
  `below_threshold_days` counts days that count whose record holds a reason alone or an amount
  below the threshold; its `missing_days` counts days that count without a record (in the
  fleet, before the business date). `0011_revenue` drops the old overloads of both.
- `api.revenue_week_get(..., p_page, p_page_size, p_q text, p_now)` and
  `api.revenue_capture(..., p_expected_version, p_captured_at timestamptz, p_now)`; the
  migration drops the old signatures; contract version 5.
- Capture step 1 in order: `revenue_reason_invalid`; `money_invalid` (0 or less, more than
  two decimals, above 999,999,999,999.99, as before; an amount of 0 with a reason is the reason
  alone); `revenue_entry_required` (neither an amount nor a reason); `revenue_note_length`;
  `revenue_note_without_other` (a note on an amount without Other answers here, not
  `revenue_amount_with_reason` as before). Step 4b, after the identical replay:
  `revenue_low_needs_reason`; `revenue_amount_with_reason`. Both threshold refusals carry
  `DETAIL` `{currency, threshold}` (`KES`, `4,000`).
- A new record with an amount and a reason logs `Recorded revenue for {reg} on {d MMM yyyy}:
  {label}`; the other sentences are today's.
- The conflict's `current` cell uses the caller's rights and earliest writable date, as the
  week does. Step 7b reads the membership without a lock: a limit tightened while a capture
  runs is a concurrent change whose order is free (the person save reads no revenue), so there
  is no write skew to guard against (`docs/12-security.md` section 7).
- The revenue settings save logs in the change-log section `organization`, not `revenue`:
  `ck_change_log_vehicle` requires a vehicle on every `revenue` row, and those rows are a
  vehicle's records. `tenancy.setting_word` names the keys `the low-day threshold` and `the
  amber band`; `tenancy.setting_value` writes the band as `{n} per cent`. The section's numbers
  are of the kind `decimal` (any JSON number; `tenancy.check_revenue_settings` holds them to
  two decimals and their ranges).
- `revenue.round_half_even` is called by no routine any more (every figure is a sum of cents);
  it stays with its tests.

## 11. Routines of prompt 08b (expenses, scheduled runs, reports, exports, day capture)

Rules are the ids of `docs/inventory/inventory-expenses-reports.md`; where the design notes decide instead, the decision
is named (`docs/15-design-v2-3.md` section 2, `DEC-30` onward). Tables are `docs/04-schema.md` section 14. Every routine
here keeps the conventions of sections 1 to 7: the tenant guard first, refusals as codes (texts in `docs/06` 2.13.6),
one call one transaction, statement budget 2 per route. Folders: `db/routines/57_expenses` and `58_reports` (after
`55_pettycash`, so their dependencies load first), additions to `40_setup`, `50_revenue` and `55_pettycash`.

### 11.1 Postings: one SQL source for every figure (FP-1 to FP-7)

| Helper | Signature | Behaviour |
|---|---|---|
| `setup.recurring_due_days` (changed) | unchanged | also leaves out the days a pause of the item covers (`setup.recurring_pauses`, SR-4) |
| `setup.report_window` (unchanged) | unchanged | the window of every posting source (FP-2): `[max(from, joined_on), min(through, today, left_on - 1)]`, away days not excluded; the postings call it, no second helper |
| `setup.scheduled_runs` | `(p_vehicle_ids uuid[], p_from date, p_through date, p_today date) RETURNS TABLE (item_id uuid, version_id uuid, run_on date, vehicle_id uuid, kind smallint, name text, expense_item_id uuid, note text, amount numeric, state smallint)` | every run of every version with a share on the vehicles, inside each vehicle's report window, on the version's due days (`recurring_due_days`, one version in charge per day): one row per (item, day, vehicle) by construction (`DEC-32`). `state`: 0 posted (a cost), 1 saved (a saving without a revenue rule, or a decided `saved`), 2 skipped (decided), 3 held (a saving with a rule and no decision). Set-based over `unnest(p_vehicle_ids)`; the versions read once |
| `setup.fleet_postings` | `(p_vehicle_ids uuid[], p_from date, p_through date, p_today date) RETURNS TABLE (source smallint, kind smallint, day date, vehicle_id uuid, id uuid, version_id uuid, name text, item_name text, expense_item_id uuid, category_name text, main_category_id uuid, main_category_name text, bucket smallint, units numeric, unit_amount numeric, amount numeric, note text, recorded_by uuid, holder_id uuid, group_id uuid, group_size integer, group_total numeric, group_units numeric, group_unit_amount numeric, version bigint)` | the union, each inside its vehicle's report window: 1 central rows not removed (`expenses.entries`); 2 approved petty-cash expenses not removed; 3 `scheduled_runs` with state 0 or 1 (a skipped or held saving sets nothing aside). `kind` 1 cost, 2 saving. `name` as the source states it (a run's version name), `item_name` the item's current name; category and main category through item -> category -> main category (current, so moving a category regroups every past posting, DN-B16-5); `bucket` the category's, 2 for a cost whose category has none, null for a saving. The only function that sums sources: the vehicle report, the investment, every fleet report, the ledger's scheduled rows and its figures read it or `scheduled_runs` |
| `setup.vehicle_net` (changed) | unchanged | `setup.vehicle_money_in` over the report window less `sum(amount)` of `fleet_postings` with `kind = 1` (replaces the two source helpers) |
| `setup.vehicle_postings`, `pettycash.vehicle_postings` | | dropped by `0013` (replaced by `fleet_postings`); `api.setup_vehicle_report` lists `fleet_postings` (`source` null for scheduled, `central`, `pettycash`) |
| `setup.saving_window_revenue` | `(p_vehicle_id uuid, p_run_on date, p_days integer) RETURNS TABLE (revenue numeric, complete boolean)` | over `[run_on - days + 1, run_on]` cut to the vehicle's days: `revenue` = the sum of recorded amounts (a reason-only day counts 0, an amount with a reason counts its amount, B14-8); `complete` = every day of the window on which the vehicle is active (joined, not left, not away: `setup.vehicle_active_on`) has a record (`DEC-34`) |
| `setup.decide_saving_runs` | `(p_vehicle_id uuid, p_first date, p_last date, p_now timestamptz) RETURNS integer` | `VOLATILE`. Takes `pg_advisory_xact_lock(hashtextextended('xcode.saving_runs:' || organization || ':' || vehicle, 0))`, then (a new statement, so it sees every commit made before the lock was granted) decides each held run of the vehicle with `run_on` between `p_first` and `least(p_last + 29, today)` whose window is complete: `saved` when the revenue reaches `condition_min`, else `skipped`; `INSERT ... ON CONFLICT DO NOTHING` into `setup.saving_runs`; answers the count decided. Callers: the revenue capture and day save (the saved day), `setup.save_recurring` (a saving with a rule, from its start to today), `api.setup_vehicle_update` (a later join date: the days it drops), `api.setup_vehicle_restore` (the away span it inserts) (`DEC-31`) |
| `setup.saving_balance` | `(p_item_id uuid, p_vehicle_ids uuid[], p_as_of date, p_today date) RETURNS numeric` | `DEC-35`: the opening amounts of those vehicles when `opened_on <= p_as_of`, plus the saved runs (`scheduled_runs` state 1) dated after `opened_on` (all when there is no opening) and on or before `least(p_as_of, p_today)` |

Lock order, for every routine of this section and the ones it changes: a vehicle row (`FOR SHARE` for writes that check
it, `FOR UPDATE` for the vehicle's own writes) before the saving-runs advisory lock of that vehicle; several vehicles in
ascending id. No routine takes the advisory lock and then a vehicle row.

### 11.2 Central expenses (E01 to E06; `CE-*`; folder `57_expenses`)

Helpers: `expenses.check_date(p_date, p_today)` (`expense_date_future`, `expense_date_too_old`: 3 650 days, CE-9);
`expenses.check_purchase(p_date, p_item, p_units, p_unit_amount, p_note, p_allocations jsonb) RETURNS TABLE (vehicle_id
uuid, units numeric, unit_amount numeric)` (CE-1 `expense_vehicles_invalid`; CE-2 through `pettycash.check_line(2, ...)`
with the first vehicle, the same rule and codes as a petty-cash expense line; CE-3 `expense_allocation_amount`,
`expense_allocation_sign`, `expense_allocation_sum`; the rows of CE-5 in the order sent; amounts read from text, exactly);
`expenses.row_document(p_id, p_today, p_earliest, p_can_capture, p_can_correct) RETURNS jsonb` (one ledger row, CE-21, for
the 409's `current`); `expenses.describe(p_id) RETURNS text` (`central expense on {registration} for {d Mon yyyy}:
{item}, {CUR} {amount}`, CE-15); `expenses.entry_snapshot(p_id) RETURNS json` (CE-16 keys).

| Routine | Gate | Parameters (after the three standard ones) | Raises, in order | Writes and logs |
|---|---|---|---|---|
| `api.expenses_ledger_get` | `expenses.view` | `p_from, p_to, p_source text, p_q text, p_page, p_page_size, p_now` | `page_out_of_range`; `expense_period_required`; `expense_period_order`; `expense_period_length` (`to - from > 366`); `expense_source_invalid`; `expense_search_length` (trimmed `q` above 200) | none. One statement: the stored rows (central, approved petty cash) of the visible vehicles inside their windows and the scheduled cost runs of `setup.scheduled_runs` for `[from, min(to, today)]`; `figures` over all of them; `total`, `amount` and the page over those matching `source` and `q` (ILIKE with `%`, `_`, `\` escaped; CE-20), ordered day desc, source, registration `COLLATE "C"`, then the id as text (a scheduled row's `{item}:{yyyy-MM-dd}:{vehicle}`); `LIMIT`/`OFFSET` in SQL (CE-19). Flags: CE-21 and, for a central row, its date not before the viewer's `tenancy.earliest_writable` (`DEC-30`) |
| `api.expenses_options_get` | any of `expenses.capture`, `expenses.correct` | `p_date (null = today), p_now` | `expense_date_future`, `expense_date_too_old` | none; vehicles visible and active that day (away excluded) by registration with `fleet_number`; items and categories in use that day with the main category (CE-22) |
| `api.expenses_entry_create` | `expenses.capture` | `p_id uuid (null = new), p_date, p_expense_item_id, p_units, p_unit_amount, p_note, p_allocations jsonb [{vehicle_id, amount}], p_now` | `expenses.check_purchase`; then `pg_advisory_xact_lock` on the purchase id, so a racing duplicate waits and then answers as a retry; rows with that `group_id` or `id`: any of another group or recorder -> `XC409 expense_saved_by_other`, else return them (by id, the stored `group_total`) (CE-8); `expenses.check_date`; `tenancy.check_writable(p_date, p_now)` (B12); each vehicle visible, locked `FOR SHARE` in id order, else `expense_vehicle_not_yours`; active on the date, else `expense_vehicle_inactive` `{registration}`; the item and its category in use (locked `FOR SHARE`), else `expense_item_not_in_use` | the rows (CE-5, CE-6); one `centralexpenses` change-log entry per row (`Recorded ...`, the vehicle), audit `expenses.recorded`; answers `{ids (in the order sent), total}` |
| `api.expenses_entry_update` | any of `expenses.capture`, `expenses.correct` | `p_id, p_date, p_vehicle_id, p_expense_item_id, p_units, p_unit_amount, p_note, p_expected_version bigint, p_now` | `pettycash.check_line(2, ...)` (CE-2); the row visible and not removed, locked `FOR UPDATE`, else `XC404`; identical -> `unchanged` with its id and version (before any right or version check, CE-10); CE-12 `expense_change_other`, `expense_change_earlier_day` (403); a new date without `expenses.correct` -> `expense_change_date` (403); `tenancy.check_writable(old date)`; `expense_version_required`; stale -> `XC409 expense_version_conflict` with `current`; a new date: `expenses.check_date`, `tenancy.check_writable(new date)`; a new date or vehicle: the vehicle visible (`FOR SHARE`), active, and (new vehicle) not already in the purchase -> `expense_purchase_has_vehicle` `{registration}`; a new date or item: in use | the row; CE-11 detaches it; version + 1; `Changed ...` (after), snapshots before and after |
| `api.expenses_entry_remove` | any of the two | `p_id, p_expected_version, p_reason, p_now` | `reason_length` (required, trimmed); the row as above, else `XC404`; CE-12; `tenancy.check_writable(row date)` (`DEC-30`); `expense_version_required`; stale -> `expense_version_conflict` | soft removal, version + 1; `Removed ... . Reason: {reason}.` |

`tenancy.check_writable`'s callers (section 10.2) add the central expense remove.

### 11.3 Scheduled items: pause, resume, runs, summary, the saving model (S53 to S56; `SR-*`; B18)

| Routine | Gate | Parameters | Raises, in order | Writes, logs, answer |
|---|---|---|---|---|
| `api.setup_recurring_pause` / `_resume` | member; any of `scheduled.pause`, `savings.pause`; then the pause right of the item's current kind | `p_item_id, p_now` | `XC403 permission_missing` (neither right); the item, locked `FOR UPDATE`, visible with its kind's view right, else `XC404`; the kind's pause right (`XC403`); a vehicle of the current version not visible -> `XC403` (no detail); pause: stopped on or before today -> `recurring_already_stopped`, already paused -> `unchanged`; resume: no open pause -> `unchanged` (before the stop, SR-3), stopped -> `recurring_already_stopped` | pause: a row from today; resume: `paused_through = greatest(today, paused_from) - 1`; section `recurring`, reason `Saving, {name}` or `Scheduled expense, {name}` (DN-B17-3, `DEC-43`), snapshots with `PausedFrom` and `Pauses` (SR-6); `W` |
| `api.setup_recurring_runs` | any of `scheduled.view`, `savings.view` | `p_item_id, p_now` | the item visible with its kind's view right, else `XC404` | `{id, name, kind, start, total, run_count, runs: [{date, amount, shares: [{vehicle_id, registration, amount, state, revenue}]}]}`: the last ten run dates to today on visible vehicles, newest first; `amount` and `total` count posted and saved shares only; `state` `posted`, `saved`, `skipped`, `held`; `revenue` the stored figure, the window so far for a held share, null without a rule (SR-8) |
| `api.setup_recurring_summary` | any of `scheduled.view`, `savings.view` | `p_now` | | `{from, to, costs_due, saved, savings_balance, running_costs, paused_costs, running_savings, paused_savings}` on visible vehicles (SR-9): `costs_due` (costs posted this month to today plus those to come, open pauses skipping the days to come) and the cost counts null without `scheduled.view`; the saving figures null without `savings.view`; `savings_balance` through `setup.saving_balance` (openings included) |
| `api.setup_recurring_list` (changed) | as D3 | as D3 | as D3 | items add `paused_from`, `last_run`, `last_run_vehicles`, `balance` (SR-7, the balance through `setup.saving_balance`), `last_run_states {saved, skipped, held}`, `condition {min, days}` or null, `opening {date, total}` or null, `next_run` (the next run date after today, null while paused or stopped) |
| `setup.save_recurring` (changed; create and revise) | as D3 | adds `p_condition jsonb` (`{min, days}` or null) and `p_opening jsonb` (`{date, amounts: [{vehicle_id, amount}]}`, null to remove, absent to keep on a revise) | after D3's checks: a cost with a rule -> `recurring_condition_on_cost`; `recurring_condition_min` (min above 0, two decimals); `recurring_condition_days` (1, 7 or 30); a cost with an opening -> `recurring_opening_on_cost`; `recurring_opening_future`; an opening amount through `tenancy.check_money` (0 means none); a vehicle not among the shares -> `recurring_opening_vehicle`; a saving with an end date that is new or differs from the stored one -> `recurring_savings_end` (a migrated end stands until cleared, `docs/10` 3.2 row 24). Savings may run daily, weekly, monthly or yearly (`recurring_savings_frequency` and, for savings, `recurring_daily_retired` no longer apply); a new saving's `start_on` is the business date whatever is sent, a revise keeps it (`DEC-33`). It also locks the share vehicles and their companies `FOR SHARE` in id order and the item `FOR SHARE` (the open 06 finding `06:V-D3-2`) | the version with its condition; the opening replaced; a saving with a rule then calls `setup.decide_saving_runs` per vehicle from its start to today; snapshots add `Opening {Date, Amounts}` after `Versions` and per version `ConditionMin`, `ConditionDays` after `Allocations` |
| `api.revenue_capture`, `api.revenue_day_save`, `api.setup_vehicle_update`, `api.setup_vehicle_restore` (changed) | | | | after their writes, `setup.decide_saving_runs` for the days they touched (11.1) |

### 11.4 Reports (G01 to G04; `RP-*`; folder `58_reports`)

Table helpers (`reports` schema), shared by every report and export:

| Helper | Signature | Behaviour |
|---|---|---|
| `reports.check_period` | `(p_from date, p_to date, p_today date) RETURNS daterange` | `report_period_both`; `report_period_order`; `report_period_length` (more than 367 days counted inclusive); `report_period_future` (`from` after today); `to` cut to today (RP-2) |
| `reports.check_query` | `(p_q text, p_page integer, p_page_size integer) RETURNS text` | `tenancy.check_page`; `report_search_length` (trimmed, above 200); the trimmed text or null |
| `reports.cell_text` | `(p_cell jsonb, p_kind text) RETURNS text` | RP-13's forms: the text; a date also as `FMDD Mon YYYY`; a number as written (no trailing zeros) and with thousands separators (`#,##0`, or `#,##0.00` when it has cents) |
| `reports.page` | `(p_table jsonb, p_q text, p_page integer, p_page_size integer) RETURNS jsonb` | the rows whose texts hold every word of `q` (case-insensitive), `total`, `totals` (each summed column over every match, null for the others), and the page; headline and figures untouched |
| `reports.matching_rows` | `(p_table jsonb, p_q text) RETURNS jsonb` | the matching rows, unpaged (exports) |
| `reports.document` | `(p_table jsonb, p_rows jsonb, p_filters text, p_format text, p_now timestamptz) RETURNS jsonb` | what a file needs: the table with `p_rows`, `organization` (branding display name, else `XCODE`), `period` (`d Mon yyyy`, `{from} to {to}`, or null), `filters`, `exported_by` (the actor's name), `exported_on`, `currency`, `file_name` (`{title}[ {period}].{xlsx|pdf}`), `content_type` |
| `reports.log_export` | `(p_table jsonb, p_row_count integer, p_filters text, p_q text, p_format text, p_snapshot jsonb, p_now timestamptz) RETURNS void` | the change-log entry of RP-14 (section `reports`, a new entity id, no vehicle, `after` the snapshot, reason `Exported {title}[ for {period}][, searched for "{q}"] to {Excel|PDF}`), audit `reports.exported` |
| `reports.check_export` | `(p_format text, p_row_count integer) RETURNS text` | `export_format_invalid` (not null, empty, `xlsx` or `pdf`); `export_too_many_rows` `{count}` above 10 000 rows (every export, reports included, `docs/12-security.md` 2.8); `xlsx` or `pdf` |
| `reports.vehicles` | `(p_company_id uuid) RETURNS TABLE (vehicle_id uuid, registration text, fleet_number text, company_name text, joined_on date)` | the visible vehicles, of the company when given, by registration `COLLATE "C"` (RP-3) |
| `reports.vehicle_figures` | `(p_vehicle_ids uuid[], p_from date, p_through date, p_today date) RETURNS TABLE (vehicle_id uuid, revenue numeric, target numeric, captured integer, no_revenue integer, missing integer, missing_days date[], money_out numeric, saved numeric, saving_runs integer)` | RP-4 from `revenue.vehicle_days` (day targets of the set in force each day, B9-12; `DEC-37`) and `setup.fleet_postings`, set-based; the vehicle report's figures by construction |
| `reports.money_out_by_main` | `(p_vehicle_ids uuid[], p_from date, p_through date, p_today date) RETURNS TABLE (vehicle_id uuid, main_category_id uuid, main_category_name text, amount numeric)` | cost postings per vehicle and main category (null = `No main category`) |

Builders, each `RETURNS jsonb` (the whole table of RP-13's shape, before search and paging), in `reports`:

| Builder | Rows and columns | Headline and figures |
|---|---|---|
| `reports.fleet_net` | vehicles with days in the period, by net desc, registration; `vehicle, company, revenue`, then one money column per main category holding money in the period (key `main:{id}`, label its name, by name), `main:none` `No main category` last when it holds money, then `moneyOut, net, saved` (`DEC-38`) | `Net`; `Revenue`, `Money out`, `Saved` |
| `reports.fleet_target` | RP-6, the target from the day targets | `Revenue`; `Target`, `Reached`, `Missing days` |
| `reports.fleet_gaps` | RP-7 (revenue only; question 76) | `Missing days`; `Vehicles with gaps` |
| `reports.fleet_money_out` | cost postings grouped by item (a scheduled cost without one by name): `mainCategory` (`Not set`), `category, item, entries, quantity, low, high, amount, share`; quantity and unit costs as RP-10 | `Money out`; one figure per main category holding money, `No main category` last (`DEC-38`) |
| `reports.fleet_savings` | per vehicle with any run or balance: `vehicle, company, savedRuns, skippedRuns, heldRuns, saved, notSaved, balance` (`notSaved` the skipped runs' amounts; `balance` as at the period's last day through `setup.saving_balance`), by balance desc, registration | `Saved`; `Balance` (as at), `Not saved`, `Runs skipped`, `Waiting for revenue` |
| `reports.fleet_investment` | undated; vehicles that have joined: `vehicle, company, joined, invested, net, recovered`; `invested` = initial investment + dated entries (null when neither, question 61), `net` = `setup.vehicle_net` from the join date to today, `recovered` null without an investment; by recovered desc, those without last, then registration (`DEC-39`) | `Invested in vehicles`; `Net since joining`, `Recovered` |
| `reports.pettycash_*` | `cash_book`, `managers`, `vehicles`, `items`, `waiting`, `sent_back` as RP-12 over the entries the Petty cash page shows the person (08's visibility), with B19's statuses: By manager adds `rejected`; a rejected expense is not spent (DN-B19-7); `sent_back` lists waiting expenses with a send-back reason; new `rejected` ("Rejected and reopened": expenses rejected, or reopened, in the period, with the reason) (`DEC-41`) | as RP-12 |

| Routine | Gate | Parameters | Raises, in order | Answer |
|---|---|---|---|---|
| `api.report_catalog_get` | `reports.view` | `p_now` | | `{business_date, first_day_of_week, fleet, petty_cash, holders, can_export}`: `investment` with `reports.investment`; the petty-cash ids with `pettycash.reports` (adding `rejected`); holders every float with `pettycash.view_all`, else the person's own when they keep one; `can_export` = `reports.export` |
| `api.report_get` | `reports.view`; investment `reports.investment`; petty cash `pettycash.reports` | `p_group text, p_report text, p_from, p_to, p_company_id, p_holder_id, p_q, p_page, p_page_size, p_now` | `reports.check_query`; unknown group or report -> `XC404`; the report's own right (`XC403 report_investment_permission` for the investment report, `XC403 report_pettycash_permission` for a petty-cash report; the sentences of `docs/06` 2.13.6); for a petty-cash report a `holder_id` not among the person's floats -> `XC404`; then the period (dated reports), as .NET checks the holder first | `reports.page` of the builder's table |
| `api.report_export_get` | `reports.export`, then as `api.report_get` | the same without paging, plus `p_format` | `reports.check_export` (format first); `reports.check_query`; as `api.report_get`; `export_too_many_rows` | `reports.document`; writes `reports.log_export` (snapshot `{group, report, from, to, holderId, companyId, q, rows, format}`) in the same transaction |
| `api.revenue_export_get` | `revenue.export` and `revenue.view` | `p_week_start, p_company_id, p_format, p_now` | format; then as `api.revenue_week_get` (one vehicle page of at most 500, as the grid's legacy page) | the `Revenue` table of `DEC-44`: `vehicle, company`, seven day columns (key the date, label `ddd d`; the amount, the reason label, `Missing`, or null), `total` (Week total), `target` (`Target to date`, `Target` for a finished week), `gap` (signed); figures `Gap to target so far` (or `Gap to target`), `Below {threshold}`, `Missing days`; logged as RP-15 |
| `api.expenses_export_get` | `expenses.export` and `expenses.view` | `p_from, p_to, p_source, p_q, p_format, p_now` | format; the ledger's checks; `export_too_many_rows` | RP-15's `Central expenses` table, every matching row; logged |
| `api.pettycash_export_get` | `pettycash.export` and the petty-cash read gate | `p_from, p_to, p_holder_id, p_view text, p_status text, p_q, p_format, p_now` | format; `pettycash_export_view_invalid`; the overview's period checks; the list's filter checks; `export_too_many_rows` | RP-15's two petty-cash tables, with B19's statuses (`Rejected`); logged |

Every export reads its rows and writes its change-log row in one transaction (`docs/12-security.md` 2.8): a failure
after commit leaves the row of an export the person did not receive; never a file without a row. The gateway marks
exports idempotent: a retried export after a transient failure is a new transaction whose earlier row rolled back. The
file is built in Python from `reports.document` (`docs/02-stack.md` ADR-16).

### 11.5 Day capture (D01, D02; `RD-*`)

| Routine | Gate | Parameters | Raises, in order | Answer |
|---|---|---|---|---|
| `revenue.capture_entry` (new helper) | (the caller's) | `p_vehicle_id, p_day, p_amount, p_reason, p_note, p_expected_version, p_captured_at, p_now` | D4's steps 1 to 8 of `api.revenue_capture` (section 10.5), moved here unchanged: entry shape, vehicle (`FOR SHARE`), record lock `NOWAIT`, the identical replay, the threshold, date, activity, rights (`revenue.capture` for a day without a record, `revenue.correct` for a saved one), `tenancy.check_writable`, version | `W`; logs as today; then `setup.decide_saving_runs(vehicle, day, day, now)` |
| `api.revenue_capture` (changed) | as D4 | unchanged | membership and either right, then `revenue.capture_entry` | unchanged contract and budget |
| `api.revenue_day_get` | `revenue.view` | `p_date (null = today), p_company_id, p_now` | `revenue_day_date_range` | `{date, business_date, vehicles: [{id, company_id, registration, day, last_week, fleet_number}], truncated}`: visible vehicles in the fleet and not away that day, of the company, by registration `COLLATE "C"` then id, at most 500; `day` is `revenue.cell` as the week builds it (the viewer's rights and earliest writable date); `last_week` `{amount, reason}` of seven days earlier or null |
| `api.revenue_day_save` | member, then either of `revenue.capture`, `revenue.correct` | `p_date, p_rows jsonb [{vehicle_id, amount, reason, note, version}], p_now` | `revenue_day_rows_required`; `revenue_day_rows_limit` (500); `revenue_day_vehicle_repeated`; every vehicle visible, else `XC404` (no detail, before any row); step 1 (entry shape) of every row in the order sent; then each row through `revenue.capture_entry` in ascending vehicle id (one lock order for every multi-row write, `DEC-42`), inside a block that catches a 400-class refusal and raises it again through `tenancy.refuse` with the caught code and SQLSTATE and `vehicle_registration` added to its `DETAIL` (the header lists those codes `via revenue.capture_entry`), and turns a version conflict into `XC409 revenue_day_conflict` `{vehicle_id, registration, current}`; a 403 passes unchanged | `{rows: [{vehicle_id, id, version}]}` in the order sent; all or none (RD-5) |

The HTTP layer prefixes the sentence of any 400 whose `DETAIL` carries `vehicle_registration` with `{registration}: `
(one rule in `http/errors.py`, `docs/06` 2.13.6). The day save takes no `capturedAt`: it is a web screen, checked as of
the request.

### 11.6 Petty-cash additions (`DEC-26`, question 68)

| Routine | Change |
|---|---|
| `api.pettycash_entry_create` | an expense may carry `p_allocations jsonb` (2 to 50 vehicles): `expenses.check_purchase`'s rules, one entry per vehicle sharing `group_id` = the entry id sent (or a new one) with the purchase as bought; the retry key is the group (CE-8's rule, holder and recorder the same); each part is approved, rejected and reopened on its own; one change-log row per part |
| `api.pettycash_entry_update` | a change of item, units or unit amount takes the part out of its group (CE-11); date, vehicle and note keep it |
| entry document | adds `group {id, size, total, units, unit_amount}` (null alone): `size` counts the group's parts not removed and not rejected, read live, so a deleted or rejected part recounts the others |

### 11.7 Statement budgets and evidence

Every route of `docs/06` 2.13 is 2 statements (the call and its result), asserted through `statement_counter`. The heavy
reads (`api.expenses_ledger_get`, `api.report_get` for `net`, `gaps` and `moneyOut`, the three screen exports,
`api.setup_recurring_summary`) need `EXPLAIN (ANALYZE, BUFFERS)` files under `docs/perf/` at 10x the demo seed, as
prompt 07 did for the week grid.

### 11.8 Change log (drift register row 14)

`api.history_list` (prompt 05's, with 07b's and 08's clauses) adds the two sections of `docs/04-schema.md` 14.5, as
.NET's history filter has them (`SetupRepository.cs:381-386`): `centralexpenses` rows are visible to a scoped viewer
when the row's vehicle is visible (the `pettycash` rule), and `reports` rows only to a viewer who sees every company
(RP-18). The `section` filter accepts both. Test: `tests/db/test_history_routines.py::test_central_expense_and_export_rows_follow_the_scope`.
