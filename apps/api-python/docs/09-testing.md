# Testing

## 1. Evidence standard

Carried over from the repository's CLAUDE.md and made specific for this project:
- Every requirement in a prompt is proven by a test that fails without the change.
- A test that fakes the capability under test is not evidence: no mocked gateway in
  behaviour tests, no mocked PBKDF2, no mocked RLS.
- A declared invariant must be exercised: a `version` column is proven to change and to
  reject a stale writer; a cap is proven to refuse the N+1th attempt; a policy is proven to
  hide another tenant's row.
- Assertions are never weakened to make a test pass. If an expectation is wrong, the HTTP
  contract (`docs/06-http-contract.md`, which comes from the .NET tests and clients) decides.
- Unit tests of use cases with fakes prove orchestration (what is told to which port, in
  which order); they are never the evidence for a business rule, a permission or a tenant
  boundary, which are proven in `tests/db/` against PostgreSQL.
- Zero-trust controls in `docs/12-security.md` each name their test; a control without a
  passing test is not implemented.
- A passing suite is where verification starts, not where it ends: every phase ends with
  the challenge pass of `docs/14-verification.md`, run as if nobody had reviewed the code
  before.

## 2. Harness

- `tests/conftest.py` starts (or connects to) PostgreSQL once per session:
  `XCODE_TEST_DATABASE_URL` (superuser or owner-capable) when set, else
  `testcontainers[postgres]` with `postgres:18`.
- Session setup applies `db/roles/*.sql` (including `900_local_dev.sql`), creates
  `xcode_template`, runs the migration runner and the routine step into it, stamps its
  comment with a SHA-256 fingerprint of every file under `db/roles`, `db/migrations` and
  `db/routines` and of the runner, and marks it `datallowconn = false`. A frozen template
  whose fingerprint differs is rebuilt. Every session holds a shared advisory lock
  (`xcode.test.template.use`) while it clones; a rebuild needs it exclusively, so a session
  that finds a stale template while another session runs fails with a message instead of
  dropping the template under that run or testing old routines.
- Each test gets `CREATE DATABASE test_<worker>_<n> TEMPLATE xcode_template`, two URLs
  (as `xcode_app`, as `xcode_owner`) and drops the database at teardown. Parallel workers
  (pytest-xdist) never share a database.
- The app under test is `create_app(settings, container=build_container(settings, pool, ...))`
  with `Settings.for_tests(database_url=...)`. Ports are replaced through the keyword
  arguments of `build_container`, never by dependency overrides or monkey-patching, using
  the fixtures in `tests/support/`:
  `ManualClock` (time control, replacing the .NET `IClock`), `MailSpy` (captures messages;
  the real `MailQueue` is still exercised), `MemoryRateLimiter` with a test limit.
- Fixture names (`tests/conftest.py`): the database-backed app is `db_client`, built from
  `db_settings`, `pool` and `db_container`; `client`, `settings`, `ops` and
  `make_container` are the database-free variants that drive the HTTP plumbing tests with
  `FakeOpsRepository`; `owner_conn`, `app_conn`, `operator_conn` and `competing_writer` are
  direct psycopg connections to the test database; `fresh_owner_url` is a schema-only
  database for runner tests; `manual_clock` and `mail_spy` are the port doubles.
- PBKDF2 iterations: the test settings use the real algorithm with a low iteration count
  (`PIN_ITERATIONS_TESTING`, 1 000) for speed, except `tests/unit/test_pin_hasher.py`, which
  runs the full count once to prove the parameter is applied (against an independent
  derivation) and checks a published PBKDF2-HMAC-SHA256 vector.
- `statement_counter` fixture: the gateway increments a counter per routine call and per
  underlying statement; tests assert the budget from `docs/06-http-contract.md`.
- `competing_writer` fixture: a second connection that performs a given write between two
  steps of a test, replacing the .NET `DatabaseProbe.Interleave`.
- Authenticated clients come from `tests/support/client.py` (`AuthApi.onboard()`:
  provision through the operator routine, then the real first-PIN flow) and
  `tests/support/setup_client.py` (`join(api, email=, phone=, role=)` gives a `Member`
  with bearer headers), so every token comes from the routines (no token minting
  shortcuts in API tests; unit tests may mint tokens).

## 3. Layers of tests

| Layer | Folder | Runs as | What it proves |
|---|---|---|---|
| Unit | `tests/unit/` | n/a | settings validation matrix; JWT issue/verify; PBKDF2 vectors; code format; refresh-token digest; problem-details encoder; import-layer rule; rate limiter contract (memory adapter) |
| Use case (unit) | `tests/unit/test_use_case_<name>.py` | n/a | orchestration only, with `tests/support/fakes.py`: order of port calls, after-commit effects (mail enqueued only after the repository call returned), uniform refusal shaping, dummy hash for unknown accounts; never evidence for a rule |
| Fake parity | `tests/db/test_fakes_match_routines.py` | `xcode_app` | the shared contract cases pass against the fakes and against the real routines, so unit tests cannot drift from the database |
| Gateway | `tests/db/test_gateway.py` | `xcode_app` | one transaction per call, retry only for idempotent calls and only on transient SQLSTATEs, SQLSTATE translation table, statement counter |
| Structure | `tests/db/test_structure.py` | `xcode_owner` | roles exist with the right attributes; `xcode_app` has no table/sequence privileges anywhere; every `api.*` routine is SECURITY DEFINER, owned by `xcode_api_executor`, has the search_path setting, `PUBLIC` lacks EXECUTE; every tenant table has RLS plus the policy; every index in `docs/04-schema.md` exists; `public` is empty |
| Routine | `tests/db/test_<area>_routines.py` | `xcode_app` | per routine: happy path, each `XC` error with its `MESSAGE` code, tenant isolation (actor from another organization), version bump and `XC409`, idempotent replay, pagination clamp |
| Migration runner | `tests/db/test_migrate.py` | `xcode_owner` | fresh apply, idempotent re-run, checksum drift refused, concurrent runners serialized, `down` then `up`, routine ownership fix-up |
| HTTP contract | `tests/api/test_<feature>.py` | app role via the app | status codes, exact bodies and headers from `docs/06-http-contract.md`, auth and permission refusals, enumeration uniformity, statement budgets, OpenAPI document assertions |
| Operability | `tests/api/test_operability.py` | | health routes, request id propagation, JSON logs with request id outside development, problem details carry `requestId` and never `exception`, graceful mail drain, startup refusals (production without key/host/from/url; dev flags outside development) |

