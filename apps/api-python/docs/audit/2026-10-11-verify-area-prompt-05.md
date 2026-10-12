# Verify `area:prompt 05`, 2026-10-11 (fix mode, standard depth)

Scope: `docs/prompts/05-tenancy-access.md` D1 to D7 and its invariants: message catalogue,
snapshot and reason helpers, access and people routines, change log, organization settings,
logo, appearance and preferences, domain, ports, gateway, fakes, use cases and HTTP. Drift
register row 8 (people list filters) is assigned to this run by `docs/prompts/README.md`.
Run beside three other sessions (verify 03, verify 04, 07b design D0), coordinated through
`apps/api-python/.coordination/board.md` (kept out of git).

## 1. Verdict

**pass with findings.** Claims: 25 checked: 23 hold, 2 failed and fixed (C22, C25), 0
unproven, 0 not checked (section 2). Findings: 0 blockers, 3 majors (all fixed), 0 minors,
3 notes (one for the user, one fixed in the docs). Full suite: shared run 1, 4242 passed,
0 failed, exit 0; the tests added after it pass in the targeted runs of section 8.

## 2. Thesis and claims

Thesis (steelmanned): prompt 05 delivers D1 to D7; every refusal sentence comes from
`http/messages.py`; the people rules (only an Owner grants or changes an Owner, nobody edits
themselves, only held roles and permissions, `access.manage` for single permissions and
limits, who may change sign-in details, hidden scope kept) are enforced in SQL; writes are
version-checked under a row lock; the change log shows a scoped viewer only what they may
see; and the behaviour, routes and wire shapes equal the .NET API at 493bf82 plus the
working tree of `fix/web-dropdowns`, including the people list filters of 9276c51.

