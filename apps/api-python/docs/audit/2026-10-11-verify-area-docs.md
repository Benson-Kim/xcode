# Verification: `SCOPE: area:docs`, `MODE: fix`, `DEPTH: standard` (2026-10-11)

Method: `docs/14-verification.md`. Session: a verify session that wrote none of the code or
documents it checked. It stopped early under the prompt's context rule, then resumed at
14:12 on the user's word (section 11 lists what is left).

## 1. Verdict

**pass with findings if the prompt-06 session's full run is green, fail otherwise.** No
blocker and no major survived.

My own full run (13:34) was broken at about 13:45, when the prompt-06 session dropped
`xcode_template` for its targeted run (V-D6-1). The user then asked me to rely on that
session's full run: `pytest -n auto -q -p no:cacheprovider`, started 14:02:38 and still
running at 14:56. Its counts are in that session's output, which this session cannot read.
Copy them into section 8. The tests I added after 14:02 are not in that run; their targeted
runs are in section 8.

| | holds | fails | unproven | n/a | not checked | total |
|---|---|---|---|---|---|---|
| Probes (section 4) | 7 | 8 | 0 | 0 | 0 (+ D5, D7 whole domains; D1 to D3 and D9 only through `docs/12`) | 15 |
| Claims (section 2) | 10 | 8 | 0 | 0 | 2 | 20 |

| Severity | blocker | major | minor | note |
|---|---|---|---|---|
| Surviving findings | 0 | 0 | 14 | 5 |

## 2. Thesis and claims

Thesis (steelmanned): the documents and prompts of `apps/api-python` describe the current
Python code and the .NET contract at `HEAD` 493bf82 plus the uncommitted tree of
`fix/web-dropdowns` accurately enough that the next session builds the right thing. Every
file and section reference resolves; every served route and every routine is documented;
every setting is documented and tested; the drift register names every .NET change no
document describes; and the status lines are current.

| # | Claim | Where stated | Carried by | Verdict | Grade |
|---|---|---|---|---|---|
| C1 | `docs/06` section 2 lists every endpoint "exactly as the clients use it today" (80 routes) | `README.md` reading order; `docs/06` totals line | `docs/06` section 2 | fails: the .NET API serves 99; 19 rows and the S05/S17/S24 filters were missing (V-D4-1). Corrected | A (script over `apps/api/Api/*.cs`, `Program.cs`) |
| C2 | Every Python operation has its `docs/06` row with the same `operationId` | `docs/06` section 1.11 | `tests/unit/test_endpoint_catalogue.py` (new) | holds | A |
| C3 | Every `api.*` routine has a `docs/05` entry | `docs/05` intro | 68 routines in `db/routines`, all named in `docs/05` | holds | B (sweep output; no test) |
| C4 | Every `Raises:` code has a test | `docs/14` D10 | each of 180 direct (routine, code) pairs appears as a string in `tests/` | holds | B (string presence, not assertion reading) |
| C5 | Every file path cited in the docs exists | `docs/14` D11 | sweep over 33 documents | holds, except files that later prompts create and stale inventory paths (V-D11-6) | B |
| C6 | Every "`docs/x.md` section N" reference resolves | `docs/14` D11 | sweep | holds (0 misses) | B |
| C7 | The drift register is complete | `docs/prompts/README.md` | `git log`/`git status` of `apps/api`, `tests/api` | holds: no .NET change after 10 Oct 22:46. The 19 routes and 7 test classes match rows 1 to 12. Row 8's text was stale (V-D11-2) | A (command output) |
| C8 | The crosswalk plus the register cover every .NET test class | `docs/09` section 4 | class sweep | holds | B |
| C9 | Every `XCODE_*` setting is in `settings.py`, `.env.example`, `docs/08` and `tests/unit/test_settings.py` | `docs/14` D8 | sweep | fails for `test_settings.py`: 7 settings (V-D8-1). Corrected | A (sweep) |
| C10 | `db verify` has 21 checks | prompts README; memory | `len(verify._CHECKS)` = 21 | holds | A |
| C11 | `docs/03` section 9: the tenant-guard check allow-lists identity routines by name | `docs/03:278-280` | `db/verify.py` `check_tenant_routines_enter_organization`, `TENANT_GUARD_ALLOW_LIST` = empty | fails (V-D11-3). Corrected | A (code read) |
| C12 | README status | `README.md:3-8` | status table | fails: it said only bootstrap and foundation were done (V-D11-1). Corrected | A |
| C13 | Prompt status table (06 in progress) | prompts README | observed: setup routine files written 13:32, `messages.py` 13:36, its run at 13:45 | holds | A |
| C14 | OpenAPI tags | `docs/06` section 1.11 | `docs/06` section 2.11 says tag `Petty cash`; 1.11 omitted it | fails (V-D11-4). Corrected | A |
| C15 | `docs/05` names every helper | `docs/05` | `identity.normalize_email` has no entry | fails (V-D11-5). Corrected | A |
| C16 | Test names cited in the docs exist | `docs/09`, `docs/12` | sweep: 0 misses (the hits are .NET class names) | holds | B |
| C17 | Full suite: about 1 to 2 hours with `-n 3` | `docs/09` section 5 | full run | not checked by this session: my run was interrupted, and the prompt-06 session's run stands in for it (section 1) | F |
| C18 | Each `docs/12` control is "proven by" the tests it names | `docs/12` sections 2.1 to 2.6 | the named files and tests | fails: five rows named `tests/api/test_operability.py`, which asserts none of headers, 413, OpenAPI or hosts, and nothing tested the host check (V-D11-7, V-D9-1). Corrected | A |
| C19 | Migrations and routines apply to an empty database and pass every structural check | `docs/03` section 9 | `db migrate`, `db routines`, `db verify`, `db status` on a throwaway database | holds: 0001 to 0007 applied, 171 routine files twice, 21 of 21 checks ok, no drift | A (command output) |
| C20 | `docs/06` error and body claims match .NET and the Python code | `docs/06` sections 1, 2.4, 3, 4 | read-only probe (helper), spot-checked | fails on seven points (V-D4-2 to V-D4-8) | A (code read on both sides) |

