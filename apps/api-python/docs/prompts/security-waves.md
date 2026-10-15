# Security certification waves — session handoffs

The ordered set of sessions that takes `apps/api-python` to the defensible completion claim
in `docs/16-security-matrix.md` section 5: no open critical or major finding across clusters
SC1–SC9 and the independent checks, every finding pinned as a test or CI gate, the owner
signed off on the residual-risk register in `docs/12` section 7.

Scope is **API + the web-facing surface that reaches it**; mobile is out of scope this round.

Each session below is a separate Claude Code session started in the repository root. It
loads only the security-skill cluster named for its domain (`docs/16-security-matrix.md`),
and a skill finding is not done until it is a test that fails without the fix. Offensive
skills run only against local targets we own (the 5433 cluster, a local `xcode-api serve`,
the code) — never cPanel `priori`, staging, or any shared or production host.

House rules apply to every session (`CLAUDE.md`): `git status` first; one writer per set of
files; at most two writer sessions in this tree at once; never revert, reformat or kill what
you did not start; no commits unless asked; no AI attribution; no comments or plan/prompt
identifiers in code.

---

## Wave 0 — evidence you can trust (prerequisite for the rest)

Not a verify session. The owner runs or authorises these; they gate everything after.

- **0a Baseline.** Commit the `apps/api-python` tree (and `.github/workflows/xcode-api.yml`)
  to a branch and push, so CI runs the full suite on PostgreSQL 18 with pip-audit and trivy
  on a committed SHA. This also discharges D1's full run that was stopped at 1% for low
  memory. Every later report cites that SHA.
- **0b Hosting facts.** Answer `docs/13-open-questions.md` questions 39–45 on the real host
  (PostgreSQL version, whether the five `db/roles/010_roles.sql` roles can exist, Python
  3.13, whether Passenger runs the ASGI lifespan, the thread count under the 100-process
  cap). Read-only; no attack tooling on that host. **Gate:** if the roles cannot exist, RLS
  protects nothing — choose a separate cPanel account or a VPS before Wave 2 builds further.

## Wave 1 — verify what is already built, under attack (one session at a time)

Each is a `docs/prompts/verify.md` run. Fill its parameters, load the cluster, attack, then
fix with failing-first tests. Report lands at
`docs/audit/<yyyy-mm-dd>-verify-<scope>.md`.

### W1-A — verify prompt 06 (setup)
- Model Opus. `SCOPE: prompt:06` · `MODE: fix` · `DEPTH: standard`.
- Cluster **SC2** (object/function/property authorization, mass assignment).
- Attack focus: a token for org A reaching any company, vehicle, target, away period,
  expense-catalogue or scheduled-item id of org B (numeric, uuid, slug); extra body fields
  binding into version, `OrganizationId`, role or permission; the `companyId`/`kind`/`status`
  list filters leaking cross-tenant rows or bypassing the permission check.
- New this round: 06 has never had its own verify run; treat its "validated" status as a
  claim. Tests land in `tests/api/test_object_authorization.py`,
  `tests/api/test_mass_assignment.py`, and the existing setup test modules.

### W1-B — verify prompt 07 (revenue)
- Model Opus (concurrency). `SCOPE: prompt:07` · `MODE: fix` · `DEPTH: deep`.
- Clusters **SC4** (business logic + race) and the SQL half of **SC3** (injection,
  second-order through stored snapshots).
- Attack focus: two writers on the same cell/day racing the `Version` token (must 409, never
  lost-update); idempotent replay of the offline queue; the capped paging (≤100) and the
  `EXPLAIN` evidence at 10× the seed (`DEPTH: deep`); any revenue value echoed into a later
  snapshot without re-escaping.
- Tests: per-write two-connection race tests in the 07 modules; replay-idempotency tests.

### W1-C — verify prompt 07b D1 (sign-in) + first live attack
- Model Opus. **Not** the session that built D1 (revenue-17). `SCOPE: prompt:07b` scoped to
  the D1 deliverables · `MODE: fix` · `DEPTH: deep`.
- Cluster **SC1** (auth-weaknesses, jwt-token-security, jwt-algorithm-confusion, jwt-none,
  rate-limiting-bypass). Run the first live attack against a local `xcode-api serve`.
- Attack focus: forge an HS256 token with `alg=none` and with an RS/HS confusion using the
  public material; truncated-key forgery (the known test-only HS384/HS512 path must stay
  test-only); the number step and the lock paths returning an identical body and headers for
  a real account, a simulated unknown number, a paused account and a capped untrusted device;
  beating the code caps (3 tries, 1/min, 5/hr) and the PIN-pool cap with parallel requests.