| # | Claim | Stated in | Code | Verdict | Grade |
|---|---|---|---|---|---|
| C1 | Every code of `docs/06` section 3 has its sentence, status and title; nothing else | 05 D1 | `http/messages.py` | holds | A (`tests/unit/test_messages.py`, 372 passed at 21:06 and again after the 07b doc fix) |
| C2 | Every code raised in `db/routines` has an entry and every entry is raised | 05 D1 | `http/messages.py`, routines | holds | A (`tests/db/test_message_codes.py`) |
| C3 | Unknown code is an `IntegrityBug` (500) | 05 D1 | `http/errors.py:112` | holds | B (log line read; test in the module set) |
| C4 | Snapshots carry the exact .NET keys and casing | 05 D2 | `person_snapshot.sql`, `settings_snapshot.sql`, `logo_snapshot.sql` | holds | B (literal-JSON tests green; assertions not re-read this session) |
| C5 | `check_person_grant` implements steps 10 to 15 once for create and update | 05 D2 | `check_person_grant.sql:46-196` | holds | A (read in full; one test per step, `test_step_*`) |
| C6 | Only an Owner grants Owner and only an Owner changes an Owner, also for lifecycle and sign-out | 05 D3 | `check_person_grant.sql:150-157`, `people_set_active.sql:42-44`, `people_sign_out.sql:32-34` | holds | A (`test_step_12_only_an_owner_changes_an_owner`, `test_access_routines.py:1921-1922`) |
| C7 | Nobody edits, deactivates or signs out themselves | 05 D3 | `check_person_grant.sql:146`, `people_set_active.sql:32`, `people_sign_out.sql:27` | holds | A |
| C8 | Only held roles and permissions; `access.manage` for single permissions and limits | 05 D3 | `check_person_grant.sql:167-183` | holds | A |
| C9 | Sign-in details of someone else: Owner, or whole scope and every holding | 05 D3 | `check_person_grant.sql:185-197` | holds | A |
| C10 | Hidden scope kept and pinning the scope kind | 05 D3 | `check_person_grant.sql:103-123` | holds | A |
| C11 | A new contact ends sessions and devices in the same transaction | 05 D3 | `save_person.sql:196-210` | holds | A (`test_people.py` session side-effect tests) |
| C12 | A stale writer gets `XC409`; a racing writer waits for the row lock, then conflicts | 05 D3; `docs/14` D3 | `save_person.sql:102-112` | **unproven before this run** (one connection only); holds now | A (new `test_step_9_a_save_racing_another_waits_for_it_then_conflicts`; fails with the lock removed) |
| C13 | Settings, logo and lifecycle writes take the row lock before they read what they compare | 05 D5 | `organization_settings_set.sql:51-54`, `organization_logo_set.sql:47`, `organization_logo_delete.sql:30-33`, `people_set_active.sql:39-42` | **unproven before this run**; holds now | A (four new two-connection tests, each failing with its routine's lock removed: section 7) |
| C14 | `unchanged` update writes no log row and keeps the version | 05 D3 | `save_person.sql:185-187` | holds | A |
| C15 | History: filters, both paging forms, `total` on request | 05 D4 | `history_list.sql` | holds | B (tests green; not re-attacked) |
| C16 | History visibility per viewer kind, unknown sections hidden from scoped viewers | 05 D4 | `history_list.sql:93-113` (`ELSE false`) | holds | A (per-viewer tests in `test_history_routines.py`) |
| C17 | People snapshots redacted for scoped viewers | 05 D4 | `history_list.sql:129-140` | holds | A |
| C18 | Logo: PNG, JPEG, WebP only, signature of the declared type, 256 KiB | 05 D5 | `organization_logo_set.sql:32-44` | holds | A |
| C19 | Settings merge, time zone and held date, slug conflict, effective values | 05 D5 | `organization_settings_set.sql` | holds | B (re-derived against `SettingsSections.cs` and `Organization.cs:93-115`: partial merge onto the stored row, the legacy grouping name losing to the current one, the held-date check only when the merge changed something, a future date against the calendar date of the stored zone, an equal date unchanged, name trimmed and slug lower-cased with the same lengths and pattern, a taken slug 409 with the .NET sentence; tests green. Two differences conceded in section 6) |
| C20 | Fakes match the routines for the parity cases | 05 D6 | `tests/support/fakes.py` | holds | A (`test_fakes_match_routines.py`); the fake's people filter added with the fix |
| C21 | Routes, operation ids and tags equal .NET | 05 D7; `docs/14` D4 | `http/routers/access.py`, `organization.py`, `history.py` | holds | A (mechanical: 19 routes, 19 identical operation ids, tags `Setup`/`Organization`) |
| C22 | The people list takes `role` and `status` as .NET does | `docs/06` S05; drift row 8 | `api.people_list` | **fails** → fixed (05:V-D4-1) | A |
| C23 | Statement budget 2 per request | 05 D7 | routers | holds | A (asserted in the new filter test and the existing page test) |
| C24 | Use cases hold no rule; routers branch only on the outcome | 05 invariants | `application/access/*`, `application/organization/*` | holds | B (every `execute` read: one repository call, no branch; the only transport work is `LogoUpload.parse` of the data URL, which the routine re-checks; the three routers have no `if`, `raise` or `try`) |
| C25 | No two 05 writes take rows in opposite order | `docs/14` D3 | `save_person.sql`, `people_set_active.sql`, `record_change.sql:37-46` | **fails** → fixed (05:V-D3-2) | A (`test_a_person_write_leaves_the_membership_open_to_the_change_log_key_check`) |

Counts: holds 23 (C1 to C21 without C22, C23, C24; C12 and C13 after their tests), fails 2
(C22 and C25, both fixed), unproven 0, not checked 0.

## 3. Findings

| id | mode | claim attacked | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| 05:V-D4-1 | falsification | `docs/06` S05: the people list filters by `role` and `status`; drift row 8 gives the people part to this run | `GET /setup/people?status=waiting` returned every person; FastAPI drops unknown query parameters, so the web's filter (`apps/web/components/PeopleAccessView.tsx:49-50`) silently did nothing. .NET filters (`AccessUseCases.List`, 9276c51) and answers 400 `Status must be active, waiting or none.` for anything else | new `test_the_people_page_keeps_one_role_and_one_sign_in_state` failed before the fix: 3 ids where 1 was expected | looked for a filter elsewhere (router, use case, routine, fake): none; the docs said "Not built in Python yet" | survives, **major** (a rule wrong on a reachable path) | **fixed**: `api.people_list` gains `p_role`, `p_status`; role compared case-insensitively (as role names are unique by `lower(name)` and SQL Server's default collation compares them so); `status` refused with `people_filter_status_invalid` after the permission and page checks, the .NET order; fake, gateway, use case, router, message, `docs/05` 4.1, `docs/06` S05 and section 3, drift row 8, prompt 08b updated |
| 05:V-D3-1 | Socratic | `docs/14` D3: "prove both with two connections, not one" | no 05 test raced two writers; a refactor dropping `FOR UPDATE` in `save_person.sql:103` would still pass every test (READ COMMITTED lets the second writer pass its version check, then its guarded `UPDATE` touches no row while role, scope and change-log rows are written) | `grep` of `tests/db/test_access_routines.py` and `test_organization_routines.py` for a second connection: none | read the lock statements: present in every 05 write | survives, **major** (missing test for an integrity claim) | **fixed**: one two-connection test per 05 write (person save: the late save waits, then `XC409`, one log row; deactivation; settings section save; logo upload; logo removal), each failing with its routine's lock removed (section 7) |
| 05:V-D3-2 | red team (found by revenue-17 for the 07b sign-in path as D1-F1, `docs/audit/2026-10-11-verify-prompt-07b.md`; reached here in 05 code alone) | section 4 D3 of this report said no opposite-order pair exists | an Owner edits office admin P: `save_person` or `people_set_active` locks P's membership `FOR UPDATE`, then reaches the organization row in `record_change`. Meanwhile P saves anyone else: `record_change` updates the organization row, then the `change_log` insert's `fk_change_log_actor` check takes `KEY SHARE` on P's membership. Each waits for the other; PostgreSQL ends one with 40P01, a 503 `TransientFailure` (writes are not retried, `db/session.py:60`) | `FOR KEY SHARE NOWAIT` on the membership from a second connection while a person write is open: `LockNotAvailable` with `FOR UPDATE` | my lock-order sweep counted the explicit locks only, not the row locks a foreign-key check takes | survives, **major** (an integrity claim wrong on a reachable path; nothing is lost, one request fails) | **fixed** by revenue-17 in the 07b D1 build at 22:36 (`save_person.sql:105`, `people_set_active.sql:42`: `FOR NO KEY UPDATE`, which still serialises the writers, as the race tests show); 05 test added here |
| 05:V-D1-1 | red team | an operator's `ops_remove_user` ends a compromised account | an Owner deactivates and reactivates the membership: `people_set_active.sql:67` sets `identity.users.status = 'active'`, undoing the operator's removal | .NET does the same (`Application/AccessUseCases.cs:235`) | parity confirmed | survives as **note**, parity | for the user (section 10) |
| 05:V-D11-1 | pre-mortem | `docs/06` section 3 is the built catalogue | the 07b design session added planned codes and new sentences inside section 3; `tests/unit/test_messages.py` parses that range and failed for every session | observed 20:55 (KeyError and extra codes) | none: the test is right | survives as **note** (process, not 05 code) | resolved by 07b-d0 at 21:05 (planned rows moved to `docs/06` 2.12.5); rule posted on the board |
| 05:V-D4-2 | falsification | `docs/06`: every length limit equals .NET's | the settings name (200), person names (100) and reasons (500) count code points (`char_length`), while .NET counts UTF-16 units (`name.Length`, `SettingsSections.cs:102`); 60 emoji in a 100-character field pass in Python and fail in .NET | `docs/04` section 1 (`char_length`), `docs/07` section 10 row 4 (accepted for auth only) | looked for a recorded decision outside auth: none | survives as **note** (Python is never stricter; no released client depends on the refusal) | **fixed in the docs**: `docs/06` 1.2 row "Text lengths" records the deviation for every route |