## 4. Crosswalk from the .NET suite

One row per .NET test class (`docs/inventory/inventory-tests.md` section 2 holds every
method with its decisive assertions; section 4 the behaviours only tests state; section 5
the reader's seed of this table). The rule for the implementers: every method of a class
below appears in the named Python module as a test whose name carries the same behaviour,
or in the report with the reason it cannot. The audit (prompt 11) checks this table against
the Python suite. Layers are those of section 3: `unit`, `db`, `api` (contract and
operability tests live under `tests/api/`; migration tests under `tests/db/`).

Mechanical substitutions that apply to every row and are not repeated:

- `AuthFactory` and `EnsureCreated` become the session template database and the per-test
  database of section 2; SQLite Guid traps disappear.
- `DatabaseProbe.Commands` becomes the gateway statement counter (`statement_counter`):
  an exact budget from `docs/06-http-contract.md` section 2 where .NET asserted an exact
  number; "same at two sizes" stays a two-size comparison; `Rows` and `Transactions`
  assertions are replaced by the one-transaction-per-call gateway test and by `EXPLAIN`
  evidence (prompt 07).
- `Interleave` and `BetweenAttempts` become the `competing_writer` fixture; `FailNextCommit`
  becomes a gateway hook raising a transient SQLSTATE once; `TestClock.Advance` becomes
  `ManualClock` through `p_now` (the clock starts at the fixed instant
  `2026-10-07T09:00:00+00:00` so no test depends on the calendar).
- Direct entity inserts and `Provisioning = true` become the scenario builder
  (`tests/support/scenario.py`), which calls the real routines.
- Tests that read `AuditEvents`, the change log or the policy row keep doing so through
  SQL in `tests/db/`, with the table names of `docs/04-schema.md`.

| .NET class | Python module(s) | What changes |
|---|---|---|
| `AuthTests` (46 rows) | `tests/api/test_auth_contract.py`; lockout, cap and clamp rules in `tests/db/test_auth_routines.py`; concurrency in the same module (`test_concurrent_wrong_pins_on_one_account_are_both_counted`, `test_revoking_a_device_waits_for_the_accounts_other_auth_work`); the stale-write and retried-attempt rows have no counterpart: they tested EF's concurrency token and retry strategy, which the row lock replaces | `Seen` becomes the header-and-body diff helper with the same three exclusions; the in-process gate becomes two connections contending on the user row lock; `PRAGMA ignore_check_constraints` becomes an owner insert with constraints deferred; mail-after-commit timing uses `MailSpy` |
| `Phase1AuthContractTests`, `Phase1AppearanceAndCatalogContractTests`, `Phase1WebSettingsContractTests` (19) | `tests/api/test_contract_released_clients.py`: the auth rows, the appearance and catalogue rows and the people, settings and preferences rows are in place; the fleet rows (`FleetScreensReadAndWriteAsTheDevelopWebDoes`, the two recurring refusals, the company and vehicle-report parts of `RefusalsKeepTheirStatusAndAProblemTheWebCanShow`) arrive with prompt 06 | raw-JSON, case-sensitive property checks kept verbatim (`has(parent, name, kinds)`); the strongest reusable contract; `useGrouping` and the legacy name both asserted |
| `AccessAndSetupTests` (19), `AccessLifecycleTests` (7), `PeopleHistoryTests` (1) | `tests/api/test_people.py`, `test_access.py`, `test_history.py`; role defaults in `tests/db/test_tenancy_helpers.py` | `RoleDefaultsComeOnlyFromTheCatalog` has no table to drift (`RolePermissions` dropped): becomes the catalogue seed test of prompt 02 |
| `OrganizationSettingsTests` (13), `SettingsContractTests` (2), `AppearanceTests` (3), `AutomaticReasonTests` (6) | `tests/api/test_organization_settings.py`, `test_appearance.py`; routine-level in `tests/db/test_organization_routines.py`; reasons in `tests/db/test_tenancy_helpers.py` | the reflection check on a private method is dropped (the rule is tested); `EachSettingsDtoWritesWhatItsEntityWrote` becomes golden JSON per section; the version-once rule is a routine test |
| `ChangeLogAndScopeTests` (10), `ChangeLogPagingTests` (6) | `tests/api/test_history.py`; `tests/db/test_history_routines.py`; the retry rows become `competing_writer` cases on `tenancy.record_change` (no retry loop exists: the row lock serialises) | SQL-text assertions (`OFFSET`, `"Version" <`) become `EXPLAIN` evidence of the seek plan; the `ChangeLogVehicle` backfill has no counterpart (the column exists from the first migration; the data migration tool checks it) |
| `PeopleQueryCostTests` (8), `RecurringQueryCostTests` (2), `VehicleReportTests` (6, the count rows), `RevenueComplexityTests` (3), `ExpenseCatalogTests` (the count rows) | statement budgets in each `tests/api/test_<feature>.py` (2 per request) and two-size comparisons in `tests/db/test_<area>_routines.py`; `EXPLAIN` files under `docs/perf/` | EF command counts (10, 5, 1, 3) are not reproduced: the budget is 2 statements and the routine's plan is reviewed |
| `RevenueCaptureTests` (16), `RevenueTests` (2), `RevenueRefusalTests` (3), `RevenueDashboardCardTests` (2), `VehicleAwayTests` (4), `RevenueWeekPagingTests` (8) | `tests/api/test_revenue.py`; `tests/db/test_revenue_routines.py` | the SQLite trigger race becomes two connections on the unique key; JSON property order asserted on the serialised body; the SQL-shape test becomes `EXPLAIN` evidence |
| `RevenueDashboardCacheTests` (13) | not ported: the design has no dashboard cache (`docs/05-routines.md` section 7); the "fresh figures after a change" rows become freshness tests in `tests/db/test_revenue_routines.py` | if a cache table is added later, its invalidation tests come with it |
| `InvestmentTests` (5), `RecurringCrudTests` (4), `ScheduledItemRulesTests` (9), `DomainRuleTests` (20), `DueDateGeneratorTests` (2), `ExpenseCatalogTests` (6) | `tests/api/test_setup_*.py`; `tests/db/test_setup_*_routines.py`, `test_setup_helpers.py` | domain-rule tests move to routine tests (the rules live in SQL); the seeded property test of `DomainRuleTests` (`Random(20260930)`, 400 runs) is kept as a `hypothesis`-free loop against `setup.target_on` |
| `ListFilterTests` (3) | vehicles by company: `tests/db/test_setup_vehicle_routines.py` and `tests/api/test_setup_vehicles.py` `test_the_company_filter_counts_and_pages_its_matches_only`; scheduled items by kind, company and status, running ones first: `tests/db/test_setup_recurring_routines.py` `test_the_list_filters_by_kind_company_and_status_with_running_items_first` (and the scope and refusal tests beside it), `tests/api/test_setup_recurring.py` the test of the same name | `PeopleFilterByRoleAndWhereTheyAreWithSigningIn` is not built yet (drift register row 8: 08b D6 or a `verify.md` run on `prompt:05`) |
| `ForwardedClientTests` (3), `CompressionTests` (3), `OperabilityTests` (12), `ProductionStartupTests` (4), `OpenApiTests` (2), `ArchitectureTests` (1), `PermissionKeysTests` (6) | `tests/api/test_http_plumbing.py`, `test_compression.py`, `test_operability.py`, `test_openapi.py`; `tests/unit/test_layers.py`; `tests/db/test_enum_parity.py` plus `tests/unit/test_permission_keys.py` (the catalogue, `Permission`, `CellStatus` and the shared `PERMISSION_KEYS` and `REVENUE_STATUSES` lists read from the repository root; `ARefusalNamesAKeyTheCatalogDoesNotLabel` has no counterpart: refusal sentences are fixed strings in `http/messages.py`) | Brotli rows become gzip-only (prompt 09); startup messages name the `XCODE_*` settings; the EF-specific operability tests (`AuthTransactionsWorkWithRetryStrategy`, `TestingEnvironmentDoesNotAutoMigrate`) become the gateway retry test and the "startup runs no DDL" test |
| `MigrationSnapshotTests` (5), `SetupMigrationSnapshotTests` (1), `SqlServerTests` (2), `DemoSeedTests` (3) | `tests/db/test_migrate.py`, `test_schema_structure.py`; `tests/db/test_ops_routines.py` (seed twice) | snapshot and `sp_rename` script tests have no counterpart; `db verify` and the structure tests replace them; the policy clamp data fix is a data-migration check |
| `PettyCashTests` (21 since 9276c51) | `tests/api/test_petty_cash.py`, `tests/db/test_pettycash_routines.py` and `test_pettycash_helpers.py` (prompt 08) | per `docs/inventory/inventory-petty-cash.md` section 5 |

Decisions taken on the inventory's open questions (`inventory-tests.md` section 6.2): the
problem `title` and `detail` strings shown to people are contract and reproduced
(question 1); EF command counts are not (2); the two revenue 409 titles are both kept, each
for its case as `docs/06-http-contract.md` section 1.6 states (3); snapshot JSON names and
audit action names are contract (4, `docs/05-routines.md` section 6.2); no dashboard cache
(5); gzip only (6); a fixed clock instant (7); settings overrides through
`Settings.for_tests(...)` per test app (8); the rate-limit default is asserted by the
settings matrix (9); the duplicate snapshot test is ported once (10); the `useGroupping`
retirement is `docs/13-open-questions.md` question 22 (11).

### 4.1 Tests that pin the design notes v2.29 to v2.33 (prompt 07b)

One or more tests per rule of `docs/15-design-v2-3.md`, each failing without the rule, at
the layer that owns it (routine rules against PostgreSQL, wire facts against the app). The
build session named in the register writes them; a rule without its test is not done.
"Released" rows go to `tests/api/test_contract_released_clients.py` and use the v2.11
request shapes verbatim (all six `AuthRequest` strings, trust by `deviceId`).

| Rules | Test (module :: name) | Asserts |
|---|---|---|
| DN-B1-1, DEC-2 | `tests/api/test_auth_steps.py::test_the_number_step_routes_by_account_state` | one number per state (unknown, PIN, no PIN, forced reset, blocked, locked) gets its status, HTTP code and `purpose`; no answer has a name |
| DN-B1-5, DEC-2 | `::test_the_number_step_answers_an_unknown_number_like_an_account_with_a_pin` | the two answers equal byte for byte (the `Seen` exclusions) |
| DN-B1-5, DEC-2 | `::test_an_unknown_number_counts_down_and_locks_like_a_real_one` | five wrong PINs: `triesLeft` 4..1, then `pin_locked`, equal to a real untrusted account's answers at each step; N01 then `pin_locked` for both; N05 and N03 for the unknown number equal a real one's |
| DN-B1-5 | `::test_pin_checks_are_throttled_per_address_and_per_device` | the 21st PIN check from one address and the 11th from one `deviceId` in ten minutes answer 429 empty with `Retry-After`; other addresses and devices are not affected |
| DN-B1-8 | `tests/api/test_appearance.py::test_appearance_serves_the_idle_unlock_seconds` | `idleUnlockSeconds` 900 for a new organization; `lockoutThreshold` 5 |
| DN-B2-2, DN-B3-1 | `tests/db/test_auth_routines.py::test_the_number_step_sends_a_first_sign_in_or_reset_code` | a code row of the purpose for the device, `check_email`-style silence past the caps (no row, same answer) |
| DN-B3-2, DN-B8-1 | `tests/db/test_access_routines.py::test_making_a_person_reset_ends_their_sessions_at_once` | flag set; every device and refresh token revoked; `security_version + 1`; the session check refuses their token; change-log row `signIn` "PIN reset required, {name}" with the snapshots |
| DN-B3-2 | `::test_people_sign_in_cannot_be_granted_without_holding_it`, `::test_people_sign_in_cannot_be_used_on_oneself`, `::test_only_an_owner_resets_an_owner`, `::test_the_sign_in_actions_need_the_sign_in_right`, `::test_a_scoped_editor_cannot_act_on_a_person_outside_their_view`, `::test_a_pin_reset_already_due_or_without_a_pin_is_unchanged` | `people_permission_not_held` (create and update), `people_self_sign_in`, `people_owner_edit`, `permission_missing`, `XC404`, each for the three actions; a second reset is `unchanged` |
| DN-B3-2, DN-B3-3 (locks) | `::test_a_sign_in_action_waits_for_a_save_of_the_same_person`, `::test_two_resets_at_once_reset_once`, `::test_a_device_removal_racing_remove_all_logs_once`, `::test_a_sign_in_action_leaves_the_membership_open_to_the_change_log_key_check` | two connections: the second waits and sees the first's result; no deadlock with a sign-in event's `KEY SHARE` |
| DN-B3-3 | `::test_removing_one_device_leaves_the_others`, `::test_a_device_row_that_is_gone_or_someone_elses_is_not_found`, `::test_remove_all_is_logged_as_trusted_device_removed`, `::test_remove_all_with_nothing_left_to_remove_is_unchanged`, `tests/api/test_people.py::test_remove_all_is_logged_as_trusted_device_removed`, `::test_removing_one_device_ends_only_that_device`, `::test_making_a_person_reset_the_pin_ends_their_sessions` | one row revoked with its tokens; S11 logs in `signIn`; `unchanged` when nothing is left |
| DN-B3-4, DN-B3-5 | `tests/db/test_access_routines.py::test_the_people_status_follows_the_sign_in_state`, `::test_the_status_filter_accepts_the_new_and_the_legacy_words`, `::test_the_sign_in_pane_lists_live_devices_most_recent_first`, `tests/api/test_people.py::test_the_status_filter_accepts_the_new_and_the_legacy_words` | the five statuses in precedence order; `waiting` and `none` alias; `people_filter_status_invalid`; S06 `signIn` pane with devices for `people.view` |
| DN-B4-1, DEC-1 | `tests/db/test_auth_routines.py::test_five_wrong_pins_on_a_trusted_device_lock_every_device` | the fifth answers `pin_locked`; then trusted and untrusted devices are refused whatever the PIN, nothing counted; refresh refused |
| DN-B4-1, DEC-1 | `::test_five_wrong_pins_from_untrusted_devices_leave_trusted_devices_working` | untrusted devices refused after five; a trusted device signs in with the right PIN |
| DN-B4-1, DEC-1 | `::test_a_right_pin_on_a_trusted_device_does_not_clear_the_untrusted_count` | four untrusted wrongs, a trusted sign-in, one more untrusted wrong: locked for new devices |
| DN-B4-1 | `::test_two_wrong_pins_at_once_both_count_toward_the_lock` | two connections, both counted, the lock written once |
| DN-B4-2 | `::test_only_a_reset_with_a_code_or_clear_pause_unlocks` | no lapse with `p_now` a year later; A09 clears both; `api.ops_clear_pause` clears both scopes (an untrusted-only lock, with no live trusted device, recovers through it) |
| DN-B4-3, DN-B8-1 | `::test_the_lock_is_written_to_the_change_log` | one `signIn` row "PIN locked after 5 wrong tries", `Status` `Locked` after |
| DN-B5-1, DN-B5-2 | `tests/unit/test_policies.py::test_new_pin_problems` | table: `12345` length, `1111`, `1234`, `4321`, `0123`, `6789`, `9876`, the number's last four weak, `8901` and `2468` accepted, the current PIN unchanged |
| DN-B5-2 | `tests/db/test_auth_routines.py::test_a_reset_refuses_the_pin_being_replaced` | `invalid_pin` `unchanged` after a valid code; the code is not consumed |
| DN-B5-4, DEC-7 | `tests/api/test_contract_released_clients.py::test_a_six_digit_pin_still_signs_in_from_a_v211_phone`; `::test_a_new_pin_of_six_digits_is_refused_with_minimum_four` | the old PIN verifies on A01; A06 answers `invalid_pin` with `minimumPinLength` 4 whatever the organization's `pin_length` |
| DN-B6-2, DEC-8 | `tests/db/test_auth_routines.py::test_the_third_wrong_code_voids_it_and_issues_a_replacement` | after three wrongs the code is consumed and a new row exists inside the first minute; N03 `code_resent`; A03 the uniform 401; the mail spy gets the replacement after the reply |
| DN-B6-3 | `tests/db/test_identity_helpers.py::test_codes_are_capped_at_one_a_minute_and_five_an_hour_per_person` | across purposes and devices; superseded codes count, withdrawn ones not; a replacement passes the minute but not the hour |
| DN-B6-3 | `tests/db/test_auth_routines.py::test_a_new_device_code_is_resent_only_after_a_right_pin` | N04 `new_device` issues nothing without a `new_device` code for the device in the last ten minutes, and answers the same |
| DN-B6-4 | `tests/unit/test_mail_templates.py::test_the_code_email_holds_the_code_the_purpose_and_the_device_only` | exact body for each purpose; `Unknown device` without a name |
| DN-B7-1, DEC-4 | `tests/unit/test_device_tokens.py`; `tests/db/test_auth_routines.py::test_device_token_is_stored_only_as_its_digest` | 43 Base64url characters; SHA-256 upper hex in `token_hash`; the raw token nowhere in the database |
| DN-B7-1, DEC-5 | `::test_a_device_trusted_with_a_token_is_not_trusted_by_its_id_on_the_old_routes`; `::test_a_new_route_with_no_token_does_not_trust_a_legacy_row_by_device_id`; `tests/api/test_contract_released_clients.py::test_a_v211_phone_trusted_by_device_id_signs_in_with_the_pin` | A01 with the id of a token row asks for a code; N02 with a legacy row's `deviceId` and no `deviceToken` is not PIN-only trusted (asks for the PIN, then a code like any untrusted device); a legacy row still signs in on the old routes |
| DN-B7-2 | `::test_a_device_unused_for_90_days_needs_a_code` | `p_now` 90 days after `last_used_at`: PIN step asks for a code, session refused; a refresh inside the window moves `last_used_at` |
| DN-B7-3 | `::test_a_pin_reset_removes_every_other_device` | after A09 or N06 `pin_reset` only the completing device is live |
| DN-B7-5, DEC-6 | `::test_an_untrusted_sign_in_gives_a_session_but_not_a_remembered_device` | `trustDevice` false: tokens issued, no `deviceToken`, the next N02 asks for a code, A11 revokes the row |
| DN-B7-6 | `tests/api/test_auth_steps.py::test_change_pin` | right current PIN: `pin_changed`, devices and sessions kept, "PIN changed"; wrong current PIN counts toward the every-device lock; `pinProblem` cases |
| DN-B7-7 | `::test_own_devices_are_listed_and_removed` | N08 lists live remembered rows with `thisDevice`; N09 removes, another user's id is 404; removing this device ends the session |
| DN-B8-2 | `tests/db/test_auth_routines.py::test_ordinary_sign_ins_go_to_the_history_not_the_change_log` | a sign-in writes an attempt row and `last_signed_in_at`, and no change-log row |
| DEC-3, question 54 | `tests/api/test_contract_released_clients.py` (the v2.11 auth rows) | number and PIN together, trust by `deviceId`, the seven-property envelope; the byte-for-byte refusals of `test_auth_contract.py` hold for unknown, blocked, reset-due and locked-untrusted accounts |
| DN-B9-1 to DN-B9-7, DEC-14 | `tests/db/test_setup_target_routines.py` (every test); `tests/db/test_setup_races.py::test_two_target_sets_saved_for_one_date_at_once_leave_the_later_one`, `::test_a_target_set_saved_while_its_vehicle_leaves_waits_and_is_refused`, `::test_a_target_set_removed_while_it_is_replaced_waits_and_the_replacement_is_gone`; `tests/api/test_setup_targets.py` | a set starting today and later ones; a past start refused; equal to the set in force on its date refused with `{date}`; a future set replaced and removed; today's set replaced, not removed; a started set not removed; "Target set, {reg}" and "Target removed before it started, {reg}" with the sets before and after; two saves on one vehicle at once serialised by the vehicle lock; a save waits for a retire and is refused; S47 to S49 over HTTP |
| DN-B9-2 | `tests/db/test_setup_helpers.py::test_a_day_target_is_the_weekday_figure_of_the_set_in_force`, `::test_there_is_no_day_target_while_away_after_leaving_or_without_a_set`, `::test_the_set_in_force_is_the_latest_started_and_its_week_total_is_the_sum_of_seven`; `tests/db/test_setup_vehicle_routines.py::test_the_report_counts_money_in_the_target_each_bucket_and_savings_once` (the report target is the sum of the day targets); `tests/db/test_revenue_helpers.py::test_vehicle_days_agree_with_the_setup_predicates_day_by_day` (D4) | Saturday and Sunday differ; a new set never changes an earlier week |
| DN-B9-8, DN-B9-10, DEC-13, DEC-15 | `tests/db/test_setup_vehicle_routines.py::test_create_adds_the_vehicle_with_its_first_target_set_from_the_join_date_and_says_so`, `::test_create_needs_seven_day_targets_that_are_money`, `::test_a_new_fleet_number_is_saved_and_said_and_the_targets_stay`, `::test_moving_the_join_date_before_the_first_set_copies_the_first_set_to_it`; `tests/db/test_setup_target_routines.py::test_saving_and_removing_need_vehicles_target_alone`; `tests/api/test_setup_vehicles.py::test_editing_a_vehicle_leaves_its_targets_alone`; `tests/api/test_mass_assignment.py::test_a_vehicle_body_cannot_set_its_leave_date_targets_or_away_periods` | seven required on create, from the join date; an update with any `weeklyTarget` changes no set; S48 and S49 without `vehicles.target` are 403, with it alone allowed |
| DN-B9-9, DN-B9-11 | `tests/api/test_setup_vehicles.py::test_the_list_shows_the_target_in_force_and_the_next_one`; `tests/db/test_setup_vehicle_routines.py::test_the_list_carries_targets_scheduled_items_and_away_periods_for_a_manager`, `::test_the_set_in_force_shows_while_the_vehicle_is_away_but_no_weekly_target_counts` | `weeklyTarget` = sum; `dayTargets` the set in force; `nextTarget` with its date; `targets` (released clients) holds only started sets |
| DN-B10-1, DN-B10-2 | `tests/db/test_setup_vehicle_routines.py::test_create_needs_a_fleet_number_of_at_most_twenty_characters`, `::test_a_fleet_number_is_unique_in_its_company_whatever_the_case`, `::test_an_update_refuses_a_fleet_number_another_vehicle_of_the_company_uses`, `::test_update_checks_in_order`; `tests/db/test_setup_races.py::test_two_vehicles_with_one_fleet_number_racing_leave_one_row_and_a_unique_conflict`; `tests/db/test_setup_helpers.py::test_an_empty_or_long_fleet_number_is_refused` | create and update without it refused; the same number in two companies allowed, in one refused (also through the unique index on a race); a change logged |
| DN-B10-3, DN-B10-4 | `tests/api/test_setup_vehicles.py::test_vehicle_options_carry_the_fleet_number`; `tests/db/test_setup_recurring_routines.py::test_the_picker_offers_only_vehicles_a_new_share_can_use` (S25); `tests/db/test_access_routines.py::test_scope_options_exclude_vehicles_that_left_or_wait_to_join_or_have_an_archived_company`, `::test_my_scope_of_a_vehicle_scoped_member_is_their_vehicle_and_its_company` (S03, S04); `tests/api/test_revenue.py::test_the_week_search_matches_registration_or_fleet_number` (D4); `tests/db/test_revenue_routines.py::test_the_search_finds_only_vehicles_the_viewer_may_see` | options of S03, S04, S25 and R01; `q` filters before paging and the totals follow; a scoped viewer's search finds no hidden vehicle and its whole-grid figures count none |
| DN-B11-1 | `tests/db/test_setup_vehicle_routines.py::test_an_initial_investment_is_optional_and_zero_means_none`, `::test_the_initial_investment_is_changed_or_cleared_and_said` | null and 0 store null; a negative or three-decimal amount refused; clearing logged |
| DN-B12-1 to DN-B12-3 | `tests/db/test_back_limit.py::test_earliest_writable`, `::test_a_month_back_from_a_month_end_is_the_last_day_of_the_shorter_month`, `::test_a_fixed_date_later_than_the_rolling_limit_wins`, `::test_no_limit_writes_any_date` | table: none; 0 days (today only); 7 days; 1 month from 31 March (28 February, 29 in a leap year); 1 month from 30 June (30 May); a fixed date later and earlier than the rolling one; both null |
| DN-B12-6 | `tests/db/test_back_limit.py::test_the_limit_turns_at_midnight_in_the_organization_zone`, `::test_a_held_business_date_moves_the_limit` | `p_now` 23:59:59 and 00:00:00 Africa/Nairobi, then America/New_York (daylight saving) at the same instant; `record_too_old` names the earliest date |
| DN-B12-4, DN-B12-7, DN-B12-8 | `tests/db/test_access_routines.py::test_a_new_person_starts_on_seven_days_back`, `::test_a_back_limit_change_is_logged_with_the_access_change`, `::test_a_back_limit_needs_a_known_mode_and_a_count_in_range`, `::test_a_back_limit_inside_the_bounds_is_accepted`, `::test_a_fixed_date_after_the_business_date_is_refused`, `::test_my_scope_carries_the_actors_limit_and_earliest_date`, `tests/db/test_back_limit.py::test_can_change_words`, `tests/api/test_people.py::test_a_back_limit_is_saved_read_back_and_refused_when_out_of_range` | the words of the notes' examples; the bounds 0-3650 days and 0-120 months on both sides |
| DN-B12-5, DN-B12-6, DEC-12 | `tests/db/test_revenue_routines.py::test_capture_and_change_respect_the_back_limit`, `::test_an_offline_replay_is_checked_at_its_capture_time_within_72_hours`, `::test_an_identical_replay_is_answered_whatever_the_limit`, `::test_capture_fills_and_correct_changes` (the cells), `::test_the_capture_time_is_read_on_the_organizations_calendar` (midnight in Nairobi and New York), `tests/api/test_revenue.py::test_a_capture_time_moves_the_back_limit_within_72_hours` | `record_too_old` after the permission check; `capturedAt` honoured, clamped; replay before every check |
| DN-B13-1, DEC-9, DEC-10 | `tests/unit/test_permission_keys.py::test_the_permission_enumeration_equals_the_catalogue_in_order`, `::test_the_catalogue_has_the_rights_of_the_prototype_one_to_one`, `::test_released_clients_read_only_keys_the_server_still_issues` (the 40 `PERMISSION_KEYS` of `packages/shared` are the 19 kept keys plus the 21 non-catalogue ones), `tests/db/test_enum_parity.py`, `tests/db/test_tenancy_helpers.py::test_legacy_keys_are_derived_never_granted`, `::test_only_owners_hold_the_hidden_organization_key`, `tests/db/test_access_routines.py::test_a_legacy_key_cannot_be_granted`, `::test_the_hidden_organization_key_cannot_be_granted_even_by_an_owner`, `::test_only_owners_manage_organization_settings`, `tests/api/test_contract_released_clients.py::test_the_session_keeps_the_keys_a_v211_phone_gates_on` | the rows equal `docs/15` 3.1 (a fixture), and the prototype's `MODS` ids and labels map one to one; the token carries the legacy keys; the person save refuses them |
| DN-B13-1 | `tests/db/test_migrate.py::test_the_grant_translation_keeps_what_each_person_could_do` | people of every role with grants and denials seeded at version 8, their sets read by the unchanged resolver, then migrated: every old key's translation held, every legacy key with a held source still held, the Owner holds every right; no override names a legacy key |
| DN-B13-2 | `tests/db/test_access_routines.py::test_the_people_list_shows_modules_can_change_and_status`, `tests/api/test_people.py::test_a_created_person_reads_back_in_the_wire_order` | `modules`, `everything`, `canChange`, `status`, `lastSignedInAt`, `backLimit`, `signIn` |
| DN-B13-4 | `tests/db/test_access_routines.py::test_blocking_needs_the_block_right`, `::test_scope_options_open_to_either_right_alone`, `::test_step_14_single_permissions_need_people_edit`, `tests/api/test_people.py::test_people_routes_need_their_permissions` | `people.block` gates S09/S10; `people.add` or `people.edit` S03; single permissions and limits need `people.edit` |
| DN-B14-1 to DN-B14-3, DEC-16 | `tests/db/test_revenue_routines.py::test_a_low_day_needs_a_reason`, `::test_the_entry_shape_is_checked_before_the_vehicle`, `::test_the_threshold_is_checked_after_the_vehicle_and_before_the_date`, `::test_an_identical_replay_is_answered_whatever_the_threshold`, `tests/db/test_constraints.py` (`ck_records_entry`), `tests/api/test_revenue.py::test_a_low_day_is_saved_with_its_reason`, `::test_an_entry_that_cannot_be_recorded_is_a_400`, `tests/api/test_contract_released_clients.py::test_a_v211_phone_retrying_an_entry_saved_under_another_threshold_gets_its_answer` | 3,999 without a reason `revenue_low_needs_reason`; with one stored with both; 4,000 with a reason refused; 0 with a reason stored as a reason alone; Other without a note accepted; the threshold read from the setting and checked after the identical replay, so an entry already stored (before the rule or under another threshold) is answered `replayed` |
| DN-B14-4 | `tests/db/test_revenue_routines.py::test_below_threshold_days_count_low_and_no_revenue_days`, `tests/db/test_revenue_helpers.py::test_low_days_are_judged_by_their_amount_against_the_threshold` | low days in the totals; `belowThresholdDays` counts reason-only days and amounts below the threshold, an old record of 3,500 without a reason included |
| DN-B14-5, DN-B14-6 | `tests/db/test_revenue_routines.py::test_capture_fills_and_correct_changes`, `::test_a_reason_needs_only_the_right_of_its_path`, `tests/db/test_revenue_helpers.py::test_who_may_open_a_cell_follows_its_status_day_and_limit`, `tests/api/test_contract_released_clients.py::test_what_a_v211_phone_can_no_longer_save_answers_with_a_sentence` | capture only cannot change today's saved record; correct changes any; `can_edit` per right and limit |
| DN-B15-1, DN-B15-2 | `tests/db/test_revenue_helpers.py::test_the_gap_counts_the_days_so_far`, `::test_gap_band`, `::test_each_day_expects_its_own_figure_and_the_week_sums_them`, `tests/db/test_revenue_routines.py::test_the_week_carries_the_gap_and_its_band`, `::test_the_revenue_settings_default_save_and_log_in_the_organization_section`, `::test_revenue_settings_out_of_range_or_of_the_wrong_kind_are_refused`, `::test_only_owners_change_the_revenue_settings` | today counted only once recorded; a finished week all seven; band edges at exactly the amber percent |
| DN-B15-3, DN-B15-4 | `tests/api/test_revenue.py::test_the_week_carries_the_gap_and_the_day_targets`, `::test_the_week_in_wire_order_with_its_cells_and_figures`, `::test_the_revenue_settings_are_read_and_saved_by_the_owner`, `tests/db/test_revenue_helpers.py::test_vehicle_days_agree_with_the_setup_predicates_day_by_day` (against `setup.day_target`) | `expected` is the day target; `gap`, `gapBand`, settings in the body |
| DN-B16-1 to DN-B16-6, DEC-17 | `tests/db/test_setup_main_category_routines.py` (every test); `tests/db/test_setup_expense_routines.py::test_a_category_is_created_under_a_main_category_and_says_so`, `::test_the_rename_and_move_reasons`, `::test_a_category_update_checks_name_then_record_then_main_category_then_uniqueness`; `tests/db/test_migrate.py::test_the_setup_migration_splits_weekly_targets_and_groups_categories_by_bucket`; `tests/api/test_mass_assignment.py::test_a_category_body_bucket_is_accepted_and_ignored` | create, rename, unique; a category without one; moving a category regroups its items; `categoriesWithoutMain`; one main category per bucket in use after `0010` |
| DN-B16-7 | `tests/db/test_setup_expense_routines.py::test_each_catalogue_write_needs_its_own_right`, `::test_reading_needs_catalogue_expense_or_schedule_access`; `tests/db/test_setup_main_category_routines.py::test_adding_needs_catalog_add_and_renaming_catalog_edit` | |
| DN-B17-1, DN-B17-3 | `tests/db/test_setup_recurring_routines.py::test_the_rights_of_one_kind_reach_no_item_of_the_other`, `::test_switching_the_kind_needs_the_edit_right_of_both_kinds`, `::test_viewing_rights_alone_cannot_open_the_vehicle_picker`, `::test_every_revise_names_the_kind_and_the_item_as_it_ends`; `tests/db/test_setup_helpers.py::test_an_item_is_hidden_from_a_member_without_the_view_right_of_its_current_kind` | each kind needs its own rights; the list leaves out the kind not viewable; reasons "Saving, {name}" and "Scheduled expense, {name}" |
| DN-B17-2 | `tests/db/test_migrate.py::test_the_grant_translation_keeps_what_each_person_could_do` | `commitments.*` holders get both kinds |
| `docs/15` section 4 | `tests/api/test_contract_released_clients.py` | one row per line of the table, with the deliberate changes asserted as the new answer |
| every new or changed routine | `tests/db/test_fakes_match_routines.py` | the fakes of `tests/support/fakes.py` for the new routines (each build session adds its own) pass the shared contract cases |

### 4.2 The .NET classes of 9 and 10 October (prompt 08b; drift register row 12)

Methods and their decisive assertions: `docs/inventory/inventory-expenses-reports.md` section 5. The substitutions of
section 4 apply; where the design notes decide (`docs/15-design-v2-3.md` B9, B11, B12, B16, B18 and `DEC-30` onward),
the Python test asserts the notes' answer and its name says so.

| .NET class | Python module(s) | What changes |
|---|---|---|
| `CentralExpenseTests` (17) | `tests/api/test_expenses.py` (each scenario, same assertions, the change-log reasons verbatim); rules in `tests/db/test_expense_routines.py` (one test per `CE-*` rule and per `Raises:` code; the two-connection purchase race; the stale writer's 409 with `current`; split rows as one row per vehicle with one group and no cent lost or invented, over a table of splits including 100 / 3 and negative refunds) | `ASaveThatLosesARaceOnTheVersionIsAConflictNotAnOverwrite` becomes a two-connection test on the row lock (the stale writer gets `expense_version_conflict`); `TheLedgerReadsTheSameNumberOfTimesHoweverManyRowsThePeriodHolds` becomes the 2-statement budget plus `EXPLAIN` at 5, 150 and 300 rows (`docs/perf/expenses.md`); permission sentences use the 59 labels (`Edit an expense`); B12 adds `test_a_central_expense_before_the_limit_is_refused_on_record_change_and_remove` |
| `CentralExpenseDomainTests` (5) | `tests/db/test_expense_routines.py` (`expenses.check_purchase` and the detachment rule, against PostgreSQL) | domain tests move to routine tests (the rules live in SQL) |
| `ReportTests` (13) | `tests/api/test_reports.py` (contract, files opened and read cell by cell, the change-log reasons); `tests/db/test_report_routines.py` (each builder, `reports.page`, `reports.cell_text`, the period checks, scope); `tests/unit/test_export_files.py` (the two adapters on fixed documents: layout cells, number formats, quote prefix, page size, embedded fonts) | `NetByVehicleAgreesWithEachVehicleReport` asserts per-main-category columns (`DEC-38`) and still equality with each vehicle report; `MoneyOutGroupsEverySourceByItemAtTheTrueUnitCost` adds the main category; `SavingsCountRunsInThePeriodAndTheBalanceSinceEachSavingBegan` asserts saved, skipped and held runs and the opening balance (B18); `InvestmentShowsWhatCameBackSinceJoiningAndNeedsItsPermission` adds the initial investment and the vehicle without one last (`DEC-39`); `PettyCashReportsFollowTheFloatsAPersonMaySee` uses B19's statuses and `pettycash.reports`; the PDF test opens the file with `pypdf` (pages 842 x 595, the three fonts embedded) |
| `RecurringPauseTests` (4) | `tests/api/test_recurring_pause.py`; `tests/db/test_recurring_pause_routines.py` (pause, resume, the same-day resume, a stop, the overlap and one-open-pause constraints, the runs and summary figures, the saving rule's held, skipped and saved runs, the two-connection decision, the opening balance) | the change-log reasons are `Saving, {name}` (DN-B17-3, `DEC-43`); rights `savings.pause` / `scheduled.pause` |
| `RevenueDayTests` (4) | `tests/api/test_revenue_day.py`; `tests/db/test_revenue_day_routines.py` (one test per D4 rule a row runs; all or none; the vehicle named in a 400; the 409's `vehicleId`; two day saves over the same vehicles in opposite orders finish without a deadlock) | rows run D4's rules (the threshold, `revenue.correct` for today's saved record, the back-dating limit), not .NET's older ones |
| `ListFilterTests` (3) | built: `tests/api/test_people.py`, `test_setup_vehicles.py`, `test_setup_recurring.py` and their routine modules (section 4's `ListFilterTests` row) | the 08b build re-checks them against the .NET class in its drift check; `test_list_filters.py` holds any scenario found missing |
| `VehicleReportTests` (the parts changed in 9276c51) | `tests/api/test_setup_vehicles.py`, `tests/db/test_setup_vehicle_routines.py` | `CentralExpensesReachTheReportUnderTheirBucketAndOneReadCoversAnyNumberOfThem`: central postings with `source` `central`, one statement however many; every posting source through `setup.fleet_postings` |
| `PettyCashTests` (the working tree's two new methods) | prompt 08's modules (drift row 7) | shared purchases add `tests/db/test_pettycash_routines.py::test_a_shared_purchase_is_one_entry_per_vehicle_and_recounts` |
| none (released clients) | `tests/api/test_contract_released_clients.py`: raw-JSON rows for the ledger and options, the reports catalogue and one report per group, the scheduled-items summary | the property names, kinds and order the web reads (`docs/06` 2.13) |

## 5. Commands

```
pytest tests/unit                 # seconds, no database
pytest tests/db -n auto           # routines and structure
pytest tests/api -n auto          # HTTP contract
pytest -n auto                    # everything
ruff check . && ruff format --check . && mypy
xcode-api db verify               # against the test database URL
```

Measured, not targeted: about 3 200 tests took 57 minutes with `-n 4` on a quiet 4-core
Windows machine and one to two hours with `-n 3` while other sessions ran (2026-10-10);
`-n 4` once stopped for low memory. The original target of five minutes is not met; each
database test pays about 4 s for its clone. So:
- run the touched modules first (`pytest tests/db/test_x.py tests/api/test_x.py`);
- run the full suite once per change set, in the background, with a log file, and read the
  counts from the log; a partial run is evidence only for what it ran;
- after changing a migration, a routine file or the runner, the next run rebuilds
  `xcode_template` by itself; when it refuses because another session is running, wait
  for that run to end and rerun. Never drop the template by hand under another session's
  run (`pg_stat_activity`, the `test_gw*` databases).

The local cluster on the development machine is PostgreSQL 16 (port 5433, trust
authentication, `XCODE_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5433/postgres`);
Docker is not installed there, so the `testcontainers` fallback does not run. CI is
configured for PostgreSQL 18 but has not run (nothing is committed). The version on the
production host is not known yet (`docs/13-open-questions.md` question 39).

## 6. What the .NET suite did that this one does differently

- SQLite in-memory is gone; the Guid-case trap and `EnsureCreated`-only schema disappear
  with it. `MigrationSnapshotTests` is replaced by `test_migrate.py` plus `db verify`.
- Query-count assertions (`VehicleReportTests`, `PeopleQueryCostTests`,
  `RecurringQueryCostTests`, `RevenueComplexityTests`) become statement-budget assertions
  (normally 1 routine call per request; the budget table lists the exceptions).
- `AuthTests.Seen` byte-for-byte response comparison stays, implemented by comparing status,
  body bytes and headers minus `X-Request-ID` and `Date`.
- Timing-sensitive tests (lockout minutes, trust expiry, code expiry) use `ManualClock`
  through `p_now`, never `sleep`.