One more claim is not counted above because it is a process statement: "`docs/06` section 3
equals `http/messages.py`". `tests/unit/test_messages.py` enforces it, and it failed today
on the prompt-06 session's in-flight work (section 9).

## 3. Findings

| id | mode | claim attacked | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| V-D4-1 | falsification | C1 | A session building lists from `docs/06` S05/S17/S24 (`?page&pageSize`) would ignore filters that the web sends and `ListFilterTests` pins. 19 .NET routes had no row and no pointer from `docs/06` | `apps/api/Api/SetupEndpoints.cs:74-75,107-108,123-124`; route script: .NET 99, docs 80 | The register (rows 1 to 8) lists everything, and prompt 06 line 43 builds the vehicle and recurring filters. So a prompt that runs its drift check builds the right thing. This partly concedes: downgraded from major | survives, minor | doc corrected: S05, S17, S24 carry the filters with the .NET semantics; a totals note names the 19 routes and the register. Guard: `tests/unit/test_endpoint_catalogue.py` |
| V-D6-1 | pre-mortem (it happened) | `docs/09` section 5: "never drop it under another session's run" | One shared, reused template name. A session that changes routines must drop it, which kills every other session's run. A session that forgets to drop it tests old routines | my run, 13:34 to 13:45; the other session's command line above | The rule is written in `docs/09`, the prompts README and `verify.md`, but nothing enforces it, and both sessions followed it (each checked that nobody was connected; mine checked at 13:33) | survives, minor | residual risk, owner: whoever next edits `tests/support/database.py`. Recommendation: name the template `xcode_template_<sha8 of db/migrations + db/routines contents>` and drop only the session's own stale hashes. Each routine state then gets its own template, and staleness cannot pass silently |
| V-D8-1 | Socratic | C9 | Renaming `XCODE_AUTH_ISSUER` (or audience, PIN iterations, operator URL, OpenAPI, metrics, shutdown grace) passes `test_settings.py`, which never reads them | `tests/unit/test_settings.py`; sweep output in section 8 | Some may be exercised elsewhere (`test_tokens.py` builds issuers). Searched to the end at 14:15: only `PIN_ITERATIONS_DEFAULT`, the OpenAPI default by environment and the test factory were pinned; no test read any of the seven variable names, and the positive PIN-iterations rule was untested | survives, minor | corrected: `test_each_variable_reaches_its_setting` (7 cases; renaming the variable fails all 7), `test_token_and_runtime_defaults` (issuer and audience equal the .NET `Jwt` settings), `test_pin_iterations_must_be_positive` |
| V-D11-1 | falsification | C12 | README status described the project as of prompt 01 | `README.md:3-8` (10 Oct) | none possible | survives, minor | doc corrected |
| V-D11-2 | falsification | C7 | Register row 8 said "prompt 06's text does not mention the other two" | `docs/prompts/06-setup.md:43-44` builds them | none | survives, minor | doc corrected |
| V-D11-3 | red team (hurried DBA) | C11 | `docs/03` said identity routines are allow-listed by name. In fact the check selects by the parameter name `p_organization_id`, and the allow-list is empty. A new tenant routine whose organization parameter has another name (for example `p_org_id`) escapes the check | `src/xcode_api/db/verify.py:684-702`, `:56` | Today all 48 tenant `api.*` routines use `p_organization_id`, and the 20 without it are the identity, ops, meta and rate-limit routines (sweep) | survives, minor | doc corrected to say exactly what is checked. The residual (parameter-name keyed) is recorded here; a stronger check would key on reads of tenant tables |
| V-D11-4 | falsification | C14 | Section 1.11 tag list omitted `Petty cash` and the .NET drift tags | `docs/06` sections 1.11 and 2.11; `apps/api/Api/*.cs` `WithTags` | none | survives, minor | doc corrected |
| V-D11-5 | falsification | C15 | `identity.normalize_email` (used by `ops_provision_user` and `save_person`) has no `docs/05` entry | `db/routines/20_identity/normalize_email.sql` | Mentioned in `db/routines/README.md` only | survives, minor | corrected: `docs/05` section 2.2 row. Guard: `tests/unit/test_routine_catalogue.py` fails while any function a routine file creates is unnamed in `docs/05` (it failed first with exactly this name) |
| V-D11-6 | falsification | C5 | `inventory-tests.md:811-850` proposes a test layout the suite does not use (`tests/contract/`, `tests/migrations/`, `test_auth_flows.py`, and so on). Prompt 00 cites `tests/unit/test_values.py` (real: `test_domain_values.py`). `inventory-petty-cash.md:680-692` cites web files that moved or were deleted (`FloatsTable.tsx` is deleted in the working tree) | xref sweep | `docs/09` section 4 is the authoritative crosswalk, and prompt 08's drift check re-reads the petty-cash web | survives, note | none needed now; prompt 08's drift check |
| V-D10-1 | Socratic | `docs/09` section 6: "never `sleep`" | Real-time sleeps in tests: `tests/api/test_auth_contract.py:357,651`; `tests/support/client.py:93-101` (mail polling) | grep | They wait for queued mail, not for a timing rule; `ManualClock` drives the rules | survives, note | none |
| V-D11-7 | falsification | C18 | `docs/12` cited `tests/api/test_operability.py` for the headers, `no-store`, the 413 body cap and the OpenAPI switch; that file tests health and startup only | `tests/api/test_operability.py` (5 tests); the assertions are in `tests/api/test_http_plumbing.py:140-160,162-180,305-328` | Prompt 00 put that evidence in `test_http_plumbing.py` on purpose; only the security document points elsewhere | survives, minor | corrected: the rows name the plumbing tests; `/metrics` and the access log point to prompt 09 |
| V-D9-1 | falsification | C18 | `XCODE_ALLOWED_HOSTS` is enforced (`main.py:74-75`, `TrustedHostMiddleware`) but no test sends a foreign `Host`; deleting the middleware passes the suite | grep of `tests/` | `test_settings.py` refuses `*` in production, which pins the setting, not the enforcement | survives, minor | corrected: `test_a_host_outside_the_allowed_hosts_is_refused` (with `["*"]` the foreign host gets 200 and the test fails) |
| V-D4-2 | falsification | C20 | `docs/06` (400 `revenue_earlier_missing` with `earliestMissing`) describes a rule .NET dropped: days are taken in any order | `apps/api/Application/RevenueUseCases.cs:130-131`; no `EarliestMissing` refusal left in `apps/api` | Register row 3 says the revenue use cases changed, so 07's drift check should catch it | survives, minor | in flight: the prompt-07 session removed the row from `docs/06` at 14:31; `http/messages.py` still has the code, so `test_messages.py` fails until it goes |
| V-D4-3 | falsification | C20 | `docs/06` `pettycash_line_payee_required` is not in .NET: a credit note needs a note, the payee is optional | `apps/api/Domain/PettyCash.cs:68-75` | Register row 7 records the optional payee | survives, minor | owner 08 (its D0) |
| V-D4-4 | falsification | C20 | The revenue 409 in `docs/06` carries `current` only; .NET day capture adds `vehicleId` and a per-vehicle detail, which the web reads | `apps/api/Api/RevenueEndpoints.cs:26-29`; `apps/web/components/revenue/useFleetDay.ts:119` | Register row 3 (day capture) | survives, minor | owner 08b (07 for the shared 409 shape) |
| V-D4-5 | falsification | C20 | The built S24 list omits `pausedFrom`, `lastRun`, `lastRunVehicles`, `balance`, which .NET sends and the web reads; `docs/06` S24 does not say so | `SetupContracts.cs:89-93`; `apps/web/components/setup/RecurringRows.tsx:39,134-142` | Register row 5 records the fields | survives, minor | owner 08b; a pointer in `docs/06` S24 waits for that file to be quiet |
| V-D4-6 | Socratic | C20 | Python sends `WWW-Authenticate: Bearer` on envelope 401s, which .NET never did; `docs/06` says "on every 401" without calling it an addition | `routers/auth.py:98`; .NET `AuthEndpoints.cs:80,82` | No client reads the header | survives, note | record as an accepted addition in `docs/06` section 1.12 |
| V-D4-7 | falsification | C20 | `docs/06` says paths have no trailing-slash tolerance; Starlette redirects `/setup/companies/` with a 307 | measured 14:41 | Clients send canonical paths | survives, note | wording in `docs/06` section 1.12, or `redirect_slashes=False` with a test |
| V-D4-8 | falsification | C20 | Python writes `traceId` on every problem; the `/setup/**` shape in `docs/06` omits it | `http/errors.py:65` | No client reads `traceId` | survives, note | wording in `docs/06` section 1 (B) |