## 4. Per domain

- **D1 tenancy and authorization.** Tenant guard: `api.people_list` still calls
  `tenancy.enter_organization` first; `db verify` "tenant routines enter their organization"
  ok. Anti-escalation: holds (C5 to C10). Scoped viewers: the new filters are ANDed with
  `tenancy.people_visible`; a company-scoped viewer filtering `Revenue clerk` + `waiting`
  sees 2, not the 4 an all-companies viewer would (asserted). History: `ELSE false` hides
  unknown and settings sections from scoped viewers. `{id}` routes: not-found for hidden
  people (`test_a_scoped_viewer_cannot_get_a_person_outside_their_view`). Catalogue vs
  `packages/shared`: `test_permission_keys.py` green (its `needs_shared` skip applies only
  when `packages/shared` is missing; it is present).
- **D2 identity and sessions (as 05 touches it).** Contact change and deactivation revoke
  devices and tokens and bump `security_version` in the same transaction (C11); no cache.
  The 03 vector (a decision on a value read by an earlier transaction) cannot occur in 05:
  every 05 use case makes exactly one repository call (grep of `application/access/*`,
  `application/organization/*`).
- **D3 data integrity and concurrency.** 05:V-D3-1, 05:V-D3-2. Lock order: person saves
  and lifecycle calls lock the membership row, then the person's `identity.users` row, then
  the organization row (through `tenancy.record_change`, `record_change.sql:37-40`);
  settings and logo writes lock the organization row first. Every logged write then
  inserts a `change_log` row, whose actor foreign key takes `KEY SHARE` on the actor's
  membership after the organization row: the opposite order to a person write on that
  actor. My first sweep missed it (05:V-D3-2); with the membership taken `FOR NO KEY
  UPDATE` the two locks no longer conflict, and the writers still serialise. Every 05
  write now has a two-connection test that fails without its lock.
