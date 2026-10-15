# Verification of prompt 07b D2 (people and access), 2026-10-12

`SCOPE: area:prompt 07b D2`, `MODE: fix`, `DEPTH: standard`. Method: `docs/14-verification.md`.
Session revenue-a8 [c5ed4b], registered on the coordination board at 13:52. The shared full
run of the day (started 13:00 by the coordinator, `-n 2`, a fresh `xcode_template_full` from the
live tree) froze `src/`, `db/` and `tests/` for the whole reading pass; this report reads its log
for the D2 modules, and the one fix landed after the freeze lifted.

## 1. Verdict

**pass with findings.** No blocker survives. The full suite ran to completion once on a fresh template built from the files under test (the coordinator's shared run, 13:00 to 15:23, 5617 passed and 42 failed); every D2 module in it is green, and the 42 failures belong to other scopes' in-flight work except three stale key counts that `0009` changed on purpose, fixed here. One major (an integer outside its column type answered 500 on the people routes) is fixed with a failing-first test; two minors and three notes are recorded. The one document line of the fix (`docs/06` 1.2) lands after D4's landing of the same file; until then the fix is code and test only.

| Verdict | Claims |
|---|---|
| holds | 22 (C1 to C20, C22, C23) |
| fails | 1 (C21, fixed) |
| unproven | 1 (C25) |
| n/a | 0 |
| not checked | 1 (C24) |

| Severity | Surviving findings |
|---|---|
| blocker | 0 |
| major | 1 (V-D4-1, fixed) |
| minor | 2 (V-D10-1, V-D11-1) |
| note | 3 (N-1 to N-3) |

## 2. Thesis and claims

Thesis (steelmanned): prompt 07b D2 delivers the people-and-access rows of the design notes
v2.32 and v2.33 ahead of .NET: the 59-right catalogue with its role defaults, dependencies, the
20 derived legacy keys and the hidden Owner key; a migration (`0009_access`) that rewrites every
membership's overrides so each person keeps what they could do; three people sign-in actions
(make reset, remove one device, remove all) that act at once, are gated by the new right
`people.sign_in`, obey the Owner and self rules and are logged in the `signIn` section with the
notes' wording; the five people statuses with their filter; the "can change" summary; and the
back-dating limit as a per-person setting with the earliest-writable helper and the 7-day default,
all without breaking a v2.11 phone or today's web beyond the changes `docs/15-design-v2-3.md`
section 4 lists. Every rule has a test against PostgreSQL that fails without it.

| # | Claim | Stated in | Carried by | Verdict | Grade |
|---|---|---|---|---|---|
| C1 | 59 catalogue rights in 12 modules, labels and order of the prototype, each non-base right needing its module's view right (48 dependencies) | `docs/15` 3.1, DN-B13-1 | `db/migrations/0009_access.sql` (permissions, dependencies), `api.access_catalog_list` | holds | A: `tests/db/test_access_routines.py` 1-6, `tests/unit/test_permission_keys.py` (prototype `MODS` one to one), `tests/api/test_access.py::test_every_member_reads_the_catalogue_in_its_shape`; counts measured on the work copy: 80 keys, 59 catalogue, 48 dependencies, 111 role defaults, 32 sources, 58 translations |
| C2 | Role defaults of `docs/15` 3.2 (60 + 37 + 11 + 3) | `docs/15` 3.2 | `0009_access.sql` role_defaults | holds | A: routine tests 10-13, `test_access.py::test_roles_need_people_view_and_list_by_name`; measured per role on the work copy |
| C3 | Legacy keys are derived from held sources, never granted; a denied legacy key stays off; the hidden `organization.manage` only through the Owner role | `docs/15` 3.3, 3.4, DEC-9, DEC-10 | `tenancy.effective_permissions`, `tenancy.permission_sources`, `check_person_grant` (catalogue keys only) | holds | A: `test_tenancy_helpers.py::test_legacy_keys_are_derived_never_granted`, `::test_a_denied_legacy_key_stays_off_though_its_source_is_held`, `::test_only_owners_hold_the_hidden_organization_key`; routine tests 65, 66, 186 |
| C4 | The grant translation keeps what each person could do; the Owner gets every right; dropped keys only on purpose; no override names a non-catalogue key | `docs/15` 3.5, `docs/04` 13.2 | `0009_access.sql` (old sets read by the migration's own resolver, translation table, rewritten overrides, closing `DO` checks) | holds | A: `tests/db/test_migrate.py::test_the_grant_translation_keeps_what_each_person_could_do` (seeded at version 8 with grants and denials per role) |
| C5 | "Make [name] reset the PIN": every device, refresh token and unused code removed, the security version bumped, `pin_reset_required` set, logged "PIN reset required, {First Last}"; `unchanged` for no PIN or a reset already due | DN-B3-2, `docs/05` 10.3, `docs/07` 12.11 | `api.people_pin_reset` | holds | A: routine tests 161, 162, 171 (two at once reset once), `tests/api/test_people.py::test_making_a_person_reset_the_pin_ends_their_sessions` (session 401, refresh 401, pane, history) |
| C6 | Remove one device: that row and its tokens go, the others stay; a row that is gone, someone else's or an Owner's (to a non-Owner) is 404 after the Owner rule | DN-B3-3, `docs/05` 10.3 | `api.people_device_remove`, `identity.remove_devices(user, row)` | holds | A: routine tests 163, 164, 166, 172 (racing remove-all logs once), API `test_removing_one_device_ends_only_that_device` |
| C7 | Remove all (S11) under `people.sign_in`, logged in `signIn` as "Trusted device removed, {name}", `unchanged` when nothing is left | DN-B3-3, DEC-19 | `api.people_sign_out` | holds | A: routine tests 123, 124, 156, 157; API `test_remove_all_is_logged_as_trusted_device_removed` |
| C8 | The three actions refuse self, need `people.sign_in`, obey the Owner rule and the editor's view | DN-B3-2 (D2 evidence clause) | the three routines (`people_self_sign_in`, `enter_organization(..., 'people.sign_in')`, `people_owner_edit`, `person_in_view`) | holds | A: routine tests 165-168 (each for the three actions), API `test_self_lifecycle_and_sign_out_are_refused`, `test_people_routes_need_their_permissions` |
| C9 | `people.sign_in` cannot be granted without holding it (create and update) | D2 evidence clause | `check_person_grant` (`people_permission_not_held`) | holds for granted rights; see V-D1-1 (conceded, parity) for a lifted denial | A: routine test 169 |
| C10 | Statuses Active, Not signed in yet, PIN reset due, Locked, Blocked, in that precedence; the list filter with the legacy words `waiting` and `none`; an unknown word refused after the permission and page checks | DN-B3-4, `docs/06` S05 | `identity.sign_in_status`, `api.people_list` | holds | A: routine tests 174, 175, 94-96; API `test_the_status_filter_accepts_the_new_and_the_legacy_words`, `test_the_people_page_keeps_one_role_and_one_sign_in_state` |
| C11 | The "Sign in" pane (`signIn`) on S06 with status, lock, last sign-in, email and live remembered devices most recent first | DN-B3-5 | `tenancy.person_sign_in`, `api.people_get` | holds | A: routine test 176, API `test_a_created_person_reads_back_in_the_wire_order` |
| C12 | "Can change" words, `modules` chips, `everything`, `backLimit` on every person document; the wire order keeps .NET's 16 properties first | DN-B12-8, DN-B13-2, `docs/06` S05 | `tenancy.back_limit_words`, `tenancy.person_document` | holds | A: `test_back_limit.py::test_can_change_words` (10 cases), routine tests 108, 177; API `PERSON_KEYS` order (compared with `AccessContracts.cs:15-18`) |
| C13 | The limit is stored on the membership as mode, count, date, with the `CHECK` constraints; a change is logged with the access changes and bumps the membership version | DN-B12-7, `docs/04` 13.2 | `0009_access.sql`, `tenancy.save_person`, `tenancy.person_snapshot` | holds | A: routine tests 179-184, `test_constraints.py` rows (0009), constraint text measured on the work copy |
| C14 | `tenancy.earliest_writable`: days back, months back falling to the month's last day, the later of rolling and fixed, NULL for any date; `check_writable` on the business date of the organization's zone | DN-B12-1 to 3, `docs/05` 10.2 | `earliest_writable.sql`, `back_limit_earliest.sql`, `check_writable.sql` | holds | A: `test_back_limit.py` (19 table rows: 0 days, 3650 days, 29 February, 31 March to 28/29 February, 30 June, fixed later and earlier, held business date, midnight Nairobi and New York) |
| C15 | New people start at 7 days back; an update without a mode keeps the stored limit; shape refusals (`people_back_limit_invalid`, `people_back_limit_date_future`) in the contract's step order | DN-B12-4, `docs/05` 10.3 | `tenancy.save_person` | holds | A: routine tests 178-183, API `test_a_back_limit_is_saved_read_back_and_refused_when_out_of_range` |
| C16 | A non-Owner gives no limit looser than their own, on create and when the limit changes; an Owner gives any | `docs/05` 10.3, `docs/12` 2.7 | `tenancy.save_person` (`people_back_limit_not_held`) | holds (with the day-dependence note N-1) | A: routine tests 188-191 (9 parametrised cases) |
| C17 | Gates: `people.add` (S07), `people.edit` (S08), `people.block` (S09/S10), `people.view` (S02, S05, S06), any of add/edit (S03) | `docs/06` 2.12.4 | the routines' `enter_organization` calls | holds | A: routine tests 97, 187, 20, 21, API `test_people_routes_need_their_permissions`; the tenant-guard sweep: every `api.*` routine of `30_tenancy` calls `tenancy.enter_organization` |
| C18 | `GET /setup/access/me` carries `canChange` and `earliest` | `docs/05` 10.3 | `api.access_my_scope` | holds | A: routine test 185, API `test_my_scope_lists_the_callers_own_reach` |
| C19 | Released clients: a v2.11 phone and today's web keep working; the deliberate changes (retired keys on S07/S08 refused; S01 lists 59 keys) are listed | invariant 2, `docs/15` section 4 | the token's legacy keys, the kept routes | holds pending the run | B until the run: `tests/api/test_contract_released_clients.py` (people rows, `_PHONE_GATES` per role, catalogue shape); counted below |
| C20 | Routes, operation ids and tags agree between the router, OpenAPI, `docs/06` and the .NET table (S45 and S46 absent from .NET by design) | D4 | `http/routers/access.py`, `xcode-api openapi` | holds | A: measured (section 8); the generated `422` rows are the known 06:V-D4-3 (prompt 09) |
| C21 | A malformed body answers 400 naming the field, never 500 | `docs/06` 1.2, section 3; .NET binder parity | `http/schemas/access.py` | **fails** for integers outside their column types | V-D4-1 (fixed) |
| C22 | Lint, types, all tests green; `db verify` exit 0; no TODO or prompt identifiers | invariant 4 | | holds for the D2 modules; the project-wide suite is red on other scopes' in-flight work (section 8) | measured: ruff clean (394 files), sweeps clean, `db verify` 21/21 on the work copy; mypy and the full run below |
| C23 | The documents describe the code (`docs/04` 13.2, `05` 10.2 and 10.3, `06` 2.12, `07` 12.11, `09` 4.1, `12` 2.7, `13` q58/q65/q71, README row 07b) | D11 | | holds with V-D11-1 (minor) | read clause by clause against the code; the tests `docs/12` 2.7 names exist |
| C24 | The migration applies on the CLI database `xcode` and its routines follow | build report | | not checked | `xcode` holds `0009` with routines deferred until `0010` and `0012` land (board, Numbers); its `db verify` is another session's step |
| C25 | Heavy reads keep their plans at 10x the seed | D7 | `api.people_list` | unproven | no `EXPLAIN` run (memory cap during the shared run); budget asserted at 2 statements per route |

## 3. Findings

| id | mode | claim attacked | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| V-D4-1 | falsification, red team (clerk) | C21: a malformed body is a 400 naming the field (`docs/06` 1.2 Numbers; the .NET binder refuses an integer it cannot hold) | `POST /setup/people` with `backLimit.count = 2147483648` (or `PUT .../people/{id}` and the lifecycle body with `version = 2^63`): expected 400 `Invalid setup change` with `errors.backLimit.count`; actual 500. psycopg sends a Python `int` as the smallest PostgreSQL type that holds it, so `2^31` arrives as `bigint`, `api.people_create(... integer ...)` is not found (SQLSTATE 42883) and `db/errors.py:87` turns the unknown state into `IntegrityBug` | `src/xcode_api/http/schemas/access.py` `BackLimitBody.count: int \| None`, `SavePerson.version`, `PersonLifecycleRequest.version` (no bound); `db/session.py:65` binds with bare `%s`; probe on the cluster: `pg_typeof(2147483648)` = `bigint`, `pg_temp.f(integer)` called with it: `42883 function pg_temp.f(bigint) does not exist`; the generated OpenAPI shows plain `integer` for all three | looked for a bound in `ApiModel`, the fields, the router and the gateway; none. The setup, petty-cash and revenue schemas bound theirs (`Int32`, `Version`), and the people list already bounds `page` and `pageSize` for this reason, so the people body is the gap | survives, major (a 5xx on a reachable path; the same class verify-07 fixed for amounts) | fixed: `Int32`/`Int64` bounds in `schemas/access.py`; test `tests/api/test_people.py::test_integers_beyond_their_column_types_are_refused_before_the_routine` (15:40 `1 failed` on the unfixed schema with a 500, 15:41 `1 passed` with the fix); `docs/06` 1.2 Numbers row gains the integer sentence |
| V-D10-1 | falsification (D10) | C9 and `docs/12` 2.7 row "The new people right cannot escalate": the fakes mirror the routines | `tests/support/fakes.py` has no `people_back_limit_not_held`; the shared parity case `keep_a_back_dating_limit` runs as the Owner, so the looser-limit rule is never exercised through the fake, and a use-case test could pass against a fake that lacks the rule | `grep people_back_limit_not_held tests/support/fakes.py` (no hit); `tests/support/tenancy_cases.py:200-224` | the rule's evidence is the routine tests 188-191 (grade A), which `docs/09` 1 says is where business rules are proven; the fake is orchestration only | survives, minor (coverage gap in the parity harness, no failure scenario in production) | recorded here; no fix (adding a non-Owner editor to the parity case belongs with the next fakes change, see section 10) |
| V-D11-1 | Socratic (D11) | C23: `docs/06` 1.2 states every body rule a client can hit | the Numbers row says what an input amount must fit and says nothing about integers, although three schema modules bound them and this report's fix makes the people body do the same; a reader building the next body would not know to bound an `int` | `docs/06` 1.2 Numbers row | read sections 1.2, 2.12.4 and 5 for an integer rule; none | survives, minor (a document that would make the next session build the gap again) | doc corrected with the fix: one sentence in the Numbers row |

Notes (no failure scenario; recorded for the owner of the next change):

| id | note |
|---|---|
| N-1 | The looser-limit rule compares the two earliest dates on today's business date (`save_person.sql`, the `v_editor_earliest` block). A `months` limit and a `days` limit cross: an editor on "1 month back" may give "30 days back" on 31 March (1 March is not before 28 February), and on the 28th of a later March the person writes 26 February while the editor cannot go before the 28th. At most three days, on a few days a year; `docs/05` 10.3 states the rule as it is built. |
| N-2 | `tenancy.earliest_writable` answers NULL ("any date") when the membership row is not visible (another organization, a non-member, or a caller that has not entered the organization): a fail-open shape. Every caller in D2 passes the current organization and actor after `tenancy.enter_organization`; the writes of D4, 08 and 08b must keep `check_writable` after the guard, which their own tests have to show (`docs/05` 10.2 names the order). |
| N-3 | `api.people_list` takes `p_now` and never reads it (the statuses do not depend on device liveness). Harmless; the signature matches the other list routines. |

## 4. Per domain

### D1 Tenancy and authorization

| Probe | Verdict | Evidence |
|---|---|---|
| Every tenant-scoped `api.*` routine enters its organization first | holds | sweep: every `api.*` file in `30_tenancy` calls `tenancy.enter_organization`; `db verify` check "tenant routines enter their organization" ok on the work copy |
| New tenant tables have RLS | n/a | D2 adds two global catalogue tables (`permission_sources`, `permission_translations`, no `organization_id`); RLS off like `tenancy.permissions`; executor and readonly have `SELECT` only (measured) |
| Functions owned by `xcode_owner` cannot be steered to another organization | holds | the D2 helpers are owned by `xcode_owner`, `STABLE`/`IMMUTABLE`, read `tenancy.memberships` under RLS keyed on `tenancy.current_organization()` (`person_sign_in`, `person_document`) or on the caller's organization id, which `check_writable` takes from the session setting; a foreign id answers NULL (N-2) |
| Scoped viewers: hidden companies and vehicles do not leak through the person document | holds | `person_document` keeps ids inside the viewer's reach and counts the rest; routine tests 103, 104; S45/S46/S11 answer 404 outside the view (test 168) |
| Every `{id}` route proves the id belongs to the caller's organization | holds | `person_in_view` (person roles in the current organization + `people_visible`); a device row of another user is 404 (test 164); routine tests 44, 159, 160 |
| Anti-escalation: only an Owner grants Owner, nobody edits themselves, nobody grants a right they do not hold | holds for granted rights; a lifted denial is parity (conceded, section 6) | tests 58-63, 68-72, 169 |
| The catalogue equals `packages/shared` and the design's `MODS` list | holds, with the deliberate split | `test_permission_keys.py`: the 59 equal the prototype one to one; `packages/shared` still lists the 40 old keys, every one still issued (19 kept + 21 non-catalogue), which the test pins; the web adopts the catalogue when it moves to this API (question 55) |

Hardest attacks tried: (1) a Fleet manager with `people.edit` creating a second account of their own with "any date" to escape their back-dating limit: refused by `people_back_limit_not_held` on create, the default 7 days included (tests 188, 191); (2) a non-Owner removing an Owner's device by guessing row ids: the Owner rule answers 403 before the device lookup, so no 404/403 difference reveals whether a row exists (test 166, `people_device_remove.sql` order); (3) a scoped editor acting on a person outside their companies through S45/S46/S11: 404 for all three (test 168).

### D2 Identity and sessions

| Probe | Verdict | Evidence |
|---|---|---|
| A security-version bump stops the next request | holds | `people_pin_reset` bumps it; `_session_refused` for both versions (test 161); API 401 on `/auth/session` and refresh |
| A device revocation stops the next request from that device without a bump | holds | test 163 (`security_version` stays 0, the kept device still resolves), API `test_removing_one_device_ends_only_that_device` |
| Refresh rotation and family revocation | n/a | D1's; S45 and S11 revoke the family through `identity.remove_devices` (`live_tokens == 0`, test 161) |
| Codes and caps after a forced reset | holds (D1 rules) | `auth_start.sql:48` sends a forced-reset person to the code; `auth_complete_pin.sql:96` clears the flag; `auth_resend_code.sql:54` allows `pin_reset` while the reset is due |
| No new enumeration | conceded (D0 residual) | S45 creates the "PIN reset due" state that the number step answers differently from an unknown number; decided by D0 (`docs/07` 12.14 a, `docs/12` section 7) |
| The forced reset cannot become a takeover by the editor | holds | the code goes to the person's email; changing that email needs the step-15 rules (full scope and every right the person holds; tests 73-78); both actions are logged under the editor's actor id |

Hardest attacks tried: (1) a stranger: S45 is an authenticated setup route behind `people.sign_in`; (2) the dismissed employee's old phone after S45: the device row is revoked, the refresh token revoked, the access token fails on the security version; a new sign-in needs the email code; (3) a v2.11 phone whose trusted row S45 removed: A01 answers the uniform 401 (DEC-3), the phone's "Forgot PIN" path (A07 to A09) clears the reset (pre-mortem P1 below).

### D3 Data integrity and concurrency

| Probe | Verdict | Evidence |
|---|---|---|
| Version bumped and compared; a stale writer gets 409 | holds | membership `version` bumped by `save_person`, compared with `p_expected_version` (tests 45-48, 110); the sign-in actions return the version they read and bump nothing (test 157) |
| Lock order | holds | inventory (section 8): every people routine takes the membership `FOR NO KEY UPDATE`, then `identity.lock_user` (`FOR UPDATE`), then token rows, then the organization row through `record_change`; every auth routine takes the user row first (`auth_refresh.sql:43-44` user, then the token row), then the change-log insert's `KEY SHARE` on the membership, which `NO KEY UPDATE` admits (tests 128, 173 with `NOWAIT`) |
| Two actions at once | holds | tests 170 (a reset waits for a save, then logs the new name), 171 (two resets reset once), 172 (a device removal racing remove-all is 404), 127 |
| Replays and append-only tables | n/a | no client ids; the change log is append-only by grant (`db verify` ok) |
| One routine call, one transaction | holds | the use cases tell one routine each (`application/access/*.py`) |

### D4 Contract parity

| Probe | Verdict | Evidence |
|---|---|---|
| Routes, status codes, operation ids, tags | holds | router, OpenAPI (84 paths) and `docs/06` agree for S01 to S11, S45, S46; .NET has S05 to S11 (`SetupEndpoints.cs:74-95`) and not S45/S46 (by design, `docs/06` 2.12); the OpenAPI `422` rows are 06:V-D4-3 |
| Bodies: names, order, nullability | holds | `PERSON_KEYS` keeps the 16 .NET properties in order and appends the new ones; `backLimit.from` aliased; `Amount` for `approvalLimit` |
| Errors: problem shape, exact sentences, empty 404/415 | holds, with V-D4-1 | `test_people.py` sentences; `test_a_body_route_without_json_is_415`; 500 for an out-of-range integer fixed |
| Clients | holds pending the run | released-client rows (C19); the catalogue and token keys per role |
| Drift | holds | no commit under `apps/api` or `tests/api` since 2026-10-11; the uncommitted .NET changes are the register's; the access files last changed 2026-10-09 |

### D5 Domain rules and time

| Probe | Verdict | Evidence |
|---|---|---|
| Business dates from the organization's zone and an injected `p_now` | holds | `check_writable` and `save_person` use `tenancy.business_date(org, p_now)`; no `now()`, `current_date` or `clock_timestamp()` in `db/routines` (sweep) |
| Month ends, 29 February, zones with daylight saving | holds | `test_back_limit.py` rows; measured on the work copy: 12 months before 2024-02-29 is 2023-02-28, 1 month before 2026-03-30 is 2026-02-28 |
| Words byte for byte | holds | `test_can_change_words`; measured `1 month back, not before 14 September 2026` |
| Normalisation parity | holds | unchanged from prompt 05 (test 83) |

### D6 Database craft

| Probe | Verdict | Evidence |
|---|---|---|
| `db verify` exit 0 | holds | 21 of 21 ok on `xcode_vd2_work` (a copy of `xcode_template_vd2`, built 14:21 from the live tree, fingerprint `e1bf113d…`) |
| `SECURITY DEFINER` with a fixed `search_path`, owner `xcode_api_executor`; helpers owned by `xcode_owner`; `EXECUTE` revoked from `PUBLIC` | holds | measured in `pg_proc` for the twelve D2 routines; `has_function_privilege('public', 'tenancy.earliest_writable(...)')` false; `xcode_app` can execute `api.people_pin_reset` and not `tenancy.check_writable` |
| No dynamic SQL | holds | sweep: no `EXECUTE`/`format(` in `db/routines`; `db verify` check ok |
| Migration forward-only with a reviewed `.down.sql`; signature changes drop the old overloads | holds | `0009_access.sql` drops the three changed signatures first; `0009_access.down.sql` reverses the tables, columns, catalogue and overrides (lossy by nature, stated in its header); no duplicate overload of the changed names on a fresh database (measured) |
| Features newer than PostgreSQL 16 | holds | `make_interval`, `trim_scale`, `jsonb_agg ... FILTER`, `\u` regex escapes: none newer than 13; measured `PostgreSQL 16.15` locally; CI image `postgres:18` (never run: the workflow file is untracked, `gh run list` 404) |
| Template fingerprint | holds | the comment of `xcode_template_vd2`, `xcode_template_full` (the shared run's) and `xcode_template_d3` all equal the fingerprint of the current `db/` files; no session changed `db/` after 12:59 |

### D7 Performance and scale

| Probe | Verdict | Evidence |
|---|---|---|
| Statement budgets | holds | 2 per people and access route (`statements(...)` in `test_people.py`, `test_access.py`) |
| `EXPLAIN` at 10x the seed | unproven | not run (C25) |
| No query per row inside a loop | unproven | `api.people_list` calls `tenancy.person_document` per page row, which runs `assigned_permissions` (a recursive CTE) and three aggregates: about four queries per person inside the one call; bounded by the page cap of 100 |

### D8 Reliability and operability

| Probe | Verdict | Evidence |
|---|---|---|
| Logs carry no body, PIN, code, token, phone or email | holds | the people routes log nothing of their own (sweep of `logger.*` calls in `src`); the shared middleware test `test_no_pin_code_token_phone_or_email_reaches_the_log` |
| `X-Request-ID` | holds | `test_access.py::test_the_request_id_is_echoed_and_copied_into_problems` |
| `XCODE_*` names | not checked beyond a grep | D2 adds no setting. A name grep over `settings.py`, `.env.example`, `docs/08` and `test_settings.py` differs (`XCODE_DATABASE_POOL_MAX`, `XCODE_EMAIL_FROM`, `XCODE_EMAIL_PORT` absent from `docs/08`; `XCODE_DATABASE_ALLOW_REQUIRE_SSLMODE` absent from `test_settings.py`; `settings.py` builds most names from a prefix, so the grep is not proof either way); for prompt 09 |

### D9 Hosting and supply chain

n/a: D2 changes no dependency, setting or deployment file.

### D10 Tests as evidence

| Probe | Verdict | Evidence |
|---|---|---|
| No fake of the capability under test | holds | every rule in `tests/db` against PostgreSQL; the HTTP tests use the real database |
| `skip`, `xfail`, `sleep`, bare `except` in the D2 tests | holds, one note | none in `test_access_routines.py`, `test_back_limit.py`, `test_people.py`, `test_access.py`; `test_permission_keys.py` has two `skipif` guards on sibling folders (`packages/shared`, `docs/design`), both present here, so the prototype and shared parity tests run; alone, `apps/api-python` would skip them silently |
| A wrong implementation would be caught | holds | a routine that skipped the Owner rule fails test 166; one that skipped `person_in_view` fails 168; one that let an editor lift their own limit fails 188; one that derived a denied legacy key fails `test_a_denied_legacy_key_stays_off...`; a migration that lost a translated key fails the `DO` block and `test_the_grant_translation...` |
| Every `Raises:` code has a test | holds | sweep over the eleven D2 routine headers: every code appears in `tests/` |
| Fakes match the routines | holds, with V-D10-1 | `test_fakes_match_routines.py` tenancy cases include the back limit, the statuses and the three actions |
| The full suite ran once on a fresh template | holds: the shared run of 13:00 to 15:23 on `xcode_template_full` (fingerprint equal to the files tested), 5617 passed, 42 failed, 0 skipped, 0 errors, 2 h 22 min; every D2 module green | section 8 |

### D11 Documents and prompts

| Probe | Verdict | Evidence |
|---|---|---|
| Doc clauses match the code | holds, with V-D11-1 | `docs/04` 13.2 (columns, constraints, counts), `docs/05` 10.2 and 10.3 (every row read against its routine: check orders, `unchanged` conditions, lock order, the Owner addition of the translation), `docs/06` 2.12.2 and 2.12.4 (S05 to S11, S45, S46), section 3 (the five D2 codes and their sentences in `http/messages.py`), `docs/07` 12.11, `docs/12` 2.7 (every named test exists), `docs/13` q58, q59, q65, q71, `docs/15` 3.1 to 3.5 and section 4, README row 07b and register rows B3, B12, B13, B17 |
| Section references resolve | holds | `docs/05` 10.2 and 10.3, `docs/06` 2.12, `docs/04` 13.2, `docs/09` 4.1 |
| Memory and earlier reports re-measured | holds | the counts in the build report's section 3 are superseded by the shared run (section 8) |

## 5. Per mode

### Assumption inventory (Socratic)

| Assumption | Where stated | Enforced by |
|---|---|---|
| "Only the Owner role has rights that no old key translates to and nothing needs" | `docs/15` 3.5, `0009_access.sql` comment | the migration's `chosen` CTE applies the addition to every role; measured: the Office admin, Fleet manager and Revenue clerk defaults are all translated-to, so only the Owner gains (petty-cash rights) |
| "No writer stores a denied legacy override since the catalogue change" | `effective_permissions.sql` header | `check_person_grant` refuses non-catalogue keys; the migration's `DO` block refuses any such override; `0009` deleted the old rows first |
| "The three sign-in actions and every people routine lock the membership before the user row; sign-in routines hold the user row and take `KEY SHARE` on the membership" | `docs/05` 10.3 | inventory of `FOR ... UPDATE`/`lock_user` (section 8); tests 128, 173 |
| "The limit is read on the actor's own membership row, which `enter_organization` already reads; no index" | `docs/04` 13.2 | `earliest_writable` selects by the primary key |
| "A person provisioned by the operator starts at `none`" | `docs/05` 10.3 | column default; `ops_provision_user.sql` does not set the columns |
| "Every refusal of a people route is a `problem` with a sentence" | `docs/06` section 3 | true for the routine codes; false for an integer outside its column type until V-D4-1 (fixed) |
| "One organization per database" (so a user-level forced reset affects one organization) | `ops_provision_user.sql` header, `docs/07` section 11 | `people_create` makes a new `identity.users` row per person and refuses a taken email or number across users |
| "The shared full run tested the files I read" | this report | template fingerprints equal (section 8) |

### Falsification table

The claims table of section 2 carries the falsifier result and grade per claim; the one disproved claim is C21 (V-D4-1).

### Pre-mortem narratives

| # | Narrative | Likelihood x impact | Early sign | Mitigation | Inversion: does the guaranteeing condition exist now? |
|---|---|---|---|---|---|
| P1 | An administrator makes a person on a v2.11 phone reset the PIN. S45 removes the phone's trusted row, so the next A01 answers the uniform 401 ("wrong number or PIN"); the person retries, counts toward the untrusted cap, and calls support, which cannot see why from the phone's screen | medium x low | support calls after S45 | DEC-3 (the old routes keep the uniform refusals); the phone's "Forgot PIN" (A07 to A09) clears the reset (`auth_complete_pin.sql:96`); the person's status in the people list reads "PIN reset due" | the condition (v2.11 phones in use) exists; the recovery path exists and is tested (`test_a_forgotten_pin_is_reset_with_an_email_code`) |
| P2 | A person made to reset has no working email (question 53); nothing but a code ends the forced reset, and `ops_clear_pause` clears counters, not the flag | low x medium | the person stays "PIN reset due" for days | an editor who meets the step-15 rules fixes the email (S08); the operator cannot | exists for the few people without email; recorded with question 53 and the D0 residual risks; no D2 change |
| P3 | The data migration of prompt 10 runs the same translation on the real data; an Owner-only tenant whose Owner held `organization.manage` by override alone (not by role) loses it | low x medium | the `RAISE NOTICE` "dropped on purpose" line | the Owner role carries the key; the notice names the people | the migration test seeds this (`("Owner", [("bills.view", False)])`) and the `DO` block checks the Owner's set; a non-Owner's `organization.manage` is dropped by design (question 59) |
| P4 | A page of 100 people with 59-right catalogues takes seconds on the host: four queries per person inside one call | low x low | slow people list on a big tenant | the page cap; `person_document` is already per row today | not measured (C25) |

### Red-team vectors

| Persona | Vector | Defence or gap |
|---|---|---|
| Clerk (people.view only) | S45, S46, S11 on anyone; S06 of a person outside the scope | `permission_missing` 403 (test 167, API); 404 outside the view (168) |
| Clerk with `people.edit`, limited to 3 days back | a second account of their own with "any date", or an update of a colleague to "any date" | `people_back_limit_not_held` (188 to 191); the default 7 days is refused too (V-D5-1 of the build report, kept) |
| Clerk with `people.edit` and `people.sign_in` | reset the Owner's PIN; remove the Owner's devices by guessing ids | `people_owner_edit` 403 before any device lookup (166) |
| Clerk with `people.edit`, not `people.sign_in` | lift a colleague's denied `people.sign_in` by sending the role defaults | allowed: parity with .NET (`AccessUseCases.cs:522`), conceded; see section 10 |
| Clerk | integers that psycopg types as `bigint` | 500 before the fix (V-D4-1); 400 after |
| Dismissed employee with the old phone | keep the session after S45 or S11 | access token fails (security version), refresh token revoked, device row revoked (161, 163) |
| Operator | provision a person with a loose limit | by design `none`; audited in `ops.operator_actions` |
| The calendar | 31 March minus a month, 29 February, midnight in Nairobi and New York, a held business date | `test_back_limit.py` |
| Hurried DBA | run `0009` twice, or on a database without roles | the migration runner's checksums and advisory lock; the `DO` block refuses wrong counts |

### Dialectic

| Decision | Strongest counter | Verdict | Confidence |
|---|---|---|---|
| DEC-11: existing people keep "any date", new people get 7 days | one rule for everyone is simpler to explain and safer | keep: taking away what people do today is the owner's call (question 65) | high |
| Refuse rather than clamp a limited editor's default of 7 days (build report V-D5-1) | a silent clamp would let a 3-day editor add people without choosing | keep: a refusal with a sentence beats a silent change of what was sent, the pattern the whole contract follows | high |
| The looser-limit rule compares earliest dates on today's business date | comparing shapes (mode and count) would be stable over the year | keep: shapes cannot order months against days; the drift is at most three days (N-1) | medium |
| `earliest_writable` answers NULL for an invisible membership | raising would make a misuse loud instead of permissive | keep for now: every caller enters the organization first and the writes' own tests must show the order (N-2); revisit when D4, 08 and 08b land | medium |
| Legacy keys derived in the token (DEC-9) rather than dropped | a clean catalogue now | keep: v2.11 phones gate on them; the derivation is pinned per role (`_PHONE_GATES`) and a denial still wins | high |
| S11 reused for "Remove all" under the new right and wording (DEC-19) | a new route would keep S11's old meaning for the web | keep: the effect is identical and the web does not call the Python API yet | high |

## 6. Conceded

| Challenge | Guard that defeated it |
|---|---|
| A lifted denial grants a right the editor does not hold (`check_person_grant.sql` compares only the granted set with the editor's holdings) | parity: `apps/api/Application/AccessUseCases.cs:522` applies the same rule (`after.Granted.Except(before.Granted)`), the rule predates D2 (prompt 05) and the notes do not define anti-escalation, so the .NET behaviour decides; recorded for the user in section 10 |
| Opposite-order locks between the people actions and the auth routines (people: membership, user, tokens; refresh: token then user?) | `auth_refresh.sql:43-44` locks the user row first, then the token row: the same order; the change-log insert's `KEY SHARE` on the membership does not conflict with `NO KEY UPDATE` (tests 128, 173) |
| A user-level forced reset reaches another organization's membership | one organization per database (`ops_provision_user.sql` header; a new `identity.users` row per person) |
| S46 reveals whether an Owner has a given device to a non-Owner | the Owner rule runs before the device lookup; both answer 403 |
| The migration's "only the Owner gains" addition reaches other roles | measured: every Office admin, Fleet manager and Revenue clerk default is translated-to or needed, so the `chosen` CTE adds nothing for them; the migration test asserts the Fleet manager without `pettycash.spend` gains neither petty-cash right |
| `back_limit_words` depends on `lc_time` | `to_char` without the `TM` prefix writes English month names regardless of locale; measured `14 September 2026` |
| A `from` date in the future slips through on an update without a mode | a date or count without a mode is `people_back_limit_invalid` (`save_person.sql`, API test); with a mode the business date check applies |
| `people_pin_reset` on a person already locked leaves them locked | the lock ends only with a code, which the forced reset also requires: one recovery path (`docs/07` 12.5, 12.7) |

## 7. Fixes

| Finding | Files changed | Test that failed before and passes now |
|---|---|---|
| V-D4-1 | `src/xcode_api/http/schemas/access.py`: `Int32 = Annotated[int, Field(ge=-(2**31), le=2**31 - 1)]`, `Int64` likewise for 64 bits; `BackLimitBody.count: Int32 \| None`, `SavePerson.version: Int64 \| None`, `PersonLifecycleRequest.version: Int64 \| None` (the shape the routine parameters `integer` and `bigint` hold; the range rules stay in `tenancy.save_person`). `tests/api/test_people.py`: one test appended. `docs/06-http-contract.md` 1.2 Numbers row: the integer sentence (written at 16:52, when the coordinator released the file before D4's landing; see the addendum) | `tests/api/test_people.py::test_integers_beyond_their_column_types_are_refused_before_the_routine`: 15:40 against the unfixed schema `1 failed` (`POST /setup/people` with `backLimit.count` 2^31 answered `500 {"title":"An error occurred while processing your request."}`); 15:41 with the fix `1 passed in 4.78s` (400 `Invalid setup change`, `errors` naming `backLimit.count`, then `version` on the update and on the deactivate body) |
| the three `0009` key-count failures of the shared run (section 8) | `tests/db/test_auth_routines.py` (`test_step_9_the_right_pin_on_a_trusted_device_clears_its_scope_and_issues_tokens`), `tests/db/test_identity_helpers.py` (`test_policy_for_returns_the_defaults_names_role_and_permissions`), `tests/db/test_gateway.py` (`test_identity_routines_map_every_outcome_with_one_statement_each` and the ops-routines test): `== 39` becomes `== len(held_permissions(role_rights("Owner"), "Owner"))`, the catalogue helper's effective set of an Owner (59 catalogue rights, 17 derived legacy keys, `organization.manage`: 77), so the assertion follows the catalogue instead of a count. Not a weakening: the three tests assert the Owner's effective set, which `docs/15` 3.4 defines as the catalogue rights plus the derived legacy keys, and `0009` changed that set on purpose | shared run 15:23: `assert 77 == 39` in all three; after the edit: `tests/db/test_identity_helpers.py` 56 passed (15:52), `tests/db/test_gateway.py` 16 passed and 3 failed, each past the count on D1's drift (`CodeCheck`, `DeviceVerification` need `now`; `ClearedPause` has no `was_paused`), `tests/db/test_auth_routines.py` 141 passed in 626 s (15:54 to 16:05) |

Regression after the fixes, one module at a time at `-n 0` on `xcode_template_vd2` (live tree):
`tests/api/test_people.py` 30 passed (15:42-15:45), `tests/api/test_access.py` 9 passed,
`tests/api/test_openapi.py` 5 passed, `tests/db/test_identity_helpers.py` 56 passed,
`tests/db/test_gateway.py` 16 passed and the 3 D1-drift failures, `tests/db/test_auth_routines.py`
141 passed, `tests/unit` 943 passed in 37.5 s; `ruff check` and `ruff format --check` clean on every
edited file; mypy clean (189 source files, 16:06).

Security checklist applied to the schema change (`implementing-api-schema-validation-security`):
numeric fields bounded to the type their parameter holds (the gap this fix closes); unknown
properties stay ignored on purpose (`ApiModel` `extra="ignore"`, the .NET parity rule of
`docs/06` 1.2, with the explicit field lists of `tests/api/test_mass_assignment.py`); string
fields are bounded by the routine's refusals and the body-size cap; the validation answer names
the field and carries no stack trace. Not applied: `additionalProperties: false` (parity forbids
it) and response-schema middleware (the response models are the explicit DTOs already).

## 8. Commands and outputs

Environment, measured in this session:

```
python --version                       Python 3.13.2 (.venv); psycopg 3.3.6
select version()  (127.0.0.1:5433)     PostgreSQL 16.15, compiled by Visual C++ build 1944, 64-bit
.github/workflows/xcode-api.yml        image: postgres:18 (file untracked; gh run list: workflow not found on the default branch, never run)
git log --since=2026-10-11 -- apps/api tests/api        (no commits; 27 uncommitted .NET files, the drift register's)
ls --time-style apps/api/Application/AccessUseCases.cs  2026-10-09 23:48 (AccessContracts.cs, Access.cs, PermissionKeys.cs: 2026-10-07)
```

Orientation (13:49 to 13:52): `git status --short` (89 entries, `apps/api-python/` untracked as a
whole); the newest D2 file `tests/api/test_contract_released_clients.py` 12:59 (D3's rows); no
file in scope changed in the 30 minutes before the pass; the shared full run's six pytest
processes (started 13:00:44, `-n 2`) were the only test jobs; 0.57 GB free.

Template and probes (coordinator's conditions: at or above 0.5 GB free, no pytest, read-only
SQL, one connection at a time):

```
build_vd2.py   14:01 0.43 GB, 14:06 0.37 GB, 14:15 0.39 GB: refused below 0.5 GB
               14:21 xcode_template_vd2 built in 11.7 s; xcode_vd2_work cloned
xcode-api db verify (XCODE_MIGRATION_DATABASE_URL -> xcode_vd2_work)   exit=0, 21 ok
probe_vd2.py   permissions 80 (59 catalogue), dependencies 48, role_defaults 111 (Owner 60, Office admin 37,
               Fleet manager 11, Revenue clerk 3), sources 32, translations 58;
               executor and readonly SELECT only on permission_sources/permission_translations/permissions;
               RLS off on the two global tables, on for memberships; no duplicate overload of save_person,
               people_create, people_update, people_list, auth_sign_in, company_snapshot, unknown_code_tries;
               the twelve D2 routines: api.* SECURITY DEFINER owned by xcode_api_executor, helpers owned by
               xcode_owner, every one with search_path=pg_catalog, pg_temp
probe_vd2b.py  ck_memberships_back_limit_count / _mode as docs/04 13.2; xcode_app may execute
               api.people_pin_reset and not tenancy.check_writable; PUBLIC may not execute
               tenancy.earliest_writable; earliest_writable under a foreign organization setting -> NULL;
               back_limit_words('months',1,'2026-09-14') -> "1 month back, not before 14 September 2026";
               back_limit_earliest: 12 months before 2024-02-29 -> 2023-02-28, 1 month before 2026-03-30 -> 2026-02-28
probe_int.py   pg_typeof: 7 smallint, 32768 integer, 2147483647 integer, 2147483648 bigint, 2^63 numeric;
               pg_temp.f(integer) called with 2147483648 -> 42883 function pg_temp.f(bigint) does not exist
probe_fp.py    files fingerprint e1bf113dc47a0cb23f1a9e16839340183d44271e1d37ec3a91b7343e5f8af98b;
               xcode_template_full, xcode_template_vd2, xcode_template_d3: note matches, datallowconn false
```

Sweeps (`db/routines`, `src`, `tests`):

```
now()/current_date/clock_timestamp()/random() in db/routines    none
EXECUTE / format( in db/routines                                none
SECURITY DEFINER without SET search_path                        none
skip/xfail/importorskip/sleep/bare except in the D2 tests       none (two skipif guards in test_permission_keys.py on sibling folders, both present)
TODO/FIXME/XXX/HACK/prompt identifiers in src, db, tests        none
log calls carrying a body, phone, email, PIN, code or token     none
routes: router (13) = OpenAPI (13 of 84 paths) = docs/06 (S01-S11, S45, S46); .NET SetupEndpoints.cs:74-95 has S05-S11
api.* routines of 30_tenancy without tenancy.enter_organization none
Raises: codes of the eleven D2 routines without a test          none
D2 routines named in docs/05                                    all seven new ones
ruff check . / ruff format --check .                            All checks passed / 394 files already formatted
mypy                                                            Success: no issues found in 189 source files (16:06)
```

Lock inventory (`grep "FOR UPDATE|FOR NO KEY UPDATE|FOR SHARE|FOR KEY SHARE|lock_user("`):
people routines (`save_person.sql:131-132`, `people_set_active.sql:42-43`, `people_sign_out.sql:42-43`,
`people_pin_reset.sql:43-44`, `people_device_remove.sql:43-44`): membership `FOR NO KEY UPDATE`,
then `identity.lock_user`; auth routines (`auth_refresh.sql:43-44`, `auth_sign_in.sql:38`,
`auth_change_pin.sql:32`, `auth_device_remove.sql:28`, `auth_revoke_device.sql:28`,
`auth_sign_out.sql:37`, `auth_withdraw_code.sql:27`, `matching_code.sql:32` after `lock_user`):
user row first; `record_change.sql:37` updates the organization row last in both.

Shared full run (coordinator's, `pytest -n 2 -q -p no:cacheprovider -rfE --junitxml`, fresh
`xcode_template_full`, started 13:00):

```
full.log tail      42 failed, 5617 passed, 4 warnings in 8547.14s (2:22:27)      (13:00 to 15:23)
full.xml           tests 5659, failures 42, errors 0, skipped 0
D2 modules         tests/db/test_access_routines 366 passed, test_back_limit 40, test_tenancy_helpers 116,
                   test_enum_parity 27, test_constraints 59, test_organization_routines 340, test_ops_routines 64,
                   test_migrate 18, test_history_routines 60, test_fakes_match_routines 663;
                   tests/api/test_people 29, test_access 9, test_contract_released_clients 28, test_openapi 5;
                   tests/unit 943: no failure in any of them
```

The 42 failures, attributed from `full.xml` (message heads) and the board:

| Where | Count | Cause | Owner |
|---|---|---|---|
| `tests/api/test_revenue.py`, `tests/db/test_revenue_routines.py` | 24 + 3 | D4's revenue changes in flight (the 07 modules D4 replaces at its landing; the board's queue row 7) | D4 |
| `tests/api/test_setup_*.py`, `tests/db/test_routine_headers.py` (8 `Raises:` rows of `40_setup`) | 9 | D3's rows landed 12:59 untested, and its `Raises:` lines (its own note in queue row 5) | D3 |
| `tests/db/test_auth_routines.py::test_step_9_the_right_pin_on_a_trusted_device_clears_its_scope_and_issues_tokens`, `tests/db/test_identity_helpers.py::test_policy_for_returns_the_defaults_names_role_and_permissions`, `tests/db/test_gateway.py::test_identity_routines_map_every_outcome_with_one_statement_each` | 3 | `assert 77 == 39`: an Owner's effective set after `0009` is 59 catalogue rights, 17 derived legacy keys (20 minus the three `bills.*`) and `organization.manage`; the three assertions still held the 2026-10-09 count, and D2 never ran these modules. **D2's; fixed here** (section 7) | this report |
| `tests/db/test_gateway.py::test_verify_device_maps_through_the_gateway`, `::test_ops_routines_map_the_operator_routines` | 2 | `DeviceVerification.__init__() missing 'now'`, `'ClearedPause' object has no attribute 'was_paused'`: the gateway test was not adapted to D1's command and outcome changes (the second also holds a 39 that this report's edit updates) | D1 (unowned since verify-07b-d1 stopped); reported, not fixed |
| `tests/db/test_structure.py::test_verify_reports_a_missing_schema` | 1 | `cannot drop schema pettycash because other objects depend on it`: the probe drops a schema that 08's `0012` populated | 08 |

## 9. Regressions and misses against earlier audits

Read after the pass: `docs/audit/2026-10-12-build-07b-d2.md` (the builder's challenge pass) and
`docs/audit/2026-10-11-verify-prompt-07b.md` (the design verification).

| Earlier record | State now |
|---|---|
| build V-D1-1 (a limited editor adding an unlimited account of their own), fixed with `people_back_limit_not_held` | holds: `save_person.sql` block after the grant rules; tests 188-191 |
| build V-D10-1 (a denied legacy key derived again), fixed in `effective_permissions` | holds: `test_a_denied_legacy_key_stays_off_though_its_source_is_held` |
| build V-D1-2 (a dead approval-limit clause in the sign-in-details rule), removed | holds: no such clause in `check_person_grant.sql` |
| build V-D11-1 (document rows out of order with the code), corrected | holds: `docs/05` 10.3 now states the status check after the gate, S46's 404 after the Owner rule, `back_limit.from` |
| build V-D4-1 (the catalogue no longer lists the keys the phone names), conceded | holds: `_PHONE_GATES` per role pins the token keys |
| design 2026-10-11, the people/sign-in lock-order deadlock (documents corrected) | built as `FOR NO KEY UPDATE` then `lock_user`; tests 128, 173 |
| the board's 10:47 note (four D1-drift expectations in `test_organization_routines.py`) | in the shared run (section 8) |

Missed by the builder's pass and found here: V-D4-1 (an integer outside its column type is a
500), V-D10-1 (the fake lacks the looser-limit rule and the parity case never reaches it), V-D11-1
(no integer rule in `docs/06` 1.2). Nothing recorded as fixed earlier is broken again.

The same pattern elsewhere, checked by reading (the coordinator asked for a note, not a fix):
the only other unbounded integer body fields are `http/schemas/setup.py:278,291` (`bucket`, which
no use case or adapter forwards: `grep bucket src/xcode_api/db/routines/setup.py` is empty) and
the settings section bodies of `http/schemas/organization.py:64-85`, which reach
`api.organization_settings_set` as one `Jsonb` document, where the routine's range checks answer
400. Neither reaches an `integer` parameter, so neither reproduces the 500. The petty-cash and
revenue bodies bound their `version`; every `page` and `pageSize` query is bounded.

## 10. For the user

| Decision | Recommendation | Why |
|---|---|---|
| A lifted denial grants a right the editor does not hold (section 6): keep .NET's rule, or tighten it so that the person's resulting assigned set must lie inside the editor's holdings whenever single permissions change | tighten, in one place (`tenancy.check_person_grant`, the holdings rule), when the web moves to this API (question 55); not before, so the two APIs refuse the same requests while both serve | the label "You can only grant permissions you hold" and the notes' module rights read as the resulting set; the gap needs an existing denied override on a person whose role already carries the right, so it is rare and auditable (the change log holds both snapshots) |
| Administrators and v2.11 phones (pre-mortem P1): a forced reset shows the phone "wrong number or PIN" until the person uses "Forgot PIN" | tell administrators in the release note of S45 to say so to the person; no code change | DEC-3 keeps the old routes' uniform refusals on purpose; the phone's reset path works and is tested |
| Question 71 (two widened grants of the translation) | keep as the register says (the owner removes rights person by person after the change) | the translation follows the notes; the migration notice lists who gained what |
| The looser-limit comparison on today's date drifts by up to three days between a `months` and a `days` limit (N-1) | accept | the only way to remove it is to forbid mixing the two modes between editor and person, which the notes do not ask for |

## Addendum (16:52)

The `docs/06-http-contract.md` 1.2 Numbers row now carries the integer sentence (an input integer must fit the type its routine parameter holds; beyond it the body is refused naming the field, as the .NET binder did). The coordinator released the file before D4's landing, whose three-way merge takes the sentence. With it, every change of V-D4-1 is in the tree: schema, test and document. Nothing else of this report is pending.