- New this round: D1 owes a full suite run on a quiet machine (or Wave 0a's CI run); confirm
  it completed before any D1 clause is called `holds`. Tests: `tests/api/test_jwt_forgery.py`,
  `tests/api/test_auth_enumeration.py`, and the existing `test_auth_*` / `test_auth_races.py`.

## Wave 2 — build the rest, each followed by its own verify

Build order is strict: 07b D2 → 07b D3 → 07b D4 → 08 → 08b → 09 → 10. Run the build, then a
fresh `verify.md` session (not the builder) before the next build starts. Freeze .NET
feature work before 08b's drift check (recommended: freeze now). Each build uses the prompt
file named below; the security cluster rides the build and the verify.

### W2-A — 07b D2 (people, access, rights)
- Build: `docs/prompts/07b-design-v2-3.md`, `SESSION: build-access` (Sonnet). Carries the 59-
  right catalogue, people actions and statuses, the back-dating-limit setting and helper, and
  the brand-host rules in migration `0009_access` (question 58, moved here from D1).
- Verify: `SCOPE: prompt:07b` (D2 scope) · `MODE: fix` · Opus (migration present). Cluster
  **SC2**. Attack focus: anti-escalation (only Owner grants Owner, cannot edit yourself, can
  grant only permissions you hold); the hidden Owner-only `organization.manage` not grantable
  through an override; the back-dating setting not bypassable per person.

### W2-B — 07b D3 (setup: targets, fleet, categories, savings rights)
- Build: `07b-design-v2-3.md`, `SESSION: build-setup` (Sonnet). Dated target sets with day
  figures, required/unique fleet number, optional investment, three-level categories, savings
  rights.
- Verify: `SCOPE: prompt:07b` (D3 scope) · `MODE: fix` · Opus. Clusters **SC2** + **SC4**.
  Attack focus: a started target set being mutable; a fleet-number clash across tenants; a
  category tree reparented across orgs; the dated-target maths off by a day.

### W2-C — 07b D4 (revenue low-day reason, gap, export rights)
- Build: `07b-design-v2-3.md`, `SESSION: build-revenue` (Sonnet). Below-threshold reason, the
  signed revenue gap against day targets, the module export rights (R02).
- Verify: `SCOPE: prompt:07b` (D4 scope) · `MODE: fix` · Opus. Cluster **SC4**. Attack focus:
  the threshold and gap settings being client-forgeable; the reason enum accepting free text.

### W2-D — 08 (petty cash)
- Build: `docs/prompts/08-petty-cash.md` (Sonnet). Money paths: floats, entries, approvals,
  issues, credit notes; the 20 petty-cash rights from 07b.
- Verify: `SCOPE: prompt:08` · `MODE: fix` · Opus (money + concurrency). Clusters **SC4** +
  **SC3**. Attack focus: the balance identity (opening + issued − expenses − credit notes)
  under concurrent approve/remove; the ticked all-or-none approve racing a version change
  (409, approved ones skipped); a shared purchase's group recount after a part changes.

### W2-E — 08b (central expenses, reports, exports)
- Build: `docs/prompts/08b-expenses-reports.md`, `SESSION: design` then `SESSION: build`
  (design on Opus, verify the D0 docs with `SCOPE: change:<D0 files>` before building).
- Verify: `SCOPE: area:reports` and `area:expenses` · `MODE: fix` · Opus. Clusters **SC3**
  (Excel/CSV formula injection on every export) + **SC4** (ledger-of-record integrity across
  sources central/pc/sched). Attack focus: a vehicle name, category or reason of `=cmd()`,
  `+`, `-`, `@`, tab or CR exporting as a live formula; an export leaking another tenant's
  rows; the back-dating limit (B12) applied to central-expense writes.
- Tests: `tests/api/test_export_injection.py`.

### W2-F — 09 (operability, deploy, CI finish)
- Build: `docs/prompts/09-operability-cli-seed.md` (Sonnet). Includes D0 hosting facts
  (questions 39–45) if Wave 0b did not already record them in `deploy/README.md`.
- Verify: `SCOPE: area:operability` and `area:hosting` · `MODE: fix` · Opus. Cluster **SC5**
  (schema validation, OWASP-API-Top-10, rate-limit/abuse, inventory/shadow-endpoints) and the
  start of **SC8**. Attack focus: a route missing from the OpenAPI document or from `docs/06`
  (shadow endpoint); the 1 MiB body cap and the 429 empty body; readiness and startup checks
  actually running under the chosen server (not skipped by a WSGI adapter).

### W2-G — 10 (data migration + cutover rehearsal)
- Build: `docs/prompts/10-data-migration.md` (Sonnet). Extract, transform, load, verification,
  cutover rehearsal on a copy of production data, and a written rollback (SQL Server + .NET
  kept read-only and ready for N days).
- Verify: `SCOPE: area:data-migration` · `MODE: fix` · Opus. Attack focus: a backfilled row
  that breaks a `docs/10` invariant; a migration that cannot roll back; tenant data crossing
  during load.

## Wave 3 — independent checks (own prompt files)

- **Parity:** `docs/prompts/parity.md` — run .NET and Python on the same seed and diff every
  response; only design-register rows may differ. Breaks the model-checks-model loop on
  contract behaviour.
- **Security tooling:** `docs/prompts/security-tooling.md` — gitleaks over history, custom
  Semgrep + CodeQL SAST, OWASP ZAP DAST, schemathesis/RESTler fuzz, an SBOM, SHA-pinned
  actions, dependency-confusion guards. Cluster **SC8** plus the fuzz half of **SC5**.
- (Also recommended, not scripted here: a web browser pass once web points at Python (SC6);
  capacity and failure drills against the 100-thread cap, the PIN pool, DB/mail outage and a
  migration rollback.)

## Last — final audit and sign-off

`docs/prompts/11-audit.md` (read-only Opus, wrote none of the code). Runs `verify.md` with
`SCOPE: all`, `MODE: report`, `DEPTH: deep`, folds in cluster **SC9** (threat model appended
to `docs/12`, security review), confirms every SC1–SC9 and independent-check finding is a
passing test or CI gate, and writes the go/no-go that decides the rename to `apps/api`.