- **D4 contract parity.** 05:V-D4-1. Routes 19/19 (section 2 C21). Drift since the
  inventory (2026-10-07): `ad2f1cc` (settings use cases split, `SettingsSections`,
  `SettingsText`; behaviour already in `docs/06` per prompt 05), `9276c51` (people filters:
  this run), `6f130aa` (migration only for this area). No uncommitted .NET change in the 05
  area (`git status apps/api tests/api`).
- **D5 domain rules and time.** No `now()`, `current_date`, `clock_timestamp()` or
  `random()` in any routine. Settings time-zone and held-date rules: hold, re-derived against
  .NET (C19).
- **D6 database craft.** No dynamic SQL (every `EXECUTE` hit is `GRANT EXECUTE`; no
  `format(`); every `SECURITY DEFINER` routine sets `search_path`. `db routines` 184 files,
  exit 0; `db verify` exit 0. The old 8-argument `api.people_list` overload stays in the CLI
  database as an orphan, not executable by `xcode_app` (`has_function_privilege` checked),
  executable by its owner `xcode_api_executor` only. PostgreSQL features: the change uses
  none newer than 13.
- **D7 performance.** Two statements per request, asserted. The filter adds two primary-key
  joins (`tenancy.roles`, `identity.users`) per listed person; the page is capped at 100.
- **D8 operability.** No log call in the scope passes a body, phone, email, PIN, code or
  token (sweep: `request.refusal_without_message` logs only the code).
  `XCODE_*` sweep: every setting appears in `settings.py`, `.env.example`, `docs/08` and
  `tests/unit/test_settings.py` (the docs group some names, for example
  `XCODE_EMAIL_HOST/PORT/FROM/...`).
- **D9 hosting.** Not touched by 05. CI never ran: `.github/workflows/xcode-api.yml` is
  untracked (0 commits) and pins `postgres:18`; every run tonight was on PostgreSQL 16.15.
- **D10 tests as evidence.** No `skip`, `xfail`, `sleep` or broad `except` in the 05 test
  modules. Wrong implementations and whether the tests catch them: dropping the visibility
  join from `api.people_list` (caught: per-viewer list tests and the new scoped filter
  assertion); dropping `FOR UPDATE` from `save_person` (caught now, not before); letting a
  non-Owner edit an Owner (caught: `test_step_12_*`); a router that ignores a query
  parameter (caught now for the people filters, by the HTTP test); a sentence typed in a
  router instead of the catalogue (caught: `test_messages.py` both ways).
- **D11 documents and prompts.** Corrected: `docs/06` S05 ("Not built in Python yet"),
  section 3 (new code), `docs/05` 4.1 `api.people_list` row, drift register row 8, prompt
  08b list-filter bullet, `docs/06` 1.2 text lengths (05:V-D4-2), the `docs/14` D3
  lock-order bullet (implicit foreign-key locks, 05:V-D3-2), and the README status row
  "04, 05" (both verdicts). The 07b design rows in `docs/05` section 10 and `docs/06` 2.12.5
  now name this run's code `people_filter_status_invalid` (07b-d0 renamed theirs).

## 5. Per mode