## 4. Per domain

- **D4 (contract parity, as the docs state it)**:
  - routes: **fails** (V-D4-1, corrected; after the fix, Python ⊆ `docs/06` holds, grade A, new test);
  - bodies, errors, clients: **fails** (V-D4-2 to V-D4-8). A read-only helper read .NET, Python and the clients; I spot-checked every finding in the code. Holds: Money is a JSON number, enumerations are integers where .NET sends integers, property names and order match on the sampled auth, access, settings and setup bodies, and 404, 405 and 415 have empty bodies;
  - drift: **holds** (no .NET change after 10 Oct 22:46; `git status` of `apps/api`, `tests/api` lists exactly the register's sources).
- **D6**: template probe **fails** (V-D6-1); the other D6 probes are **not checked** (scope is the documents).
- **D8**:
  - settings probe **fails** (V-D8-1, corrected);
  - log probe **holds**: the only log call naming a body is `LogMailer` `mail.body`, which needs `reveal_body`, and `XCODE_MAIL_BACKEND=log` is refused in production (`settings.py:275`).
  - Other D8 probes: **not checked**.
- **D10**:
  - grep sweep **holds**: the two skips are conditional (no database; the role needs a superuser), and the sleeps are a note;
  - `Raises:` tests **holds** (grade B);
  - full suite: my run **fails** (interrupted); the prompt-06 session's run stands in for it (section 1);
  - no fake of the capability **holds**: `tests/db/test_fakes_match_routines.py` runs the setup case table (`tests/support/setup_cases.py`) against the routines and the fake, including every list filter, invalid filter values and an unknown company;
  - named rule distinguishes **holds** (grade A, read): the filtered total (3, not 4), an out-of-scope company giving `{total: 0, items: []}`, running items first, running judged on vehicles in reach only (`test_setup_vehicle_routines.py:213-235`, `test_setup_recurring_routines.py:1001-1057`); owner grants and self-edits (`test_step_11_*`, `test_step_12_*`); byte-for-byte sign-in refusals (`test_auth_contract.py:284`).
- **D11**:
  - doc clauses match code: **fails** on 6 clauses (V-D4-1, V-D11-1 to V-D11-5), 5 of them corrected;
  - memory claims re-measured: **holds** (21 `db verify` checks; PostgreSQL 16.15; Python 3.13.2; drift register).
- **D1, D2, D3, D9 (doc clauses)**: `docs/12` sections 2.1 to 2.6 read row by row against the tests they cite: the cited test names exist (23 of 23 across all documents); five rows pointed at the wrong file and one control had no test (V-D11-7, V-D9-1); the JWT row (HS256 pinned, `iss`, `aud`, zero leeway: `security/tokens.py:24,77-80`) and the redaction row (`infra/logging.py:17-26`) hold.
- **D5, D7**: **not checked** (the scope is the documents).

## 5. Per mode

**Assumptions (Socratic)**

| Assumption | Where stated | Enforced by |
|---|---|---|
| Implementers work from the documents, so the documents must equal the code | prompts README | before this run, nothing for routes; now `tests/unit/test_endpoint_catalogue.py` |
| The drift register is complete | prompts README | nothing; re-measured by hand in each prompt's drift check (holds today) |
| A frozen `xcode_template` holds the current routines | `tests/support/database.py:92-98` | nothing but the name (V-D6-1) |
| Every setting is pinned by `test_settings.py` | `docs/14` D8 | nothing (V-D8-1) |
| `docs/06` section 3 equals `messages.py` | `docs/06`, `messages.py` | `tests/unit/test_messages.py` (it caught the in-flight codes today) |

**Falsification**: the claims table in section 2.

**Pre-mortem**

1. (It happened today.) Two sessions share `xcode_template`. A targeted run drops it under
   a full run, and about 200 errors appear at 10%. A hurried reader blames the setup code.
   Early sign: `test_gw*` databases vanish mid-run. Inversion: a shared mutable name plus
   manual staleness guarantees this, and both exist now. Mitigation: V-D6-1.
2. Three weeks after cutover, an admin filters people by "waiting" and sees everyone,
   because Python ignores `status`. Trigger: 08b skips its D6 because `docs/06` S05 had no
   filter. Mitigation: the S05 row and register row 8 (V-D4-1).
3. 08b adds the central-expense routes, and `docs/06` never gets their rows; the gap
   surfaces only at the prompt-11 audit. Mitigation: the new test fails when a served
   operation has no row.
4. `XCODE_AUTH_ISSUER` is renamed in a refactor, and no settings test reads it. After
   deploy, every client token is refused. Mitigation: V-D8-1 (open).

**Red team**

1. Hurried DBA: a new tenant routine with `p_org_id` escapes the tenant-guard check
   (V-D11-3). The defence is a convention only; the residual risk is recorded.
2. Clerk in tenant A: `GET /setup/vehicles?companyId=<company outside scope>`. .NET filters
   inside the visible set (`SetupRepository.cs:81-83`), giving an empty page with no leak;
   the docs now say so. The recurring `companyId` likewise filters through visible vehicles
   (`:183-185`). Conceded for the contract; the Python behaviour is prompt 06's to prove.
3. Gamer: export cells starting with `=`. Exports are not in Python yet; prompt 08b
   (lines 98 and 153-154) requires neutralising them. Conceded for the documents.

**Dialectic**

| Decision | Strongest counter | Verdict | Confidence |
|---|---|---|---|
| Drift lives in the register, not in `docs/06` rows, until the owning prompt designs it | the contract document must equal .NET at all times, or someone builds from a partial table | keep the register, but `docs/06` must point at it and carry what .NET already serves on documented routes (done) | medium |
| One shared `xcode_template` name | one template per routine state (content hash) | change it (V-D6-1) | high |
| Message codes join `docs/06` section 3 in the same change as the routine | document first, so `test_messages.py` never goes red mid-session | keep: the red state is transient and proves the guard bites | medium |

## 6. Conceded

- Per-test database names cannot collide between sessions: `tests/conftest.py:129` `_unique_db_name` adds a random suffix (`test_gw0_dc92fd68f1bd`).
- `mail.body` logging leaks codes: refused outside development (`settings.py:275`; `LogMailer` docstring).
- `SECURITY DEFINER` without `search_path`: the only hit, `db/roles/030_grants.sql:17`, is a comment.
- `now()`, `current_date`, `clock_timestamp()`, `random()`, `EXECUTE`, `format(` in `db/routines`: none.
- `TODO`, `FIXME`, `HACK` and plan identifiers in `src`, `db`, `tests`: the two `XXX` hits are the `+254XXXXXXXXX` phone format.
- Section references: 0 unresolved.
- Python routes not in `docs/06`: 0.
- .NET test classes missing from both the crosswalk and the register: 0.

## 7. Fixes

| Finding | Files | Test |
|---|---|---|
| V-D4-1 | `docs/06-http-contract.md` (S05, S17, S24 rows and notes; totals note) | `tests/unit/test_endpoint_catalogue.py::test_every_served_operation_has_its_catalogue_row` passes. `test_a_served_route_without_a_row_or_with_another_operation_id_is_reported` proves the guard fails when a row is dropped or an `operationId` renamed. This is a doc correction, so there is no failing-first code test |
| V-D11-1 | `README.md` | doc correction |
| V-D11-2 | `docs/prompts/README.md` register row 8 | doc correction |
| V-D11-3 | `docs/03-database.md` section 9 | doc correction |
| V-D11-4 | `docs/06-http-contract.md` section 1.11 | doc correction |
| V-D8-1 | `tests/unit/test_settings.py` | `test_each_variable_reaches_its_setting` (fails 7 of 7 with the variable names changed), `test_token_and_runtime_defaults`, `test_pin_iterations_must_be_positive` |
| V-D11-5 | `docs/05-routines.md` section 2.2 | `tests/unit/test_routine_catalogue.py` failed first with `['identity.normalize_email']`, passes after; `test_a_routine_missing_from_the_document_is_reported` proves the guard |
| V-D11-7 | `docs/12-security.md` sections 2.2, 2.4, 2.6 | doc correction (the cited tests exist and pass) |
| V-D9-1 | `tests/api/test_http_plumbing.py` | `test_a_host_outside_the_allowed_hosts_is_refused` (fails with `allowed_hosts=["*"]`) |

## 8. Commands and outputs

- Orient at 13:22: `apps/api-python` is untracked as a whole. Files written in the last
  30 minutes: `docs/*` and `docs/prompts/*` (12:58-13:07, the docs session) and
  `tests/api/test_setup_*.py` (13:03-13:12, the prompt-06 session). I edited only files
  older than 30 minutes at the time of editing.
- Versions: `SELECT version()` gives PostgreSQL 16.15 (port 5433); Python 3.13.2. CI image
  (PostgreSQL 18 in `.github/workflows/xcode-api.yml`): never run, because the workflow is
  untracked.
- Template: built at 12:05:51, after the newest routine file (12:05:34). At 13:33 two
  newer files appeared (`setup_vehicle_list.sql` 13:32:10, `setup_recurring_list.sql`
  13:32:37). I dropped the template with no connection open and four idle `test_gw*`
  leftovers, which I left alone.
- Baseline (before any change): `test_messages`, `test_settings`, `test_permission_keys`,
  `test_layers`, `test_routine_headers`, `test_message_codes`, `test_openapi`: **1389
  passed** in 74.5 s.
- Route sweep: .NET 99, `docs/06` 81 (80 + OpenAPI), Python OpenAPI 64 plus 3 health
  routes. .NET routes not in `docs/06`: 19 (register rows 1 to 5 and 7). Python routes not
  in `docs/06`: 0. Not built yet: R01-R03, P01-P10.
- Routine sweep: 68 `api.*` routines, all in `docs/05`; 98 helpers, one undocumented
  (`identity.normalize_email`).
- Settings sweep, missing from `test_settings.py`: `XCODE_DATABASE_OPERATOR_URL`,
  `XCODE_AUTH_ISSUER`, `XCODE_AUTH_AUDIENCE`, `XCODE_AUTH_PIN_ITERATIONS`,
  `XCODE_OPENAPI_ENABLED`, `XCODE_METRICS_ENABLED`, `XCODE_SHUTDOWN_GRACE_SECONDS`.
- After the fixes:
  - `pytest tests/unit`: 779 passed, 3 failed. All three are in `test_messages.py` and
    belong to the prompt-06 session: `recurring_filter_kind_invalid` and
    `recurring_filter_status_invalid` were added to `messages.py` at 13:36 without their
    `docs/06` section 3 rows.
  - `tests/unit/test_endpoint_catalogue.py`: 2 passed.
  - `ruff check .`: all passed. `ruff format --check .`: 303 files formatted (before the
    new test; the new file is formatted). `mypy`: no issues in 146 files.
- Full run: started 13:34 (`pytest -n 3 -q -p no:cacheprovider`). Interrupted at about 10%
  (1 F, then setup errors) when the template was dropped. I stopped it at 13:48. Counts and
  duration: **not available**.
- 14:21, throwaway database `xcode_verify_142114` (created as `postgres`, `020_schemas.sql` and `030_grants.sql` applied as `xcode_owner`, dropped at 14:24): `db migrate` applied 0001 to 0007 and 171 routine files; `db routines` applied 171 again; `db verify` 21 of 21 ok; `db status` no pending, no routine drift, no checksum drift. The shared `xcode` database was not touched.
- 14:43, after the fixes: `pytest tests/unit tests/api/test_http_plumbing.py`: 821 passed, 4 failed in 60 s. All four belong to the prompt-07 session's in-flight work: two in `test_messages.py` (`revenue_earlier_missing` is still in `messages.py`, its row left `docs/06` at 14:31) and two in `test_routine_catalogue.py` (the new `revenue.*` helpers written from 14:34 have no `docs/05` entry yet). I then decoupled the second catalogue test from the live routine set; it now fails only on its own fixture. The first keeps failing until 07 documents its helpers, which is its purpose.
- `ruff check .`: one E501 and one I001 in `src/xcode_api/application/repositories.py` (prompt 07, 14:42). `ruff format --check .`: 307 files formatted. `mypy`: no issues in 147 files.

## 9. Regressions and misses against earlier audits

`docs/audit/` holds only `README.md`; no earlier report exists, so there is nothing to
regress against. The 04/05 validation left no report (the prompts README already says so).

## 10. For the user

Nothing irreversible came up. Two items need someone other than this session:

- V-D6-1 (a content-hashed template name) changes shared tooling. Make it in a session
  that owns `tests/support/database.py` while no other session runs tests.
- `docs/06` items V-D4-5 to V-D4-8 wait until the prompt-07 session stops editing that file
  (it changed it at 14:31). V-D4-2 is already being corrected there.

The design notes v2.29 to v2.33 (`docs/design/XCODE_Build_Notes_v2.3.md`, added 14:42) were
recorded in the design register of `docs/prompts/README.md` and `docs/13-open-questions.md`
after this verification; they are outside its findings.

## 11. Resume here

1. Copy the counts and duration of the prompt-06 session's full run (started 14:02:38) into
   section 8 and settle the verdict line.
2. Run the tests added after 14:02 in the next full run: `tests/unit/test_settings.py`,
   `tests/unit/test_routine_catalogue.py`, the host test in `tests/api/test_http_plumbing.py`.
3. `docs/06`: V-D4-5 to V-D4-8, once the file is quiet.
4. D5 and D7 doc clauses; the D6, D8 and D9 probes outside `docs/12`.
