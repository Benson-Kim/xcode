# Verification: `SCOPE: all`, `MODE: report`, `DEPTH: deep` (partial)

Session `audit-all [004606]`, 2026-10-14 15:10 to 15:45 EAT. Fresh eyes: this session wrote
none of this code and read no earlier audit until its own pass was done. Read-only: the only
files written are this report and one row in `.coordination/board.md` section 1.

Purpose: decide whether `apps/api-python` can be renamed to `apps/api`.

Re-run 2026-10-14 ~17:00 EAT (same session, second independent pass): every deterministic check below was executed again and reconfirmed with identical results, and the central .NET-route crosswalk was repeated (88 of 88 served). This pass changed nothing but the wording of this report, which now states each probe as a defensive question against our own code rather than as an attacker action; no finding, verdict or grade moved. The full-suite gate is unchanged (688 MB free against the 1.0 GB `-n 2` gate), so the verdict stands.

## 1. Verdict

**fail** — on one rule only: the full suite did not run to completion in this session
(`docs/prompts/verify.md` section "Report": *"`fail` ... if the full suite did not run to
completion"*). **No blocker was found in the code.** Every security, tenancy, concurrency
and contract claim this session could test held, most at evidence grade A.

Read the verdict as "evidence incomplete", not "defect found". The resource ceiling is
stated in section 8 and what remains is listed in section 11.

| Verdict | Count |
|---|---|
| holds | 22 |
| fails | 3 |
| unproven | 2 |
| not checked | 7 |
| **total claims** | **34** |

| Severity | Count |
|---|---|
| Blocker | 0 |
| Major | 1 (database state, pre-existing and already reported) |
| Minor | 5 |
| Note | 2 |

## 2. Thesis and claims

**Steelmanned thesis.** `apps/api-python` is a complete, behaviour-equal Python and
PostgreSQL replacement for the .NET API: every .NET route is served with the same contract;
tenant isolation is enforced in the database by row-level security plus a membership and
permission gate that every tenant routine must pass; identity answers are
enumeration-resistant and constant-work; optimistic concurrency, replay and lock order are
proven against a real cluster; the deployment, settings and supply chain are documented and
checked; and the test suite is evidence rather than decoration. Therefore the folder can be
renamed.

The thesis is largely earned. The claims table:

| # | Claim | Where stated | Verdict | Grade | Evidence |
|---|---|---|---|---|---|
| 1 | Lint, format and types clean | `CLAUDE.md` commands | holds | A | `ruff check` all passed; `ruff format --check` 505 files; `mypy` 227 files, no issues |
| 2 | Every .NET route is served by Python | `docs/14` D4 | holds | A | 88 unique .NET routes resolved from `apps/api/Api/*.cs`; all 88 present in `xcode-api openapi` (115 operations) |
| 3 | Every tenant-scoped `api.*` routine enters its organization | `docs/14` D1 | holds | A | `db verify` check ok; 89/89 routines taking `p_organization_id` call `tenancy.enter_organization`; allow list empty (`db/verify.py:56`); the check is proven to bite by `tests/db/test_structure.py:140` |
| 4 | Every tenant table has RLS and the `tenant_isolation` policy | `docs/14` D1 | holds | A | `db verify` check ok; negative test `tests/db/test_structure.py:202` |
| 5 | Only deliberate owner-owned functions read past RLS, unsteerable by caller input | `docs/14` D1 | holds | A | Exactly two: `identity.active_organization(uuid)`, `tenancy.organization_ids()`. See section 4 D1 |
| 6 | `api.*` routines are definer, executor-owned, `search_path`-pinned, not PUBLIC | `docs/12` | holds | A | `db/verify.py:305-341` checks all four including the NULL-acl default; negative test `tests/db/test_structure.py:101` |
| 7 | No dynamic SQL built from inputs | `docs/14` D6 | holds | A | Only `format(%I, current_database())` in `db/roles/020_schemas.sql:20`, `030_grants.sql`; `db verify` ok; negative test `tests/db/test_structure.py:118` |
| 8 | Decision paths take injected time, never `now()` | `docs/14` D5 | holds | A | 0 hits for `now()`/`current_date`/`clock_timestamp()`/`random()` in `db/routines`; enforced as a test by `tests/db/test_routine_headers.py:144` |
| 9 | Unknown number, paused account and capped device answer byte for byte alike | `docs/14` D2 | holds | A | `tests/api/test_auth_contract.py:286` compares 7 refusal states to the unknown-number baseline on two routes, over status + all headers but `Date`/`Content-Length`/`X-Request-ID` + body bytes |
| 10 | Exactly one PBKDF2 derivation per attempt (timing) | `docs/14` D2 | holds | A | `tests/api/test_auth_contract.py:708` wraps the real `Pbkdf2PinHasher` in a counting spy; 5 attempt shapes incl. unknown and malformed number |
| 11 | Token algorithm pinned; `iss`/`aud`/`exp` required; zero leeway; forgeries rejected | `docs/07` 1 | holds | A | `security/tokens.py:23,77-85`; `tests/unit/test_tokens.py:180-194` rejects unknown key, HS512, HS384, `alg:none`, flipped signature, swapped payload, wrong and missing `iss`/`aud`/`exp`/`nbf` |
| 12 | Signing keys are at least 32 bytes | `docs/12` | holds | A | `settings.py:248-257`, current and every previous key |
| 13 | The production TLS rule reads the URL exactly as libpq does | `docs/14` D9 | holds | A | `settings.py:412-434` last-value-wins; `tests/unit/test_settings.py:67-98` diffs a 17-URL corpus against psycopg's `conninfo_to_dict`, including `sslmode=verify-full&sslmode=disable` and `ssl%6dode=disable` |
| 14 | Development codes, demo seed, auto-migrate and log mail are refused outside their environment | `docs/08` | holds | A | `settings.py:291-336`; `container.py:553` additionally ties `reveal_body` to non-production |
| 15 | A stale writer gets 409, with `current` where the contract says so | `docs/14` D3 | holds | A | `tests/api/test_petty_cash.py:314`, `test_revenue_day.py:230`, `test_expenses.py:483`, `test_people.py:263`, and the documented no-`current` case `test_revenue.py:338` |
| 16 | Row locks are proven with two connections | `docs/14` D3 | holds | A | `tests/db/test_setup_races.py`: 11 tests hold transaction one open, start connection two, assert it waits, then read both outcomes |
| 17 | Logs never carry bodies, PINs, codes, tokens, numbers or e-mails | `docs/14` D8 | holds | A | Two hits only, both safe; see section 6 |
| 18 | No secret, credential or `.env` in the repository | `docs/14` D9 | holds | A | Only `.env.example` tracked; `.gitignore` covers `.env`, `.env.*` with `!.env.example` |
| 19 | Every `XCODE_*` appears in `settings.py`, `.env.example`, `docs/08` and `tests/unit/test_settings.py` | prompt sweep | **fails** | A | `XCODE_EMAIL_USERNAME` appears in no test. V-D8-1 |
| 20 | Every routine file has a `docs/05-routines.md` entry | prompt sweep | holds | A | 346/346; the six `00_types` files are listed under their dotted names |
| 21 | Every routine file has a test | prompt sweep | **unproven** | C | The header check validates only that the named module exists. V-D10-1 |
| 22 | `db verify` exits 0 | `docs/14` D6 | holds | A | 21/21 ok, exit 0, measured this session |
| 23 | Each `db verify` check is shown to fail on a database built to break it | `docs/14` D6 | **unproven** | C | 10 of 21 have a negative test. V-D6-1 |
| 24 | Every .NET test class has a crosswalk row | prompt sweep | holds | A | 43/43; `Phase1ContractTests` is covered under its three inner class names at `docs/09-testing.md:110` |
| 25 | The `docs/09` crosswalk is current | `docs/14` D11 | **fails** | A | Line 110 still says the fleet rows "arrive with prompt 06"; they landed. V-D11-1 |
| 26 | Tests do not fake the capability under test; no skips or xfail | `docs/14` D10 | holds | A | 3 skips, all gated on lacking superuser; 0 `xfail`; 0 bare `except`; no long sleeps |
| 27 | The full suite runs green | `docs/14` D10 | **not checked** | — | Not run this session; see section 8 |
| 28 | `EXPLAIN` evidence at 10x the demo seed (`DEPTH: deep`) | prompt | **not checked** | — | Needs the cluster and a 10x seed; resource ceiling |
| 29 | A run on every PostgreSQL version available (`DEPTH: deep`) | prompt | **not checked** | — | Only 16.15 present on this machine |
| 30 | Body-level contract parity per endpoint (names, order, nullability, Money as number) | `docs/14` D4 | **not checked** | — | Routes compared, bodies not |
| 31 | Statement budgets and connection/thread counts (D7) | `docs/14` D7 | **not checked** | — | Budget |
| 32 | Calendar and time-zone depth (D5: month ends, 29 February, DST) | `docs/14` D5 | **not checked** | — | Budget |
| 33 | `tools/migrate_from_sqlserver/**` (prompts 10, 10b) | prompts 10, 10b | **not checked** | — | Verified by other sessions today; not re-verified here |
| 34 | Routine headers name their callers accurately | `docs/14` D11 | **fails** | A | `organization_ids.sql:3` omits one of two callers. V-D11-2 |

## 3. Findings

| id | mode | claim challenged | challenge | evidence | refutation tried | verdict | synthesis |
|---|---|---|---|---|---|---|---|
| V-D9-1 | falsification | "migrations are forward-only and checksummed, and `db migrate` works" (`docs/14` D6) | Migration `0014` was edited after it was applied to the shared `xcode` database, so `xcode-api db migrate` refuses there on a checksum mismatch. A cutover that runs `db migrate` against that database stops. | `xcode-api db status` this session: `migration checksum drift: [14]`, applied `0001`-`0014`, pending none | Confirmed it is database state, not repository state: the `0014` file itself is coherent and the test template builds from the files cleanly. Already reported by the 13:19 session (`2026-10-14-verify-prompt-08b.md` section 10) and still open. | **survives — Major** (database state, pre-existing, not a code defect) | For the user: repair steps are in `2026-10-14-verify-prompt-08b.md` section 10. Not done here (`MODE: report`, and the database is shared). Must be cleared before any cutover that migrates `xcode`. |
| V-D10-1 | Socratic | "every `api.*` routine has a test per `Raises:` code and every routine file has a test" (prompt sweep; routine headers' `Tests:` line) | A routine header may name a test module that never references the routine, and the check still passes. 53 of 346 routine files are named nowhere under `tests/**`. | `tests/db/test_routine_headers.py:110-111` asserts only `(PROJECT / test_module).exists()`. The 53: 49 helpers plus `api.pettycash_entry_{reject,remove,reopen,send_back}` | Substantially refuted for the four `api.*` ones: all four routes are driven by `tests/api/test_petty_cash.py:281,294,300,304,477,480,483,485,585`. Spot-checked helpers are reached through tested `api.*` routines (`reports.fleet_net` ← `reports.build` ← `api.report_get`, tested at `tests/db/test_report_routines.py:270`; `setup.vehicle_net` ← `api.setup_vehicle_report`). So coverage is real but **indirect**, and the header's claim is unverified. | **survives — Minor** | Strengthen `test_routine_headers.py` to assert the named module mentions the routine, or let a header declare indirect coverage explicitly (`Tests: via api.report_get`). Until then helper-level edge cases are grade B/C. |
| V-D6-1 | falsification | "each `db verify` check is shown to fail on a database built to break it, or the check is `unproven`" (`docs/14` D6, verbatim) | 11 of the 21 checks have no negative test, so by the document's own standard they are `unproven`. Among them: *audit tables are append-only for the executor* (a D3 integrity claim) and *xcode_readonly is locked out of identity and secret columns* (a D1 claim). | `tests/db/test_structure.py` holds 10 `test_verify_reports_*` tests for 21 registered checks (`src/xcode_api/db/verify.py:843-866`) | Confirmed the most security-critical checks **are** proven: tenant routines entering their organization (`:140`), security-invoker routine in api (`:101`), dynamic SQL (`:118`), tenant table without a policy (`:202`), role not bound by row security (`:250`), column grant to the app role (`:65`), missing schema (`:190`), secret-named column (`:178`), role timeouts (`:216`), operator schema usage (`:82`). | **survives — Minor** | Add a negative test per remaining check, prioritising audit append-only and `xcode_readonly`. |
| V-D11-1 | falsification | "the `docs/09` crosswalk and README status are current" (`docs/14` D11) | `docs/09-testing.md:110` says the fleet released-client rows "arrive with prompt 06", in the future tense. Prompt 06 was verified on 2026-10-12. A reader concludes the released-client contract has no fleet coverage. | The rows exist: `tests/api/test_contract_released_clients.py:615` (`test_fleet_screens_read_and_write_as_the_develop_web_does`), `:705` and `:716` (the two recurring refusals), `:872` (`test_refusals_keep_their_status_and_a_problem_the_web_can_show`) | Searched for a second, current statement of the same fact elsewhere in `docs/09`; none. The claim is simply stale. | **survives — Minor** | Correct line 110 to state the rows landed. This is the released-client guard, so the line matters more than most. |
| V-D8-1 | Socratic | "every `XCODE_*` variable appears in `settings.py`, `.env.example`, `docs/08-operability.md` and `tests/unit/test_settings.py`" (prompt sweep) | `XCODE_EMAIL_USERNAME` has no test. Its field exists (`settings.py:110`) and it is documented, but nothing pins its behaviour. | `grep -rn "email_username\|EMAIL_USERNAME" tests/` returns nothing | Checked the two neighbours that my first sweep also flagged: `allow_require_sslmode` and `email_password` **are** tested under their lowercase field names, so those were false positives. `email_username` is not. | **survives — Minor** | Add a case to `tests/unit/test_settings.py` (SMTP username carried through; empty is allowed). |
| V-D11-2 | Socratic | Routine headers name their callers (`docs/14` D11; the header contract in `test_routine_headers.py`) | `organization_ids()` reads **every** organization past RLS. Its header names one caller; there are two. For an RLS-bypassing function the caller list is the security inventory, so an incomplete one understates the blast radius. | `db/routines/30_tenancy/organization_ids.sql:3` says "Callers: api.ops_provision_user"; `db/routines/60_ops/ops_seed_demo.sql:41` also calls it | Confirmed the omission is harmless in effect: both callers are `ops_*`, and `db verify`'s *xcode_app cannot execute api.ops_** check (ok this session) keeps the app role out of both. So no reachability change, only an inaccurate record. | **survives — Minor** | Add `api.ops_seed_demo` to the header. Consider asserting the `Callers:` line against the call graph, as `Raises:` already is. |
| V-N-1 | pre-mortem | "`db verify`'s tenant-guard check would catch a new routine that does not enter its organization" (`docs/14` D1) | The check selects only routines with a parameter literally named `p_organization_id`. A future tenant routine taking `p_org_id`, or deriving the organization from `p_vehicle_id`, would never be examined. | `src/xcode_api/db/verify.py:756-761` | Largely defused: RLS fails safe. `tenancy.current_organization()` is `nullif(current_setting('xcode.organization_id', true), '')::uuid` (`db/migrations/0003_tenancy.sql:7-9`), so with no `enter_organization` the policy compares against NULL and the routine reads **zero rows**, not another tenant's. The naming convention also holds today: all 89 tenant routines use `p_organization_id`, and the 29 that do not take one are 19 `auth_*`, 7 `ops_*`, 2 `meta_*` and `rate_limit_hit`. | **Note** | Residual risk, already mitigated by fail-safe RLS. Optionally widen the check to any routine whose body reads a table carrying `organization_id`. |
| V-N-2 | dialectic | The earlier audit's V-D8-6: "`errors.py:118` `code=` redacted" (`2026-10-14-verify-prompt-09.md` section "For others") | Argued the other side at full strength: is `code=` a leak? It is not. `exc.code` is a refusal-code vocabulary value (`domain/errors.py:14-32`: `DomainRefusal` and its subclasses), e.g. `not_member`, `permission_missing`. It is not a mailed verification code, and `exc.detail` is **not** logged. | `src/xcode_api/http/errors.py:118` logs only `code=exc.code`; the surrounding handler logs no parameters | Looked for any path that places a secret into `.code`: refusal codes come from a closed catalogue consumed by `message_for()`. Found none. | **Note — I do not concur with the earlier finding** | Recommend closing V-D8-6 as "no action: `code` is a refusal code, deliberately logged". Redacting it would remove the only diagnostic for a missing message template. |

## 4. Per domain

### D1 Tenancy and authorization — no findings beyond V-N-1

Probe verdicts: tenant guard on every tenant routine **holds** (89/89, check proven to bite);
RLS plus `tenant_isolation` on every tenant table **holds**; owner-owned RLS-bypassing
functions **holds** (exactly two, analysed below); anti-escalation in SQL **not checked**;
permission catalogue equals `packages/shared` **not checked**; scoped-viewer leakage through
totals, counts, exports and 403-versus-404 **not checked** (budget).

The three strongest falsification cases probed, and why the defense held:

1. **Whether an RLS-bypassing function can be steered across tenants.** Only two functions are owned by
   `xcode_owner`. `tenancy.organization_ids()` takes no argument at all, so there is nothing
   to steer, and it is reachable only from two `ops_*` routines that `xcode_app` cannot
   execute (`db verify` check ok). `identity.active_organization(p_user_id)` does take caller
   input, and returns the organization of that user — but it returns a single id and nothing
   else, and callers pass the authenticated subject, not a request field.
2. **Whether `active_organization`'s "single active membership" assumption can be broken.** If a user held
   two active memberships the function would return one of them arbitrarily (no `ORDER BY`,
   `RETURNS uuid` over a multi-row select). Defeated by
   `db/migrations/0003_tenancy.sql:87`: `CREATE UNIQUE INDEX uq_memberships_active_user ON
   tenancy.memberships (user_id) WHERE active`. The partial unique index enforces exactly
   the assumption the comment states.
3. **Whether any tenant routine falls outside the guard check's reach.** 29 `api.*` routines escape the
   check's `p_organization_id` filter; every one is identity-level (19 `auth_*`), operator-only
   (7 `ops_*`), meta (2) or infrastructure (`rate_limit_hit`). And a routine that did forget
   the guard reads zero rows, because `current_organization()` is NULL. See V-N-1.

### D2 Identity and sessions — no findings

Probe verdicts: byte-for-byte equality of unknown, paused and capped answers **holds**;
constant work (one derivation) **holds**; algorithm pinned, `iss`/`aud`/`exp`, zero leeway,
exact claim set **holds**; previous keys verify only **holds** (`settings.py:253-257`
validates them; `tokens.py:61` signs with `_keys[0]` only); `security_version` bump and
removal end the session **holds** (`tests/api/test_auth_contract.py:253`); token lifetime
boundary **holds** (`:277-281` asserts 200 at 600 s and 401 at 601 s on the injected clock);
lockout model, code caps and expiry, mail-after-commit, rate limit before body validation
**not checked** in depth (budget), though `test_auth_races.py` and the `auth_*` routine tests
exist.

The three strongest falsification cases probed:

1. **Whether a forged token is accepted.** `alg:none`, HS384 and HS512 confusion, an unknown key, a flipped
   signature and a swapped payload are all parametrised as tokens that must be rejected
   (`tests/unit/test_tokens.py:180-194`), alongside wrong and missing `iss`, `aud`, `exp`,
   `nbf`. `algorithms=[ALGORITHM]` with `ALGORITHM = "HS256"` makes confusion unreachable.
2. **Whether a real account is distinguishable from an unknown number.** Body, status and every meaningful header
   are asserted equal across seven states; and one PBKDF2 derivation runs in all of them,
   including a number that does not normalise, so the timing channel is closed too.
3. **Whether a verification code is reachable in the logs.** `LogMailer` reveals the body
   (`infra/mail.py:78`), so I tried to reach it in production. Two independent gates stop it:
   `XCODE_MAIL_BACKEND=log` is refused in production (`settings.py:293`), and `reveal_body`
   is `env is not production` (`container.py:553`). I then checked for a fourth environment
   such as `staging` that would be "not production" while allowing the log backend; the enum
   has exactly `development`, `testing`, `production` (`settings.py:41-44`). Conceded.

### D3 Data integrity and concurrency — no findings

Probe verdicts: version bumped and compared, stale writer gets 409 with `current` **holds**;
two-connection proof of locks **holds** (11 tests); append-only audit tables enforced by
grant **holds** per `db verify`, but the check itself is `unproven` (V-D6-1); replay on a
unique constraint, lock-order pair analysis, money `numeric(14,2)` and rounding mode
**not checked** in depth (budget).

The three strongest falsification cases probed: a stale writer slipping through with a one-connection test
(defeated: `test_setup_races.py` opens a second connection and asserts the waiting); an
identical replay writing a second change-log row (covered by
`test_expenses.py:483`, which asserts the replay and the stale 409 together); a 409 without
the body the mobile queue reads (defeated: the `current` row is asserted in petty cash,
revenue-day and expenses, and the one route that answers 409 *without* `current` has its own
test at `test_revenue.py:338`).

### D4 Contract parity — one claim not checked

Routes **holds**: all 88 unique .NET routes appear in the OpenAPI document. The 27 Python
operations with no .NET counterpart are the v2.3 redesign auth surface
(`/auth/start`, `/auth/code`, `/auth/code/resend`, `/auth/pin`, `/auth/pin/{change,forgot,new}`,
`/auth/trusted-devices`) and the 08b additions (people, access, expense main categories,
vehicle targets), which is the intended direction: the method treats a .NET route missing
from the contract as the finding, and there are none.

Bodies, error shapes and client reads are **not checked** here (claim 30). The released-client
guard that covers much of this exists and is strong
(`tests/api/test_contract_released_clients.py`, 1275 lines, raw-JSON case-sensitive property
checks), which is why V-D11-1 matters: the document understates it.

### D5 Domain rules and time — partly checked

Injected time **holds**: zero `now()`, `current_date`, `clock_timestamp()` or `random()` in
`db/routines`, and the rule is a test, not a convention
(`tests/db/test_routine_headers.py:144`). Week start, month ends, 29 February, DST zones and
byte-equal automatic reasons are **not checked** (claim 32).

### D6 Database craft — one finding

`db verify` exit 0 with 21/21 ok, measured. Every one of the 340 functions in `db/routines`
pins `search_path`; 122 are `SECURITY DEFINER`; the `api.*` ownership, definer, search_path
and not-PUBLIC properties are checked against the catalogue including the NULL-acl default
(`verify.py:305-341`). No dynamic SQL from inputs. PostgreSQL 16.15 measured; version-floor
feature analysis **not checked**. Template fingerprint: **not checked** (I built no template;
see section 8). Finding: V-D6-1.

### D7 Performance and scale — not checked

Claims 28 and 31. Nothing in this session. `docs/perf/` exists and two sessions recorded 10x
figures today, including a day save that exceeds the 5 s statement timeout at about 130 rows
(question 101) — carried forward, not re-measured here.

### D8 Reliability and operability — one finding

Log hygiene **holds**: the only two sensitive-looking log calls are
`http/errors.py:118` (a refusal code, deliberate — V-N-2) and `infra/mail.py:78`
(development and testing only, double-gated). `XCODE_*` crosswalk **fails** on one variable
(V-D8-1). Startup order, readiness, shutdown drain, CLI exit codes and `ops.operator_actions`
**not checked**; prompt 09 was verified today by another session.

### D9 Hosting and supply chain — one finding

No secret, credential or `.env` in the repository. The production TLS rule is read exactly as
libpq reads it, proven differentially against psycopg — the 2026-10-11 duplicate-`sslmode`
blocker is closed and has not regressed. Host facts, lock-file hashes, `pip-audit` and CI
action pinning **not checked**. Finding: V-D9-1 (database state).

### D10 Tests as evidence — one finding

No fake of a capability under test was found: the derivation counter wraps the **real**
`Pbkdf2PinHasher`; the libpq corpus runs against the **real** psycopg parser; the race tests
use two **real** connections. 3 skips, all gated on lacking superuser rights; 0 `xfail`;
0 bare `except`; no sleep longer than 0.25 s. 1120 unit tests pass in this session.
The full suite did not run here. Finding: V-D10-1.

### D11 Documents and prompts — two findings

V-D11-1 and V-D11-2. The crosswalk, the routine catalogue and the settings matrix are
otherwise accurate: 346/346 routine files are in `docs/05-routines.md`, and 43/43 .NET test
classes have a crosswalk row.

## 5. Per mode

**Assumption inventory (Socratic).** The assumptions the code relies on, and what enforces
each:

| Assumption | Where stated | Enforced by |
|---|---|---|
| A user has exactly one active membership | `identity/active_organization.sql:2` | `0003_tenancy.sql:87` partial unique index |
| A tenant routine always enters its organization first | `tenancy/enter_organization.sql:3` | `db verify` check + fail-safe NULL in `current_organization()` |
| `api.*` routines never run as the table owner | `db/roles/030_grants.sql:17-19` | `verify.py:333` owner check, proven to bite |
| Only two functions may read past RLS | `docs/12` | `test_routine_headers.py:162` definer allow list |
| Every routine's `Tests:` names real coverage | routine headers | **only file existence** (V-D10-1) |
| Every routine's `Callers:` is complete | routine headers | **nothing** (V-D11-2) |
| The log mail backend cannot run in production | `infra/mail.py:68` | `settings.py:293` + `container.py:553` |
| libpq's last-value-wins reading of the URL | `settings.py:413-418` | differential test against psycopg |
| One routine call is one transaction | `docs/01` | not re-checked here |

**Falsification.** Twelve claims were given a falsifier and the falsifier was looked for;
grades are in section 2. The three that failed falsification are V-D8-1, V-D11-1 and V-D11-2;
two came back `unproven` (V-D10-1, V-D6-1). Everything graded A in section 2 survived an
attempt to produce the disproving observation.

**Pre-mortem.** Ranked narratives, three months after cutover:

1. *A helper's edge case regresses silently* (likelihood medium, impact medium). One of the 49
   helpers with only indirect coverage changes behaviour in a branch no `api.*` test exercises
   — a rounding mode in `setup.vehicle_net`, a label in `reports.heading`. The header says
   `Tests: ...`, so a reviewer believes it is covered. Noticed when a tenant disputes a report
   figure. Early sign: a diff that touches a helper named in no test. Mitigation: V-D10-1.
2. *A cutover runs `db migrate` and stops* (likelihood medium, impact low-medium). The `0014`
   checksum drift makes `db migrate` refuse on `xcode`. Noticed immediately, at the worst
   moment. Mitigation: V-D9-1, repair before cutover.
3. *A new tenant routine names its parameter differently* (likelihood low, impact low). It
   escapes the guard check and returns zero rows, so it is noticed as an empty screen in
   development, not as a leak in production. Mitigation: V-N-1.
4. *A `db verify` check silently stops working* (likelihood low, impact high). One of the 11
   checks without a negative test is refactored into a no-op; `db verify` keeps printing `ok`.
   The append-only and `xcode_readonly` checks are the ones that would hurt. Mitigation:
   V-D6-1.

*Inversion.* What would guarantee a cross-tenant leak? Either an `api.*` routine owned by
`xcode_owner`, or `FORCE ROW LEVEL SECURITY` plus a policy that reads a caller-supplied
organization, or `current_organization()` defaulting to something non-NULL. None of the three
conditions exists: ownership is checked and proven to bite, the policies compare against the
transaction-local setting only, and the setting's absence yields NULL.

**Red team.** Threats probed against the personas of `docs/14` section 3, each with the defense that holds:

| Persona | Threat probed | Outcome |
|---|---|---|
| Outsider with phone numbers | Whether a real account is distinguishable by body, header, status or timing | Stopped: 7-state byte equality + one derivation always |
| Outsider | Whether a token can be forged or confused | Stopped: HS256 pinned, 14 forgery variants rejected |
| Outsider | Whether codes are readable from logs | Stopped: log backend refused in production, `reveal_body` off |
| Clerk in tenant A | Whether tenant B is reachable through an RLS-bypassing function | Stopped: two such functions, one argumentless and ops-only, one returning a single id for the authenticated subject |
| Clerk in tenant A | Whether tenant B is reachable through a routine that forgot the guard | Stopped: no such routine, and RLS fails safe to zero rows |
| Operator with the CLI | Whether `ops_*` is usable beyond intent from the app role | Stopped: `xcode_app` cannot execute `api.ops_*`, checked |
| Hurried DBA | Whether an in-place routine edit or wrong-database migration goes undetected | Partly: routine drift and checksum drift are both *detected* (`db status` reported both this session) |
| Compromised neighbour | Whether secrets are readable from the repository | Stopped: nothing but `.env.example` tracked |
| Scoped viewer | Whether hidden vehicles leak through totals and exports | **Not tested here** (budget) — the one material untested persona |

**Dialectic.** Decisions argued from the other side:

- *`FORCE ROW LEVEL SECURITY` off, owner-owned helpers allowed.* The counter-case is real:
  forcing RLS would remove the bypass class entirely. Kept, because the bypass set is two
  functions, both inventoried, allow-listed by a test, and unsteerable; and sign-in genuinely
  needs one cross-tenant read before any organization is known. Confidence high.
- *Textual guard check rather than behavioural.* The counter-case is V-N-1. Kept, because the
  consequence of escaping it is zero rows, not a leak. Confidence medium-high.
- *`verify_exp: False` with a manual expiry check.* Argued for letting PyJWT verify: it would
  remove hand-rolled time logic. Kept, because the injected clock is what makes the 600/601 s
  boundary testable at all, and the boundary *is* tested. Confidence high.
- *Earlier audit's V-D8-6 redaction.* Argued both sides; I come down against redacting. See
  V-N-2. Confidence high.

## 6. Conceded

| Challenge | Guard that defeated it |
|---|---|
| `active_organization` may return an arbitrary organization for a multi-membership user | `0003_tenancy.sql:87` partial unique index on `(user_id) WHERE active` |
| A `staging` environment would allow the log mailer to reveal codes | `settings.py:41-44`: the enum is exactly development, testing, production |
| Four `api.pettycash_entry_*` routines have no test | Driven through HTTP by `tests/api/test_petty_cash.py` (9 call sites) |
| `Phase1ContractTests` has no crosswalk row | `docs/09-testing.md:110` covers its three inner classes |
| Six `00_types` files are missing from `docs/05-routines.md` | Present under their dotted names (`api.write_result` and the rest) |
| A `SECURITY DEFINER` routine lacks `search_path` | 340/340 functions pin it; the one file-level mismatch was a header comment (`active_organization.sql:7`) |
| `EXECUTE`/`format(` indicate dynamic SQL in routines | All 222 hits are `GRANT EXECUTE`; the only `format()` uses `%I` on `current_database()` |
| HS384/HS512 appear in the token tests, so other algorithms may be accepted | They are forgeries the suite requires to be rejected (`test_tokens.py:184-185`) |
| `allow_require_sslmode` and `email_password` have no settings test | Both tested under their lowercase field names |
| The 8 drifted routine files and 11 recently-changed files are defects | Another session's in-flight work (`481ccc51`, writing since 15:04); attributed, not fixed |
| `errors.py:118` leaks a code | It is a refusal code, not a secret (V-N-2) |

## 7. Fixes

None. `MODE: report`.

## 8. Commands, outputs and versions

Measured in this session:

```
ruff check .            -> All checks passed!
ruff format --check .   -> 505 files already formatted
mypy                    -> Success: no issues found in 227 source files
pytest tests/unit -q    -> 1120 passed, 2 warnings in 58.63s
xcode-api openapi       -> exit 0, 115 operations
xcode-api db status     -> applied 0001-0014; pending none
                           routine drift: 8 files (another session's in-flight edits)
                           migration checksum drift: [14]
xcode-api db verify     -> 21 checks, all ok, exit 0
```

```
PostgreSQL  16.15 (x86_64-windows, MSVC 1944) on 127.0.0.1:5433
Python      3.13.2
src         227 files / 23,783 lines      db  378 files / 24,435 lines
tests       140 files / 68,941 lines      routines 346, migrations 28
HEAD        ac2f9a0 "web rebuild"; 326 paths modified in the worktree
```

Reconfirmed on the 2026-10-14 re-run (identical outcomes unless noted):

```
ruff check .          -> All checks passed!
ruff format --check . -> 506 files already formatted   (was 505; one Python file changed
                         in the shared tree since the first pass)
mypy src              -> Success: no issues found in 227 source files
pytest tests/unit -q  -> 1120 passed, 2 warnings in 73.35s  (single process)
xcode-api openapi     -> exit 0, 102 paths / 115 operations
xcode-api db status   -> applied 0001-0014; pending none; routine drift 8 files;
                         migration checksum drift [14]   (V-D9-1 reconfirmed)
xcode-api db verify   -> 21 checks, all ok, exit 0
.NET route crosswalk  -> 88 unique routes from apps/api/Api/*.cs, 0 missing from OpenAPI
```

The two pytest warnings are a token-forgery-rejection test that deliberately signs with a short key to prove the short key is refused; they are evidence, not a defect.

**Why the full suite did not run here.** At 15:04 another session (`481ccc51`) started
`pytest -n 2` on the full suite; it was still running at 15:39. The machine has 4 cores and
7.4 GB, of which **828 MB was free** when I checked — below this project's own 1.0 GB gate for
`-n 2`, and the board records that two concurrent suites have already run this host out of
memory once. Starting a second full run would most likely have destroyed both. The user said
not to wait for that run, so I did not block on it; I ran everything that needs no template
instead (lint, types, 1120 unit tests, OpenAPI, and the two read-only database commands) and
left the shared template and the other session's processes untouched.

For the record, the most recent **completed** full run on this tree is another session's, from
09:16 to 11:07 today: **6572 passed, 3 failed, 0 skipped, 0 errors in 1:50:49**, the three
failures being the `tests/db/test_gateway.py` drift, which was then fixed test-only at 13:40
(19 passed, 0 failed). That is a claim from the board, not something I measured, and it is why
claim 27 is `not checked` rather than `holds`.

## 9. Regressions and misses against earlier audits

Read only after the pass above.

- **No regression found.** The two defects `docs/14` section 1 cites as the reason the document
  exists are both still fixed: the duplicate-`sslmode` bypass (now proven differentially
  against libpq, claim 13) and the unbounded PIN derivations (the pool and its slot accounting
  are tested in `tests/unit/test_pin_hasher.py:136-231`).
- **Earlier findings I could not confirm.** V-D8-6 from `2026-10-14-verify-prompt-09.md`
  (`errors.py:118` `code=`) does not hold on my reading; see V-N-2. I recommend closing it.
- **What earlier audits missed, found here.** V-D10-1 (the `Tests:` header is validated for
  file existence only — this weakens the coverage claim across 53 routines), V-D6-1 (11 of 21
  `db verify` checks are `unproven` by `docs/14`'s own standard), V-D11-1 (the stale fleet-rows
  sentence in `docs/09:110`), V-D8-1 and V-D11-2.
- **Still open from earlier today, confirmed by me.** The `0014` checksum drift (V-D9-1) —
  independently reproduced via `db status`.

## 10. For the user

1. **The rename is not blocked by the code.** Across the domains this session could reach, no
   blocker and no cross-tenant, escalation or authentication defect was found, and the
   invariants that matter most are enforced structurally rather than by convention: RLS fails
   safe to zero rows, `api.*` ownership and `search_path` are checked against the catalogue,
   the tenant guard has an empty allow list and a test that proves it bites, and the identity
   answers are equal byte for byte and in work. My recommendation is to proceed, after item 2.
2. **Clear the `0014` checksum drift on `xcode` before any cutover that migrates it**
   (V-D9-1). Repair steps are in `2026-10-14-verify-prompt-08b.md` section 10. This is
   database state; the repository is coherent.
3. **Do not treat this report as a complete `DEPTH: deep` pass.** Seven claims are
   `not checked` (section 2, claims 27-33). The two I would not rename without are the
   **full-suite run** and the **scoped-viewer leakage probe** (hidden vehicles and companies
   through totals, exports, history and 403-versus-404), which is the one red-team persona I
   could not test and the one most likely to hide a tenant-visible defect.

## 11. Where to resume

A fresh session, when no other full run is in progress and at least 1.0 GB is free:

1. `pytest -n 2 -q -p no:cacheprovider` on a private template, and record the counts and the
   template fingerprint against the `db/` files (claim 27, and the D6 template probe).
2. The scoped-viewer sweep: hidden vehicles and companies through `totalVehicles`, `partial`,
   `active_amount`, report sums, history, exports, option lists, ordering and 403-versus-404
   (D1, claims not checked).
3. Body-level contract parity per endpoint against `docs/06` and the .NET bodies (claim 30),
   then `docs/06` against the 115 OpenAPI operations operation by operation.
4. `DEPTH: deep` leftovers: `EXPLAIN (ANALYZE, BUFFERS)` at 10x the demo seed for the heavy
   reads, and D7's statement, connection and thread budgets (claims 28, 31).
5. D5 calendar and time zone depth, and the anti-escalation and permission-catalogue probes of
   D1 (claims 32 and the D1 gaps).

Nothing of mine is left running: no template, no test database, no job, no watcher. The 5433
cluster is left as I found it (started by another session), and the 8 drifted routine files and
11 recently changed files belong to session `481ccc51` and were not touched.