**Assumptions (Socratic).**
1. Role names compare case-insensitively on the .NET side. Grade D: SQL Server's default
   collation is case-insensitive, but the `XCodeTest` collation was not queried. Default
   kept (case-insensitive), consistent with `uq_roles_name` on `lower(name)`.
2. One role per person: `pk_person_roles (organization_id, user_id)`, so the role join
   cannot duplicate rows. Holds (constraint read).
3. Only the web sends the filters: holds (no `setup/people` call in `apps/mobile/src`).
4. Each 05 use case is one transaction: holds (grep).
5. Every 05 write locks before it reads what it compares: holds, proven with two
   connections for every write (C12, C13).

**Falsification.** Section 2: C22 and C25 failed (both fixed); C12 and C13 lacked their
distinguishing tests (added, each shown to fail without its lock); C19 re-derived.

**Pre-mortem**, each with its inversion check:
1. "After the web moved to Python, an office admin filtered people by Waiting, saw
   everyone, and re-sent first-PIN mails to people already signed in." Cause: 05:V-D4-1.
   Inversion: a filter is safe only when the HTTP test sends the web's own query; added.
2. "Two admins saved one clerk at once; one role change vanished while the log showed
   both." Defeated by the row lock; now proven (05:V-D3-1), as for two settings saves
   of one section, which would merge onto a stale row without the lock (tested).
3. "The operator removed a compromised account; the next morning the Owner reactivated
   it." Parity; for the user.
4. "The night before cut-over a design session's document edits turned the suite red."
   Happened at 20:55 (05:V-D11-1); resolved in ten minutes through the board.
5. "The Owner fixed an admin's phone while the admin was saving a vehicle; one of them
   got 'service unavailable'." Cause: 05:V-D3-2. Inversion: a person write must leave
   the membership open to key checks; tested.

**Red team** (personas of `docs/14`):

| vector | persona | result |
|---|---|---|
| use the new filters to count hidden people | scoped office admin | defeated: filters ANDed with `people_visible`; scoped total asserted |
| `role=%` or a quote in `role` | any member with `people.view` | defeated: bound parameter compared with `=`, not `LIKE` |
| `status=%00` or an unpaired surrogate | outsider with a token | defeated: `SetupRoute` refuses 400 before authentication (`tests/api/test_http_plumbing.py:387`, `test_setup_vehicles.py:394`) |
| take over the Owner by changing their phone | office admin with `people.manage` | defeated: `people_owner_edit` (`check_person_grant.sql:155-157`) |
| deactivate or sign out the Owner | office admin | defeated: `people_set_active.sql:42-44`, `people_sign_out.sql:32-34` |
| stored XSS through an SVG logo | organization manager | defeated: allow-list and signature (`organization_logo_set.sql:32-44`) |
| create a person with another tenant user's phone, then change their sign-in details | malicious tenant admin | defeated: create always inserts a new identity user and refuses a contact used anywhere (`save_person.sql:128-153`); residual: the refusal tells that the contact exists somewhere (as .NET) |
| read settings rows in the history as a scoped viewer | scoped viewer | defeated: `history_list.sql:95-113` |
| sneak past the rate limit as 04:V-D4-1 did on `/auth` | anyone | not applicable: .NET limits only `/auth` (`AuthEndpoints.cs:26`, `Program.cs:95-99`); no 05 route has a limiter in either stack |

**Dialectic.**
- Case of the role filter. Thesis: `docs/06` said "exact name". Antithesis: role names are
  unique ignoring case, and SQL Server compares them ignoring case. Synthesis:
  case-insensitive; the status words stay case-sensitive, as the .NET `switch` is.
- Order of the status check. Thesis: refuse filters first, as the recurring list does.
  Antithesis: .NET reads the people filter inside `execution.Read`, after the permission
  and the page bounds. Synthesis: follow each endpoint's own .NET order (tested).
- One shared full run versus one per verify session. Thesis: each verify needs its own
  evidence. Antithesis: three one-to-two-hour suites on a 4-core machine with 0.5 GB free,
  and two at once ran out of memory before. Synthesis: one run after every fix landed,
  with a freeze on `src/`, `db/`, `tests/`; each session attributes failures in its scope.

## 6. Conceded

- 04:V-D4-1 (rate limit after authentication) applied to 05: conceded, no limiter on
  `/setup` in .NET or Python.
- 03:V-D2-1 (decision on a value read by an earlier transaction) applied to 05: conceded,
  one repository call per use case.
- Cross-tenant takeover through contact reuse: conceded (`save_person.sql:128-153`).
- SVG logo: conceded (allow-list).
- Orphaned `api.people_list` overload with wider grants: conceded, `xcode_app` cannot
  execute it.
- History leaks of unknown sections: conceded (`ELSE false`).
- Business date parsing: .NET `DateOnly.TryParse` also takes culture forms such as
  `8/10/2026`; Python takes `yyyy-MM-dd` only. Conceded: `docs/06` 1.2 fixes the date form,
  and the web sends `<input type=date>` values (`OrganizationSettingsView.tsx:380`); mobile
  does not save settings.
- Role filter with trailing spaces: SQL Server's `=` pads, so .NET matches `role=Revenue clerk `
  to the role (`AccessUseCases.cs:74`); Python gives an empty page. Conceded: the web sends
  names taken from the role list.

## 7. Fixes

| finding | files | test that failed before and passes now |
|---|---|---|
| 05:V-D4-1 | `db/routines/30_tenancy/people_list.sql`; `src/xcode_api/db/routines/tenancy.py`; `domain/tenancy.py` (`PeopleQuery`); `application/access/list_people.py`; `application/repositories.py`; `http/routers/access.py`; `http/messages.py`; `tests/support/fakes.py`; `docs/05-routines.md`, `docs/06-http-contract.md`, `docs/prompts/README.md`, `docs/prompts/08b-expenses-reports.md` | `tests/api/test_people.py::test_the_people_page_keeps_one_role_and_one_sign_in_state` (3 ids instead of 1 before); `tests/db/test_access_routines.py::test_people_list_keeps_one_role_by_name_and_one_sign_in_state`, `test_people_list_refuses_an_unknown_sign_in_state`, `test_people_list_checks_permission_and_page_before_the_state` (no 8-argument function before) |
| 05:V-D3-1 | `tests/db/test_access_routines.py` (one `_race` helper; the person-save race rewritten on it), `tests/db/test_organization_routines.py` (the same helper) | `test_step_9_a_save_racing_another_waits_for_it_then_conflicts`, `test_two_deactivations_at_once_end_the_person_once`, `test_two_saves_of_one_section_at_once_keep_both_changes`, `test_a_logo_upload_racing_another_logs_the_first_as_its_before`, `test_two_logo_removals_at_once_remove_it_once`: evidence for existing code, so each was made to fail by removing its routine's lock in the per-test database (a scratch pytest plugin running `CREATE OR REPLACE` on the `pg_get_functiondef` text; nothing in the tree changed): the late save succeeded instead of `XC409`; the second deactivation was `updated` and logged twice; the currency went back to `KES`; the replacement logged `null` as its before; the second removal logged again |
| 05:V-D3-2 | the routines: revenue-17 (07b D1, `FOR NO KEY UPDATE`); the test: `tests/db/test_access_routines.py` | `test_a_person_write_leaves_the_membership_open_to_the_change_log_key_check[save]`, `[deactivate]`: 2 passed; with `FOR UPDATE` put back by the same plugin, 2 failed with `LockNotAvailable` |
| 05:V-D4-2 | `docs/06-http-contract.md` 1.2 | documents only (`tests/unit/test_messages.py`, `test_endpoint_catalogue.py`, which parse `docs/06`: 374 passed) |

Existing `people_list` calls in `test_access_routines.py` gained the two new arguments.

## 8. Commands and outputs

- Versions: PostgreSQL 16.15 (`SELECT version()` on 5433); Python 3.13.2; CI image
  `postgres:18`, never run.
- Baseline (20:28, `-n 2`, template `xcode_template_v05`, 16 modules, the code before any
  of my changes): 1487 passed, 99 failed in 1:05:38 (machine shared with two other suites).
  All 99 are in `tests/db/test_fakes_match_routines.py` (49 routine cases, 49 fake cases, 1
  method-coverage check), every one `TypeError: PinVerdict.__init__() missing 1 required
  positional argument: 'checked_pin_hash'`: verify-03's `PinVerdict` change landed between
  this run's start and its update of `tests/support/auth_cases.py` (fixed by verify-03 at
  21:12, board section 3). None is in a prompt 05 module; the full run re-measures them.
- Fail-first (20:47, template `xcode_template_v05b`): 2 failed, for the reasons in
  section 3.
- After the fix: 20 passed (filter, list, visibility, catalogue tests). A pass over
  `test_message_codes`, `test_messages`, `test_openapi`, `test_people`,
  `test_endpoint_catalogue`, `test_routine_catalogue`, `test_routine_headers` failed
  `test_messages`: 07b-d0's planned message rows sat inside the parsed `docs/06` section 3
  (moved to 2.12.5 by 07b-d0 on request). Then `test_messages`: 372 passed;
  `test_routine_catalogue`, `test_endpoint_catalogue`, `test_messages`, `test_permission_keys`:
  381 passed; the other modules of that pass are measured by the full run. The two-connection
  test and the stale-version test: 2 passed.
- `ruff check`, `ruff format --check` on the touched files: clean; `mypy`: no issues in
  153 source files.
- `xcode-api db routines`: 184 files, exit 0; `db verify`: every check ok, exit 0.
- Full run: shared run 1 (verify-03, `-n 3`, template `xcode_template_v03e` built at 21:31
  from the tree with this run's `people_list`): 4242 passed, 0 failed, 0 skipped, 6
  warnings (PyJWT `InsecureKeyLengthWarning` from tests signing HS384/HS512 with the
  36-byte test key), 1:03:26, exit 0. Read from its log at 22:35; its counts include no
  test of this run added later.
- After run 1 (22:40, `-p no:xdist`, template `xcode_template_v05b` rebuilt from the tree
  with the 07b D1 build): the five race tests 5 passed (40.9 s); with each lock removed, 5
  failed (37.8 s). The key-check test 2 passed; with `FOR UPDATE` back, 2 failed.
- Not rerun after the 07b D1 build: the rest of `test_access_routines.py`,
  `test_organization_routines.py` and `test_people.py`. Free memory was 421 MB at 22:47,
  under the board's 1 GB rule, held by desktop applications and five agent sessions
  rather than by test runs. Their last full pass is run 1 (the 21:31 tree, before D1). D1
  changed only the lock mode in this scope's routines (`save_person.sql`,
  `people_set_active.sql`) and runs its own suite.

## 9. Regressions and misses against earlier reports

No earlier verify report covers prompt 05 (`docs/audit` holds 00, 01, 02 and the docs).
Missed by this run and found by another: 05:V-D3-2, by revenue-17 while building 07b D1
(posted on the coordination board, confirmed by revenue-45's 07b verify). My D3 sweep
listed `FOR UPDATE` statements and forgot that a foreign-key check locks the referenced
row too; the method gap is posted for `docs/14` D3 (section 10).
The 2026-10-10 validation left no report. Claims from the memory notes re-measured here:
`SetupRoute` refuses U+0000 in query values (holds, tests named in section 5); "an
`unchanged` write carries the current version" (holds, C14). Missed by that validation:
05:V-D4-1 (its drift row was written on 2026-10-11, after it) and 05:V-D3-1.

## 10. For the user

- **A tenant Owner can undo a platform operator's removal of a user** (05:V-D1-1):
  deactivate then reactivate sets the account active again, in .NET as in Python.
  Recommendation: keep parity now; when the operator role gets a "blocked by the platform"
  state, make `people_set_active` refuse to reactivate it. Reason: an operator removal is
  the tool for a compromised account, and a tenant should not be able to reverse it.
- **The deadlock fix for people writes ships with the 07b D1 build** (05:V-D3-2): the
  `FOR NO KEY UPDATE` in `save_person.sql` and `people_set_active.sql` came in with D1's
  uncommitted change at 22:36. If D1 is committed separately from prompt 05's files, take
  those two lines with prompt 05; `test_a_person_write_leaves_the_membership_open_to_the_change_log_key_check`
  fails without them.
- **Method gap, closed in `docs/14` D3**: the lock-order probe listed explicit locks only.
  It now counts the `FOR KEY SHARE` a foreign-key check takes and asks for a `NOWAIT` proof.
  The 03 verify's lock order (`2026-10-11-verify-area-prompt-03.md:118`) lists explicit
  locks the same way; worth a second look under the new bullet.
